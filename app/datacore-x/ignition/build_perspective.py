"""Build the DATACORE-X Perspective screens and import them into an Ignition 8.3 project.

    python ignition/build_perspective.py                 # write ignition/_build/DATACORE_X_perspective.zip only
    python ignition/build_perspective.py --apply         # export project, merge screens, import (overwrite)

Visual language follows ISA-101 high-performance HMI practice: neutral grey
background, dark text, no decorative colour; colour appears only for abnormal
conditions (amber = approaching a limit, red = limit exceeded or worse than baseline).

Screens (bound to the [default]DATACORE_X tags created by setup_ignition.py):
  DCX/Header     top bar: site, navigation, simulation clock, link status
  DCX/Overview   3D facility model (live) + facility summary + rack inlet table + plant status
  DCX/Equipment  air side, chilled-water plant, pumps, heat rejection, electrical tables
  DCX/Scenarios  what-if scenarios: run on an isolated copy of the twin, preview in
                 3D (scenario / baseline), apply to the live plant, clear faults
  DCX/Alarms     ISA-18.2 alarm summary: Ignition alarm status table (ack, shelve) + alarm philosophy
  DCX/Compare    conventional EMPC vs PI-HA-EMPC on the same fault (recorded MATLAB runs)
  DCX/Maintenance work orders raised from HI/RUL (acknowledge, schedule, close, print/PDF, CMMS JSON),
                 health-aware changeover on/off, simulation speed, measured-data replay status
Page routes: "/" Overview, "/equipment", "/scenarios", "/alarms", "/compare" (and "/twin" full 3D twin UI).
The header carries an alarm banner (highest-priority active alarm, counts) that links to /alarms.
Alarms themselves are configured on the tags by add_alarms.py.

The 3D model is the DATACORE-X browser twin (http://localhost:8000) embedded with
?embed=bare. It reads the same twin state as the OPC UA tags, so anything applied
to the live plant appears in the 3D model and in every Ignition tag at once.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
KEY = Path(os.path.expandvars(r"%USERPROFILE%")) / "Documents" / "DATACORE-X" / "ignition_api_key.txt"
ROOT = "[default]DATACORE_X"
PV = "com.inductiveautomation.perspective"
TWIN = "http://localhost:8000"

# ----------------------------------------------------------------- ISA-101 style palette
BG, PANEL, BORDER, HEAD_ROW = "#E3E5E8", "#FFFFFF", "#C9CDD2", "#F1F2F4"
TEXT, MUTED = "#1F2328", "#5E6670"
BAR, BAR_TEXT, BAR_MUTED = "#2E3338", "#F3F4F5", "#AEB4BB"
ACCENT = "#2F5A86"                       # single restrained accent for actions
WARN, ALARM = "#B7791F", "#B42318"
PRIO_COL = {4: "#B42318", 3: "#C2410C", 2: "#B7791F", 1: "#2F5A86"}   # Critical, High, Medium, Low
FONT = "'Segoe UI', 'Noto Sans', Arial, sans-serif"
NROWS = 12


def tag(path: str) -> str:
    return "{" + f"{ROOT}/{path}" + "}"


def expr(e: str) -> dict:
    return {"binding": {"type": "expr", "config": {"expression": e}}}


def prop(path: str, bidirectional=False) -> dict:
    return {"binding": {"type": "property", "config": {"path": path, "bidirectional": bidirectional}}}


def fmt(t: str, pattern="0.0") -> str:
    return f"numberFormat({t}, '{pattern}')"


def label(name, text="", text_expr=None, style=None, grow=0, basis="auto", style_expr=None, shrink=1):
    st = {"fontFamily": FONT, "fontSize": "13px", "color": TEXT}
    st.update(style or {})
    c = {"type": "ia.display.label", "meta": {"name": name},
         "position": {"grow": grow, "shrink": shrink, "basis": basis}, "props": {"text": text, "style": st}}
    pc = {}
    if text_expr:
        pc["props.text"] = expr(text_expr)
    for k, e in (style_expr or {}).items():
        pc[f"props.style.{k}"] = expr(e)
    if pc:
        c["propConfig"] = pc
    return c


def flex(name, children, direction="row", style=None, grow=0, basis="auto", shrink=1, wrap=False, align=None):
    p = {"direction": direction, "style": style or {}}
    if wrap:
        p["wrap"] = "wrap"
    if align:
        p["alignItems"] = align
    return {"type": "ia.container.flex", "meta": {"name": name},
            "position": {"grow": grow, "shrink": shrink, "basis": basis}, "props": p, "children": children}


def panel(name, title, body, grow=1, basis="auto", subtitle=None, shrink=1):
    head = [label("title", title, style={"fontSize": "13px", "fontWeight": "600"}, shrink=0)]
    if subtitle:
        head.append(label("sub", subtitle, style={"fontSize": "12px", "color": MUTED, "marginLeft": "10px"}))
    return flex(name, [
        flex("head", head, align="baseline", shrink=0,
             style={"padding": "8px 10px", "borderBottom": f"1px solid {BORDER}"}),
        body,
    ], direction="column", grow=grow, basis=basis, shrink=shrink,
        style={"backgroundColor": PANEL, "border": f"1px solid {BORDER}", "borderRadius": "2px", "margin": "4px",
               "overflow": "hidden"})


def limit_color(t: str, warn: float, alarm: float, normal=TEXT) -> str:
    return f"if({t} >= {alarm}, '{ALARM}', if({t} >= {warn}, '{WARN}', '{normal}'))"


def state_color(t: str) -> str:
    s = f"upper(toStr({t}))"
    return (f"if(indexOf({s}, 'TRIP') >= 0 || indexOf({s}, 'FAULT') >= 0 || indexOf({s}, 'ALARM') >= 0 || "
            f"indexOf({s}, 'CRIT') >= 0 || indexOf({s}, 'FAIL') >= 0, '{ALARM}', "
            f"if(indexOf({s}, 'WARN') >= 0 || indexOf({s}, 'DEGRAD') >= 0 || indexOf({s}, 'BATTERY') >= 0, '{WARN}', '{MUTED}'))")


# ----------------------------------------------------------------- tables
def table(name, columns, rows):
    """columns: [(header, basis, align)]; rows: [[(text, expr, color_expr), ...]]"""
    def cell(i, txt, e, col, header=False):
        _, basis, align = columns[i]
        st = {"padding": "5px 8px", "textAlign": align, "fontVariantNumeric": "tabular-nums",
              "whiteSpace": "nowrap", "overflow": "hidden"}
        if header:
            st.update({"color": MUTED, "fontSize": "12px", "fontWeight": "600"})
        return label(f"c{i}", txt or "", text_expr=e, style=st, grow=1 if basis == "auto" else 0,
                     basis="60px" if basis == "auto" else basis, shrink=1 if basis == "auto" else 0,
                     style_expr={"color": col} if col else None)
    out = [flex("hdr", [cell(i, h, None, None, True) for i, (h, _, _) in enumerate(columns)], shrink=0,
                style={"backgroundColor": HEAD_ROW, "borderBottom": f"1px solid {BORDER}"})]
    for r, cells in enumerate(rows):
        out.append(flex(f"r{r}", [cell(i, *c) for i, c in enumerate(cells)], shrink=0,
                        style={"borderBottom": f"1px solid {HEAD_ROW}"}))
    return flex(name, out, direction="column", shrink=0)


def c_txt(t):
    return (t, None, None)


def c_num(path, p="0.0", col=None):
    return (None, fmt(tag(path), p), col)


def c_state(path):
    return (None, f"toStr({tag(path)})", state_color(tag(path)))


# ----------------------------------------------------------------- header
def header_view() -> dict:
    def nav(name, text, url):
        active = f"{{page.props.path}} = '{url}'"
        return {"type": "ia.input.button", "meta": {"name": name}, "position": {"basis": "auto", "shrink": 0},
                "props": {"text": text, "style": {"fontFamily": FONT, "fontSize": "13px", "backgroundColor": "transparent",
                                                  "color": BAR_MUTED, "border": "none", "borderRadius": "0",
                                                  "padding": "0 14px", "height": "44px", "boxShadow": "none"}},
                "propConfig": {"props.style.color": expr(f"if({active}, '{BAR_TEXT}', '{BAR_MUTED}')"),
                               "props.style.borderBottom": expr(f"if({active}, '2px solid {BAR_TEXT}', '2px solid transparent')")},
                "events": {"component": {"onActionPerformed": {
                    "type": "script", "scope": "G", "config": {"script": f"\tsystem.perspective.navigate('{url}')"}}}}}
    small = {"fontSize": "12px", "color": BAR_MUTED, "padding": "0 12px", "whiteSpace": "nowrap"}
    root = flex("root", [
        label("site", "DATACORE-X", style={"color": BAR_TEXT, "fontWeight": "600", "fontSize": "14px",
                                           "padding": "0 8px 0 14px"}, shrink=0),
        label("area", "Data hall 1 · reference facility", style={**small, "padding": "0 18px 0 0"}, shrink=0),
        nav("n1", "Overview", "/"), nav("n2", "Equipment", "/equipment"), nav("n3", "Scenarios", "/scenarios"),
        nav("n4", "Alarms", "/alarms"), nav("n6", "Maintenance", "/maintenance"), nav("n5", "Compare", "/compare"),
        label("spacer", "", grow=1),
        alarm_banner(),
        label("clock", text_expr=f"'Sim time ' + toStr({tag('System/Sim_Clock')})", style=small, shrink=0),
        label("src", text_expr=f"toStr({tag('System/Source')})", style=small, shrink=0),
        label("link", text_expr=f"if({tag('System/Last_Poll_OK')}, 'Twin link online', 'Twin link OFFLINE')",
              style=small, shrink=0,
              style_expr={"color": f"if({tag('System/Last_Poll_OK')}, '{BAR_MUTED}', '#F28B82')"}),
    ], align="center", style={"backgroundColor": BAR, "height": "44px"})
    custom = {"alm": {"n": 0, "un": 0, "prio": -1, "text": "Alarms: waiting for gateway"}}
    pc = {"custom.alm": {"binding": {"type": "expr", "config": {"expression": "now(2000)"},
                                     "transforms": [{"type": "script", "code": ALARM_QUERY}]}}}
    return {"custom": custom, "params": {}, "propConfig": pc,
            "props": {"defaultSize": {"height": 44, "width": 1600}}, "root": root}


ALARM_QUERY = '''
	import sys
	def summary():
		res = system.alarm.queryStatus(state=['ActiveUnacked', 'ActiveAcked', 'ClearUnacked'], source=['*DATACORE_X*'])
		n = 0
		un = 0
		top = None
		for a in res:
			cleared = a.isCleared()
			if not cleared:
				n += 1
			if not a.isAcked():
				un += 1
			p = int(a.getPriority().ordinal())
			if not cleared and (top is None or p > top[0]):
				lbl = None
				try:
					lbl = a.getLabel()
				except:
					pass
				if not lbl:
					lbl = str(a.getDisplayPathOrSource())
				top = (p, lbl)
		if top is None:
			if un:
				return {'n': 0, 'un': un, 'prio': 0, 'text': str(un) + ' cleared alarm(s) awaiting acknowledgement'}
			return {'n': 0, 'un': 0, 'prio': -1, 'text': 'No active alarms'}
		names = ['Diagnostic', 'Low', 'Medium', 'High', 'Critical']
		return {'n': n, 'un': un, 'prio': top[0], 'text': names[top[0]] + ': ' + top[1]}
	try:
		return summary()
	except:
		return {'n': 0, 'un': 0, 'prio': 0, 'text': 'Alarm query error: ' + str(sys.exc_info()[1])[:160]}
'''


def alarm_banner():
    f = lambda k: "{view.custom.alm." + k + "}"
    col = (f"case({f('prio')}, 4, '{PRIO_COL[4]}', 3, '{PRIO_COL[3]}', 2, '{PRIO_COL[2]}', 1, '{PRIO_COL[1]}', "
           f"0, '#4B5259', 'transparent')")
    txt = (f"if({f('prio')} < 0, 'No active alarms', "
           f"if({f('n')} > 0, toStr({f('n')}) + ' active · ' + toStr({f('un')}) + ' unack · ' + {f('text')}, {f('text')}))")
    c = label("alarms", style={"fontSize": "12px", "color": BAR_TEXT, "padding": "0 12px", "height": "28px",
                               "lineHeight": "28px", "borderRadius": "2px", "margin": "0 10px", "whiteSpace": "nowrap",
                               "overflow": "hidden", "textOverflow": "ellipsis", "maxWidth": "560px", "cursor": "pointer",
                               "fontWeight": "600"},
              text_expr=txt, shrink=1,
              style_expr={"backgroundColor": col,
                          "color": f"if({f('prio')} < 0, '{BAR_MUTED}', '{BAR_TEXT}')",
                          "fontWeight": f"if({f('prio')} < 0, '400', '600')"})
    c["events"] = {"dom": {"onClick": {"type": "script", "scope": "G",
                                       "config": {"script": "\tsystem.perspective.navigate('/alarms')"}}}}
    return c


def iframe(name, src_expr):
    return {"type": "ia.display.iframe", "meta": {"name": name}, "position": {"grow": 1, "basis": "400px"},
            "props": {"src": "", "style": {"border": "none"}},
            "propConfig": {"props.src": expr(src_expr)}}


# ----------------------------------------------------------------- overview
def summary_rows():
    F = "Facility"
    items = [("IT load", f"{F}/it_load_kw", "kW", "0.0", None),
             ("Facility power", f"{F}/facility_power_kw", "kW", "0.0", None),
             ("Cooling power", f"{F}/cooling_power_kw", "kW", "0.0", None),
             ("PUE", f"{F}/pue", "", "0.000", limit_color(tag(f"{F}/pue"), 1.5, 1.8)),
             ("Max rack inlet", f"{F}/max_inlet_c", "°C", "0.0", limit_color(tag(f"{F}/max_inlet_c"), 26, 27)),
             ("CHW supply / return", None, "°C", None, None),
             ("Ambient wet bulb", f"{F}/wetbulb_c", "°C", "0.0", None),
             ("Facility energy", f"{F}/energy_kwh", "kWh", "#,##0", None)]
    rows = []
    vst = {"textAlign": "right", "fontVariantNumeric": "tabular-nums", "fontWeight": "600"}
    for i, (lab, path, unit, p, col) in enumerate(items):
        if path is None:
            v = label("v", text_expr=f"{fmt(tag(F + '/chws_c'))} + ' / ' + {fmt(tag(F + '/chwr_c'))}", style=vst, grow=1)
        else:
            v = label("v", text_expr=fmt(tag(path), p), grow=1, style=vst, style_expr={"color": col} if col else None)
        rows.append(flex(f"k{i}", [label("l", lab, style={"color": MUTED}, grow=1),
                                   v, label("u", unit, style={"color": MUTED, "paddingLeft": "8px"}, basis="40px", shrink=0)],
                         align="center", shrink=0, style={"padding": "6px 10px", "borderBottom": f"1px solid {HEAD_ROW}"}))
    return flex("sum", rows, direction="column", shrink=0)


def rack_table():
    rows = []
    for i in range(1, 9):
        r = f"DataHall/R_{i:02d}"
        inlet = tag(r + "/inlet_c")
        rows.append([c_txt(f"R-{i:02d}"), (None, fmt(inlet), limit_color(inlet, 26, 27)),
                     c_num(r + "/outlet_c"), c_num(r + "/power_kw"),
                     (None, fmt(f"27 - {inlet}"), limit_color(inlet, 26, 27))])
    return table("racks", [("Rack", "64px", "left"), ("Inlet °C", "auto", "right"), ("Outlet °C", "auto", "right"),
                           ("Power kW", "auto", "right"), ("Margin K", "auto", "right")], rows)


def plant_status():
    rows = [[c_txt(a), c_state(p)] for a, p in (
        ("Chiller CH-01", "Cooling/CH_01/State"), ("Chiller CH-02", "Cooling/CH_02/State"),
        ("Pump P-01", "Cooling/P_01/State"), ("Pump P-02", "Cooling/P_02/State"), ("Pump P-03", "Cooling/P_03/State"),
        ("Generator GEN-01", "Electrical/GEN_01/State"), ("Switchgear SWG-01", "Electrical/SWG_01/State"))]
    return table("status", [("Asset", "auto", "left"), ("State", "auto", "left")], rows)


def overview_view() -> dict:
    left = panel("model", "Facility model",
                 flex("body", [iframe("twin3d", f"'{TWIN}/?embed=bare&view=datahall'")], grow=1),
                 grow=1, basis="600px", subtitle="Live 3D digital twin · drag to orbit, click an asset for details")
    right = flex("side", [
        panel("summary", "Facility summary", summary_rows(), grow=0, shrink=0),
        panel("racks", "Rack inlet temperature", rack_table(), grow=0, shrink=0, subtitle="ASHRAE recommended ≤ 27 °C"),
        panel("status", "Plant status", plant_status(), grow=0, shrink=0),
    ], direction="column", basis="460px", shrink=0, style={"overflowY": "auto"})
    root = flex("root", [left, right], style={"backgroundColor": BG, "padding": "4px", "fontFamily": FONT})
    return {"custom": {}, "params": {}, "props": {"defaultSize": {"height": 900, "width": 1600}}, "root": root}


# ----------------------------------------------------------------- equipment
def equipment_view() -> dict:
    def vib(path):
        return (None, fmt(tag(path), "0.00"), limit_color(tag(path), 4.5, 7.1))
    crah = [[c_txt(f"CRAH-{i:02d}"), c_num(f"Cooling/CRAH_{i:02d}/supply_c"), c_num(f"Cooling/CRAH_{i:02d}/return_c"),
             c_num(f"Cooling/CRAH_{i:02d}/valve_pct", "0"), c_num(f"Cooling/CRAH_{i:02d}/fan_speed_pct", "0"),
             c_num(f"Cooling/CRAH_{i:02d}/fan_kw", "0.00"), c_num(f"Cooling/CRAH_{i:02d}/coil_kw"),
             vib(f"Cooling/CRAH_{i:02d}/vib_mms"), c_state(f"Cooling/CRAH_{i:02d}/State")] for i in range(1, 5)]
    crah_t = table("t", [("Unit", "80px", "left"), ("Supply °C", "auto", "right"), ("Return °C", "auto", "right"),
                         ("Valve %", "auto", "right"), ("Fan %", "auto", "right"), ("Fan kW", "auto", "right"),
                         ("Coil kW", "auto", "right"), ("Vib mm/s", "auto", "right"), ("State", "110px", "left")], crah)
    ch = [[c_txt(c.replace("_", "-")), c_num(f"Cooling/{c}/load_kw"), c_num(f"Cooling/{c}/plr_pct", "0"),
           c_num(f"Cooling/{c}/power_kw"), c_num(f"Cooling/{c}/cop", "0.00"), c_num(f"Cooling/{c}/chws_c"),
           c_num(f"Cooling/{c}/cwe_c"), c_state(f"Cooling/{c}/State")] for c in ("CH_01", "CH_02")]
    ch_t = table("t", [("Unit", "80px", "left"), ("Load kW", "auto", "right"), ("PLR %", "auto", "right"),
                       ("Power kW", "auto", "right"), ("COP", "auto", "right"), ("CHWS °C", "auto", "right"),
                       ("CW in °C", "auto", "right"), ("State", "110px", "left")], ch)
    hx = [[c_txt("HX-01"), c_num("Cooling/HX_01/duty_kw"), c_num("Cooling/HX_01/effectiveness_pct", "0"),
           c_txt("—"), c_txt("—"), c_state("Cooling/HX_01/State")]]
    for t in ("CT_01", "CT_02"):
        hx.append([c_txt(t.replace("_", "-")), c_num(f"Cooling/{t}/heat_rej_kw"), c_txt("—"),
                   c_num(f"Cooling/{t}/approach_k"), c_num(f"Cooling/{t}/fan_kw", "0.00"), c_state(f"Cooling/{t}/State")])
    hx_t = table("t", [("Unit", "80px", "left"), ("Duty kW", "auto", "right"), ("Effectiveness %", "auto", "right"),
                       ("Approach K", "auto", "right"), ("Fan kW", "auto", "right"), ("State", "110px", "left")], hx)
    pumps = [[c_txt(p.replace("_", "-")), c_num(f"Cooling/{p}/speed_pct", "0"), c_num(f"Cooling/{p}/flow_ls", "0.00"),
              c_num(f"Cooling/{p}/head_kpa", "0"), c_num(f"Cooling/{p}/power_kw", "0.00"), c_num(f"Cooling/{p}/eff_pct", "0"),
              vib(f"Cooling/{p}/vib_mms"), c_state(f"Cooling/{p}/State")] for p in ("P_01", "P_02", "P_03")]
    pump_t = table("t", [("Pump", "80px", "left"), ("Speed %", "auto", "right"), ("Flow L/s", "auto", "right"),
                         ("Head kPa", "auto", "right"), ("Power kW", "auto", "right"), ("Eff %", "auto", "right"),
                         ("Vib mm/s", "auto", "right"), ("State", "110px", "left")], pumps)
    el = []
    for u in ("UPS_A", "UPS_B"):
        el.append([c_txt(u.replace("_", "-")), c_num(f"Electrical/{u}/load_kw"), c_num(f"Electrical/{u}/load_pct", "0"),
                   (None, fmt(tag(f"Electrical/{u}/eff_pct"), "0.0") + " + ' % eff'", None), c_state(f"Electrical/{u}/State")])
    for b in ("BAT_A", "BAT_B"):
        el.append([c_txt(b.replace("_", "-")), (None, fmt(tag(f"Electrical/{b}/soc_pct"), "0") + " + ' % SoC'", None),
                   (None, fmt(tag(f"Electrical/{b}/soh_pct"), "0") + " + ' % SoH'", None),
                   (None, fmt(tag(f"Electrical/{b}/runtime_min"), "0") + " + ' min'", None), c_state(f"Electrical/{b}/State")])
    for p in ("PDU_A", "PDU_B"):
        el.append([c_txt(p.replace("_", "-")), c_num(f"Electrical/{p}/load_kw"), c_num(f"Electrical/{p}/load_pct", "0"),
                   (None, fmt(tag(f"Electrical/{p}/imbalance_pct"), "0.0") + " + ' % imbal.'", None),
                   c_state(f"Electrical/{p}/State")])
    el.append([c_txt("TX-01"), (None, fmt(tag("Electrical/TX_01/load_kva")) + " + ' kVA'", None),
               c_num("Electrical/TX_01/load_pct", "0"), (None, fmt(tag("Electrical/TX_01/winding_c")) + " + ' °C'", None),
               c_state("Electrical/TX_01/State")])
    el.append([c_txt("GEN-01"), c_num("Electrical/GEN_01/power_kw"), c_txt("—"),
               (None, fmt(tag("Electrical/GEN_01/fuel_pct"), "0") + " + ' % fuel'", None), c_state("Electrical/GEN_01/State")])
    el.append([c_txt("SWG-01"), (None, fmt(tag("Electrical/SWG_01/bus_voltage_v"), "0") + " + ' V'", None), c_txt("—"),
               (None, f"case({tag('Electrical/SWG_01/source_code')}, 1, 'on utility', 2, 'on generator', 'no source')", None),
               c_state("Electrical/SWG_01/State")])
    el_t = table("t", [("Asset", "80px", "left"), ("Load / value", "auto", "right"), ("Load %", "auto", "right"),
                       ("Detail", "auto", "right"), ("State", "110px", "left")], el)
    root = flex("root", [
        flex("c1", [panel("air", "Air side", crah_t, grow=0, shrink=0),
                    panel("pumps", "Chilled-water pumps", pump_t, grow=0, shrink=0),
                    panel("hx", "Heat rejection", hx_t, grow=0, shrink=0)], direction="column", grow=1, basis="700px"),
        flex("c2", [panel("chillers", "Chillers", ch_t, grow=0, shrink=0),
                    panel("elec", "Electrical", el_t, grow=0, shrink=0)], direction="column", grow=1, basis="600px"),
    ], wrap=True, style={"backgroundColor": BG, "padding": "4px", "fontFamily": FONT, "overflowY": "auto"})
    return {"custom": {}, "params": {}, "props": {"defaultSize": {"height": 900, "width": 1600}}, "root": root}


# ----------------------------------------------------------------- scenarios (gateway-scoped Jython)
HDR = "{'X-DCX-Role': 'engineer', 'X-DCX-User': 'ignition-perspective'}"
BLANK = "{'label': '', 'unit': '', 'base': '', 'scen': '', 'delta': '', 'flag': ''}"

SCRIPT_RUN = f"""
	c = self.view.custom
	client = system.net.httpClient(timeout=15000)
	hdr = {HDR}
	try:
		q = '?scenario_id=' + str(c.scenario) + '&horizon_s=' + str(int(c.horizon_s))
		r = client.post(c.host + '/api/scenarios/requests' + q, headers=hdr)
		if not r.good:
			c.message = 'Request refused by the twin: ' + r.text[:200]
			return
		rid = r.json['request_id']
		a = client.post(c.host + '/api/scenarios/requests/' + rid + '/approve', headers=hdr)
		if not a.good:
			c.message = 'Approval refused by the twin: ' + a.text[:200]
			return
		run_id = a.json['run_id']
	except Exception as e:
		c.message = 'Twin service not reachable at ' + c.host + ' (' + str(e)[:120] + ')'
		return
	c.rows = [{BLANK} for i in range({NROWS})]
	c.run_id = run_id
	c.state = 'RUNNING'
	c.progress = 0
	c.applied = False
	c.branch = 'scenario'
	c.src = c.host + '/?embed=bare&view=datahall&run=' + run_id + '&branch=scenario'
	c.message = run_id + ' is running on an isolated copy of the twin. The live plant is not affected.'
"""

SCRIPT_POLL = f"""
	c = self.custom
	if not c.run_id or c.state not in ('RUNNING', 'QUEUED'):
		return
	try:
		j = system.net.httpClient(timeout=8000).get(c.host + '/api/scenarios/runs/' + c.run_id).json
	except Exception as e:
		c.message = 'Lost contact with the twin service while polling ' + c.run_id
		return
	c.progress = int(round(100.0 * float(j.get('progress') or 0)))
	st = j.get('status')
	if st == 'FAILED':
		c.state = 'FAILED'
		c.message = c.run_id + ' failed: ' + str(j.get('error'))
		return
	if st != 'COMPLETED':
		return
	def f(v, u):
		if v is None:
			return '-'
		if isinstance(v, basestring):
			return v
		if float(v) == int(v) and u in ('-', 's'):
			return '%d' % int(v)
		if u == 's' or abs(v) >= 100:
			return '%.0f' % v
		if u == '-':
			return ('%.3f' % v) if abs(v) < 10 else ('%.1f' % v)
		return '%.1f' % v
	rows = []
	for x in j['result']['comparison']:
		d = x.get('delta')
		ds = '' if d is None else (('+' if d > 0 else '') + f(d, x.get('unit')))
		w = x.get('worse')
		flag = '' if w is None else ('worse' if w else 'better')
		if ds.lstrip('+-').strip('0.') == '':
			ds, flag = '0', ''
		rows.append({{'label': x['label'], 'unit': x.get('unit') or '', 'base': f(x.get('baseline'), x.get('unit')),
		             'scen': f(x.get('scenario'), x.get('unit')), 'delta': ds, 'flag': flag}})
	while len(rows) < {NROWS}:
		rows.append({BLANK})
	c.rows = rows[:{NROWS}]
	c.progress = 100
	c.state = 'COMPLETED'
	c.message = c.run_id + ' complete. Review the predicted impact and the 3D playback, then apply to the live plant if required.'
"""

SCRIPT_APPLY = f"""
	c = self.view.custom
	try:
		r = system.net.httpClient(timeout=15000).post(c.host + '/api/scenarios/runs/' + c.run_id + '/apply', headers={HDR})
	except Exception as e:
		c.message = 'Twin service not reachable (' + str(e)[:120] + ')'
		return
	if not r.good:
		c.message = 'Apply refused: ' + r.text[:200]
		return
	now = system.date.now()
	c.applied = True
	c.branch = 'live'
	c.src = c.host + '/?embed=bare&view=datahall&t=' + str(system.date.toMillis(now))
	c.message = c.run_id + ' applied to the live plant at ' + system.date.format(now, 'HH:mm:ss') + '. All screens, tags and the 3D model now show the injected condition.'
"""

SCRIPT_CLEAR = f"""
	c = self.view.custom
	try:
		r = system.net.httpClient(timeout=15000).post(c.host + '/api/live/clear_faults', headers={HDR})
	except Exception as e:
		c.message = 'Twin service not reachable (' + str(e)[:120] + ')'
		return
	now = system.date.now()
	c.applied = False
	c.branch = 'live'
	c.src = c.host + '/?embed=bare&view=datahall&t=' + str(system.date.toMillis(now))
	c.message = 'Live faults cleared and tripped equipment reset at ' + system.date.format(now, 'HH:mm:ss') + '.'
"""


def show_script(branch):
    if branch == "live":
        src = "c.host + '/?embed=bare&view=datahall&t=' + str(system.date.toMillis(system.date.now()))"
        guard = ""
    else:
        src = f"c.host + '/?embed=bare&view=datahall&run=' + c.run_id + '&branch={branch}'"
        guard = "\tif not c.run_id:\n\t\treturn\n"
    return f"\n\tc = self.view.custom\n{guard}\tc.branch = '{branch}'\n\tc.src = {src}\n"


def button(name, text, script, primary=False, enabled_expr=None):
    st = {"fontFamily": FONT, "fontSize": "13px", "borderRadius": "2px", "margin": "0 6px 6px 0", "padding": "0 14px",
          "height": "32px", "boxShadow": "none"}
    st.update({"backgroundColor": ACCENT, "color": "#FFFFFF", "border": f"1px solid {ACCENT}"} if primary else
              {"backgroundColor": PANEL, "color": TEXT, "border": f"1px solid {BORDER}"})
    b = {"type": "ia.input.button", "meta": {"name": name}, "position": {"basis": "auto", "shrink": 0},
         "props": {"text": text, "style": st},
         "events": {"component": {"onActionPerformed": {"type": "script", "scope": "G", "config": {"script": script}}}}}
    if enabled_expr:
        b["propConfig"] = {"props.enabled": expr(enabled_expr)}
    return b


def seg_button(name, text, branch):
    en = None if branch == "live" else "len({view.custom.run_id}) > 0 && {view.custom.state} = 'COMPLETED'"
    b = button(name, text, show_script(branch), enabled_expr=en)
    act = f"{{view.custom.branch}} = '{branch}'"
    b["propConfig"] = dict(b.get("propConfig", {}))
    b["propConfig"]["props.style.backgroundColor"] = expr(f"if({act}, '{HEAD_ROW}', '{PANEL}')")
    b["propConfig"]["props.style.fontWeight"] = expr(f"if({act}, '600', '400')")
    return b


def scenarios_view(catalogue) -> dict:
    options = [{"value": s["id"], "label": f"{s['id']}  {s['title']}"} for s in catalogue]
    desc = {s["id"]: s["description"] for s in catalogue}
    field = lambda n, t: label(n, t, style={"color": MUTED, "fontSize": "12px", "margin": "10px 0 4px 0"}, shrink=0)
    dd_style = {"fontFamily": FONT, "fontSize": "13px", "borderRadius": "2px"}
    dd = {"type": "ia.input.dropdown", "meta": {"name": "scenario"}, "position": {"basis": "34px", "shrink": 0},
          "props": {"options": options, "value": "S11", "showClearIcon": False, "style": dd_style},
          "propConfig": {"props.value": prop("view.custom.scenario", True)}}
    hz = {"type": "ia.input.dropdown", "meta": {"name": "horizon"}, "position": {"basis": "34px", "shrink": 0},
          "props": {"options": [{"value": 900, "label": "15 min"}, {"value": 1800, "label": "30 min"},
                                {"value": 3600, "label": "60 min"}, {"value": 7200, "label": "120 min"}],
                    "value": 1800, "showClearIcon": False, "style": dd_style},
          "propConfig": {"props.value": prop("view.custom.horizon_s", True)}}
    status = label("status", shrink=0, text_expr=(
        "if({view.custom.state} = 'RUNNING', 'Running ' + toStr({view.custom.progress}) + ' %', "
        "if({view.custom.state} = 'COMPLETED', if({view.custom.applied}, 'Applied to live plant', 'Complete, not applied'), "
        "if({view.custom.state} = 'FAILED', 'Failed', 'Idle')))"),
        style={"fontWeight": "600", "margin": "8px 0 2px 0"},
        style_expr={"color": f"if({{view.custom.state}} = 'FAILED', '{ALARM}', if({{view.custom.applied}}, '{WARN}', '{TEXT}'))"})
    wrap = {"color": MUTED, "fontSize": "12px", "whiteSpace": "normal"}
    controls = flex("controls", [
        field("f1", "Scenario"), dd,
        label("desc", text_expr="{view.custom.description}", shrink=0, style={**wrap, "marginTop": "6px"}),
        field("f2", "Prediction horizon"), hz,
        label("note", "Uses the catalogue's default parameters. The what-if runs on an isolated copy of the twin; "
                      "the live plant changes only when the result is applied.", shrink=0, style={**wrap, "margin": "10px 0"}),
        flex("btns", [button("run", "Run what-if", SCRIPT_RUN, primary=True, enabled_expr="{view.custom.state} != 'RUNNING'"),
                      button("apply", "Apply to live plant", SCRIPT_APPLY,
                             enabled_expr="{view.custom.state} = 'COMPLETED' && !{view.custom.applied}"),
                      button("clear", "Clear live faults", SCRIPT_CLEAR)], wrap=True, shrink=0),
        status,
        label("msg", text_expr="{view.custom.message}", style=wrap, shrink=0),
    ], direction="column", shrink=0, style={"padding": "10px 12px"})

    cols = [("Indicator", "auto", "left"), ("Unit", "44px", "left"), ("Baseline", "80px", "right"),
            ("Scenario", "80px", "right"), ("Change", "80px", "right")]
    rows = []
    for i in range(NROWS):
        p = lambda k: f"try({{view.custom.rows[{i}].{k}}}, '')"
        rows.append([(None, p("label"), None), (None, p("unit"), None), (None, p("base"), None), (None, p("scen"), None),
                     (None, p("delta"), f"if({p('flag')} = 'worse', '{ALARM}', '{TEXT}')")])
    results = table("cmp", cols, rows)

    left = flex("left", [panel("ctl", "What-if scenario", controls, grow=0, shrink=0),
                         panel("res", "Predicted impact over the horizon", results, grow=0, shrink=0,
                               subtitle="red = worse than baseline")],
                direction="column", basis="520px", shrink=0, style={"overflowY": "auto"})
    seg = flex("seg", [label("l", "Show", style={"color": MUTED, "fontSize": "12px", "marginRight": "8px"}, shrink=0),
                       seg_button("s1", "Scenario", "scenario"), seg_button("s2", "Baseline", "baseline"),
                       seg_button("s3", "Live plant", "live")], align="center", shrink=0,
               style={"padding": "6px 10px 0 10px"})
    right = panel("model", "3D model", flex("body", [seg, iframe("twin3d", "{view.custom.src}")], direction="column", grow=1),
                  grow=1, basis="600px", subtitle="what-if playback or live plant")
    root = flex("root", [left, right], style={"backgroundColor": BG, "padding": "4px", "fontFamily": FONT})
    custom = {"host": TWIN, "scenario": "S11", "horizon_s": 1800, "description": desc.get("S11", ""),
              "desc": desc, "run_id": "", "state": "IDLE", "progress": 0, "applied": False, "branch": "live",
              "src": f"{TWIN}/?embed=bare&view=datahall", "message": "Select a scenario and run a what-if.",
              "rows": [{"label": "", "unit": "", "base": "", "scen": "", "delta": "", "flag": ""} for _ in range(NROWS)],
              "tick": 0}
    prop_config = {
        "custom.tick": {"binding": {"type": "expr", "config": {"expression": "now(1500)"}},
                        "onChange": {"enabled": None, "script": SCRIPT_POLL}},
        "custom.scenario": {"onChange": {"enabled": None, "script":
                            "\n\ttry:\n\t\tself.custom.description = self.custom.desc[currentValue.value]\n"
                            "\texcept:\n\t\tself.custom.description = ''\n"}},
    }
    return {"custom": custom, "params": {}, "propConfig": prop_config,
            "props": {"defaultSize": {"height": 900, "width": 1600}}, "root": root}


# ----------------------------------------------------------------- alarms
def alarms_view() -> dict:
    table_c = {"type": "ia.display.alarmstatustable", "meta": {"name": "alarms"},
               "position": {"grow": 1, "basis": "400px"},
               "props": {"filters": {"active": {"conditions": {"source": "*DATACORE_X*"}}}}}
    phil = [("Critical", PRIO_COL[4], "Equipment tripped; rack inlet > 32 °C (ASHRAE A1 allowable); twin data link lost",
             "Immediate action"),
            ("High", PRIO_COL[3], "Vibration in ISO 10816 zone D (≥ 7.1 mm/s); rack inlet > 27 °C",
             "Act within minutes"),
            ("Medium", PRIO_COL[2], "Vibration in ISO 10816 zone C (≥ 4.5 mm/s); CHW supply > 20.5 °C",
             "Plan maintenance"),
            ("Low", PRIO_COL[1], "Advisory (reserved)", "For information")]
    rows = []
    for i, (p, col, cond, resp) in enumerate(phil):
        rows.append(flex(f"p{i}", [
            label("sw", "", basis="6px", shrink=0, style={"backgroundColor": col, "margin": "4px 10px 4px 0"}),
            label("p", p, basis="70px", shrink=0, style={"fontWeight": "600"}),
            label("c", cond, grow=1, style={"whiteSpace": "normal"}),
            label("r", resp, basis="130px", shrink=0, style={"color": MUTED})],
            align="stretch", shrink=0, style={"padding": "6px 10px", "borderBottom": f"1px solid {HEAD_ROW}"}))
    rows.append(label("note", "ISA-18.2 lifecycle: every alarm needs operator acknowledgement (Ack Mode = Manual). "
                              "Active-unacknowledged, active-acknowledged and cleared-unacknowledged states are shown; "
                              "alarms can be shelved from the table. Thresholds are set on the tags by ignition/add_alarms.py.",
                      shrink=0, style={"color": MUTED, "fontSize": "12px", "whiteSpace": "normal", "padding": "8px 10px"}))
    phil_p = panel("phil", "Alarm philosophy", flex("b", rows, direction="column", shrink=0), grow=0, shrink=0)
    tbl = panel("tbl", "Active alarms", flex("b", [table_c], direction="column", grow=1), grow=1, basis="500px",
                subtitle="select to acknowledge or shelve")
    root = flex("root", [tbl, phil_p], direction="column",
                style={"backgroundColor": BG, "padding": "4px", "fontFamily": FONT})
    return {"custom": {}, "params": {}, "props": {"defaultSize": {"height": 900, "width": 1600}}, "root": root}


# ----------------------------------------------------------------- maintenance (work orders)
WO_POLL = f"""
	import system
	client = system.net.httpClient(timeout=5000)
	try:
		wo = client.get('{TWIN}/api/workorders').json
		pol = client.get('{TWIN}/api/policy').json
	except Exception as e:
		return {{'ok': False, 'msg': 'Twin service not reachable', 'items': [], 'open': 0, 'policy': {{}}, 'replay': [], 'speed': 0}}
	items = []
	for w in wo.get('items', [])[:8]:
		rul = w.get('rul_h')
		items.append({{'id': w['wo_id'], 'asset': w['asset'], 'title': w.get('title', ''), 'priority': w.get('priority', ''),
		              'status': w['status'], 'hi': w.get('health_index'), 'rul': '-' if rul is None else '%.2f' % rul,
		              'due': (w.get('due_clock') or '')[11:16], 'fault': w.get('fault') or '', 'crit': w.get('criticality') or '',
		              'actions': w.get('recommended_actions') or [], 'parts': w.get('parts') or [],
		              'ctl': [a.get('clock', '')[11:16] + '  ' + a.get('text', '') for a in (w.get('control_actions') or [])],
		              'src': (w.get('evidence') or {{}}).get('data_source', 'Live digital-twin measurements'),
		              'vib': (w.get('evidence') or {{}}).get('vibration_mms'), 'zone': (w.get('evidence') or {{}}).get('iso10816_zone'),
		              'raised': (w.get('created_clock') or '')[11:16], 'trade': w.get('trade') or '', 'hours': w.get('est_labour_h'),
		              'acts_txt': '\\n'.join(['%d. %s' % (i + 1, a) for i, a in enumerate(w.get('recommended_actions') or [])]),
		              'ctl_txt': '\\n'.join([a.get('clock', '')[11:16] + '  ' + a.get('text', '') for a in (w.get('control_actions') or [])]) or 'None yet'}})
	while len(items) < 8:
		items.append({{'id': '', 'asset': '', 'title': '', 'priority': '', 'status': '', 'hi': 0, 'rul': '', 'due': '',
		              'fault': '', 'crit': '', 'actions': [], 'parts': [], 'ctl': [], 'src': '', 'vib': 0, 'zone': '',
		              'raised': '', 'trade': '', 'hours': 0, 'acts_txt': '', 'ctl_txt': ''}})
	return {{'ok': True, 'msg': '', 'items': items, 'open': wo.get('open', 0), 'policy': pol.get('health_aware_changeover', {{}}),
	        'replay': pol.get('replay', []), 'speed': pol.get('speed', 0)}}
"""


def wo_action(action, label_text, primary=False, enabled_expr=None):
    script = f"""
	import system
	c = self.view.custom
	if not c.sel:
		c.msg = 'Select a work order first.'
		return
	try:
		r = system.net.httpClient(timeout=10000).post('{TWIN}/api/workorders/' + c.sel + '/{action}',
		    headers={{'X-DCX-Role': 'engineer', 'X-DCX-User': 'ignition-maintenance'}}, data={{'note': 'from Ignition'}})
		c.msg = (c.sel + ': {action} done') if r.good else ('Refused: ' + r.text[:160])
	except Exception as e:
		c.msg = 'Twin service not reachable'
	self.view.refreshBinding('custom.wo')
"""
    return button(f"b_{action}", label_text, script, primary=primary, enabled_expr=enabled_expr)


def link_button(name, text, url_expr):
    script = f"\n\timport system\n\tc = self.view.custom\n\tif c.sel:\n\t\tsystem.perspective.navigate(url={url_expr}, newTab=True)\n"
    return button(name, text, script)


def speed_button(name, text, speed):
    script = f"""
	import system
	try:
		system.net.httpClient(timeout=5000).post('{TWIN}/api/sim/speed', headers={{'X-DCX-Role': 'engineer'}}, data={{'speed': {speed}}})
	except Exception:
		pass
	self.view.refreshBinding('custom.wo')
"""
    return button(name, text, script)


POLICY_TOGGLE = f"""
	import system
	en = not bool(self.view.custom.wo.policy.enabled)
	try:
		system.net.httpClient(timeout=5000).post('{TWIN}/api/policy', headers={{'X-DCX-Role': 'engineer'}}, data={{'enabled': en}})
	except Exception:
		pass
	self.view.refreshBinding('custom.wo')
"""


BLANK_WO = {"id": "", "asset": "", "title": "", "priority": "", "status": "", "hi": 0, "rul": "", "due": "", "fault": "",
            "crit": "", "actions": [], "parts": [], "ctl": [], "src": "", "vib": 0, "zone": "", "raised": "", "trade": "",
            "hours": 0, "acts_txt": "", "ctl_txt": ""}


def maintenance_view() -> dict:
    W = "{view.custom.wo"
    sel = "{view.custom.sel}"
    cols = [("WO", "84px", "left"), ("Asset", "64px", "left"), ("Work", "auto", "left"), ("Priority", "104px", "left"),
            ("Status", "110px", "left"), ("HI", "48px", "right"), ("RUL h", "60px", "right"), ("Due", "56px", "right")]
    rows = []
    for i in range(8):
        f = lambda k: f"try({W}.items[{i}].{k}}}, '')"
        prio_col = f"if(indexOf(toStr({f('priority')}), 'P1') >= 0, '{ALARM}', if(indexOf(toStr({f('priority')}), 'P2') >= 0, '{WARN}', '{TEXT}'))"
        rows.append([(None, f("id"), None), (None, f("asset"), None), (None, f("title"), None), (None, f("priority"), prio_col),
                     (None, f("status"), f"if({f('status')} = 'CLOSED', '{MUTED}', '{TEXT}')"),
                     (None, f"if(len({W}.items[{i}].id}}) = 0, '', numberFormat({W}.items[{i}].hi}}, '0'))", None),
                     (None, f("rul"), None), (None, f("due"), None)])
    tbl = table("wo", cols, rows)
    for i, r in enumerate(tbl["children"][1:]):
        r["events"] = {"dom": {"onClick": {"type": "script", "scope": "G", "config": {
            "script": f"\n\tv = self.view.custom.wo.items[{i}].id\n\tif v:\n\t\tself.view.custom.sel = v\n\t\tself.view.refreshBinding('custom.det')\n"}}}}
        r["propConfig"] = {"props.style.backgroundColor": expr(
            f"if(try({W}.items[{i}].id}}, '') = {sel} && len({sel}) > 0, '{HEAD_ROW}', '{PANEL}')")}
        r["props"]["style"]["cursor"] = "pointer"
    # selected-order detail
    D = "{view.custom.det"
    kv = lambda n, k, e: flex(n, [label("k", k, style={"color": MUTED}, basis="150px", shrink=0),
                                  label("v", text_expr=e, grow=1, style={"whiteSpace": "normal"})],
                              shrink=0, style={"padding": "5px 10px", "borderBottom": f"1px solid {HEAD_ROW}"})
    lst = lambda n, e: label(n, text_expr=e, shrink=0, style={"whiteSpace": "pre-line", "padding": "6px 10px", "fontSize": "13px"})
    detail = flex("det", [
        kv("k1", "Work order", f"if(len({D}.id}}) = 0, 'Select a work order in the list', {D}.id}} + '  ·  ' + {D}.priority}} + '  ·  ' + {D}.status}})"),
        kv("k2", "Asset / criticality", f"if(len({D}.id}}) = 0, '', {D}.asset}} + '  ·  ' + {D}.crit}})"),
        kv("k3", "Likely fault", f"{D}.fault}}"),
        kv("k4", "Health / RUL", f"if(len({D}.id}}) = 0, '', 'HI ' + numberFormat({D}.hi}}, '0') + ' / 100  ·  RUL ' + {D}.rul}} + ' h  ·  due ' + {D}.due}})"),
        kv("k5", "Vibration", f"if(len({D}.id}}) = 0 || isNull({D}.vib}}), '', numberFormat({D}.vib}}, '0.00') + ' mm/s (ISO 10816 zone ' + {D}.zone}} + ')')"),
        kv("k6", "Data source", f"{D}.src}}"),
        kv("k7", "Trade / labour", f"if(len({D}.id}}) = 0, '', {D}.trade}} + '  ·  ' + numberFormat({D}.hours}}, '0.0') + ' h')"),
        label("h1", "Recommended actions", shrink=0, style={"fontWeight": "600", "padding": "10px 10px 0 10px"}),
        lst("acts", f"{D}.acts_txt}}"),
        label("h2", "Control actions already taken", shrink=0, style={"fontWeight": "600", "padding": "6px 10px 0 10px"}),
        lst("ctl", f"{D}.ctl_txt}}"),
        flex("btns", [wo_action("ack", "Acknowledge", True), wo_action("schedule", "Schedule"),
                      wo_action("close", "Work done: close"),
                      link_button("pdf", "Print / PDF", f"'{TWIN}/api/workorders/' + c.sel + '/print'"),
                      link_button("json", "CMMS JSON", f"'{TWIN}/api/workorders/' + c.sel + '/cmms.json'")],
             wrap=True, shrink=0, style={"padding": "10px"}),
        label("msg", text_expr="{view.custom.msg}", shrink=0, style={"color": MUTED, "fontSize": "12px", "padding": "0 10px 10px 10px"}),
    ], direction="column", shrink=0)
    status = flex("ctl", [
        label("pol", shrink=0, text_expr=f"'Health-aware changeover: ' + if({W}.policy.enabled}}, 'ON (bearing faults: HI < ' + numberFormat({W}.policy.hi_below}}, '0') + ' or RUL < ' + numberFormat({W}.policy.rul_below_min}}, '0') + ' min)', 'OFF')",
              style={"fontWeight": "600", "marginRight": "10px"}),
        button("tog", "Toggle", POLICY_TOGGLE),
        label("sp", shrink=0, text_expr=f"'Simulation speed ' + numberFormat({W}.speed}}, '0') + 'x'",
              style={"color": MUTED, "margin": "0 8px 0 18px"}),
        speed_button("s10", "10x", 10), speed_button("s60", "60x", 60), speed_button("s120", "120x", 120),
        label("rp", grow=1, text_expr=f"if(len(toStr({W}.replay}})) > 2, 'Replaying measured data: ' + {W}.replay[0].bearing}} + ' on ' + {W}.replay[0].asset}} + ', bearing life ' + numberFormat(100 * {W}.replay[0].life_frac}}, '0') + ' % elapsed', '')",
              style={"color": WARN, "fontWeight": "600", "marginLeft": "18px"}),
    ], align="center", wrap=True, shrink=0, style={"padding": "10px"})
    left = flex("left", [panel("pol", "Maintenance automation", status, grow=0, shrink=0),
                         panel("list", "Work orders", tbl, grow=0, shrink=0,
                               subtitle="raised automatically from Health Index and RUL · click a row")],
                direction="column", grow=1, basis="760px", style={"overflowY": "auto"})
    right = panel("detail", "Selected work order", detail, grow=0, basis="520px", shrink=0)
    root = flex("root", [left, right], style={"backgroundColor": BG, "padding": "4px", "fontFamily": FONT})
    custom = {"wo": {"ok": False, "items": [dict(BLANK_WO) for _ in range(8)], "open": 0, "policy": {"enabled": False, "hi_below": 0, "rul_below_min": 0},
                     "replay": [], "speed": 0}, "sel": "", "det": dict(BLANK_WO), "msg": ""}
    pc = {"custom.wo": {"binding": {"type": "expr", "config": {"expression": "now(2000)"},
                                    "transforms": [{"type": "script", "code": WO_POLL}]}},
          "custom.det": {"binding": {"type": "expr", "config": {"expression": "now(2000)"},
                                     "transforms": [{"type": "script", "code":
                                         "\n\tsel = self.view.custom.sel\n\tfor w in self.view.custom.wo['items']:\n\t\tif sel and w['id'] == sel:\n\t\t\treturn w\n\treturn " + repr(BLANK_WO) + "\n"}]}}}
    return {"custom": custom, "params": {}, "propConfig": pc,
            "props": {"defaultSize": {"height": 900, "width": 1600}}, "root": root}


# ----------------------------------------------------------------- comparison
def compare_view() -> dict:
    body = flex("body", [iframe("cmp", f"'{TWIN}/compare/'")], grow=1)
    root = flex("root", [panel("cmp", "Conventional EMPC vs PI-HA-EMPC", body, grow=1,
                               subtitle="recorded closed-loop MATLAB runs · identical plant, weather, load and fault")],
                style={"backgroundColor": BG, "padding": "4px", "fontFamily": FONT})
    return {"custom": {}, "params": {}, "props": {"defaultSize": {"height": 900, "width": 1600}}, "root": root}


# ----------------------------------------------------------------- project packaging
def page_config() -> dict:
    dock = {"top": [{"anchor": "fixed", "autoBreakpoint": 480, "content": "push", "handle": "hide", "iconUrl": "",
                     "id": "dcx-header", "modal": False, "resizable": False, "show": "visible", "size": 44,
                     "viewParams": {}, "viewPath": "DCX/Header"}]}
    return {"pages": {"/": {"docks": dock, "title": "DATACORE-X · Overview", "viewPath": "DCX/Overview"},
                      "/equipment": {"docks": dock, "title": "DATACORE-X · Equipment", "viewPath": "DCX/Equipment"},
                      "/scenarios": {"docks": dock, "title": "DATACORE-X · Scenarios", "viewPath": "DCX/Scenarios"},
                      "/alarms": {"docks": dock, "title": "DATACORE-X · Alarms", "viewPath": "DCX/Alarms"},
                      "/maintenance": {"docks": dock, "title": "DATACORE-X · Maintenance", "viewPath": "DCX/Maintenance"},
                      "/compare": {"docks": dock, "title": "DATACORE-X · Controller comparison", "viewPath": "DCX/Compare"},
                      "/twin": {"docks": dock, "title": "DATACORE-X · 3D twin", "viewPath": "DCX/Twin3D"}},
            "sharedDocks": {}}


def resource(files):
    return json.dumps({"scope": "G", "version": 1, "restricted": False, "overridable": True, "files": files,
                       "attributes": {"lastModification": {"actor": "dcx-build",
                                      "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}}}, indent=2)


def load_catalogue():
    try:
        return httpx.get(f"{TWIN}/api/scenarios", timeout=5).json()
    except Exception:
        sys.exit(f"twin service not reachable at {TWIN}; start the backend first (needed for the scenario catalogue)")


def merge(base: bytes | None, catalogue) -> bytes:
    twin = json.loads((HERE / "perspective" / "view.json").read_text(encoding="utf-8"))
    views = {"DCX/Header": header_view(), "DCX/Overview": overview_view(), "DCX/Equipment": equipment_view(),
             "DCX/Scenarios": scenarios_view(catalogue), "DCX/Alarms": alarms_view(), "DCX/Compare": compare_view(),
             "DCX/Maintenance": maintenance_view(),
             "DCX/Twin3D": twin}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        skip = (f"{PV}/views/DCX/", f"{PV}/page-config/")
        if base:
            with zipfile.ZipFile(io.BytesIO(base)) as b:
                for n in b.namelist():
                    if not n.startswith(skip):
                        z.writestr(n, b.read(n))
        else:
            z.writestr("project.json", json.dumps({"title": "DATACORE-X", "description": "", "enabled": True,
                                                   "inheritable": False, "parent": ""}, indent=2))
        for path, view in views.items():
            z.writestr(f"{PV}/views/{path}/view.json", json.dumps(view, indent=2, ensure_ascii=False))
            z.writestr(f"{PV}/views/{path}/resource.json", resource(["view.json"]))
        z.writestr(f"{PV}/page-config/config.json", json.dumps(page_config(), indent=2))
        z.writestr(f"{PV}/page-config/resource.json", resource(["config.json"]))
    return out.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", default="http://localhost:8088")
    ap.add_argument("--project", default="DATACORE_X")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    build = HERE / "_build"
    build.mkdir(exist_ok=True)
    cat = load_catalogue()
    if not a.apply:
        zp = build / f"{a.project}_perspective.zip"
        zp.write_bytes(merge(None, cat))
        print(f"wrote {zp} (not imported; use --apply)")
        return
    tok = KEY.read_text(encoding="utf-8").strip()
    c = httpx.Client(base_url=a.gateway, headers={"X-Ignition-API-Token": tok}, timeout=60)
    r = c.get(f"/data/api/v1/projects/export/{a.project}")
    if r.status_code != 200:
        sys.exit(f"export {a.project} -> HTTP {r.status_code} {r.text[:200]}")
    (build / f"{a.project}_backup.zip").write_bytes(r.content)
    data = merge(r.content, cat)
    (build / f"{a.project}_perspective.zip").write_bytes(data)
    url = f"/data/api/v1/projects/import/{a.project}"
    r = c.post(url, params={"overwrite": "true"}, content=data, headers={"Content-Type": "application/zip"})
    if r.status_code >= 300:
        r = c.post(url, params={"overwrite": "true"}, files={"file": (f"{a.project}.zip", data, "application/zip")})
    print(f"import -> HTTP {r.status_code} {r.text[:400]}")
    r = c.get(f"/data/api/v1/projects/export/{a.project}")
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist() if r.status_code == 200 else []
    ok = all(any(n.startswith(f"{PV}/views/DCX/{v}/") for n in names)
             for v in ("Overview", "Header", "Equipment", "Scenarios", "Alarms", "Compare", "Maintenance"))
    print(f"verify: DCX views present in project = {ok}")
    r = c.post("/data/api/v1/scan/projects")
    print(f"project scan -> HTTP {r.status_code}")
    print(f"open: {a.gateway}/data/perspective/client/{a.project}")


if __name__ == "__main__":
    main()
