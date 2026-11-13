"""DATACORE-X asset registry — the single source of truth.

Every consumer (surrogate plant, MATLAB bridge, historian, OPC UA adapter,
Ignition tag export and the 3D frontend) resolves assets, hierarchy, data
points, engineering units and scene placement from this module.  The JSON
written by ``export_registry`` is what the browser loads, so the 3D scene can
never reference an asset or tag the backend does not publish.

Coordinate system (metres): x = east, z = south, y = up.  Ground y = 0,
raised-floor top in the data hall y = 0.6.  ``pos`` is the base-centre of the
equipment footprint, ``size`` = [width_x, height_y, depth_z].
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

REGISTRY_VERSION = "1.0.0"
FLOOR_Y = 0.6  # raised floor top in data hall

# ---------------------------------------------------------------------------
# Data point templates per asset type: (key, label, unit, decimals)
# ---------------------------------------------------------------------------
TAG_TEMPLATES: dict[str, list[tuple[str, str, str, int]]] = {
    "rack": [
        ("cpu_util", "CPU utilisation", "%", 1),
        ("gpu_util", "GPU utilisation", "%", 1),
        ("power_kw", "Rack power", "kW", 2),
        ("inlet_c", "Inlet temperature", "°C", 2),
        ("outlet_c", "Outlet temperature", "°C", 2),
        ("airflow_m3s", "Server airflow", "m³/s", 3),
        ("heat_kw", "Heat generation", "kW", 2),
    ],
    "crah": [
        ("fan_speed_pct", "Fan speed", "%", 1),
        ("airflow_m3s", "Supply airflow", "m³/s", 2),
        ("supply_c", "Supply air temperature", "°C", 2),
        ("return_c", "Return air temperature", "°C", 2),
        ("valve_pct", "CHW valve position", "%", 1),
        ("chw_flow_ls", "CHW coil flow", "L/s", 2),
        ("coil_kw", "Coil duty", "kW", 1),
        ("fan_kw", "Fan power", "kW", 2),
        ("vib_mms", "Fan vibration", "mm/s", 2),
    ],
    "chiller": [
        ("load_kw", "Evaporator load", "kW", 1),
        ("plr_pct", "Part-load ratio", "%", 1),
        ("cop", "COP", "-", 2),
        ("power_kw", "Compressor power", "kW", 1),
        ("chws_c", "CHW leaving temperature", "°C", 2),
        ("chwr_c", "CHW entering temperature", "°C", 2),
        ("cwe_c", "Condenser water entering", "°C", 2),
        ("cwl_c", "Condenser water leaving", "°C", 2),
        ("capacity_kw", "Available capacity", "kW", 1),
    ],
    "pump": [
        ("speed_pct", "Speed", "%", 1),
        ("flow_ls", "Flow", "L/s", 2),
        ("head_kpa", "Differential head", "kPa", 1),
        ("power_kw", "Shaft power", "kW", 2),
        ("eff_pct", "Hydraulic efficiency", "%", 1),
        ("vib_mms", "Vibration (RMS)", "mm/s", 2),
        ("current_a", "Motor current", "A", 1),
    ],
    "hx": [
        ("duty_kw", "Heat duty", "kW", 1),
        ("effectiveness_pct", "Effectiveness", "%", 1),
        ("chw_in_c", "CHW in", "°C", 2),
        ("chw_out_c", "CHW out", "°C", 2),
        ("cw_in_c", "CW in", "°C", 2),
        ("cw_out_c", "CW out", "°C", 2),
        ("ua_kwk", "Effective UA", "kW/K", 2),
    ],
    "tower": [
        ("fan_speed_pct", "Fan speed", "%", 1),
        ("leaving_c", "Leaving water", "°C", 2),
        ("entering_c", "Entering water", "°C", 2),
        ("heat_rej_kw", "Heat rejection", "kW", 1),
        ("fan_kw", "Fan power", "kW", 2),
        ("approach_k", "Approach", "K", 2),
        ("wetbulb_c", "Ambient wet-bulb", "°C", 2),
    ],
    "pipe": [
        ("flow_ls", "Flow", "L/s", 2),
        ("temp_c", "Temperature", "°C", 2),
        ("velocity_ms", "Mean velocity", "m/s", 2),
    ],
    "zone": [
        ("temp_c", "Zone temperature", "°C", 2),
        ("rh_pct", "Relative humidity", "%", 1),
    ],
    "transformer": [
        ("load_kva", "Load", "kVA", 1),
        ("load_pct", "Loading", "%", 1),
        ("losses_kw", "Losses", "kW", 2),
        ("winding_c", "Winding hot-spot", "°C", 1),
        ("lv_voltage_v", "LV voltage", "V", 1),
    ],
    "switchgear": [
        ("bus_voltage_v", "Bus voltage", "V", 1),
        ("bus_current_a", "Bus current", "A", 1),
        ("frequency_hz", "Frequency", "Hz", 2),
        ("mech_load_kw", "Mechanical bus load", "kW", 1),
        ("source_code", "Source (0 none,1 utility,2 generator)", "-", 0),
    ],
    "generator": [
        ("power_kw", "Output power", "kW", 1),
        ("frequency_hz", "Frequency", "Hz", 2),
        ("fuel_pct", "Fuel level", "%", 1),
        ("run_s", "Run time", "s", 0),
    ],
    "ups": [
        ("load_kw", "Output load", "kW", 1),
        ("load_pct", "Loading", "%", 1),
        ("eff_pct", "Efficiency", "%", 2),
        ("losses_kw", "Losses", "kW", 2),
        ("input_v", "Input voltage", "V", 1),
        ("output_v", "Output voltage", "V", 1),
    ],
    "battery": [
        ("soc_pct", "State of charge", "%", 1),
        ("soh_pct", "State of health", "%", 1),
        ("voltage_v", "String voltage", "V", 1),
        ("current_a", "Current (+dis/-chg)", "A", 1),
        ("temp_c", "Battery temperature", "°C", 2),
        ("runtime_min", "Estimated runtime", "min", 1),
        ("rint_mohm", "Internal resistance", "mΩ", 1),
    ],
    "pdu": [
        ("load_kw", "Load", "kW", 2),
        ("load_pct", "Loading", "%", 1),
        ("current_l1_a", "Current L1", "A", 1),
        ("current_l2_a", "Current L2", "A", 1),
        ("current_l3_a", "Current L3", "A", 1),
        ("imbalance_pct", "Phase imbalance", "%", 1),
    ],
}

# Asset types that carry an Equipment Health Index / RUL from the intelligence layer
HEALTH_TYPES = {"pump", "crah", "chiller", "battery", "ups", "hx", "tower"}

# Ignition-style folder per type
IGN_FOLDER = {
    "rack": "DataHall", "zone": "DataHall", "pdu": "Electrical",
    "crah": "Cooling", "chiller": "Cooling", "pump": "Cooling", "hx": "Cooling",
    "tower": "Cooling", "pipe": "Cooling",
    "transformer": "Electrical", "switchgear": "Electrical", "generator": "Electrical",
    "ups": "Electrical", "battery": "Electrical",
}


def _asset(aid, name, atype, layer, parent, pos, size, rot=0.0, **extra):
    a = {
        "id": aid, "name": name, "type": atype, "layer": layer, "parent": parent,
        "pos": [round(v, 3) for v in pos], "size": list(size), "rot_y_deg": rot,
    }
    a.update(extra)
    return a


def _build_assets() -> list[dict]:
    A: list[dict] = []
    # --- Structural / grouping nodes (no data points) ---------------------
    A.append(_asset("DCX", "DATACORE-X Facility", "facility", "building", None, [13, 0, 11], [32, 5, 24]))
    A.append(_asset("BLD-01", "Main building", "building", "building", "DCX", [13, 0, 9], [26, 4.2, 18]))
    A.append(_asset("DH-01", "Data hall", "room", "building", "BLD-01", [7, 0, 6], [14, 4.0, 12]))
    A.append(_asset("PR-01", "Chiller plant room", "room", "building", "BLD-01", [20, 0, 6], [12, 4.0, 12]))
    A.append(_asset("ER-01", "Electrical / UPS room", "room", "building", "BLD-01", [7, 0, 15], [14, 4.0, 6]))
    A.append(_asset("YARD-01", "Outdoor yard", "room", "building", "DCX", [16, 0, 21], [32, 0.1, 6]))
    A.append(_asset("ROOF-01", "Cooling tower deck", "room", "building", "DCX", [29.5, 0, 6], [6, 0.1, 12]))
    A.append(_asset("ROW-A", "Rack row A", "group", "it", "DH-01", [7.0, FLOOR_Y, 4.6], [3.4, 2.2, 1.2]))
    A.append(_asset("ROW-B", "Rack row B", "group", "it", "DH-01", [7.0, FLOOR_Y, 7.4], [3.4, 2.2, 1.2]))

    # --- Zones ----------------------------------------------------------------
    A.append(_asset("ZONE-CA", "Cold aisle (contained)", "zone", "zone", "DH-01",
                    [7.0, FLOOR_Y, 6.0], [3.4, 2.3, 1.6]))
    A.append(_asset("ZONE-HA", "Hot aisle / room return", "zone", "zone", "DH-01",
                    [7.0, FLOOR_Y, 6.0], [9.0, 3.2, 9.0]))

    # --- Racks -----------------------------------------------------------------
    xs = [5.8, 6.6, 7.4, 8.2]
    for i in range(8):
        row = "ROW-A" if i < 4 else "ROW-B"
        z = 4.6 if i < 4 else 7.4
        rot = 0.0 if i < 4 else 180.0  # row A front faces +z, row B faces -z (both into cold aisle)
        A.append(_asset(f"R-{i+1:02d}", f"Rack {i+1:02d}", "rack", "it", row,
                        [xs[i % 4], FLOOR_Y, z], [0.6, 2.2, 1.2], rot,
                        rated_kw=16.0, phase=["L1", "L2", "L3"][i % 3]))
    A.append(_asset("PDU-A", "PDU A (A-feed)", "pdu", "electrical", "DH-01", [4.9, FLOOR_Y, 4.6], [0.8, 1.9, 1.0], rated_kw=150.0))
    A.append(_asset("PDU-B", "PDU B (B-feed)", "pdu", "electrical", "DH-01", [4.9, FLOOR_Y, 7.4], [0.8, 1.9, 1.0], rated_kw=150.0))

    # --- CRAH -------------------------------------------------------------------
    crah_pos = {"CRAH-01": [3.5, FLOOR_Y, 0.75], "CRAH-02": [10.5, FLOOR_Y, 0.75],
                "CRAH-03": [3.5, FLOOR_Y, 11.25], "CRAH-04": [10.5, FLOOR_Y, 11.25]}
    for k, p in crah_pos.items():
        A.append(_asset(k, k.replace("-", " "), "crah", "cooling", "DH-01", p, [2.4, 2.0, 0.9],
                        0.0 if p[2] < 6 else 180.0))

    # --- Plant room -------------------------------------------------------------
    A.append(_asset("CH-01", "Chiller 01", "chiller", "cooling", "PR-01", [18.2, 0, 3.0], [4.0, 1.9, 1.6], rated_kw=160.0))
    A.append(_asset("CH-02", "Chiller 02", "chiller", "cooling", "PR-01", [18.2, 0, 9.0], [4.0, 1.9, 1.6], rated_kw=160.0))
    for i, z in enumerate([4.0, 6.0, 8.0]):
        A.append(_asset(f"P-{i+1:02d}", f"CHW pump {i+1:02d}" + (" (standby)" if i == 2 else " (duty)"),
                        "pump", "cooling", "PR-01", [23.0, 0, z], [1.3, 0.9, 0.6], 90.0, rated_kw=4.0))
    A.append(_asset("HX-01", "Waterside economiser HX", "hx", "cooling", "PR-01", [24.9, 0, 1.6], [0.7, 1.8, 1.2]))

    # --- Cooling towers -------------------------------------------------------
    A.append(_asset("CT-01", "Cooling tower 01", "tower", "cooling", "ROOF-01", [29.5, 0, 3.5], [3.0, 3.8, 3.0], rated_kw=110.0))
    A.append(_asset("CT-02", "Cooling tower 02", "tower", "cooling", "ROOF-01", [29.5, 0, 8.5], [3.0, 3.8, 3.0], rated_kw=110.0))

    # --- Electrical -------------------------------------------------------------
    A.append(_asset("TX-01", "Transformer 11/0.415 kV", "transformer", "electrical", "YARD-01", [4.0, 0, 21.0], [2.2, 2.4, 1.8], rated_kva=500.0))
    A.append(_asset("GEN-01", "Standby generator", "generator", "electrical", "YARD-01", [10.5, 0, 21.2], [5.0, 2.5, 2.0], rated_kw=400.0,
                    note="Added to the 8A asset list: required for a realistic utility-failure scenario."))
    A.append(_asset("SWG-01", "Main LV switchgear", "switchgear", "electrical", "ER-01", [3.6, 0, 13.4], [5.0, 2.2, 0.8]))
    A.append(_asset("UPS-A", "UPS A", "ups", "electrical", "ER-01", [8.2, 0, 13.4], [1.6, 2.0, 0.9], rated_kw=150.0))
    A.append(_asset("UPS-B", "UPS B", "ups", "electrical", "ER-01", [8.2, 0, 16.6], [1.6, 2.0, 0.9], rated_kw=150.0))
    A.append(_asset("BAT-A", "Battery bank A", "battery", "electrical", "ER-01", [11.6, 0, 13.4], [2.2, 2.0, 0.8], capacity_ah=60.0))
    A.append(_asset("BAT-B", "Battery bank B", "battery", "electrical", "ER-01", [11.6, 0, 16.6], [2.2, 2.0, 0.8], capacity_ah=60.0))

    # --- Piping (polylines; flow direction = point order) -----------------------
    y_sup, y_ret = 0.32, 0.18
    chws = [
        [[16.2, 1.0, 3.0], [15.3, 1.0, 3.0], [15.3, 1.0, 6.2]],
        [[16.2, 1.0, 9.0], [15.3, 1.0, 9.0], [15.3, 1.0, 6.2]],
        [[15.3, 1.0, 6.2], [14.4, 1.0, 6.2], [14.4, y_sup, 6.2], [10.5, y_sup, 6.2], [3.5, y_sup, 6.2]],
        [[10.5, y_sup, 6.2], [10.5, y_sup, 1.3]],
        [[10.5, y_sup, 6.2], [10.5, y_sup, 10.7]],
        [[3.5, y_sup, 6.2], [3.5, y_sup, 1.3]],
        [[3.5, y_sup, 6.2], [3.5, y_sup, 10.7]],
    ]
    chwr = [
        [[3.9, y_ret, 1.3], [3.9, y_ret, 5.7]],
        [[3.9, y_ret, 10.7], [3.9, y_ret, 5.7]],
        [[10.9, y_ret, 1.3], [10.9, y_ret, 5.7]],
        [[10.9, y_ret, 10.7], [10.9, y_ret, 5.7]],
        [[3.9, y_ret, 5.7], [10.9, y_ret, 5.7], [14.7, y_ret, 5.7], [14.7, 1.7, 5.7], [21.8, 1.7, 5.7]],
        [[21.8, 1.7, 5.7], [21.8, 1.7, 4.0], [22.3, 0.6, 4.0]],
        [[21.8, 1.7, 5.7], [21.8, 1.7, 6.0], [22.3, 0.6, 6.0]],
        [[21.8, 1.7, 5.7], [21.8, 1.7, 8.0], [22.3, 0.6, 8.0]],
        [[23.7, 0.6, 4.0], [24.3, 0.6, 4.0], [24.3, 0.6, 1.6]],
        [[23.7, 0.6, 6.0], [24.3, 0.6, 6.0], [24.3, 0.6, 4.0]],
        [[23.7, 0.6, 8.0], [24.3, 0.6, 8.0], [24.3, 0.6, 6.0]],
        [[24.9, 1.9, 1.6], [24.9, 2.3, 1.6], [20.4, 2.3, 1.6], [20.4, 1.4, 3.0]],
        [[20.4, 2.3, 1.6], [20.4, 2.3, 9.0], [20.4, 1.4, 9.0]],
    ]
    cw = [
        [[18.2, 1.95, 3.0], [18.2, 2.8, 3.0], [27.0, 2.8, 3.0], [27.0, 3.9, 3.5], [28.0, 3.9, 3.5]],
        [[18.2, 1.95, 9.0], [18.2, 2.8, 9.0], [27.0, 2.8, 9.0], [27.0, 3.9, 8.5], [28.0, 3.9, 8.5]],
        [[28.0, 0.3, 3.5], [26.6, 0.3, 3.5], [26.6, 0.3, 1.0], [25.3, 0.3, 1.0]],
        [[28.0, 0.3, 8.5], [26.6, 0.3, 8.5], [26.6, 0.3, 3.5]],
        [[25.3, 1.2, 1.0], [26.0, 1.2, 1.0], [26.0, 1.2, 6.0], [20.2, 0.5, 6.0], [20.2, 0.5, 3.0]],
        [[20.2, 0.5, 6.0], [20.2, 0.5, 9.0]],
    ]
    A.append(_asset("PIPE-CHWS", "Chilled-water supply", "pipe", "piping", "BLD-01", [14, 0, 6], [0, 0, 0],
                    paths=chws, diameter_m=0.10, medium="chw_supply"))
    A.append(_asset("PIPE-CHWR", "Chilled-water return", "pipe", "piping", "BLD-01", [14, 0, 6], [0, 0, 0],
                    paths=chwr, diameter_m=0.10, medium="chw_return"))
    A.append(_asset("PIPE-CW", "Condenser water", "pipe", "piping", "PR-01", [24, 0, 6], [0, 0, 0],
                    paths=cw, diameter_m=0.125, medium="condenser"))
    return A


# Single-line electrical connectivity (drawn as cable runs, used for fault-propagation highlighting)
ELECTRICAL_LINKS = [
    ("TX-01", "SWG-01"), ("GEN-01", "SWG-01"),
    ("SWG-01", "UPS-A"), ("SWG-01", "UPS-B"),
    ("UPS-A", "BAT-A"), ("UPS-B", "BAT-B"),
    ("UPS-A", "PDU-A"), ("UPS-B", "PDU-B"),
    ("SWG-01", "CH-01"), ("SWG-01", "CH-02"), ("SWG-01", "P-02"),
    ("SWG-01", "CRAH-01"), ("SWG-01", "CRAH-03"),
] + [("PDU-A", f"R-{i:02d}") for i in range(1, 9)] + [("PDU-B", f"R-{i:02d}") for i in range(1, 9)]
# Every rack is dual-corded (A + B feed); in normal operation each path carries 50 % of rack load.

# Airflow pathway (CRAH -> underfloor plenum -> perforated tiles -> cold aisle -> racks -> hot aisle -> return)
AIRFLOW = {
    "tiles": [[x, FLOOR_Y, z] for x in (5.8, 6.6, 7.4, 8.2) for z in (5.6, 6.4)],
    "plenum_y": 0.3,
    "return_y": 3.3,
}


def assets() -> list[dict]:
    out = []
    for a in _build_assets():
        t = a["type"]
        a["tags"] = [
            {"key": k, "label": lbl, "unit": u, "decimals": d,
             "path": f"[DATACORE_X]{IGN_FOLDER[t]}/{a['id'].replace('-', '_')}/{k}",
             "opc_node": f"ns=2;s=DCX.{a['id']}.{k}"}
            for (k, lbl, u, d) in TAG_TEMPLATES.get(t, [])
        ]
        a["has_health"] = t in HEALTH_TYPES
        out.append(a)
    return out


def asset_index() -> dict[str, dict]:
    return {a["id"]: a for a in assets()}


def flat_tag_list() -> list[dict]:
    rows = []
    for a in assets():
        for tg in a["tags"]:
            rows.append({"asset_id": a["id"], **tg})
    return rows


def registry_document() -> dict:
    return {
        "registry_version": REGISTRY_VERSION,
        "units_system": "SI (temperatures in °C)",
        "coordinate_system": "metres; x east, z south, y up; pos = base-centre",
        "assets": assets(),
        "electrical_links": [list(l) for l in ELECTRICAL_LINKS],
        "airflow": deepcopy(AIRFLOW),
        "facility_tags": [
            {"key": k, "label": l, "unit": u, "decimals": d,
             "path": f"[DATACORE_X]Facility/{k}", "opc_node": f"ns=2;s=DCX.Facility.{k}"}
            for k, l, u, d in [
                ("it_load_kw", "IT load", "kW", 1), ("facility_power_kw", "Facility power", "kW", 1),
                ("cooling_power_kw", "Cooling power", "kW", 1), ("elec_losses_kw", "Electrical losses", "kW", 2),
                ("pue", "PUE", "-", 3), ("max_inlet_c", "Max rack inlet", "°C", 2),
                ("chws_c", "CHW supply", "°C", 2), ("chwr_c", "CHW return", "°C", 2),
                ("wetbulb_c", "Ambient wet-bulb", "°C", 2), ("energy_kwh", "Facility energy (run)", "kWh", 2),
                ("it_energy_kwh", "IT energy (run)", "kWh", 2),
            ]
        ],
    }


def export_registry(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(registry_document(), indent=1, ensure_ascii=False), encoding="utf-8")
    return p
