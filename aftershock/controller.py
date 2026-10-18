import asyncio
import os
import time
import uuid
import httpx
from aftershock.agents import Agents, ModelWaiting
from aftershock.domain import Action, ACTION_INFO, evaluate
from aftershock.mcp_client import GraphTools


class Controller:
    def __init__(self, store, workspaces=None):
        self.store = store
        self.agents = Agents(store)
        self.owner = uuid.uuid4().hex
        self.workspaces = workspaces
        self.lock = workspaces.lock if workspaces else asyncio.Lock()
        self.pipeline = None
        self.pipeline_run = None
        self.http = httpx.AsyncClient(timeout=15)
        self.worlds = {
            "main": os.environ.get("SANDBOX_MAIN", "http://main:9000"),
            Action.ROLLBACK: os.environ.get("SANDBOX_ROLLBACK", "http://rollback:9000"),
            Action.RESTART: os.environ.get("SANDBOX_RESTART", "http://restart:9000"),
            Action.FALLBACK: os.environ.get("SANDBOX_FALLBACK", "http://fallback:9000"),
        }

    async def request(self, world, path, payload=None):
        response = await self.http.request(
            "GET" if payload is None else "POST",
            self.worlds[world] + path,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def create(self, name):
        async with self.lock:
            self.idle()
            if self.store.active():
                raise ValueError(
                    "An active company already exists. Reset it before starting another."
                )
            for world in self.worlds:
                await self.request(world, "/reset", {})
            return self.store.create_run(name)

    def idle(self):
        if self.workspaces:
            self.workspaces.require_owner(self.store.tenant)
            self.workspaces.idle()
        if self.pipeline and not self.pipeline.done():
            raise ValueError(
                "Wait for the current investigation before changing the company."
            )

    async def fault(self, run_id):
        async with self.lock:
            self.idle()
            run = self.store.get(run_id)
            if run["status"] == "archived":
                raise ValueError("This run has been archived.")
            await self.request("main", "/fault", {"enabled": True})
            run.update(
                fault=True,
                status="incident",
                incident=run["incident"] + 1,
                version=run["version"] + 1,
                experiments=[],
                recommendation=None,
                error=None,
                model_calls=0,
                escalation=None,
                requires_new_incident=False,
            )
            self.store.q(
                "MATCH (s:Service {id:'recommendations'}),(checkout:Service {id:'checkout'}) SET s.fault=true,checkout.fallback=false",
                graph=run["company_graph"],
            )
            self.store.incident(run)
            self.store.save(run)
            self.store.event(
                run_id,
                "system",
                "Incident detected",
                "Recommendations time out. Checkout cannot complete orders.",
                evidence_ids=["checkout:DEPENDS_ON:recommendations"],
            )
            return run

    async def policy(self, run_id, required):
        async with self.lock:
            self.idle()
            run = self.store.get(run_id)
            if run["status"] == "archived":
                raise ValueError("This run has been archived.")
            await self.request("main", "/policy", {"required": required})
            decision = self.store.policy(run["company_graph"], required)
            run.update(required=required, version=run["version"] + 1)
            if run["incident"]:
                run.update(
                    status="stale", recommendation=None, requires_new_incident=True
                )
            self.store.save(run)
            self.store.event(
                run_id,
                "system",
                "Company policy changed",
                "Recommendations are now mandatory. Previous experiment snapshots are stale."
                if required
                else "Recommendations are optional again. Revalidate before applying a repair.",
                evidence_ids=["policy-recommendations"],
                decision=decision,
            )
            return run

    async def start(self, run_id):
        async with self.lock:
            if self.workspaces:
                self.workspaces.require_owner(self.store.tenant)
            if (
                self.pipeline
                and not self.pipeline.done()
                and self.pipeline_run == run_id
            ):
                return self.store.get(run_id)
            self.idle()
            run = self.store.get(run_id)
            if run.get("requires_new_incident"):
                raise ValueError(
                    "Requirements changed. Inject a fresh incident to replace stale experiment context."
                )
            if not run["fault"] or run["status"] == "archived":
                raise ValueError("Inject an incident before investigating.")
            if run["status"] in ("ready", "unresolved", "resolved"):
                return run
            self.pipeline_run = run_id
            self.pipeline = asyncio.create_task(self.investigate(run_id))
            return run

    async def task(self, run, role, function):
        task_id = self.store.task(run, role)
        result = self.store.task_result(task_id)
        if result is not None:
            self.store.event(
                run["id"],
                role,
                "Handoff restored",
                "Loaded the completed task from FalkorDB after a controller handoff.",
            )
            return result
        # A former controller's lease expires naturally; do not steal live work.
        deadline = time.monotonic() + 95
        while not self.store.claim(task_id, self.owner):
            if time.monotonic() > deadline:
                raise ModelWaiting(
                    "Another controller owns this task. Retry after its lease expires."
                )
            await asyncio.sleep(1)
        self.store.event(
            run["id"],
            role,
            "Task claimed",
            f"{role.title()} acquired a persisted task lease.",
            task_id=task_id,
            attempt=self.owner,
        )

        async def heartbeat():
            while True:
                await asyncio.sleep(20)
                if not self.store.claim(task_id, self.owner):
                    raise RuntimeError("Task lease lost")

        heart = asyncio.create_task(heartbeat())
        try:
            result = await function()
            self.store.finish_task(task_id, self.owner, result)
            return result
        finally:
            heart.cancel()
            await asyncio.gather(heart, return_exceptions=True)
            self.store.release(task_id, self.owner)

    async def investigate(self, run_id):
        try:
            run = self.store.get(run_id)
            run.update(status="investigating", error=None)
            self.store.save(run)

            async def investigator():
                async def propose(args):
                    candidates = self.store.discover_repairs(run["company_graph"])
                    actions = args.get("actions", [])
                    if (
                        not isinstance(actions, list)
                        or len(actions) != len(set(actions))
                        or set(actions) != {c["action"] for c in candidates}
                    ):
                        raise ValueError(
                            "Submit each graph-discovered candidate exactly once; do not add actions absent from the connected runbook graph."
                        )
                    return {
                        "actions": actions,
                        "candidates": candidates,
                        "summary": str(args.get("summary", ""))[:1800],
                    }

                async with GraphTools(self.store, run) as mcp:
                    names = [
                        "inspect_dependencies",
                        "retrieve_evidence",
                        "search_incidents",
                        "inspect_company_context",
                        "discover_repairs",
                        "explain_path",
                    ]
                    self.store.event(
                        run_id,
                        "investigator",
                        "MCP capabilities discovered",
                        f"Connected to {len(mcp.tools)} run-scoped graph tools over the MCP stdio transport.",
                        transport="MCP stdio",
                    )
                    tools = mcp.callbacks(names)
                    tools["propose_action"] = propose
                    return await self.agents.decide(
                        run, "investigator", tools, mcp.tools
                    )

            proposal = await self.task(run, "investigator", investigator)
            run = self.store.get(run_id)
            run["candidates"] = proposal["candidates"]
            run["company_context"] = self.store.company_context(run["company_graph"])
            self.store.save(run)
            self.store.event(
                run_id,
                "investigator",
                f"{len(proposal['actions'])} graph-discovered interventions",
                proposal["summary"],
            )
            if not proposal["actions"]:
                run.update(
                    status="unresolved",
                    recommendation=None,
                    experiments=[],
                    report="No connected runbook contains an enabled bounded repair.",
                )
                self.store.save(run)
                self.store.remember(
                    run,
                    {
                        "action": "none",
                        "status": "unresolved",
                        "required": run["required"],
                    },
                )
                run["escalation"] = self.store.escalate(run)
                self.store.save(run)
                return

            async def coordinate():
                snapshot = self.store.snapshot(run)
                if snapshot is None:
                    graph = (
                        f"{run['company_graph']}_incident_{run['incident']}_snapshot"
                    )
                    self.store.drop_graph(graph)
                    self.store.copy(run["company_graph"], graph)
                    bundle = await self.request("main", "/snapshot", {})
                    self.store.save_snapshot(run, bundle, graph)
                    snapshot = bundle, graph, run["version"]
                bundle, graph, version = snapshot
                if self.store.get(run_id)["version"] != version:
                    raise ValueError(
                        "Company changed since snapshot. Inject a new incident to revalidate."
                    )
                self.store.event(
                    run_id,
                    "coordinator",
                    "Snapshot frozen",
                    f"Company v{version} · {bundle['checksum'][:12]}. Graph and SQLite snapshot shared by all experiments.",
                )
                existing = {e["action"]: e for e in self.store.experiments(run)}

                async def experiment(action):
                    if existing.get(action, {}).get("verdict"):
                        return existing[action]
                    return await self.experiment(run, action, bundle, graph, version)

                return await asyncio.gather(
                    *(experiment(action) for action in proposal["actions"])
                )

            experiments = await self.task(run, "coordinator", coordinate)

            async def verify():
                async with GraphTools(self.store, run) as mcp:
                    return await self.agents.decide(
                        run, "verifier", mcp.callbacks(["read_results"]), mcp.tools
                    )

            report = await self.task(run, "verifier", verify)
            passing = [e for e in experiments if e.get("verdict", {}).get("passed")]
            passing.sort(
                key=lambda e: (
                    e["verdict"]["affected_customer_groups"],
                    e["verdict"]["billing_failures"]
                    + e["verdict"]["checkout_failures"],
                    1,
                    e["action"],
                )
            )
            run = self.store.get(run_id)
            run.update(
                status="ready" if passing else "unresolved",
                experiments=experiments,
                recommendation=passing[0]["action"] if passing else None,
                snapshot_version=experiments[0]["version"],
                report=report.get("summary"),
                error=None,
            )
            self.store.save(run)
            self.store.record_decisions(run, experiments, run["recommendation"])
            self.store.event(
                run_id,
                "verifier",
                "Repair verified" if passing else "No safe repair",
                "Graceful fallback passed independent runtime verification."
                if passing
                else "None of the available interventions satisfies current requirements. No action will be applied.",
                evidence_ids=sorted(
                    {id_ for e in experiments for id_ in e["verdict"]["evidence_ids"]}
                ),
            )
            if not passing:
                run["escalation"] = self.store.escalate(run)
                self.store.save(run)
                if run["escalation"]:
                    self.store.event(
                        run_id,
                        "coordinator",
                        "Owner handoff created",
                        f"Assigned an internal escalation to {run['escalation']['owner']['name']} ({run['escalation']['owner']['team']}).",
                        evidence_ids=run["escalation"]["decision_ids"],
                    )
                self.store.remember(
                    run,
                    {
                        "action": "none",
                        "status": "unresolved",
                        "required": run["required"],
                        "evidence_ids": [
                            id_
                            for e in experiments
                            for id_ in e["verdict"]["evidence_ids"]
                        ],
                    },
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            try:
                run = self.store.get(run_id)
                run.update(
                    status="waiting" if isinstance(error, ModelWaiting) else "error",
                    error=str(error),
                )
                self.store.save(run)
                self.store.event(run_id, "system", "Investigation paused", str(error))
            except Exception:
                # Graph unavailability cannot be replaced with local authoritative state.
                pass

    async def experiment(self, run, action, bundle, source_graph, version):
        graph = f"{source_graph}_{action}"
        self.store.drop_graph(graph)
        self.store.copy(source_graph, graph)
        prediction = self.store.predict(graph, action)
        self.store.mutate_branch(graph, action)
        record = {
            "action": action,
            "title": ACTION_INFO[Action(action)]["title"],
            "graph": graph,
            "version": version,
            "checksum": bundle["checksum"],
            "status": "running",
            "prediction": prediction,
            "observations": [],
            "verdict": None,
            "started_at": time.time(),
        }
        self.store.save_experiment(run, record)
        self.store.event(
            run["id"],
            "coordinator",
            "Experiment started",
            record["title"],
            action=action,
            graph=graph,
        )
        await self.request(action, "/restore", bundle)
        before = await self.request(action, "/status")
        # Probe billing independently so checkout timeouts never mask the interruption.
        observing = True

        async def monitor():
            while observing:
                record["observations"].append(await self.request(action, "/observe"))
                await asyncio.sleep(0.08)

        monitor_task = asyncio.create_task(monitor())
        await asyncio.sleep(0.35)
        action_result = None
        try:
            if prediction["eligible"] or action != Action.FALLBACK:
                action_result = await self.request(
                    action, "/action", {"action": action}
                )
            else:
                action_result = {"blocked": True, "reason": prediction["reason"]}
            await asyncio.sleep(1.15)
        finally:
            observing = False
            await monitor_task
        # Three independent post-intervention probes establish stable recovery.
        for _ in range(3):
            record["observations"].append(await self.request(action, "/observe"))
            await asyncio.sleep(0.08)
        after = await self.request(action, "/status")
        record.update(
            status="complete",
            verdict=evaluate(action, record["observations"], prediction).model_dump(),
            action_result=action_result,
            processes_before=before["processes"],
            processes_after=after["processes"],
            duration_ms=round((time.time() - record["started_at"]) * 1000),
            discrepancy=(
                prediction["eligible"]
                and not all(p["checkout"]["ok"] for p in record["observations"][-3:])
            ),
        )
        self.store.save_experiment(run, record)
        self.store.event(
            run["id"],
            "verifier",
            "Experiment passed"
            if record["verdict"]["passed"]
            else "Experiment rejected",
            " ".join(record["verdict"]["reasons"]),
            action=action,
            evidence_ids=prediction["evidence_ids"],
        )
        return record

    async def apply(self, run_id, key):
        async with self.lock:
            self.idle()
            run = self.store.get(run_id)
            if run.get("requires_new_incident"):
                raise ValueError(
                    "These experiment results are stale. Inject a fresh incident before applying a repair."
                )
            if run["status"] == "resolved":
                reservation = self.store.reserve_application(
                    run, key, run["recommendation"]
                )
                if reservation["key"] != key:
                    raise ValueError(
                        "This incident was already applied with another idempotency key."
                    )
                return run
            if run["status"] != "ready" or not run["recommendation"]:
                raise ValueError("A complete, verified recommendation is required.")
            if run["version"] != run["snapshot_version"]:
                raise ValueError(
                    "Company version changed; these experiment results are stale. Inject a new incident."
                )
            prediction = self.store.predict(run["company_graph"], run["recommendation"])
            if not prediction["eligible"]:
                raise ValueError("The current graph no longer permits this repair.")
            reservation = self.store.reserve_application(
                run, key, run["recommendation"]
            )
            if reservation["key"] != key:
                raise ValueError(
                    "An application already exists. Retry with its original idempotency key."
                )
            # The selected fallback is idempotent; a pending application is safe to resume.
            await self.request("main", "/action", {"action": run["recommendation"]})
            observations = [await self.request("main", "/observe") for _ in range(3)]
            verdict = evaluate(run["recommendation"], observations, prediction)
            if not verdict.passed:
                raise ValueError(
                    "Main environment verification failed. The repair is not recorded as successful."
                )
            self.store.mutate_branch(run["company_graph"], run["recommendation"])
            self.store.applied(run)
            run.update(
                status="resolved",
                version=run["version"] + 1,
                applied_at=time.time(),
                application_observations=observations,
            )
            self.store.save(run)
            self.store.remember(
                run,
                {
                    "action": run["recommendation"],
                    "status": "resolved",
                    "required": run["required"],
                    "evidence_ids": prediction["evidence_ids"],
                    "observations": observations,
                },
            )
            self.store.event(
                run_id,
                "verifier",
                "Main company recovered",
                "Applied fallback and verified three successful checkout and billing requests. Outcome saved to persistent incident memory.",
                evidence_ids=prediction["evidence_ids"],
            )
            return run

    async def reset(self, run_id):
        async with self.lock:
            self.idle()
            run = self.store.get(run_id)
            if self.store.active() != run_id:
                raise ValueError(
                    "Only the active run can reset shared sandbox resources."
                )
            for world in self.worlds:
                await self.request(world, "/reset", {})
            self.store.reset_run(run)
            return {"ok": True}

    async def close(self):
        if self.pipeline and not self.pipeline.done():
            self.pipeline.cancel()
            await asyncio.gather(self.pipeline, return_exceptions=True)
        await self.http.aclose()
