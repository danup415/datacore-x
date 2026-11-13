"""Alarm management (ISA-18.2 style states): ACTIVE_UNACK, ACTIVE_ACK,
CLEARED_UNACK.  Evaluated on *measured* values + intelligence outputs."""
from __future__ import annotations

PRIORITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


class AlarmManager:
    def __init__(self, sp_getter=None):
        self.alarms: dict[str, dict] = {}
        self.history: list[dict] = []
        self.sp_getter = sp_getter or (lambda: {"chws_c": 18.0})

    def _conds(self, m: dict, health: dict, diag: dict, comm: dict) -> dict[str, tuple]:
        c: dict[str, tuple] = {}
        v = lambda a, k: m.get(a, {}).get("v", {}).get(k)
        s = lambda a: m.get(a, {}).get("state")
        for i in range(1, 9):
            r = f"R-{i:02d}"
            t = v(r, "inlet_c")
            if t is not None and t > 32.0:
                c[f"{r}:INLET_HH"] = ("CRITICAL", r, f"{r} inlet {t:.1f} °C > 32 °C (ASHRAE A1 allowable)")
            elif t is not None and t > 27.0:
                c[f"{r}:INLET_H"] = ("HIGH", r, f"{r} inlet {t:.1f} °C > 27 °C (ASHRAE recommended)")
            if s(r) == "NO_POWER":
                c[f"{r}:NO_POWER"] = ("CRITICAL", r, f"{r} lost power — IT outage")
            d = diag.get(r, {})
            if "drift" in d.get("finding", ""):
                c[f"{r}:SENSOR"] = ("MEDIUM", r, f"{r} inlet sensor inconsistent with twin (residual {d['residual_k']} K)")
            q = m.get(r, {}).get("q", {})
            if any(x == "BAD" for x in q.values()):
                c[f"{r}:SENSOR_BAD"] = ("MEDIUM", r, f"{r} sensor quality BAD")
        for a in ("P-01", "P-02", "P-03", "CRAH-01", "CRAH-02", "CRAH-03", "CRAH-04", "CH-01", "CH-02"):
            if s(a) == "TRIPPED":
                c[f"{a}:TRIP"] = ("HIGH", a, f"{a} tripped")
        for u in ("UPS-A", "UPS-B"):
            if s(u) == "BATTERY":
                c[f"{u}:ON_BATTERY"] = ("MEDIUM", u, f"{u} on battery")
            if s(u) == "OUTPUT_OFF":
                c[f"{u}:OUTPUT_OFF"] = ("CRITICAL", u, f"{u} output off")
        for b in ("BAT-A", "BAT-B"):
            soc = v(b, "soc_pct")
            if soc is not None and soc < 30:
                c[f"{b}:SOC_LOW"] = ("HIGH", b, f"{b} SoC {soc:.0f} % < 30 %")
            tb = v(b, "temp_c")
            if tb is not None and tb > 35:
                c[f"{b}:TEMP"] = ("MEDIUM", b, f"{b} temperature {tb:.1f} °C")
        if s("SWG-01") == "DEAD_BUS":
            c["SWG-01:DEAD_BUS"] = ("CRITICAL", "SWG-01", "LV main bus dead — mechanical plant unpowered")
        elif s("SWG-01") == "ON_GENERATOR":
            c["SWG-01:ON_GEN"] = ("MEDIUM", "SWG-01", "Facility on standby generator")
        if s("TX-01") == "DE-ENERGISED":
            c["TX-01:UTILITY"] = ("HIGH", "TX-01", "Utility supply lost")
        chws = v("PIPE-CHWS", "temp_c")
        if chws is not None and chws > self.sp_getter()["chws_c"] + 2.0:
            c["PIPE-CHWS:HIGH"] = ("HIGH", "PIPE-CHWS", f"CHW supply {chws:.1f} °C above setpoint +2 K")
        for p in ("PDU-A", "PDU-B"):
            lp = v(p, "load_pct")
            if lp is not None and lp > 80:
                c[f"{p}:LOAD"] = ("MEDIUM", p, f"{p} loading {lp:.0f} %")
        for a, h in health.items():
            hi = h.get("hi", 100)
            if hi < 20:
                c[f"{a}:HEALTH"] = ("HIGH", a, f"{a} health {hi:.0f} — {h.get('fault')}")
            elif hi < 40:
                c[f"{a}:HEALTH"] = ("MEDIUM", a, f"{a} health {hi:.0f} — {h.get('fault')}")
            elif hi < 60:
                c[f"{a}:HEALTH"] = ("LOW", a, f"{a} maintenance advisory: {h.get('fault')} (HI {hi:.0f})")
        for k, st in comm.items():
            if st not in ("OK", "DISABLED"):
                c[f"COMM:{k}"] = ("HIGH", "DCX", f"Communication {k}: {st}")
        return c

    def evaluate(self, m, health, diag, comm, t):
        conds = self._conds(m, health, diag, comm)
        for aid, (prio, asset, text) in conds.items():
            a = self.alarms.get(aid)
            if a is None or a["state"] == "CLEARED_UNACK":
                if a is None:
                    self.alarms[aid] = {"id": aid, "priority": prio, "asset": asset, "text": text,
                                        "state": "ACTIVE_UNACK", "t_active": round(t, 1), "t_clear": None,
                                        "acked_by": None}
                else:
                    a.update(state="ACTIVE_UNACK", t_active=round(t, 1), t_clear=None, text=text, priority=prio)
            else:
                a["text"] = text
                if PRIORITY_RANK[prio] > PRIORITY_RANK[a["priority"]]:
                    a["priority"] = prio
                    a["state"] = "ACTIVE_UNACK"
        for aid, a in list(self.alarms.items()):
            if aid not in conds and a["state"].startswith("ACTIVE"):
                a["t_clear"] = round(t, 1)
                if a["state"] == "ACTIVE_ACK":
                    self._retire(aid)
                else:
                    a["state"] = "CLEARED_UNACK"

    def _retire(self, aid):
        self.history.append(self.alarms.pop(aid))
        self.history = self.history[-500:]

    def ack(self, aid, user):
        a = self.alarms.get(aid)
        if not a:
            return False
        a["acked_by"] = user
        if a["state"] == "CLEARED_UNACK":
            self._retire(aid)
        else:
            a["state"] = "ACTIVE_ACK"
        return True

    def active(self):
        return sorted(self.alarms.values(), key=lambda a: (-PRIORITY_RANK[a["priority"]], a["t_active"]))
