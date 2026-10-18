import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from redis.exceptions import RedisError
import httpx
from aftershock.controller import Controller
from aftershock.domain import ApplyRequest, CreateRun, PolicyRequest
from aftershock.graph import GraphStore
from aftershock.tenants import Workspaces, COOKIE
from aftershock.access import OperatorAccess


@asynccontextmanager
async def lifespan(app):
    app.state.access = OperatorAccess.from_environment()
    registry = Workspaces()
    registry.initialize()
    app.state.workspaces = registry
    app.state.store = registry.stores["northstar"]
    app.state.controller = registry.controllers["northstar"]
    owner = registry.controllers.get(registry.owner)
    if owner and owner.store.active():
        active = owner.store.active()
        run = owner.store.get(active)
        owner.store.event(
            active,
            "system",
            "Controller connected",
            "Tenant-scoped state restored from FalkorDB.",
        )
        if run["status"] == "investigating":
            await owner.start(active)
    yield
    await registry.close()


app = FastAPI(title="AFTERSHOCK", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def bind_workspace(request: Request, call_next):
    from fastapi.responses import JSONResponse

    access = app.state.access
    if request.url.path != "/api/health" and not access.accepts(
        request.headers.get("authorization")
    ):
        return JSONResponse(
            {"detail": "Operator sign-in is required."},
            status_code=401,
            headers={
                "WWW-Authenticate": 'Basic realm="AFTERSHOCK operator", charset="UTF-8"',
                "Cache-Control": "no-store",
            },
        )
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    from urllib.parse import urlparse

    registry = app.state.workspaces
    tenant = registry.resolve(request.cookies.get(COOKIE))
    bootstrap = request.url.path in ("/api/config", "/api/health")
    if not tenant and not bootstrap:
        return JSONResponse(
            {"detail": "Open the workspace console to establish a scoped session."},
            status_code=401,
        )
    if request.method == "POST" and request.headers.get("origin"):
        if urlparse(request.headers["origin"]).netloc != request.url.netloc:
            return JSONResponse(
                {"detail": "Workspace changes require the same origin."},
                status_code=403,
            )
    issue = tenant is None
    tenant = tenant or "northstar"
    request.state.tenant = tenant
    request.state.store = registry.stores[tenant]
    request.state.controller = registry.controllers[tenant]
    response = await call_next(request)
    if issue:
        response.set_cookie(
            COOKIE,
            registry.issue(tenant),
            httponly=True,
            samesite="strict",
            max_age=604800,
            secure=access.secure_cookies,
        )
    return response


@app.post("/api/workspaces/{tenant}/activate")
async def activate_workspace(tenant: str, request: Request):
    from fastapi.responses import JSONResponse

    registry = app.state.workspaces
    metadata = await registry.activate(tenant)
    response = JSONResponse(metadata)
    response.set_cookie(
        COOKIE,
        registry.issue(tenant),
        httponly=True,
        samesite="strict",
        max_age=604800,
        secure=app.state.access.secure_cookies,
    )
    return response


@app.get("/api/coordination-check")
async def coordination_check(request: Request):
    return app.state.workspaces.verification()


@app.get("/api/runs/{run_id}/decision-diff")
async def decision_diff(run_id: str, request: Request):
    run = request.state.store.get(run_id)
    return request.state.store.decision_diff(run)


@app.exception_handler(RedisError)
async def graph_unavailable(_, error):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={
            "detail": "FalkorDB unavailable; actions are disabled until the graph reconnects."
        },
    )


@app.exception_handler(httpx.HTTPError)
async def sandbox_unavailable(_, error):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={
            "detail": "A sandbox request failed. Inspect service health before retrying."
        },
    )


@app.exception_handler(KeyError)
async def missing(_, error):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=404, content={"detail": "Run or resource not found"}
    )


@app.exception_handler(ValueError)
async def invalid(_, error):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.get("/api/health")
async def health(request: Request):
    try:
        request.state.store.q("RETURN 1")
        return {
            "ok": True,
            "graph": "FalkorDB",
            "mode": request.state.controller.agents.mode,
        }
    except Exception:
        raise HTTPException(503, "FalkorDB unavailable; actions are disabled")


@app.get("/api/config")
async def config(request: Request):
    controller = request.state.controller
    return {
        **app.state.workspaces.metadata(request.state.tenant),
        "mode": controller.agents.mode,
        "model": controller.agents.model,
        "key_configured": bool(os.environ.get("GEMINI_API_KEY")),
        "active_run": request.state.store.active(),
        "tool_transport": "MCP stdio",
        "embedding_model": request.state.store.embeddings.model,
    }


@app.post("/api/runs", status_code=201)
async def create_run(body: CreateRun, request: Request):
    return await request.state.controller.create(body.name)


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    run = request.state.store.get(run_id)
    run["experiments"] = request.state.store.experiments(run) if run["incident"] else []
    return run


@app.post("/api/runs/{run_id}/fault")
async def fault(run_id: str, request: Request):
    return await request.state.controller.fault(run_id)


@app.post("/api/runs/{run_id}/policy")
async def policy(run_id: str, body: PolicyRequest, request: Request):
    return await request.state.controller.policy(run_id, body.required)


@app.post("/api/runs/{run_id}/investigate", status_code=202)
async def investigate(run_id: str, request: Request):
    return await request.state.controller.start(run_id)


@app.post("/api/runs/{run_id}/apply")
async def apply(run_id: str, body: ApplyRequest, request: Request):
    return await request.state.controller.apply(run_id, body.idempotency_key)


@app.post("/api/runs/{run_id}/reset")
async def reset(run_id: str, request: Request):
    return await request.state.controller.reset(run_id)


@app.get("/api/runs/{run_id}/observe")
async def observe(run_id: str, request: Request):
    async with app.state.workspaces.lock:
        app.state.workspaces.require_owner(request.state.tenant)
        if request.state.store.active() != run_id:
            raise HTTPException(
                409, "Only the active company has a running environment"
            )
        return await request.state.controller.request("main", "/observe")


@app.get("/api/runs/{run_id}/graph")
async def graph(run_id: str, request: Request, branch: str = "company"):
    run = request.state.store.get(run_id)
    name = run["company_graph"]
    if branch != "company":
        experiments = request.state.store.experiments(run)
        selected = next((e for e in experiments if e["action"] == branch), None)
        if not selected:
            raise HTTPException(404, "Experiment graph not found")
        name = selected["graph"]
    return request.state.store.projection(name)


@app.get("/api/runs/{run_id}/memory")
async def memory(run_id: str, request: Request):
    request.state.store.get(run_id)
    return request.state.store.search_memory()


@app.get("/api/runs/{run_id}/context")
async def company_context(run_id: str, request: Request):
    run = request.state.store.get(run_id)
    return {
        **request.state.store.company_context(run["company_graph"]),
        "candidates": request.state.store.discover_repairs(run["company_graph"]),
        "procedures": request.state.store.procedures(run["company_graph"]),
        "insights": request.state.store.graph_insights(run["company_graph"]),
    }


@app.get("/api/runs/{run_id}/conversation")
async def conversation(run_id: str, request: Request):
    request.state.store.get(run_id)
    return request.state.store.conversation(run_id)


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, request: Request, after: int = 0):
    request.state.store.get(run_id)
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        raise HTTPException(400, "Invalid Last-Event-ID")

    async def stream():
        nonlocal cursor
        while not await request.is_disconnected():
            for event in request.state.store.events(run_id, cursor):
                cursor = event["sequence"]
                yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


DIST = Path(os.environ.get("WEB_DIST", "web/dist"))
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Unknown API route")
        return FileResponse(DIST / "index.html")
