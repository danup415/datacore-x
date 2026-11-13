"""Asset intelligence layer — physics-residual health estimator v0 (L4B).

Implements Stage 1 (physics-based monitoring) and a transparent rule-based
Stage 2 of the blueprint's predictive-maintenance engine so that the 3D twin
can display *real computed* Health Index, fault class, fault probability and
RUL with confidence.  It uses **only measured values and nominal (healthy)
design parameters** — never the injected fault list — so its outputs can be
scored against simulation ground truth.

The common interface (``AssetHealth`` dict) is what the trained models from
``predictive_maintenance/`` (XGBoost, Isolation Forest, TCN-BiLSTM, …) must
return when they replace these estimators:

    {"hi": 0-100, "fault": str, "fault_code": str|None, "prob": 0-1,
     "rul_h": float|None, "rul_lo_h", "rul_hi_h", "confidence": 0-1,
     "basis": str, "residuals": {...}, "assessed_at": sim_time_s,
     "recommendation": str}
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np

ESTIMATOR_ID = "dcx-physics-residual-v0"
FAIL_HI = 30.0


def _clip(x, lo=0.0, hi=1.0):
    return lo if x < lo else (hi if x > hi else x)


def _logistic(score, mid=0.22, k=0.05):
    return 1.0 / (1.0 + math.exp(-(score - mid) / k))


class _Trend:
    """HI history + linear-trend RUL extrapolation to the failure threshold."""

    def __init__(self, window=90, every_s=10.0):
        self.buf = deque(maxlen=window)
        self.every = every_s
        self.last_t = -1e9

    def add(self, t, hi):
        if t - self.last_t >= self.every:
            self.buf.append((t, hi))
            self.last_t = t

    def rul(self, hi_now):
        if hi_now <= FAIL_HI:
            return 0.0, 0.0, 0.0, 0.9, "at or below failure threshold (HI ≤ 30)"
        if len(self.buf) < 12:
            return None, None, None, 0.0, "insufficient history for trend (< 2 min)"
        t = np.array([b[0] for b in self.buf])
        y = np.array([b[1] for b in self.buf])
        tm = t - t.mean()
        sxx = float((tm ** 2).sum())
        if sxx <= 0:
            return None, None, None, 0.0, "no time span"
        slope = float((tm * (y - y.mean())).sum() / sxx)
        resid = y - (y.mean() + slope * tm)
        dof = max(1, len(y) - 2)
        se = math.sqrt(float((resid ** 2).sum()) / dof / sxx)
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1 - float((resid ** 2).sum()) / ss_tot if ss_tot > 1e-9 else 0.0
        if slope > -0.0005:  # > -1.8 HI per hour => no meaningful degradation
            return None, None, None, round(max(0.0, r2), 2), "no degradation trend detected"
        rul_s = (hi_now - FAIL_HI) / -slope
        s_fast, s_slow = slope - 2 * se, min(-1e-6, slope + 2 * se)
        lo = (hi_now - FAIL_HI) / -s_fast
        hi = (hi_now - FAIL_HI) / -s_slow
        return rul_s / 3600, lo / 3600, min(hi / 3600, 1e4), round(_clip(r2), 2), \
            f"linear HI trend over {len(y)} samples, slope {slope*3600:.1f} HI/h, ±2σ bounds"


class HealthEngine:
    def __init__(self, nominal: dict):
        self.p = nominal
        self.trend: dict[str, _Trend] = {}
        self.smooth: dict[str, dict] = {}
        self.last: dict[str, dict] = {}

    # ------------------------------------------------------------------
    def _ewma(self, aid, key, x, alpha=0.08):
        d = self.smooth.setdefault(aid, {})
        d[key] = x if key not in d else d[key] + alpha * (x - d[key])
        return d[key]

    def _finish(self, aid, t, hi, fault, code, score, basis, res, rec, running=True):
        hi = round(_clip(hi, 0, 100), 1)
        tr = self.trend.setdefault(aid, _Trend())
        if running:
            tr.add(t, hi)
        rul, lo, up, conf, rb = tr.rul(hi)
        h = {"hi": hi, "fault": fault, "fault_code": code, "prob": round(_logistic(score), 3),
             "rul_h": None if rul is None else round(rul, 3),
             "rul_lo_h": None if lo is None else round(lo, 3),
             "rul_hi_h": None if up is None else round(up, 3),
             "confidence": conf, "basis": f"{basis}; RUL: {rb}; time-compressed simulation hours",
             "residuals": {k: round(v, 4) for k, v in res.items()}, "assessed_at": round(t, 1),
             "estimator": ESTIMATOR_ID, "recommendation": rec, "running": running}
        if code is None:
            h["prob"] = round(min(h["prob"], 0.2), 3)
        self.last[aid] = h
        return h

    def _hold(self, aid, t, state):
        h = dict(self.last.get(aid) or {"hi": 100.0, "fault": "Healthy", "fault_code": None, "prob": 0.02,
                                        "rul_h": None, "rul_lo_h": None, "rul_hi_h": None, "confidence": 0.0,
                                        "basis": "not yet assessed", "residuals": {}, "assessed_at": None,
                                        "estimator": ESTIMATOR_ID, "recommendation": "—"})
        h["running"] = False
        h["note"] = f"asset {state.lower()} — health held from last running assessment"
        if state == "TRIPPED":
            h.update(fault="Tripped (protection)", fault_code="F10", prob=1.0,
                     recommendation="Inspect cause of trip; reset only after maintenance")
        return h

    # ------------------------------------------------------------------
    def update(self, m: dict, t: float, facility: dict | None = None) -> tuple[dict, dict]:
        """Returns (health_by_asset, diagnostics_by_asset)."""
        P = self.p
        H: dict[str, dict] = {}
        D: dict[str, dict] = {}
        g = lambda a, k, d=0.0: (m.get(a, {}).get("v", {}).get(k) if m.get(a, {}).get("v", {}).get(k) is not None else d)

        # ---------------- pumps --------------------------------------------
        for p in ("P-01", "P-02", "P-03"):
            st = m.get(p, {}).get("state", "UNKNOWN")
            if st != "RUNNING" or g(p, "speed_pct") < 5:
                H[p] = self._hold(p, t, st)
                continue
            n = g(p, "speed_pct") / 100
            q, Hm, Pw, vib = g(p, "flow_ls"), g(p, "head_kpa"), g(p, "power_kw"), g(p, "vib_mms")
            H_exp = P["pump_H0"] * n * n - P["pump_kp"] * q * q
            r_h = self._ewma(p, "r_h", max(0.0, (H_exp - Hm) / max(H_exp, 1.0)))
            x = q / (n * P["pump_q_bep"])
            eta_exp = max(0.15, P["pump_eta_bep"] * (1 - 0.8 * (x - 1) ** 2))
            eta_m = q * Hm / 1000 / Pw if Pw > 0.01 else eta_exp
            r_e = self._ewma(p, "r_e", max(0.0, (eta_exp - eta_m) / eta_exp))
            vib_exp = 0.9 + 1.3 * n * n
            r_v = self._ewma(p, "r_v", max(0.0, (vib - vib_exp) / 7.1))
            sv, sh, se = 1.0 * r_v, 2.5 * r_h, 2.0 * r_e
            score = max(sv, sh, se)
            if score < 0.10:
                fault, code, rec = "Healthy", None, "No action"
            elif sh >= 0.12 and r_v > 0.15:
                fault, code, rec = "Cavitation (F02)", "F02", "Check suction pressure/NPSH, strainer and expansion vessel; reduce speed"
            elif r_v > 0.10 and sh < 0.12:
                fault, code, rec = "Bearing degradation (F01)", "F01", "Schedule bearing inspection; prepare changeover to standby pump"
            else:
                fault, code, rec = "Hydraulic efficiency degradation", "PUMP_EFF", "Inspect impeller wear / internal recirculation"
            if score > 0.6:
                rec = "URGENT: " + rec
            H[p] = self._finish(p, t, 100 * (1 - _clip(score)), fault, code, score,
                                "pump curve head & efficiency residuals + vibration vs speed baseline (ISO 10816 zone D 7.1 mm/s)",
                                {"head": r_h, "efficiency": r_e, "vibration": r_v}, rec)

        # ---------------- CRAH fans ----------------------------------------
        for c in ("CRAH-01", "CRAH-02", "CRAH-03", "CRAH-04"):
            st = m.get(c, {}).get("state", "UNKNOWN")
            s = g(c, "fan_speed_pct") / 100
            if st != "RUNNING" or s < 0.1:
                H[c] = self._hold(c, t, st)
                continue
            vib, fkw, af = g(c, "vib_mms"), g(c, "fan_kw"), g(c, "airflow_m3s")
            r_v = self._ewma(c, "r_v", max(0.0, (vib - 0.8 * s) / 4.5))
            p_exp = 5.5 * s ** 3
            r_p = self._ewma(c, "r_p", max(0.0, (fkw - p_exp) / max(p_exp, 0.05)))
            af_exp = s * P["crah_m_max"] / 1.18
            r_a = self._ewma(c, "r_a", max(0.0, (af_exp - af) / af_exp))
            score = max(r_v, 1.6 * r_a, 1.2 * r_p if r_v < 0.08 else 0.0)
            if score < 0.10:
                fault, code, rec = "Healthy", None, "No action"
            elif r_a > 0.08 and r_v < 0.1:
                fault, code, rec = "Filter / coil blockage", "CRAH_BLOCK", "Replace filters; inspect coil face"
            elif r_p > 0.08:
                fault, code, rec = "Fan bearing degradation (F04)", "F04", "Plan bearing replacement; monitor motor temperature"
            else:
                fault, code, rec = "Fan imbalance (F03)", "F03", "Dynamic balancing of impeller; check blade fouling"
            H[c] = self._finish(c, t, 100 * (1 - _clip(score)), fault, code, score,
                                "fan-law power & airflow residuals + vibration vs speed baseline",
                                {"vibration": r_v, "fan_power": r_p, "airflow": r_a}, rec)

        # ---------------- chillers -------------------------------------------
        for ch in ("CH-01", "CH-02"):
            st = m.get(ch, {}).get("state", "UNKNOWN")
            load = g(ch, "load_kw")
            if st != "RUNNING" or load < 10:
                H[ch] = self._hold(ch, t, st)
                continue
            plr = max(0.15, g(ch, "plr_pct") / 100)
            T_ev = P["chws_sp"] - 2 + 273.15
            T_cd = g(ch, "cwe_c") + 5.5 + 273.15
            cop_exp = min(12.0, P["chiller_cop_carnot_frac"] * T_ev / max(3.0, T_cd - T_ev) * (1 - 0.35 * (1 - plr) ** 2))
            r_c = self._ewma(ch, "r_c", max(0.0, (cop_exp - g(ch, "cop")) / cop_exp), 0.05)
            score = 2.2 * r_c
            fault, code, rec = ("Healthy", None, "No action") if score < 0.10 else \
                ("COP degradation (F06)", "F06", "Check refrigerant charge, condenser/evaporator approach, compressor")
            H[ch] = self._finish(ch, t, 100 * (1 - _clip(score)), fault, code, score,
                                 "COP residual vs Carnot-fraction performance map at measured lift/PLR",
                                 {"cop": r_c, "cop_expected": cop_exp}, rec)

        # ---------------- economiser HX -------------------------------------
        hx = "HX-01"
        if m.get(hx, {}).get("state") == "RUNNING" and g("PIPE-CHWS", "flow_ls") > 0.5:
            q1, q2 = g("PIPE-CHWS", "flow_ls"), g("PIPE-CW", "flow_ls")
            C1, C2 = 4.186 * q1, 4.186 * max(q2, 0.1)
            dT_max = g(hx, "chw_in_c") - g(hx, "cw_in_c")
            eps_m = C1 * (g(hx, "chw_in_c") - g(hx, "chw_out_c")) / (min(C1, C2) * dT_max) if dT_max > 0.8 else P["hx_eps"]
            r = self._ewma(hx, "r", max(0.0, (P["hx_eps"] - eps_m) / P["hx_eps"]), 0.05)
            score = 1.4 * r
            fault, code, rec = ("Healthy", None, "No action") if score < 0.12 else \
                ("Heat exchanger fouling (F05)", "F05", "Schedule plate-pack cleaning (CIP); check strainers")
            H[hx] = self._finish(hx, t, 100 * (1 - _clip(score)), fault, code, score,
                                 "effectiveness from measured temperatures & flows vs design ε=0.72",
                                 {"effectiveness": r, "eps_measured": eps_m}, rec)
        else:
            H[hx] = self._hold(hx, t, m.get(hx, {}).get("state", "BYPASS"))

        # ---------------- cooling towers --------------------------------------
        for ct in ("CT-01", "CT-02"):
            st = m.get(ct, {}).get("state")
            Q = g(ct, "heat_rej_kw")
            if st != "RUNNING" or Q < 5:
                H[ct] = self._hold(ct, t, st or "UNKNOWN")
                continue
            s = g(ct, "fan_speed_pct") / 100
            app_exp = P["tower_app_nom"] * (Q / 90.0) ** 0.6 / (0.15 + 0.85 * s) ** 0.7
            app_m = g(ct, "leaving_c") - g(ct, "wetbulb_c")
            r = self._ewma(ct, "r", max(0.0, (app_m - app_exp) / max(app_exp, 0.5)), 0.05)
            score = 0.6 * r
            fault, code, rec = ("Healthy", None, "No action") if score < 0.12 else \
                ("Tower performance degradation (F07)", "F07", "Inspect fill media, nozzles and fan drive; check water treatment")
            H[ct] = self._finish(ct, t, 100 * (1 - _clip(score)), fault, code, score,
                                 "approach residual vs nominal approach model at measured load & fan speed",
                                 {"approach": r, "approach_expected_k": app_exp}, rec)

        # ---------------- batteries + UPS ---------------------------------------
        for b in ("BAT-A", "BAT-B"):
            soh, rint, temp = g(b, "soh_pct", 100), g(b, "rint_mohm", 60), g(b, "temp_c", 24)
            h_soh = _clip((soh - 60) / 40)
            h_r = 1 - _clip((rint / (P["bat_r_ohm"] * 1000) - 1) / 1.6)
            h_t = 1 - _clip((temp - 30) / 15)
            hi = 100 * min(h_soh, h_r, h_t)
            score = 1 - min(h_soh, h_r, h_t)
            if score < 0.10:
                fault, code, rec = "Healthy", None, "No action"
            elif h_t < min(h_soh, h_r):
                fault, code, rec = "Battery overheating", "BAT_TEMP", "Check room HVAC & charger float voltage; isolate string if > 45 °C"
            else:
                fault, code, rec = "Capacity loss / R_int rise (F08)", "F08", "Capacity test; plan string replacement; reduce runtime assumption"
            H[b] = self._finish(b, t, hi, fault, code, score, "BMS SoH, internal resistance and temperature vs design",
                                {"soh": 1 - h_soh, "rint": 1 - h_r, "temp": 1 - h_t}, rec)
        for u in ("UPS-A", "UPS-B"):
            st = m.get(u, {}).get("state", "UNKNOWN")
            x = g(u, "load_pct") / 100
            eta = g(u, "eff_pct") / 100
            eta_exp = 0.965 - 0.07 * math.exp(-x / 0.12) if x > 0 else 0
            r_eta = self._ewma(u, "r_eta", max(0.0, eta_exp - eta) if (st == "DOUBLE_CONVERSION" and x > 0) else 0.0)
            ovl = _clip((x - 0.8) / 0.4)
            score = max(10 * r_eta, ovl, 1.0 if st == "OUTPUT_OFF" else 0.0)
            if score < 0.1:
                fault, code, rec = "Healthy", None, "No action"
            elif st == "OUTPUT_OFF":
                fault, code, rec = "Output lost", "UPS_OFF", "Restore input / battery; verify static bypass"
            elif ovl > 0:
                fault, code, rec = "Overload risk", "UPS_OVL", "Redistribute load across A/B paths"
            else:
                fault, code, rec = "Efficiency degradation", "UPS_EFF", "Inspect rectifier/inverter modules and fans"
            H[u] = self._finish(u, t, 100 * (1 - _clip(score)), fault, code, score,
                                "efficiency residual vs load curve + loading margin", {"efficiency": r_eta, "overload": ovl}, rec)

        # ---------------- rack twin residuals / sensor validation (Subsystem 08)
        Tca, Tha = g("ZONE-CA", "temp_c", None), g("ZONE-HA", "temp_c", None)
        for i in range(1, 9):
            r = f"R-{i:02d}"
            rv = m.get(r, {}).get("v", {})
            if Tca is None or rv.get("inlet_c") is None:
                D[r] = {"finding": "Sensor invalid (quality BAD)", "twin_inlet_est_c": None, "residual_k": None,
                        "model_confidence": 0.0}
                continue
            est = Tca + 0.04 * (Tha - Tca)
            res = rv["inlet_c"] - est
            dT = (rv.get("outlet_c") or 0) - rv["inlet_c"]
            dT_exp = 12.0
            if res > 2.0 and dT < dT_exp - 3.5:
                finding = "Inlet sensor drift suspected (F09)"
                conf = 0.45
            elif res > 2.0:
                finding = "Local recirculation hotspot"
                conf = 0.75
            else:
                finding = "Consistent with twin"
                conf = 0.9
            D[r] = {"twin_inlet_est_c": round(est, 2), "residual_k": round(res, 2), "delta_t_k": round(dT, 2),
                    "finding": finding, "model_confidence": conf}
        return H, D
