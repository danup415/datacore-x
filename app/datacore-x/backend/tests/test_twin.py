"""Backend validation suite (pytest).  Run from ./backend:  python -m pytest -q"""
import json
import math

import pytest
from fastapi.testclient import TestClient

from datacorex.core import TwinCore
from datacorex.registry import asset_index, assets, registry_document
from datacorex.scenarios import CATALOGUE, apply_scenario, resolve_params, run_isolated


@pytest.fixture(scope="module")
def warm():
    c = TwinCore(seed=7)
    c.advance(900)
    return c


def test_registry_unique_ids_and_units():
    ids = [a["id"] for a in assets()]
    assert len(ids) == len(set(ids))
    for a in assets():
        for t in a["tags"]:
            assert t["unit"], f"{a['id']}.{t['key']} has no unit"
            assert t["opc_node"].endswith(f"{a['id']}.{t['key']}")
        if a["parent"]:
            assert a["parent"] in asset_index()


def test_snapshot_covers_every_registry_point(warm):
    s = warm.snapshot()
    for a in assets():
        if not a["tags"]:
            continue
        assert a["id"] in s["assets"], a["id"]
        for t in a["tags"]:
            assert t["key"] in s["assets"][a["id"]]["v"], (a["id"], t["key"])
    assert s["schema"] == "dcx.snapshot/1" and s["seq"] >= 1
    json.dumps(s)  # serialisable


def test_steady_state_physically_plausible(warm):
    f = warm.plant.truth()["_facility"]
    assert 80 <= f["it_load_kw"] <= 120
    assert 1.1 < f["pue"] < 1.5
    assert 22 < f["max_inlet_c"] < 27
    assert abs(f["chws_c"] - warm.plant.sp["chws_c"]) < 0.5
    # energy balance: coil duty ~ IT heat (+fan heat & envelope, steady)
    assert abs(f["_coil_kw"] - f["it_load_kw"]) / f["it_load_kw"] < 0.25


def test_healthy_baseline_has_no_detected_faults(warm):
    s = warm.snapshot()
    det = [a for a, v in s["assets"].items() if v.get("health", {}).get("fault_code")]
    assert det == []


@pytest.mark.parametrize("sid,asset,code", [
    ("S11", "P-01", "F01"), ("S04", "P-01", "F02"), ("S06", "CH-01", "F06"), ("S12", "HX-01", "F05"),
    ("S13", "CT-01", "F07"), ("S09", "BAT-A", "F08"), ("S15", "CRAH-01", "F03"), ("S16", "P-01", "F10"),
])
def test_fault_detection_and_isolation(warm, sid, asset, code):
    r = run_isolated(warm, sid, resolve_params(sid, {}), 1800)
    end = r["frames"]["scenario"][-1]["assets"]
    assert end[asset]["health"]["fault_code"] == code
    others = [a for a, v in end.items() if a != asset and v.get("health", {}).get("fault_code") not in (None, "F10")]
    assert others == [], f"false positives {others}"


def test_sensor_drift_flagged_by_twin_residual(warm):
    r = run_isolated(warm, "S14", resolve_params("S14", {}), 900)
    assert "drift" in r["frames"]["scenario"][-1]["assets"]["R-03"]["diag"]["finding"]


def test_pump_trip_triggers_standby(warm):
    r = run_isolated(warm, "S16", resolve_params("S16", {}), 300)
    end = r["frames"]["scenario"][-1]["assets"]
    assert end["P-01"]["state"] == "TRIPPED" and end["P-03"]["state"] == "RUNNING"


def test_utility_failure_propagation(warm):
    r = run_isolated(warm, "S07", resolve_params("S07", {}), 1200)
    fr = r["frames"]["scenario"]
    states = {f["assets"]["SWG-01"]["state"] for f in fr}
    assert {"ON_GENERATOR", "ON_UTILITY"} <= states
    assert r["kpi_scenario"]["peak_max_inlet_c"] > r["kpi_baseline"]["peak_max_inlet_c"] + 2
    assert r["kpi_scenario"]["it_energy_kwh"] == pytest.approx(r["kpi_baseline"]["it_energy_kwh"], rel=0.02)  # no IT outage


def test_whatif_isolated_from_live(warm):
    before = (warm.plant.t, len(warm.plant.faults), warm.seq)
    run_isolated(warm, "S07", resolve_params("S07", {}), 300)
    assert (warm.plant.t, len(warm.plant.faults)) == before[:2]


def test_reproducible(warm):
    a = run_isolated(warm, "S01", resolve_params("S01", {}), 600)
    b = run_isolated(warm, "S01", resolve_params("S01", {}), 600)
    assert a["kpi_scenario"] == b["kpi_scenario"]


def test_rul_reported_with_bounds_when_degrading(warm):
    c = warm.clone()
    from datacorex.scenarios import apply_scenario
    apply_scenario(c, "S03", resolve_params("S03", {"ramp_s": 1800, "drop_pct": 40}))
    c.advance(1500)
    h = c.snapshot()["assets"]["P-01"]["health"]
    assert h["rul_h"] is not None and h["rul_lo_h"] <= h["rul_h"] <= h["rul_hi_h"]


def test_param_validation():
    with pytest.raises(ValueError):
        resolve_params("S07", {"duration_s": 99999})
    with pytest.raises(ValueError):
        resolve_params("S02", {"rack": "R-99"})


# ---------------- API -------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    from datacorex.api import app
    with TestClient(app) as c:
        yield c


def test_api_registry_tags_historian_consistent(client):
    reg = client.get("/api/registry").json()
    assert len(reg["assets"]) == len(assets())
    tags = client.get("/api/tags").json()
    rec = client.get(f"/api/historian/{tags['seq']}").json()["measured"]
    for a in assets():
        for t in a["tags"]:
            assert tags["tags"][t["path"]]["v"] == rec["assets"][a["id"]]["v"][t["key"]]


def test_api_command_roles_interlocks_and_ack(client):
    r = client.post("/api/commands", json={"command": "set_setpoint", "name": "chws_c", "value": 17},
                    headers={"X-DCX-Role": "operator"}).json()
    assert r["status"] == "REJECTED" and "requires engineer" in r["reason"]
    r = client.post("/api/commands", json={"command": "set_setpoint", "name": "chws_c", "value": 99},
                    headers={"X-DCX-Role": "engineer"}).json()
    assert r["status"] == "REJECTED"
    r = client.post("/api/commands", json={"command": "pump_start", "asset": "P-03"},
                    headers={"X-DCX-Role": "operator"}).json()
    assert r["status"] == "ACCEPTED"
    import time
    for _ in range(30):
        if client.get(f"/api/commands/{r['id']}").json()["status"] == "EXECUTED":
            break
        time.sleep(0.2)
    assert client.get(f"/api/commands/{r['id']}").json()["status"] == "EXECUTED"


def test_api_scenario_requires_approval(client):
    assert client.post("/api/scenarios/requests", json={"scenario_id": "S05"}).status_code == 403
    req = client.post("/api/scenarios/requests", json={"scenario_id": "S05", "horizon_s": 300},
                      headers={"X-DCX-Role": "operator"}).json()
    assert req["status"] == "PENDING_APPROVAL"
    ap = client.post(f"/api/scenarios/requests/{req['request_id']}/approve", headers={"X-DCX-Role": "operator"}).json()
    import time
    for _ in range(100):
        run = client.get(f"/api/scenarios/runs/{ap['run_id']}").json()
        if run["status"] == "COMPLETED":
            break
        time.sleep(0.1)
    assert run["status"] == "COMPLETED"
    assert any(c["key"] == "peak_max_inlet_c" for c in run["result"]["comparison"])
    # double approval rejected
    assert client.post(f"/api/scenarios/requests/{req['request_id']}/approve", headers={"X-DCX-Role": "operator"}).status_code == 409


def test_api_external_snapshot_validation(client):
    bad = client.post("/api/external/snapshot", json={"sim_time_s": 1, "assets": {"R-99": {"values": {}}}},
                      headers={"X-DCX-Role": "engineer"})
    assert bad.status_code == 422


def test_websocket_stream(client):
    with client.websocket_connect("/ws/stream") as ws:
        assert ws.receive_json()["type"] == "hello"
        m = ws.receive_json()
        assert m["type"] == "snapshot" and "assets" in m["data"]
        ws.send_json({"type": "ping", "t": 1})
        for _ in range(5):
            x = ws.receive_json()
            if x["type"] == "pong":
                break
        assert x["type"] == "pong"


# ---------------- measured-data replay, health-aware changeover, work orders -------------
def _replay_core(policy=True):
    from datacorex.core import TwinCore
    c = TwinCore(seed=7)
    c.advance(600)
    c.ha_policy["enabled"] = policy
    apply_scenario(c, "S17", resolve_params("S17", {}), tag=":t")
    return c


def test_replay_without_action_reaches_recorded_failure():
    c = _replay_core(policy=False)
    c.advance(80 * 60)
    assert c.snapshot()["assets"]["P-01"]["state"] == "TRIPPED"
    assert any("end of replayed run-to-failure record" in e["text"] for e in c.plant.events)


def test_replay_health_aware_changeover_avoids_trip_and_raises_work_order():
    c = _replay_core(policy=True)
    c.advance(80 * 60)
    s = c.snapshot()
    assert s["assets"]["P-01"]["state"] != "TRIPPED"
    assert c.ha_actions and c.ha_actions[0]["asset"] == "P-01"
    assert s["source"]["type"].endswith("+ replay") and s["replay"][0]["life_frac"] < 1.0
    w = c.wo.listing()[0]
    assert w["asset"] == "P-01" and w["fault_code"] == "F01" and w["priority"].startswith("P1")
    assert w["control_actions"] and "Replayed measured data" in w["evidence"]["data_source"]


def test_work_order_lifecycle_and_close_returns_asset():
    c = _replay_core(policy=True)
    c.advance(80 * 60)
    w = c.wo.listing()[0]
    with pytest.raises(ValueError):
        c.wo.transition(w["wo_id"], "bogus", "t")
    c.wo.transition(w["wo_id"], "ack", "t")
    c.wo.transition(w["wo_id"], "schedule", "t", scheduled_for="tomorrow")
    ok, _ = c.plant.apply_command({"command": "maintenance_complete", "asset": "P-01"})
    c.wo.transition(w["wo_id"], "close", "t")
    assert ok and w["status"] == "CLOSED" and not c.plant.replay_status()
    with pytest.raises(ValueError):
        c.wo.transition(w["wo_id"], "ack", "t")
    j = c.wo.cmms_json(w)
    assert j["workOrderNumber"] == w["wo_id"] and j["tasks"] and "<html>" in c.wo.html_page(w)


def test_healthy_plant_raises_no_work_orders(warm):
    assert not warm.wo.listing()
