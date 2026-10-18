"""Run with RUN_INTEGRATION=1 and the compose.dev.yaml services available."""

import asyncio
import os
import time
import uuid
import pytest
from aftershock.controller import Controller
from aftershock.graph import GraphStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION") != "1",
        reason="requires local FalkorDB and sandboxes",
    ),
]


@pytest.fixture
def environment(monkeypatch):
    monkeypatch.setenv("FALKOR_HOST", "127.0.0.1")
    monkeypatch.setenv("FALKOR_PORT", "16379")
    monkeypatch.setenv("AGENT_MODE", "rehearsal")
    for key, port in [
        ("MAIN", 9100),
        ("ROLLBACK", 9200),
        ("RESTART", 9300),
        ("FALLBACK", 9400),
    ]:
        monkeypatch.setenv(f"SANDBOX_{key}", f"http://127.0.0.1:{port}")
    store = GraphStore("test_" + uuid.uuid4().hex[:8])
    store.initialize()
    yield store
    for graph in store.db.list_graphs():
        if graph.startswith(store.prefix):
            store.drop_graph(graph)


async def finish(controller):
    await asyncio.wait_for(controller.pipeline, timeout=45)


async def test_complete_incident_memory_and_changed_policy(environment):
    store = environment
    controller = Controller(store)
    try:
        run = await controller.create("Integration company")
        healthy = await controller.request("main", "/observe")
        assert healthy["checkout"]["ok"] and healthy["billing"]["ok"]
        run = await controller.fault(run["id"])
        failed = await controller.request("main", "/observe")
        assert not failed["checkout"]["ok"] and failed["billing"]["ok"]
        await controller.start(run["id"])
        await finish(controller)
        run = store.get(run["id"])
        assert run["status"] == "ready", run.get("error")
        assert run["recommendation"] == "enable_fallback"
        experiments = {e["action"]: e for e in store.experiments(run)}
        rollback = experiments["rollback_checkout"]
        assert not rollback["verdict"]["passed"]
        assert (
            rollback["processes_before"]["checkout"]["pid"]
            != rollback["processes_after"]["checkout"]["pid"]
        )
        assert any(o["checkout"]["status"] == 409 for o in rollback["observations"])
        restart = experiments["restart_data"]
        assert restart["verdict"]["billing_failures"] > 0
        assert (
            restart["processes_before"]["data"]["pid"]
            != restart["processes_after"]["data"]["pid"]
        )
        assert experiments["enable_fallback"]["verdict"]["passed"]
        assert len({e["checksum"] for e in experiments.values()}) == 1
        assert not (await controller.request("main", "/status"))["config"]["fallback"]
        assert (await controller.request("enable_fallback", "/status"))["config"][
            "fallback"
        ]
        assert all(e["prediction"]["evidence_ids"] for e in experiments.values())
        key = "integration-repair-key"
        applied = await controller.apply(run["id"], key)
        assert applied["status"] == "resolved"
        assert (await controller.apply(run["id"], key))["version"] == applied["version"]
        with pytest.raises(ValueError, match="another idempotency"):
            await controller.apply(run["id"], "different-repair-key")
        assert any(
            m["outcome"] and m["outcome"]["status"] == "resolved"
            for m in store.search_memory()
        )
        # A fresh controller has no conversational state; its next role retrieves graph memory.
        await controller.close()
        controller = Controller(GraphStore(store.prefix))
        await controller.policy(run["id"], True)
        run = await controller.fault(run["id"])
        await controller.start(run["id"])
        await finish(controller)
        run = store.get(run["id"])
        assert run["status"] == "unresolved", run.get("error")
        assert run["recommendation"] is None
        fallback = next(
            e for e in store.experiments(run) if e["action"] == "enable_fallback"
        )
        assert not fallback["prediction"]["eligible"]
        assert fallback["action_result"]["blocked"]
        with pytest.raises(ValueError, match="verified recommendation"):
            await controller.apply(run["id"], "should-never-apply")
    finally:
        await controller.close()


async def test_stale_company_version_disables_application(environment):
    controller = Controller(environment)
    try:
        run = await controller.create("Stale snapshot")
        await controller.fault(run["id"])
        await controller.start(run["id"])
        await finish(controller)
        assert environment.get(run["id"])["status"] == "ready"
        await controller.policy(run["id"], True)
        with pytest.raises(ValueError, match="stale"):
            await controller.apply(run["id"], "stale-apply-key")
    finally:
        await controller.close()


async def test_missing_model_key_pauses_instead_of_fabricating(
    environment, monkeypatch
):
    monkeypatch.setenv("AGENT_MODE", "live")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    controller = Controller(environment)
    try:
        run = await controller.create("Model unavailable")
        await controller.fault(run["id"])
        await controller.start(run["id"])
        await finish(controller)
        result = environment.get(run["id"])
        assert result["status"] == "waiting"
        assert result["recommendation"] is None
        assert not environment.experiments(result)
    finally:
        await controller.close()


def test_graph_copies_and_task_leases_are_independent(environment):
    store = environment
    run = store.create_run("Copy test")
    branch = run["company_graph"] + "_branch"
    store.copy(run["company_graph"], branch)
    store.mutate_branch(branch, "rollback_checkout")
    query = "MATCH (s:Service {id:'checkout'}) RETURN s.version"
    assert store.q(query, graph=branch)[0][0] == 1
    assert store.q(query, graph=run["company_graph"])[0][0] == 2
    task = store.task(run, "investigator")
    assert store.claim(task, "worker-one", lease=0.1)
    assert not store.claim(task, "worker-two")
    time.sleep(0.12)
    assert store.claim(task, "worker-two")
    store.finish_task(task, "worker-two", {"result": "persisted"})
    store.release(task, "worker-two")
    assert store.task_result(task) == {"result": "persisted"}


async def test_interrupted_experiments_resume_from_graph_handoffs(environment):
    controller = Controller(environment)
    run = await controller.create("Interrupted investigation")
    await controller.fault(run["id"])
    await controller.start(run["id"])
    for _ in range(100):
        if environment.snapshot(environment.get(run["id"])):
            break
        await asyncio.sleep(0.03)
    assert environment.snapshot(environment.get(run["id"]))
    await controller.close()
    assert environment.get(run["id"])["status"] == "investigating"
    resumed = Controller(GraphStore(environment.prefix))
    try:
        await resumed.start(run["id"])
        await finish(resumed)
        assert environment.get(run["id"])["status"] == "ready"
        assert any(
            e["title"] == "Handoff restored" for e in environment.events(run["id"])
        )
    finally:
        await resumed.close()


async def test_snapshot_corruption_is_rejected_without_mutation(environment):
    controller = Controller(environment)
    try:
        bundle = await controller.request("main", "/snapshot", {})
        bundle["checksum"] = "0" * 64
        before = await controller.request("rollback_checkout", "/status")
        import httpx

        with pytest.raises(httpx.HTTPStatusError):
            await controller.request("rollback_checkout", "/restore", bundle)
        after = await controller.request("rollback_checkout", "/status")
        assert before == after
    finally:
        await controller.close()


async def test_model_budget_exhaustion_pauses_without_network_call(
    environment, monkeypatch
):
    monkeypatch.setenv("AGENT_MODE", "live")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-no-network-request")
    controller = Controller(environment)
    try:
        run = await controller.create("Budget exhausted")
        await controller.fault(run["id"])
        run = environment.get(run["id"])
        run["model_calls"] = 12
        environment.save(run)
        await controller.start(run["id"])
        await finish(controller)
        current = environment.get(run["id"])
        assert current["status"] == "waiting"
        assert "budget" in current["error"]
        assert current["model_calls"] == 12
    finally:
        await controller.close()
