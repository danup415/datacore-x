"""Cross-verification of the DATACORE-X digital twin: physics consistency and all 17 what-if scenarios.

    python tests_e2e/verify_scenarios.py [--host http://localhost:8000] [--horizon 1800]

Part A - physical consistency of the live snapshot (and of every scenario's last frame):
  energy / power balances, unit relations and KPI definitions, using the twin's published
  (measured) values, so tolerances allow for sensor noise and dynamics.
Part B - each catalogue scenario S01..S17 is requested + approved through the REST API (the same
  path as the Ignition dashboard), run with clean_start=True (isolated, fault-free copy of the live
  state; the live plant is never changed) against a baseline, and checked for the cause -> effect
  it is meant to produce.
Writes docs/scenario_verification.md and docs/scenario_verification.json.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
HDR = {"X-DCX-Role": "engineer", "X-DCX-User": "verification"}
RHO_AIR, CP_AIR, CP_W = 1.2, 1.006, 4.186          # model constants (kg/m3, kJ/kgK, kJ/kgK)
RACKS = [f"R-{i:02d}" for i in range(1, 9)]
CRAHS = [f"CRAH-{i:02d}" for i in range(1, 5)]
PUMPS = ["P-01", "P-02", "P-03"]
CHILLERS = ["CH-01", "CH-02"]
TOWERS = ["CT-01", "CT-02"]


# ----------------------------------------------------------------- helpers
def v(fr, aid, key, default=float("nan")):
    x = fr["assets"].get(aid, {}).get("v", {}).get(key)
    return default if x is None else float(x)


def st(fr, aid):
    return str(fr["assets"].get(aid, {}).get("state", ""))


def rel_err(a, b):
    return abs(a - b) / max(abs(b), 1e-6)


class Checks:
    def __init__(self, scope):
        self.scope, self.rows = scope, []

    def add(self, name, ok, detail):
        self.rows.append({"scope": self.scope, "check": name, "pass": bool(ok), "detail": detail})
        return ok

    def rel(self, name, model, ref, tol, unit=""):
        e = rel_err(model, ref)
        return self.add(name, e <= tol, f"{model:.3f} vs {ref:.3f} {unit} (err {100 * e:.1f} %, tol {100 * tol:.0f} %)")

    def abs_(self, name, model, ref, tol, unit=""):
        e = abs(model - ref)
        return self.add(name, e <= tol, f"{model:.3f} vs {ref:.3f} {unit} (|err| {e:.3f}, tol {tol})")

    def cond(self, name, ok, detail):
        return self.add(name, ok, detail)


# ----------------------------------------------------------------- Part A: physics
def physics(fr, scope, skip=()):
    c = Checks(scope)
    F = fr["facility"]
    it = sum(v(fr, r, "power_kw") for r in RACKS)
    c.rel("IT load = sum of rack power", F["it_load_kw"], it, 0.03, "kW")
    for r in RACKS:
        c.abs_(f"{r} heat = electrical power", v(fr, r, "heat_kw"), v(fr, r, "power_kw"), 0.3, "kW")
    for r in RACKS:
        if r in skip:
            continue
        m = RHO_AIR * v(fr, r, "airflow_m3s")
        if m > 0.05:
            dT = v(fr, r, "heat_kw") / (m * CP_AIR)
            c.abs_(f"{r} outlet - inlet = Q/(m cp)", v(fr, r, "outlet_c") - v(fr, r, "inlet_c"), dT, 1.5, "K")
    for a in CRAHS:
        if st(fr, a) == "RUNNING" and v(fr, a, "airflow_m3s") > 0.2:
            q_air = RHO_AIR * v(fr, a, "airflow_m3s") * CP_AIR * (v(fr, a, "return_c") - v(fr, a, "supply_c"))
            c.rel(f"{a} coil duty = m cp (Tret - Tsup)", v(fr, a, "coil_kw"), q_air, 0.15, "kW")
    for p in PUMPS:
        if st(fr, p) == "RUNNING" and v(fr, p, "flow_ls") > 0.2:
            hyd = v(fr, p, "flow_ls") * v(fr, p, "head_kpa") / 1000 / max(v(fr, p, "eff_pct") / 100, 0.05)
            c.rel(f"{p} shaft power = q H / eta", v(fr, p, "power_kw"), hyd, 0.10, "kW")
    for ch in CHILLERS:
        if v(fr, ch, "load_kw") > 5 and v(fr, ch, "cop") > 0.5:
            c.rel(f"{ch} power = load / COP", v(fr, ch, "power_kw"), v(fr, ch, "load_kw") / v(fr, ch, "cop"), 0.06, "kW")
            c.cond(f"{ch} COP plausible (2-12)", 2 <= v(fr, ch, "cop") <= 12, f"COP {v(fr, ch, 'cop'):.2f}")
    p_cool = (sum(v(fr, ch, "power_kw") for ch in CHILLERS if v(fr, ch, "load_kw") > 0.5)
              + sum(v(fr, p, "power_kw") for p in PUMPS) + sum(v(fr, t, "fan_kw") for t in TOWERS)
              + sum(v(fr, a, "fan_kw") for a in CRAHS))
    cw_on = any(st(fr, t) == "RUNNING" for t in TOWERS)
    p_cool += 3.2 if cw_on else 0.0
    c.rel("cooling power = chillers + pumps + towers + CW pump + CRAH fans", F["cooling_power_kw"], p_cool, 0.08, "kW")
    light = 4.0 if F["facility_power_kw"] > F["it_load_kw"] + F["cooling_power_kw"] + F["elec_losses_kw"] + 2 else 0.0
    c.rel("facility power = IT + cooling + losses + lighting", F["facility_power_kw"],
          F["it_load_kw"] + F["cooling_power_kw"] + F["elec_losses_kw"] + light, 0.02, "kW")
    if F["it_load_kw"] > 1:
        c.rel("PUE = facility / IT", F["pue"], F["facility_power_kw"] / F["it_load_kw"], 0.01)
        c.cond("PUE plausible (1.0-2.5)", 1.0 <= F["pue"] <= 2.5, f"PUE {F['pue']:.3f}")
    if "max_inlet" not in skip:
        c.abs_("max inlet = max rack inlet", F["max_inlet_c"], max(v(fr, r, "inlet_c") for r in RACKS), 0.4, "°C")
    q = v(fr, "PIPE-CHWS", "flow_ls")
    if q > 0.5:
        q_chw = CP_W * q * (F["chwr_c"] - F["chws_c"])
        q_plant = sum(v(fr, ch, "load_kw") for ch in CHILLERS) + v(fr, "HX-01", "duty_kw", 0.0)
        c.rel("CHW plant duty = rho cp q (Tr - Ts)", q_plant, q_chw, 0.15, "kW")
        coils = sum(v(fr, a, "coil_kw") for a in CRAHS)
        c.rel("CRAH coil duty = CHW plant duty (quasi-steady)", coils, q_plant, 0.20, "kW")
    pdu = v(fr, "PDU-A", "load_kw") + v(fr, "PDU-B", "load_kw")
    if F["it_load_kw"] > 1:
        c.rel("PDU A + B load = IT load", pdu, F["it_load_kw"], 0.05, "kW")
    for t in TOWERS:
        if st(fr, t) == "RUNNING":
            c.cond(f"{t} approach plausible (0.5-10 K)", 0.5 <= v(fr, t, "approach_k") <= 10, f"{v(fr, t, 'approach_k'):.2f} K")
    temps = [v(fr, r, k) for r in RACKS for k in ("inlet_c", "outlet_c")] + [F["chws_c"], F["chwr_c"]]
    c.cond("all key temperatures finite and in 5-60 °C", all(5 <= x <= 60 for x in temps if not math.isnan(x)) and
           not any(math.isnan(x) for x in temps), f"min {min(temps):.1f}, max {max(temps):.1f} °C")
    return c.rows


# ----------------------------------------------------------------- Part B: scenario expectations
def seq(frames, fn):
    return [fn(f) for f in frames]


def expect(sid, B, S, P):
    """B, S: baseline / scenario frame lists. Returns check rows."""
    c = Checks(sid)
    b1, s1 = B[-1], S[-1]
    if sid == "S01":
        c.cond("IT load increased (>= +20 % at end)", s1["facility"]["it_load_kw"] >= 1.2 * b1["facility"]["it_load_kw"],
               f"{b1['facility']['it_load_kw']:.1f} -> {s1['facility']['it_load_kw']:.1f} kW")
        c.cond("cooling power increased", s1["facility"]["cooling_power_kw"] > b1["facility"]["cooling_power_kw"],
               f"{b1['facility']['cooling_power_kw']:.1f} -> {s1['facility']['cooling_power_kw']:.1f} kW")
        c.cond("facility power increased by more than IT increase x 1.0",
               (s1["facility"]["facility_power_kw"] - b1["facility"]["facility_power_kw"]) >=
               (s1["facility"]["it_load_kw"] - b1["facility"]["it_load_kw"]),
               f"dFac {s1['facility']['facility_power_kw'] - b1['facility']['facility_power_kw']:.1f} kW vs "
               f"dIT {s1['facility']['it_load_kw'] - b1['facility']['it_load_kw']:.1f} kW")
    elif sid == "S02":
        r = P["rack"]
        c.abs_(f"{r} power +{P['extra_kw']:.0f} kW", v(s1, r, "power_kw") - v(b1, r, "power_kw"), P["extra_kw"], 1.5, "kW")
        c.cond(f"{r} inlet rises (recirculation)", v(s1, r, "inlet_c") - v(b1, r, "inlet_c") >= 0.5,
               f"{v(b1, r, 'inlet_c'):.2f} -> {v(s1, r, 'inlet_c'):.2f} °C")
        c.cond(f"{r} outlet rises", v(s1, r, "outlet_c") > v(b1, r, "outlet_c") + 1,
               f"{v(b1, r, 'outlet_c'):.2f} -> {v(s1, r, 'outlet_c'):.2f} °C")
    elif sid == "S03":
        p = P["pump"]
        c.abs_(f"{p} efficiency drop ~{P['drop_pct']:.0f} %", 1 - v(s1, p, "eff_pct") / max(v(b1, p, "eff_pct"), 1e-6), P["drop_pct"] / 100, 0.05)
        c.cond(f"{p} power increases", v(s1, p, "power_kw") > v(b1, p, "power_kw") * 1.1,
               f"{v(b1, p, 'power_kw'):.2f} -> {v(s1, p, 'power_kw'):.2f} kW")
        c.abs_("loop flow essentially unchanged", v(s1, "PIPE-CHWS", "flow_ls"), v(b1, "PIPE-CHWS", "flow_ls"), 0.4, "L/s")
    elif sid == "S04":
        p = P["pump"]
        c.cond(f"{p} vibration increases (broadband)", v(s1, p, "vib_mms") >= v(b1, p, "vib_mms") + 1.0,
               f"{v(b1, p, 'vib_mms'):.2f} -> {v(s1, p, 'vib_mms'):.2f} mm/s")
        c.cond(f"{p} delivered flow reduced (head loss)", v(s1, p, "flow_ls") < v(b1, p, "flow_ls") - 0.05,
               f"{v(b1, p, 'flow_ls'):.2f} -> {v(s1, p, 'flow_ls'):.2f} L/s")
    elif sid == "S05":
        a = P["crah"]
        c.cond(f"{a} tripped / stopped", st(s1, a) != "RUNNING" and v(s1, a, "fan_kw") < 0.05,
               f"state {st(s1, a)}, fan {v(s1, a, 'fan_kw'):.2f} kW")
        others = [x for x in CRAHS if x != a]
        fb = sum(v(b1, x, "fan_speed_pct") for x in others) / 3
        fs = sum(v(s1, x, "fan_speed_pct") for x in others) / 3
        c.cond("remaining CRAH fans speed up", fs > fb + 2, f"{fb:.1f} -> {fs:.1f} %")
        c.cond("max rack inlet held at/below 27 °C by the fan-trim loop", s1["facility"]["max_inlet_c"] <= 27.0,
               f"{b1['facility']['max_inlet_c']:.2f} -> {s1['facility']['max_inlet_c']:.2f} °C")
        c.rel("remaining coils absorb the duty", sum(v(s1, x, "coil_kw") for x in others),
              sum(v(b1, x, "coil_kw") for x in CRAHS), 0.15, "kW")
    elif sid == "S06":
        ch = P["chiller"]
        if v(b1, ch, "load_kw") > 5:
            ratio = v(s1, ch, "cop") / v(b1, ch, "cop")
            c.cond(f"{ch} COP reduced (severity {P['severity']} -> expected about -{30 * P['severity']:.0f} %)",
                   ratio <= 1 - 0.30 * P["severity"] * 0.6, f"COP {v(b1, ch, 'cop'):.2f} -> {v(s1, ch, 'cop'):.2f} ({100 * (ratio - 1):.0f} %)")
            c.cond("chiller electrical power increases", v(s1, ch, "power_kw") > v(b1, ch, "power_kw"),
                   f"{v(b1, ch, 'power_kw'):.2f} -> {v(s1, ch, 'power_kw'):.2f} kW")
        else:
            c.cond(f"{ch} not loaded in this window (check not applicable)", True, "chiller idle")
    elif sid == "S07":
        src = seq(S, lambda f: v(f, "SWG-01", "source_code"))
        c.cond("utility lost -> bus on generator at some point", 2 in [round(x) for x in src], f"source codes seen {sorted(set(round(x) for x in src))}")
        c.cond("generator ran", any(st(f, "GEN-01") == "RUNNING" for f in S), "GEN-01 RUNNING seen")
        soc = seq(S, lambda f: min(v(f, "BAT-A", "soc_pct"), v(f, "BAT-B", "soc_pct")))
        c.cond("UPS batteries rode through the gap (SoC dipped)", min(soc) < 100 - 0.1, f"min SoC {min(soc):.1f} %")
        it_s = seq(S, lambda f: f["facility"]["it_load_kw"])
        c.cond("IT load never interrupted", min(it_s) > 0.5 * max(it_s), f"min IT {min(it_s):.1f} kW")
        c.cond("utility restored and retransferred by end", round(src[-1]) == 1, f"end source {src[-1]:.0f}")
    elif sid == "S08":
        soc = seq(S, lambda f: min(v(f, "BAT-A", "soc_pct"), v(f, "BAT-B", "soc_pct")))
        socb = seq(B, lambda f: min(v(f, "BAT-A", "soc_pct"), v(f, "BAT-B", "soc_pct")))
        c.cond("batteries discharge", min(soc) < min(socb) - 2, f"min SoC {min(socb):.1f} -> {min(soc):.1f} %")
        c.cond("UPS reported in battery mode", any("BATT" in st(f, "UPS-A").upper() or "BATT" in st(f, "UPS-B").upper() for f in S),
               "UPS state BATTERY seen")
        it_s = seq(S, lambda f: f["facility"]["it_load_kw"])
        c.cond("IT load maintained", min(it_s) > 0.5 * max(it_s), f"min IT {min(it_s):.1f} kW")
    elif sid == "S09":
        b = P["battery"]
        c.cond(f"{b} state of health reduced", v(s1, b, "soh_pct") < v(b1, b, "soh_pct") - 10,
               f"SoH {v(b1, b, 'soh_pct'):.1f} -> {v(s1, b, 'soh_pct'):.1f} %")
        c.cond(f"{b} internal resistance increased", v(s1, b, "rint_mohm") > v(b1, b, "rint_mohm"),
               f"{v(b1, b, 'rint_mohm'):.1f} -> {v(s1, b, 'rint_mohm'):.1f} mOhm")
        soc = seq(S, lambda f: v(f, b, "soc_pct"))
        c.cond("discharge test drew the battery down", min(soc) < 99, f"min SoC {min(soc):.1f} %")
    elif sid == "S10":
        c.rel("total IT load unchanged (placement only)", s1["facility"]["it_load_kw"], b1["facility"]["it_load_kw"], 0.05, "kW")
        w = {"concentrate_row_a": ["R-01", "R-02", "R-03", "R-04"], "concentrate_edges": ["R-01", "R-04", "R-05", "R-08"],
             "spread_even": []}[P["strategy"]]
        if w:
            up = sum(v(s1, r, "power_kw") for r in w) / max(sum(v(b1, r, "power_kw") for r in w), 1e-6)
            c.cond(f"load moved onto {', '.join(w)}", up > 1.3, f"x{up:.2f}")
    elif sid == "S11":
        p = P["pump"]
        vmax = max(v(f, p, "vib_mms", 0.0) for f in S)          # peak while running (it may be changed over)
        c.cond(f"{p} vibration grows (bearing)", vmax >= v(b1, p, "vib_mms") + 2,
               f"{v(b1, p, 'vib_mms'):.2f} -> peak {vmax:.2f} mm/s")
        hi_s = s1["assets"][p].get("health", {}).get("hi")
        hi_b = b1["assets"][p].get("health", {}).get("hi")
        c.cond(f"{p} health index degrades", hi_s is not None and hi_b is not None and hi_s < hi_b - 20, f"HI {hi_b} -> {hi_s}")
    elif sid == "S12":
        c.cond("HX effectiveness reduced", v(s1, "HX-01", "effectiveness_pct") < v(b1, "HX-01", "effectiveness_pct") - 5,
               f"{v(b1, 'HX-01', 'effectiveness_pct'):.1f} -> {v(s1, 'HX-01', 'effectiveness_pct'):.1f} %")
        lb = sum(v(b1, ch, "load_kw") for ch in CHILLERS)
        ls = sum(v(s1, ch, "load_kw") for ch in CHILLERS)
        c.cond("load shifts from economiser to chillers", ls > lb, f"chiller load {lb:.1f} -> {ls:.1f} kW")
    elif sid == "S13":
        t = P["tower"]
        c.cond(f"{t} approach increases", v(s1, t, "approach_k") > v(b1, t, "approach_k") + 0.3,
               f"{v(b1, t, 'approach_k'):.2f} -> {v(s1, t, 'approach_k'):.2f} K")
    elif sid == "S14":
        r = P["rack"]
        c.abs_(f"{r} measured inlet biased by +{P['bias_k']:.0f} K", v(s1, r, "inlet_c") - v(b1, r, "inlet_c"), P["bias_k"], 0.8, "K")
        c.abs_(f"{r} outlet (physical) unchanged", v(s1, r, "outlet_c"), v(b1, r, "outlet_c"), 0.6, "°C")
        c.abs_("facility max inlet (true temperature) unchanged", s1["facility"]["max_inlet_c"], b1["facility"]["max_inlet_c"], 0.4, "°C")
        others = [x for x in RACKS if x != r]
        c.cond("other racks unaffected", max(abs(v(s1, x, "inlet_c") - v(b1, x, "inlet_c")) for x in others) < 0.5,
               "max |dT| over other racks < 0.5 K")
    elif sid == "S15":
        a = P["crah"]
        spd = v(s1, a, "fan_speed_pct") / 100
        exp_dv = 6.0 * P["severity"] * spd ** 2          # model: imbalance term 6 * sev * s^2 (mm/s)
        c.abs_(f"{a} vibration rise = 6 x severity x speed^2 (1x imbalance, speed {100 * spd:.0f} %)",
               v(s1, a, "vib_mms") - v(b1, a, "vib_mms"), exp_dv, max(0.3, 0.3 * exp_dv), "mm/s")
        c.cond(f"{a} vibration grows", v(s1, a, "vib_mms") > v(b1, a, "vib_mms") + 0.5 * exp_dv,
               f"{v(b1, a, 'vib_mms'):.2f} -> {v(s1, a, 'vib_mms'):.2f} mm/s")
        c.abs_("airflow / thermal unaffected", s1["facility"]["max_inlet_c"], b1["facility"]["max_inlet_c"], 0.4, "°C")
    elif sid == "S17":
        p = P["pump"]
        c.cond("data source labelled as replayed measured data", "replay" in str(s1.get("source", {}).get("type", "")),
               str(s1.get("source", {}).get("type")))
        vmax = max(v(f, p, "vib_mms", 0.0) for f in S)
        c.cond(f"{p} vibration follows the measured bearing record upward", vmax >= v(b1, p, "vib_mms") + 2,
               f"{v(b1, p, 'vib_mms'):.2f} -> peak {vmax:.2f} mm/s")
        hmin = min((f["assets"][p].get("health", {}).get("hi") or 100) for f in S)
        c.cond(f"{p} health index degrades", hmin < 70, f"min HI {hmin}")
        n_run_b = sum(st(b1, x) == "RUNNING" for x in PUMPS)
        n_run_s = sum(st(s1, x) == "RUNNING" for x in PUMPS)
        c.cond("health-aware changeover before the recorded failure (no trip)",
               "TRIP" not in st(s1, p).upper() and st(s1, p) != "RUNNING" and n_run_s == n_run_b,
               f"{p} {st(s1, p)}, running pumps {n_run_b} -> {n_run_s}")
        c.cond("maintenance work order raised", (s1.get("workorders") or {}).get("open", 0) >= 1,
               f"open work orders {(s1.get('workorders') or {}).get('open')}")
        c.cond("no thermal excursion", s1["facility"]["max_inlet_c"] <= 27, f"max inlet {s1['facility']['max_inlet_c']:.2f} °C")
    elif sid == "S16":
        p = P["pump"]
        c.cond(f"{p} tripped", "TRIP" in st(s1, p).upper() and v(s1, p, "flow_ls") < 0.05, f"state {st(s1, p)}, flow {v(s1, p, 'flow_ls'):.2f}")
        n_run_b = sum(st(b1, x) == "RUNNING" for x in PUMPS)
        n_run_s = sum(st(s1, x) == "RUNNING" for x in PUMPS)
        c.cond("standby pump started (redundancy restored)", n_run_s == n_run_b, f"running pumps {n_run_b} -> {n_run_s}")
        c.rel("loop flow restored", v(s1, "PIPE-CHWS", "flow_ls"), v(b1, "PIPE-CHWS", "flow_ls"), 0.10, "L/s")
        c.cond("no thermal excursion", s1["facility"]["max_inlet_c"] <= 27, f"max inlet {s1['facility']['max_inlet_c']:.2f} °C")
    # isolation: the baseline branch must not carry this scenario's injected faults
    c.cond("baseline branch free of this scenario's faults",
           not any(sid in f.get("id", f.get("fault_id", "")) for f in b1.get("faults_injected", [])), "isolation")
    return c.rows


# ----------------------------------------------------------------- runner
def run_one(cl, sid, horizon, params=None):
    r = cl.post("/api/scenarios/requests", json={"scenario_id": sid, "params": params or {}, "horizon_s": horizon, "clean_start": True}, headers=HDR)
    r.raise_for_status()
    req = r.json()
    a = cl.post(f"/api/scenarios/requests/{req['request_id']}/approve", headers=HDR)
    a.raise_for_status()
    rid = a.json()["run_id"]
    t0 = time.time()
    while True:
        x = cl.get(f"/api/scenarios/runs/{rid}").json()
        if x["status"] in ("COMPLETED", "FAILED"):
            break
        if time.time() - t0 > 600:
            raise TimeoutError(rid)
        time.sleep(1)
    if x["status"] == "FAILED":
        return req, rid, None, x.get("error")
    full = cl.get(f"/api/scenarios/runs/{rid}", params={"frames": "true"}).json()
    return req, rid, full["result"], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:8000")
    ap.add_argument("--horizon", type=float, default=1800)
    a = ap.parse_args()
    cl = httpx.Client(base_url=a.host, timeout=60)
    rows, summary = [], []
    live = cl.get("/api/snapshot").json()
    rows += physics(live, "LIVE")
    cat = cl.get("/api/scenarios").json()
    # target equipment that is actually on duty in the live plant (duty/standby rotates)
    duty_pump = next((p for p in PUMPS if st(live, p) == "RUNNING"), "P-01")
    lead_ch = max(CHILLERS, key=lambda ch: v(live, ch, "load_kw", 0.0))
    over = {"S03": {"pump": duty_pump}, "S04": {"pump": duty_pump}, "S11": {"pump": duty_pump},
            "S16": {"pump": duty_pump}, "S06": {"chiller": lead_ch},
            "S17": {"pump": duty_pump, "compress": 20}}
    print(f"duty pump {duty_pump}, lead chiller {lead_ch}", flush=True)
    for s in cat:
        sid = s["id"]
        t0 = time.time()
        req, rid, res, err = run_one(cl, sid, a.horizon, over.get(sid))
        if res is None:
            rows.append({"scope": sid, "check": "run completed", "pass": False, "detail": str(err)})
            summary.append({"id": sid, "title": s["title"], "run": rid, "pass": 0, "total": 1})
            continue
        B, S = res["frames"]["baseline"], res["frames"]["scenario"]
        sr = expect(sid, B, S, req["params"])
        skip = []
        if sid == "S14":
            skip = [req["params"]["rack"], "max_inlet"]     # measured inlet is deliberately biased
        sr += [dict(x, scope=f"{sid}/physics") for x in physics(S[-1], sid, skip=skip)]
        rows += sr
        summary.append({"id": sid, "title": s["title"], "run": rid, "params": req["params"],
                        "pass": sum(x["pass"] for x in sr), "total": len(sr), "wall_s": round(time.time() - t0, 1)})
        print(f"{sid} {s['title'][:40]:40s} {summary[-1]['pass']}/{summary[-1]['total']}", flush=True)
    npass, ntot = sum(r["pass"] for r in rows), len(rows)
    out = ROOT / "docs"
    (out / "scenario_verification.json").write_text(json.dumps({"summary": summary, "checks": rows,
                                                                "horizon_s": a.horizon, "pass": npass, "total": ntot}, indent=1))
    L = [f"# DATACORE-X scenario and physics cross-verification\n",
         f"Generated {time.strftime('%Y-%m-%d %H:%M')} against {a.host}; horizon {a.horizon:.0f} s per what-if; "
         f"values are the twin's published (measured) values.\n",
         f"**Result: {npass}/{ntot} checks pass.**\n",
         "## Scenarios\n", "| ID | Scenario | Parameters (defaults) | Checks passed |", "|---|---|---|---|"]
    for s in summary:
        L.append(f"| {s['id']} | {s['title']} | {json.dumps(s.get('params', {}))} | {s['pass']}/{s['total']} |")
    live_rows = [r for r in rows if r["scope"] == "LIVE"]
    L += ["", f"## Live twin physics ({sum(r['pass'] for r in live_rows)}/{len(live_rows)})", "",
          "| Check | Result | Detail |", "|---|---|---|"]
    L += [f"| {r['check']} | {'pass' if r['pass'] else '**FAIL**'} | {r['detail']} |" for r in live_rows]
    L += ["", "## Scenario checks", "", "| Scope | Check | Result | Detail |", "|---|---|---|---|"]
    L += [f"| {r['scope']} | {r['check']} | {'pass' if r['pass'] else '**FAIL**'} | {r['detail']} |"
          for r in rows if r["scope"] != "LIVE"]
    (out / "scenario_verification.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"TOTAL {npass}/{ntot}")
    fails = [r for r in rows if not r["pass"]]
    for r in fails:
        print("FAIL", r["scope"], "|", r["check"], "|", r["detail"])


if __name__ == "__main__":
    main()
