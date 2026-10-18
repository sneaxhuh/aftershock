"""Tenant graph scopes and a single snapshot-backed sandbox pool for local operators."""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from aftershock.graph import GraphStore
from aftershock.controller import Controller

WORKSPACES = {"northstar": "Northstar Commerce", "harbor": "Harbor Retail"}
COOKIE = "aftershock_workspace"


class Workspaces:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.model_lock = asyncio.Lock()
        self.stores = {id_: GraphStore(tenant=id_) for id_ in WORKSPACES}
        root = self.stores["northstar"]
        self.admin = root.db.select_graph(f"{root.base_prefix}_registry")
        self.controllers = {}
        self.owner = "northstar"

    def q(self, query, params=None):
        return self.admin.query(query, params or {}).result_set

    def initialize(self):
        for store in self.stores.values():
            store.initialize()
            if store.active():
                store.upgrade_context(store.get(store.active()))
        self.q(
            "MERGE (p:SandboxPool {id:'singleton'}) ON CREATE SET p.owner='northstar'"
        )
        self.owner = self.q("MATCH (p:SandboxPool {id:'singleton'}) RETURN p.owner")[0][
            0
        ]
        self.q(
            "MERGE (s:SessionSecret {id:'singleton'}) ON CREATE SET s.value=$value",
            {"value": secrets.token_hex(32)},
        )
        self.secret = bytes.fromhex(
            self.q("MATCH (s:SessionSecret {id:'singleton'}) RETURN s.value")[0][0]
        )
        self.controllers = {
            id_: Controller(store, self) for id_, store in self.stores.items()
        }
        for controller in self.controllers.values():
            controller.agents.lock = self.model_lock

    def issue(self, tenant):
        if tenant not in WORKSPACES:
            raise KeyError(tenant)
        payload = (
            base64.urlsafe_b64encode(
                json.dumps(
                    {
                        "tenant": tenant,
                        "expires": int(time.time()) + 604800,
                        "nonce": secrets.token_hex(8),
                    }
                ).encode()
            )
            .decode()
            .rstrip("=")
        )
        signature = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}"

    def resolve(self, token):
        try:
            payload, signature = token.split(".")
            expected = hmac.new(
                self.secret, payload.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, signature):
                return None
            data = json.loads(
                base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            )
            if data["expires"] <= time.time() or data["tenant"] not in WORKSPACES:
                return None
            return data["tenant"]
        except (AttributeError, ValueError, KeyError, TypeError):
            return None

    def idle(self):
        if any(c.pipeline and not c.pipeline.done() for c in self.controllers.values()):
            raise ValueError(
                "An investigation owns the sandbox pool. Wait for its handoff before switching workspaces."
            )

    def require_owner(self, tenant):
        if self.owner != tenant:
            name = WORKSPACES.get(self.owner, "a recovery operation")
            raise ValueError(
                f"The executable sandbox is assigned to {name}. Activate this workspace to restore its company state."
            )

    def metadata(self, tenant):
        return {
            "tenant_id": tenant,
            "workspace_name": WORKSPACES[tenant],
            "workspaces": [
                {"id": id_, "name": name} for id_, name in WORKSPACES.items()
            ],
            "sandbox_owner": self.owner,
            "can_control": self.owner == tenant,
            "pool_busy": any(
                c.pipeline and not c.pipeline.done() for c in self.controllers.values()
            ),
            "access_mode": "local operator; signed workspace sessions",
        }

    def save_environment(self, store, run, bundle):
        store.q(
            "MERGE (e:Environment {id:'main'}) SET e.run_id=$run,e.version=$version,e.payload=$payload",
            {
                "run": run["id"],
                "version": run["version"],
                "payload": json.dumps(bundle),
            },
        )

    async def activate(self, tenant):
        if tenant not in self.stores:
            raise KeyError(tenant)
        async with self.lock:
            self.idle()
            previous = self.owner
            if previous != tenant:
                old_bundle = None
                if previous in self.controllers:
                    old = self.controllers[previous]
                    active = old.store.active()
                    if active:
                        old_bundle = await old.request("main", "/snapshot", {})
                        self.save_environment(
                            old.store, old.store.get(active), old_bundle
                        )
                target = self.controllers[tenant]
                active = target.store.active()
                saved = target.store.q(
                    "MATCH (e:Environment {id:'main'}) RETURN e.run_id,e.version,e.payload"
                )
                bundle = None
                if active:
                    run = target.store.get(active)
                    if (
                        not saved
                        or saved[0][0] != active
                        or saved[0][1] != run["version"]
                    ):
                        raise ValueError(
                            "This workspace has no matching executable snapshot; its stored evidence remains read-only."
                        )
                    bundle = json.loads(saved[0][2])
                self.q(
                    "MATCH (p:SandboxPool {id:'singleton'}) SET p.owner='',p.restoring=$tenant",
                    {"tenant": tenant},
                )
                self.owner = ""
                try:
                    if bundle:
                        await target.request("main", "/restore", bundle)
                    else:
                        await target.request("main", "/reset", {})
                    self.q(
                        "MATCH (p:SandboxPool {id:'singleton'}) SET p.owner=$tenant,p.restoring=''",
                        {"tenant": tenant},
                    )
                    self.owner = tenant
                except Exception:
                    if old_bundle and previous in self.controllers:
                        await self.controllers[previous].request(
                            "main", "/restore", old_bundle
                        )
                        self.q(
                            "MATCH (p:SandboxPool {id:'singleton'}) SET p.owner=$tenant,p.restoring=''",
                            {"tenant": previous},
                        )
                        self.owner = previous
                    raise
            controller = self.controllers[tenant]
        active = controller.store.active()
        if active and controller.store.get(active)["status"] == "investigating":
            await controller.start(active)
        return self.metadata(tenant)

    def verification(self):
        rows = self.q(
            "MATCH (v:Verification {id:'tenant-coordination'}) RETURN v.payload"
        )
        return json.loads(rows[0][0]) if rows else {"status": "not_run"}

    async def close(self):
        await asyncio.gather(
            *(controller.close() for controller in self.controllers.values())
        )
