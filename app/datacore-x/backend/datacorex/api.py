"""DATACORE-X integration service (L3): REST + WebSocket API.

Run:  uvicorn datacorex.api:app --port 8000   (from ./backend)
Env:  DCX_SPEED (sim s per wall s, default 1), DCX_HISTORIAN (sqlite path),
      DCX_SOURCE=surrogate|external, DCX_OPCUA=1 (start OPC UA server),
      DCX_SEED (default 7)

Authorisation is header-based for the prototype (``X-DCX-Role``:
viewer|operator|engineer, ``X-DCX-User``).  In deployment this is replaced by
Ignition's identity provider / OIDC tokens; command authority stays
server-side either way.
"""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import json as _json
from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .registry import asset_index
from .runtime import ROLE_RANK, LiveRuntime
from .scenarios import CATALOGUE

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

RT: LiveRuntime | None = None


def runtime() -> LiveRuntime:
    assert RT is not None
    return RT


@asynccontextmanager
async def lifespan(app: FastAPI):
    global RT
    RT = LiveRuntime(seed=int(os.environ.get("DCX_SEED", 7)), speed=float(os.environ.get("DCX_SPEED", 1.0)),
                     historian_path=os.environ.get("DCX_HISTORIAN"))
    if os.environ.get("DCX_OPCUA") == "1":
        from .opcua_server import OpcUaPublisher
        RT.opcua = OpcUaPublisher()
        await RT.opcua.start()
        RT.core.comm["opcua"] = "OK"
    task = asyncio.create_task(RT.run_forever())
    yield
    task.cancel()
    if RT.opcua is not None:
        await RT.opcua.stop()
    RT.hist.flush()


app = FastAPI(title="DATACORE-X Digital Twin Integration Service", version="1.0.0", lifespan=lifespan)


def need(role: str | None, minimum: str):
    r = (role or "viewer").lower()
    if ROLE_RANK.get(r, -1) < ROLE_RANK[minimum]:
        raise HTTPException(403, f"role '{r}' not permitted; requires {minimum}")
    return r


# ---------------------------------------------------------------------------
@app.get("/api/registry")
def get_registry():
    return runtime().registry()


@app.get("/api/snapshot")
def get_snapshot():
    return runtime().latest


@app.get("/api/tags")
def get_tags():
    """Flat Ignition-style tag map (path -> value/unit/quality/timestamp) with the same seq as the WebSocket."""
    return runtime().flat_tags()


@app.get("/api/history")
def get_history(asset: str, key: str, seconds: float = Query(900, ge=10, le=86400), max_points: int = 600):
    if asset not in asset_index() and asset != "_facility":
        raise HTTPException(404, "unknown asset")
    return {"asset": asset, "key": key, "points": runtime().hist.trend(asset, key, seconds, max_points)}


@app.get("/api/historian/{seq}")
def historian_record(seq: int, truth: bool = False):
    rt = runtime()
    rec = rt.hist.get(seq)
    if rec is None:
        raise HTTPException(404, "seq not in historian")
    out = {"measured": rec}
    if truth:
        out["truth"] = rt.hist.get_truth(seq)
    return out


# ---------------- alarms ----------------------------------------------------
@app.get("/api/alarms")
def get_alarms():
    rt = runtime()
    return {"active": rt.core.alarms.active(), "history": rt.core.alarms.history[-100:]}


@app.post("/api/alarms/{alarm_id:path}/ack")
def ack_alarm(alarm_id: str, x_dcx_role: str | None = Header(None), x_dcx_user: str | None = Header("anonymous")):
    need(x_dcx_role, "operator")
    rt = runtime()
    with rt.lock:
        ok = rt.core.alarms.ack(alarm_id, x_dcx_user)
    if not ok:
        raise HTTPException(404, "alarm not active")
    return {"ok": True, "alarm_id": alarm_id, "acked_by": x_dcx_user}


# ---------------- commands --------------------------------------------------
class CommandIn(BaseModel):
    command: str
    asset: str | None = None
    name: str | None = None
    value: float | str | None = None
    client_cmd_id: str | None = Field(None, max_length=64)


@app.post("/api/commands")
def post_command(cmd: CommandIn, x_dcx_role: str | None = Header("viewer"), x_dcx_user: str | None = Header("anonymous")):
    return runtime().submit_command(cmd.model_dump(), x_dcx_user or "anonymous", (x_dcx_role or "viewer").lower())


@app.get("/api/commands")
def list_commands():
    return sorted(runtime().commands.values(), key=lambda c: -c["received_wall"])[:100]


@app.get("/api/commands/{cid}")
def get_command(cid: str):
    c = runtime().commands.get(cid)
    if not c:
        raise HTTPException(404, "unknown command id")
    return c


# ---------------- scenarios -------------------------------------------------
class ScenarioRequestIn(BaseModel):
    scenario_id: str
    params: dict = {}
    horizon_s: float = 1800
    clean_start: bool = False   # run the what-if from a fault-free copy (live plant untouched)


@app.get("/api/scenarios")
def scenarios():
    return CATALOGUE


@app.post("/api/scenarios/requests")
async def scenario_request(request: Request, x_dcx_role: str | None = Header(None), x_dcx_user: str | None = Header("anonymous")):
    # Tolerant body parsing: SCADA HTTP clients (e.g. Ignition system.net.httpClient) do not
    # always send Content-Type: application/json, so accept JSON regardless of the header,
    # and form-encoded fields as a fallback.
    raw = await request.body()
    try:
        data = _json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        from urllib.parse import parse_qs
        q = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace")).items()}
        data = {"scenario_id": q.get("scenario_id", ""), "horizon_s": float(q.get("horizon_s", 1800)),
                "params": _json.loads(q["params"]) if q.get("params") else {}}
    if (not data) and request.query_params.get("scenario_id"):
        qp = request.query_params
        data = {"scenario_id": qp["scenario_id"], "horizon_s": float(qp.get("horizon_s", 1800)),
                "params": _json.loads(qp["params"]) if qp.get("params") else {},
                "clean_start": qp.get("clean_start", "false").lower() in ("1", "true", "yes")}
    if not isinstance(data, dict) or "scenario_id" not in data:
        raise HTTPException(422, f"expected JSON body with scenario_id (content-type {request.headers.get('content-type')!r}, {len(raw)} bytes)")
    body = ScenarioRequestIn(**data)
    role = need(x_dcx_role, "operator")
    try:
        return runtime().scen.request(body.scenario_id, body.params, x_dcx_user, role, body.horizon_s, body.clean_start)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, str(e))


@app.get("/api/scenarios/requests")
def scenario_requests():
    return sorted(runtime().scen.requests.values(), key=lambda r: -r["requested_at"])


@app.post("/api/scenarios/requests/{rid}/approve")
def scenario_approve(rid: str, x_dcx_role: str | None = Header(None), x_dcx_user: str | None = Header("anonymous")):
    need(x_dcx_role, "operator")
    rt = runtime()
    if rid not in rt.scen.requests:
        raise HTTPException(404, "unknown request")
    try:
        run_id = rt.approve_and_run(rid, x_dcx_user)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"request_id": rid, "run_id": run_id, "status": "APPROVED"}


@app.post("/api/scenarios/requests/{rid}/reject")
def scenario_reject(rid: str, reason: str = "", x_dcx_role: str | None = Header(None), x_dcx_user: str | None = Header("anonymous")):
    need(x_dcx_role, "operator")
    try:
        return runtime().scen.reject(rid, x_dcx_user, reason)
    except KeyError:
        raise HTTPException(404, "unknown request")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/api/scenarios/runs/{run_id}")
def scenario_run(run_id: str, frames: bool = False):
    run = runtime().scen.runs.get(run_id)
    if not run:
        raise HTTPException(404, "unknown run")
    out = {k: v for k, v in run.items() if k not in ("future", "result")}
    if run["result"] is not None:
        res = dict(run["result"])
        if not frames:
            res.pop("frames")
        out["result"] = res
    return JSONResponse(out)


@app.post("/api/scenarios/runs/{run_id}/apply")
def scenario_apply(run_id: str, x_dcx_role: str | None = Header(None), x_dcx_user: str | None = Header("anonymous")):
    need(x_dcx_role, "engineer")
    try:
        runtime().apply_to_live(run_id, x_dcx_user)
    except (KeyError, ValueError) as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "run_id": run_id, "applied_to_live": True}


@app.post("/api/live/clear_faults")
def clear_live(x_dcx_role: str | None = Header(None), x_dcx_user: str | None = Header("anonymous")):
    need(x_dcx_role, "engineer")
    runtime().clear_live_faults(x_dcx_user)
    return {"ok": True}


@app.get("/api/scenarios/audit")
def scenario_audit():
    return runtime().scen.audit[-200:]


# ---------------- simulation control & diagnostics --------------------------
class SpeedIn(BaseModel):
    speed: float = Field(..., ge=0.1, le=120)


@app.post("/api/sim/speed")
def sim_speed(b: SpeedIn, x_dcx_role: str | None = Header(None)):
    need(x_dcx_role, "engineer")
    runtime().speed = b.speed
    return {"speed": b.speed}


@app.post("/api/sim/pause")
def sim_pause(paused: bool = True, x_dcx_role: str | None = Header(None)):
    need(x_dcx_role, "engineer")
    runtime().paused = paused
    return {"paused": paused}


@app.post("/api/diag/comm_loss")
def diag_comm_loss(seconds: float = Query(8.0, ge=1, le=120), x_dcx_role: str | None = Header(None)):
    """Validation hook (8A-G test 9): suppress WebSocket publication to test loss detection & recovery."""
    need(x_dcx_role, "engineer")
    runtime().comm_loss_until = time.time() + seconds
    return {"comm_loss_until": runtime().comm_loss_until}


@app.post("/api/diag/ai_service")
def diag_ai(online: bool = True, x_dcx_role: str | None = Header(None)):
    """Validation hook: take the AI/health service offline (safe fallback: conventional control unaffected)."""
    need(x_dcx_role, "engineer")
    runtime().core.comm["ai"] = "OK" if online else "OFFLINE"
    return {"ai": runtime().core.comm["ai"]}


@app.get("/api/diag")
def diag():
    rt = runtime()
    return {"stats": rt.stats, "clients": len(rt.clients), "speed": rt.speed, "comm": rt.core.comm,
            "seq": rt.latest["seq"] if rt.latest else None, "comm_loss_active": rt.comm_loss_active,
            "historian_rows_ring": len(rt.hist.ring), "source": rt.core.source}


# ---------------- external (MATLAB/Simulink) source -------------------------
class ExternalSnapshot(BaseModel):
    sim_time_s: float
    source_id: str = "matlab-01"
    model: str = "MATLAB/Simulink"
    model_version: str = "?"
    assets: dict
    facility: dict = {}


@app.post("/api/external/snapshot")
def external_snapshot(doc: ExternalSnapshot, x_dcx_role: str | None = Header(None)):
    need(x_dcx_role, "engineer")
    reg = asset_index()
    errors = []
    for aid, rec in doc.assets.items():
        if aid not in reg:
            errors.append(f"unknown asset {aid}")
            continue
        keys = {t["key"] for t in reg[aid]["tags"]}
        for k in rec.get("values", {}):
            if k not in keys:
                errors.append(f"{aid}: unknown data point '{k}'")
    if errors:
        raise HTTPException(422, {"errors": errors[:50]})
    rt = runtime()
    with rt.lock:
        rt.external_mode = True
        rt.external_last_wall = time.time()
        rt.core.ingest_external(doc.model_dump())
    return {"accepted": True, "assets": len(doc.assets)}


@app.get("/api/external/commands")
def external_commands(x_dcx_role: str | None = Header(None)):
    need(x_dcx_role, "engineer")
    rt = runtime()
    q, rt.external_cmd_queue = rt.external_cmd_queue, []
    return q


class ExternalAck(BaseModel):
    id: str
    accepted: bool
    reason: str = ""


@app.post("/api/external/commands/ack")
def external_ack(a: ExternalAck, x_dcx_role: str | None = Header(None)):
    need(x_dcx_role, "engineer")
    rec = runtime().commands.get(a.id)
    if not rec:
        raise HTTPException(404, "unknown command")
    rec.update(status="EXECUTED" if a.accepted else "REJECTED", reason=a.reason or rec["reason"])
    return rec


# ---------------- WebSocket stream -----------------------------------------
@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    await ws.accept()
    rt = runtime()
    rt.clients.add(ws)
    try:
        await ws.send_json({"type": "hello", "registry_version": rt.registry()["registry_version"],
                            "publish_hz": rt.publish_hz})
        if rt.latest and not rt.comm_loss_active:
            await ws.send_json({"type": "snapshot", "data": rt.latest})
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong", "t": msg.get("t"), "seq": rt.latest["seq"] if rt.latest else None})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        rt.clients.discard(ws)


# ---------------- maintenance work orders & health-aware policy ---------------------
from fastapi.responses import HTMLResponse  # noqa: E402
from .workorders import WorkOrderManager  # noqa: E402


@app.get("/api/workorders")
def workorders(status: str | None = None):
    rt = runtime()
    with rt.lock:
        items = rt.core.wo.listing()
    if status:
        items = [w for w in items if w["status"] == status.upper()]
    return {"open": sum(1 for w in items if w["status"] != "CLOSED"), "items": items}


@app.get("/api/workorders/{wo_id}")
def workorder(wo_id: str):
    rt = runtime()
    w = rt.core.wo.orders.get(wo_id)
    if w is None:
        raise HTTPException(404, f"unknown work order {wo_id}")
    return w


@app.get("/api/workorders/{wo_id}/cmms.json")
def workorder_cmms(wo_id: str):
    w = runtime().core.wo.orders.get(wo_id)
    if w is None:
        raise HTTPException(404, f"unknown work order {wo_id}")
    return JSONResponse(WorkOrderManager.cmms_json(w),
                        headers={"Content-Disposition": f'attachment; filename="{wo_id}.json"'})


@app.get("/api/workorders/{wo_id}/print", response_class=HTMLResponse)
def workorder_print(wo_id: str):
    w = runtime().core.wo.orders.get(wo_id)
    if w is None:
        raise HTTPException(404, f"unknown work order {wo_id}")
    return HTMLResponse(WorkOrderManager.html_page(w))


@app.post("/api/workorders/{wo_id}/{action}")
async def workorder_action(wo_id: str, action: str, request: Request,
                           x_dcx_role: str | None = Header(None), x_dcx_user: str | None = Header(None)):
    """action: ack | schedule | close. Closing records maintenance complete on the plant (engineer role)."""
    need(x_dcx_role, "engineer" if action == "close" else "operator")
    try:
        body = await request.json()
    except Exception:
        body = {}
    rt = runtime()
    with rt.lock:
        w = rt.core.wo.orders.get(wo_id)
        if w is None:
            raise HTTPException(404, f"unknown work order {wo_id}")
        user = x_dcx_user or "unknown"
        try:
            if action == "close":
                ok, msg = rt.core.plant.apply_command({"command": "maintenance_complete", "asset": w["asset"]})
                if not ok:
                    raise ValueError(msg)
            w = rt.core.wo.transition(wo_id, action, user, note=str(body.get("note", "")),
                                      scheduled_for=body.get("scheduled_for"), now_clock=rt.core.clock(rt.core.sim_time))
        except ValueError as e:
            raise HTTPException(409, str(e))
    return w


@app.get("/api/policy")
def policy_get():
    rt = runtime()
    with rt.lock:
        return {"health_aware_changeover": rt.core.ha_policy, "actions": rt.core.ha_actions[-20:],
                "replay": rt.core.plant.replay_status(), "speed": rt.speed, "sim_clock": rt.core.clock(rt.core.sim_time)}


@app.post("/api/policy")
async def policy_set(request: Request, x_dcx_role: str | None = Header(None)):
    need(x_dcx_role, "engineer")
    body = await request.json()
    rt = runtime()
    with rt.lock:
        for k in ("enabled", "hi_below", "rul_below_min"):
            if k in body:
                rt.core.ha_policy[k] = bool(body[k]) if k == "enabled" else float(body[k])
    return rt.core.ha_policy


# ---------------- frontend ------------------------------------------------------
if (FRONTEND / "dist").exists():
    app.mount("/dist", StaticFiles(directory=FRONTEND / "dist"), name="dist")
if (FRONTEND / "compare").exists():
    # controller comparison page (recorded MATLAB closed-loop runs, see matlab/control/dcx_demo_compare.m)
    app.mount("/compare", StaticFiles(directory=FRONTEND / "compare", html=True), name="compare")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")
