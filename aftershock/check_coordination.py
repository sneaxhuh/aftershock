"""One focused real-FalkorDB check. Run: python -m aftershock.check_coordination."""

import asyncio
import concurrent.futures
import json
import os
import threading
import time
import uuid

from aftershock.graph import GraphStore
from aftershock.mcp_client import GraphTools


async def main():
    os.environ["AGENT_MODE"] = "rehearsal"
    os.environ["EMBEDDINGS_ENABLED"] = "false"
    base = os.environ.get("GRAPH_PREFIX", "aftershock")
    prefix = f"{base}_verification_{uuid.uuid4().hex[:8]}"
    a, b = GraphStore(prefix, "northstar"), GraphStore(prefix, "harbor")
    started = time.monotonic()
    try:
        runs = {}
        for store in (a, b):
            store.initialize()
            run = store.create_run("Isolated coordination fixture")
            run["incident"] = 1
            store.save(run)
            store.incident(run)
            runs[store.tenant] = run
        # A tenant cannot use a peer run ID, or supply a peer graph to the adapter.
        for left, right in ((a, b), (b, a)):
            try:
                left.get(runs[right.tenant]["id"])
                raise AssertionError("Cross-tenant run was readable")
            except KeyError:
                pass
            try:
                left.q("MATCH (n) RETURN n", graph=right.memory_name)
                raise AssertionError("Cross-tenant graph was readable")
            except ValueError:
                pass
            assert all(
                item["incident"].startswith(runs[left.tenant]["id"])
                for item in left.search_memory()
            )

        barrier = threading.Barrier(8)

        def reader_writer(worker):
            tenant = "northstar" if worker % 2 == 0 else "harbor"
            store = GraphStore(prefix, tenant)
            barrier.wait(timeout=10)
            for index in range(4):
                store.message(
                    runs[tenant],
                    "check",
                    "concurrent_fixture",
                    {"tenant": tenant, "worker": worker, "index": index},
                )
                assert all(
                    item["incident"].startswith(runs[tenant]["id"])
                    for item in store.search_memory()
                )

        await asyncio.to_thread(
            lambda: list(
                concurrent.futures.ThreadPoolExecutor(max_workers=8).map(
                    reader_writer, range(8)
                )
            )
        )
        for store in (a, b):
            messages = store.conversation(runs[store.tenant]["id"])
            assert len(messages) == 16
            assert len({m["sequence"] for m in messages}) == 16
            assert all(m["content"]["tenant"] == store.tenant for m in messages)

        task = a.task(runs[a.tenant], "handoff-check")
        claims = threading.Barrier(8)

        def claim(worker):
            store = GraphStore(prefix, "northstar")
            claims.wait(timeout=10)
            owner = f"worker-{worker}"
            return owner, store.claim(task, owner, lease=3)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = await asyncio.to_thread(lambda: list(pool.map(claim, range(8))))
        winners = [owner for owner, won in results if won]
        assert len(winners) == 1, results
        await asyncio.sleep(3.1)
        resumed = GraphStore(prefix, "northstar")
        assert resumed.claim(task, "replacement-controller")
        a.finish_task(task, winners[0], {"wrong": "former lease owner"})
        assert resumed.task_result(task) is None
        handoff = {"source": "persisted graph handoff", "tenant": "northstar"}
        resumed.finish_task(task, "replacement-controller", handoff)
        assert GraphStore(prefix, "northstar").task_result(task) == handoff

        async with GraphTools(a, runs[a.tenant]) as mcp:
            result = await mcp.callbacks(["search_incidents"])["search_incidents"]({})
            assert all(
                item["incident"].startswith(runs[a.tenant]["id"])
                for item in result["episodic"]
            )
        async with GraphTools(a, runs[b.tenant]) as mcp:
            denied = await mcp.session.call_tool("read_results", {})
            assert denied.isError

        report = {
            "status": "passed",
            "checked_at": time.time(),
            "workers": 8,
            "concurrent_messages": 32,
            "successful_task_claims": len(winners),
            "cross_tenant_reads_blocked": True,
            "mcp_scope_enforced": True,
            "expired_lease_reclaimed": True,
            "stale_owner_write_blocked": True,
            "handoff_persisted": True,
            "duration_seconds": round(time.monotonic() - started, 2),
            "scope": "Functional concurrency check on real FalkorDB; not a throughput benchmark.",
        }
        admin = a.db.select_graph(f"{base}_registry")
        admin.query(
            "MERGE (v:Verification {id:'tenant-coordination'}) SET v.payload=$payload",
            {"payload": json.dumps(report)},
        )
        print(json.dumps(report, indent=2))
    finally:
        for name in a.db.list_graphs():
            for store in (a, b):
                if name == store.memory_name or name.startswith(
                    f"{store.prefix}_company_"
                ):
                    store.drop_graph(name)


if __name__ == "__main__":
    asyncio.run(main())
