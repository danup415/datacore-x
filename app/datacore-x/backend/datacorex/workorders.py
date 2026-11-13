"""Maintenance work orders raised from the asset intelligence layer (alarm -> action).

A work order is opened automatically when an asset's Health Index falls below an advisory level
or its remaining-useful-life estimate becomes short, and it is updated while it stays open.
It carries what a maintenance planner needs: the asset and its criticality, the likely fault and
the evidence, HI and RUL with their uncertainty, recommended actions and parts, a due date
(the lower RUL bound minus a safety margin), and any action the control system already took.

Lifecycle (with an audit trail): OPEN -> ACKNOWLEDGED -> SCHEDULED -> CLOSED.
Closing records 'maintenance complete' on the plant, which clears the fault and returns the
asset to service. Export: CMMS-style JSON and a printable HTML page (save as PDF from the browser).
"""
from __future__ import annotations

import datetime as _dt
import html
import time

PRIORITY_RULES = (  # (name, hi_below, rul_below_h)
    ("P1 - Urgent", 25.0, 0.5),
    ("P2 - High", 45.0, 2.0),
    ("P3 - Planned", 65.0, None),
)
SAFETY_MARGIN = 0.2          # due = now + (1 - margin) * lower RUL bound
ADVISORY_DUE_H = 24.0        # due date when no RUL trend exists yet (simulation hours)

ACTIONS = {
    "F01": {"title": "Pump bearing degradation",
            "actions": ["Isolate the pump (changeover to standby) if not already done",
                        "Replace both motor-side and pump-side bearings; inspect seats for fretting",
                        "Check lubrication (grease type, quantity, contamination) and shaft alignment",
                        "Vibration acceptance test after repair: velocity below ISO 10816 zone B"],
            "parts": ["Bearing set (drive end + non-drive end)", "Grease cartridge", "Mechanical seal kit (if disturbed)"],
            "hours": 4.0, "trade": "Mechanical fitter"},
    "F02": {"title": "Pump cavitation",
            "actions": ["Check suction pressure / NPSH available and strainer differential pressure",
                        "Check expansion vessel pre-charge and system fill pressure",
                        "Inspect impeller for cavitation erosion"],
            "parts": ["Strainer element"], "hours": 2.0, "trade": "Mechanical fitter"},
    "PUMP_EFF": {"title": "Pump hydraulic efficiency loss",
                 "actions": ["Inspect impeller and wear rings for wear / internal recirculation",
                             "Re-baseline pump curve after repair"],
                 "parts": ["Wear ring set"], "hours": 3.0, "trade": "Mechanical fitter"},
    "F03": {"title": "Fan imbalance", "actions": ["Clean impeller blades", "Dynamic balancing in situ"],
            "parts": ["Balance weights"], "hours": 2.0, "trade": "HVAC technician"},
    "F04": {"title": "Fan bearing degradation", "actions": ["Replace fan motor bearings", "Check belt tension / alignment"],
            "parts": ["Fan bearing set"], "hours": 3.0, "trade": "HVAC technician"},
    "CRAH_BLOCK": {"title": "Filter / coil blockage", "actions": ["Replace filters", "Clean coil face"],
                   "parts": ["Filter set"], "hours": 1.0, "trade": "HVAC technician"},
    "F06": {"title": "Chiller performance degradation",
            "actions": ["Check refrigerant charge and superheat/subcooling", "Inspect condenser tubes for fouling",
                        "Transfer lead to the standby chiller until repaired"],
            "parts": ["Refrigerant (as required)"], "hours": 6.0, "trade": "Refrigeration engineer"},
}
DEFAULT_ACTION = {"title": "Condition deviation", "actions": ["Inspect asset; review trend data with reliability engineer"],
                  "parts": [], "hours": 1.0, "trade": "Reliability engineer"}
REDUNDANT = {"P-01": ("P-01", "P-02", "P-03"), "P-02": ("P-01", "P-02", "P-03"), "P-03": ("P-01", "P-02", "P-03"),
             "CH-01": ("CH-01", "CH-02"), "CH-02": ("CH-01", "CH-02"),
             "CRAH-01": ("CRAH-01", "CRAH-02", "CRAH-03", "CRAH-04"), "CRAH-02": ("CRAH-01", "CRAH-02", "CRAH-03", "CRAH-04"),
             "CRAH-03": ("CRAH-01", "CRAH-02", "CRAH-03", "CRAH-04"), "CRAH-04": ("CRAH-01", "CRAH-02", "CRAH-03", "CRAH-04")}


def _priority(hi, rul_lo_h):
    for name, hi_b, rul_b in PRIORITY_RULES:
        if hi < hi_b or (rul_b is not None and rul_lo_h is not None and rul_lo_h < rul_b):
            return name
    return None


class WorkOrderManager:
    def __init__(self, clock):
        self.clock = clock              # callable: sim seconds -> ISO clock string
        self.orders: dict[str, dict] = {}
        self.n = 0

    # ------------------------------------------------------------------
    def _open_for(self, asset):
        for w in self.orders.values():
            if w["asset"] == asset and w["status"] != "CLOSED":
                return w
        return None

    def _criticality(self, asset, measured):
        grp = REDUNDANT.get(asset)
        if not grp:
            return "High (no redundancy)"
        healthy_spare = [a for a in grp if a != asset and measured.get(a, {}).get("state") not in ("TRIPPED", "NO_POWER")]
        return f"Medium (N+1: {', '.join(healthy_spare)} available)" if healthy_spare else "High (redundancy lost)"

    def update(self, t: float, health: dict, measured: dict, actions_taken: list[dict], replay: list[dict]):
        """Open or refresh work orders from the latest health assessments."""
        for asset, h in health.items():
            code = h.get("fault_code")
            hi = h.get("hi", 100.0)
            if code in (None, "F10") and hi >= 65:
                continue
            if code == "F10":                       # trip: covered by the open order if one exists
                w = self._open_for(asset)
                if w:
                    w["events"].append({"t": round(t, 1), "clock": self.clock(t), "event": "Asset tripped (protection)"})
                    w["tripped"] = True
                continue
            if h.get("running") is False:          # stopped asset: keep the last running assessment
                continue
            pr = _priority(hi, h.get("rul_lo_h"))
            if pr is None:
                continue
            w = self._open_for(asset)
            rul_lo = h.get("rul_lo_h")
            due_h = (1 - SAFETY_MARGIN) * rul_lo if rul_lo is not None else ADVISORY_DUE_H
            ad = ACTIONS.get(code, DEFAULT_ACTION)
            v = measured.get(asset, {}).get("v", {})
            ev = {"health_index": hi, "fault_probability": h.get("prob"), "residuals": h.get("residuals", {}),
                  "basis": h.get("basis")}
            if "vib_mms" in v:
                vib = v["vib_mms"]
                ev["vibration_mms"] = round(vib, 2)
                ev["iso10816_zone"] = "D" if vib >= 7.1 else ("C" if vib >= 4.5 else ("B" if vib >= 2.8 else "A"))
            rp = [r for r in replay if r["asset"] == asset]
            if rp:
                ev["data_source"] = (f"Replayed measured data: {rp[0]['title']} "
                                     f"(bearing life {100 * rp[0]['life_frac']:.0f} % elapsed, kurtosis {rp[0]['measured_kurtosis']})")
            fields = {"priority": pr, "health_index": hi, "fault": h.get("fault"), "fault_code": code,
                      "rul_h": h.get("rul_h"), "rul_lo_h": rul_lo, "rul_hi_h": h.get("rul_hi_h"),
                      "evidence": ev, "criticality": self._criticality(asset, measured),
                      "due_sim_s": round(t + due_h * 3600, 1), "due_clock": self.clock(t + due_h * 3600),
                      "recommended_actions": ad["actions"], "parts": ad["parts"], "est_labour_h": ad["hours"],
                      "trade": ad["trade"], "updated_sim_s": round(t, 1), "updated_clock": self.clock(t)}
            if w is None:
                self.n += 1
                w = {"wo_id": f"WO-{self.n:04d}", "asset": asset, "title": f"{asset}: {ad['title']}",
                     "status": "OPEN", "created_sim_s": round(t, 1), "created_clock": self.clock(t),
                     "created_wall": time.time(), "raised_by": "DATACORE-X asset intelligence (auto)",
                     "history": [{"status": "OPEN", "clock": self.clock(t), "by": "system", "note": "raised automatically"}],
                     "events": [], "control_actions": [], "tripped": False}
                self.orders[w["wo_id"]] = w
            elif pr < w["priority"]:                           # escalate only ("P1" < "P2" < "P3")
                w["history"].append({"status": w["status"], "clock": self.clock(t), "by": "system",
                                     "note": f"escalated {w['priority']} -> {pr}"})
            fields["priority"] = min(pr, w.get("priority", pr))   # never de-escalate an open order
            if w.get("fault_code") and code and w["fault_code"] != code:
                fields["title"] = f"{asset}: {ad['title']}"
            w.update(fields)
        for a in actions_taken:
            w = self._open_for(a["asset"])
            if w is not None and a not in w["control_actions"]:
                w["control_actions"].append(a)

    # ------------------------------------------------------------------
    def transition(self, wo_id, action, user, note="", scheduled_for=None, now_clock=None):
        w = self.orders[wo_id]
        flow = {"ack": ("OPEN", "ACKNOWLEDGED"), "schedule": (("OPEN", "ACKNOWLEDGED"), "SCHEDULED"),
                "close": (("OPEN", "ACKNOWLEDGED", "SCHEDULED"), "CLOSED")}
        if action not in flow:
            raise ValueError(f"unknown action {action}")
        frm, to = flow[action]
        frm = (frm,) if isinstance(frm, str) else frm
        if w["status"] not in frm:
            raise ValueError(f"{wo_id} is {w['status']}; cannot {action}")
        w["status"] = to
        rec = {"status": to, "clock": now_clock or w.get("updated_clock"), "wall": time.time(), "by": user, "note": note}
        if scheduled_for:
            w["scheduled_for"] = scheduled_for
            rec["scheduled_for"] = scheduled_for
        w["history"].append(rec)
        return w

    def listing(self):
        order = {"OPEN": 0, "ACKNOWLEDGED": 1, "SCHEDULED": 2, "CLOSED": 3}
        return sorted(self.orders.values(), key=lambda w: (order[w["status"]], w.get("priority", "P9"), -w["created_sim_s"]))

    # ------------------------------------------------------------------
    @staticmethod
    def cmms_json(w: dict) -> dict:
        """Neutral CMMS-style record (fields map onto Maximo / SAP PM / UpKeep work orders)."""
        return {"workOrderNumber": w["wo_id"], "assetNumber": w["asset"], "description": w["title"],
                "status": w["status"], "priority": w["priority"], "workType": "PdM (condition-based)",
                "failureCode": w.get("fault_code"), "problemDescription": w.get("fault"),
                "reportedDate": w["created_clock"], "targetFinishDate": w.get("due_clock"),
                "scheduledStart": w.get("scheduled_for"), "craft": w.get("trade"),
                "estimatedLaborHours": w.get("est_labour_h"), "materials": w.get("parts", []),
                "tasks": [{"seq": i + 1, "description": a} for i, a in enumerate(w.get("recommended_actions", []))],
                "condition": {"healthIndex": w.get("health_index"), "rulHours": w.get("rul_h"),
                              "rulLowerHours": w.get("rul_lo_h"), "rulUpperHours": w.get("rul_hi_h"),
                              "evidence": w.get("evidence")},
                "controlActionsTaken": w.get("control_actions", []), "statusHistory": w.get("history", []),
                "source": "DATACORE-X digital twin (simulation; time-compressed hours)"}

    @staticmethod
    def html_page(w: dict) -> str:
        e = lambda x: html.escape(str(x if x is not None else "-"))
        ev = w.get("evidence", {})
        rul = "-" if w.get("rul_h") is None else f"{w['rul_h']:.2f} h ({w.get('rul_lo_h') or 0:.2f} to {w.get('rul_hi_h') or 0:.2f} h)"
        rows = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in (
            ("Asset", w["asset"]), ("Criticality", w.get("criticality")), ("Likely fault", w.get("fault")),
            ("Health Index", f"{w.get('health_index')} / 100"), ("Remaining useful life", rul),
            ("Vibration", f"{ev.get('vibration_mms', '-')} mm/s (ISO 10816 zone {ev.get('iso10816_zone', '-')})"),
            ("Data source", ev.get("data_source", "Live digital-twin measurements")),
            ("Raised", w["created_clock"]), ("Due by", w.get("due_clock")), ("Status", w["status"]),
            ("Trade / labour", f"{w.get('trade')} · {w.get('est_labour_h')} h")))
        acts = "".join(f"<li>{e(a)}</li>" for a in w.get("recommended_actions", []))
        parts = "".join(f"<li>{e(a)}</li>" for a in w.get("parts", [])) or "<li>-</li>"
        ctl = "".join(f"<li>{e(a.get('clock'))}: {e(a.get('text'))}</li>" for a in w.get("control_actions", [])) or "<li>None</li>"
        hist = "".join(f"<tr><td>{e(h.get('clock'))}</td><td>{e(h.get('status'))}</td><td>{e(h.get('by'))}</td><td>{e(h.get('note'))}</td></tr>"
                       for h in w.get("history", []))
        return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(w['wo_id'])}</title>
<style>body{{font:14px 'Segoe UI',Arial,sans-serif;color:#1F2328;max-width:820px;margin:32px auto;padding:0 24px}}
h1{{font-size:22px;margin:0}} .sub{{color:#5E6670;margin:4px 0 18px}} table{{border-collapse:collapse;width:100%;margin:8px 0 16px}}
th,td{{border:1px solid #C9CDD2;padding:6px 10px;text-align:left;vertical-align:top}} th{{background:#F1F2F4;width:190px}}
h2{{font-size:15px;margin:18px 0 6px}} .pr{{display:inline-block;padding:2px 10px;border-radius:2px;background:#B42318;color:#fff;font-weight:600}}
.foot{{color:#5E6670;font-size:12px;margin-top:24px}} @media print{{button{{display:none}}}}</style></head><body>
<button onclick="window.print()" style="float:right">Print / save as PDF</button>
<h1>Work order {e(w['wo_id'])}: {e(w['title'])}</h1>
<div class="sub"><span class="pr">{e(w.get('priority'))}</span> &nbsp; raised automatically by the DATACORE-X asset intelligence layer</div>
<table>{rows}</table>
<h2>Recommended actions</h2><ol>{acts}</ol>
<h2>Parts</h2><ul>{parts}</ul>
<h2>Control actions already taken</h2><ul>{ctl}</ul>
<h2>Status history</h2><table><tr><th>Time</th><th>Status</th><th>By</th><th>Note</th></tr>{hist}</table>
<div class="foot">Evidence basis: {e(ev.get('basis'))}<br>Simulation study: times are simulated plant time (time-compressed). DATACORE-X digital twin.</div>
</body></html>"""
