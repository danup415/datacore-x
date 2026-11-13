"""Generate all registry-derived integration artefacts from the single source of truth.

    python -m datacorex.tools.export_artifacts

Writes:
  config/asset_registry.json            (3D frontend + all services)
  config/tag_map.csv                    (asset, key, unit, Ignition path, OPC UA node, Simulink signal)
  ignition/tags/datacorex_opc_tags.json (Ignition tag import — OPC UA bound)
  ignition/tags/datacorex_memory_tags.json (Ignition tag import — memory tags for REST polling route)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..registry import IGN_FOLDER, assets, export_registry, registry_document

ROOT = Path(__file__).resolve().parents[3]


def _fmt(dec):
    return "#,##0" + ("." + "0" * dec if dec else "")


def ignition_tags(opc: bool) -> dict:
    folders: dict[str, dict] = {}
    for a in assets():
        if not a["tags"]:
            continue
        fname = IGN_FOLDER[a["type"]]
        f = folders.setdefault(fname, {"name": fname, "tagType": "Folder", "tags": []})
        atags = []
        for tg in a["tags"]:
            t = {"name": tg["key"], "tagType": "AtomicTag", "dataType": "Float8", "engUnit": tg["unit"],
                 "formatString": _fmt(tg["decimals"]), "documentation": tg["label"],
                 "historyEnabled": True, "historyProvider": "DCX_Historian", "historicalDeadband": 0.0}
            if opc:
                t.update(valueSource="opc", opcServer="DATACORE-X", opcItemPath=tg["opc_node"])
            else:
                t.update(valueSource="memory", value=0.0)
            atags.append(t)
        state = {"name": "State", "tagType": "AtomicTag", "dataType": "String"}
        state.update({"valueSource": "opc", "opcServer": "DATACORE-X", "opcItemPath": f"ns=2;s=DCX.{a['id']}.state"}
                     if opc else {"valueSource": "memory", "value": ""})
        atags.append(state)
        if a["has_health"] and not opc:
            atags.append({"name": "Health", "tagType": "Folder", "tags": [
                {"name": k, "tagType": "AtomicTag", "valueSource": "memory",
                 "dataType": "String" if k == "fault" else "Float8"} for k in ("hi", "prob", "rul_h", "fault")]})
        f["tags"].append({"name": a["id"].replace("-", "_"), "tagType": "Folder", "tags": atags,
                          "documentation": a["name"]})
    sys_opc = {"Seq": "Seq", "Sim_Time_s": "SimTime", "Sim_Clock": "SimClock", "Source": "Source",
               "Comm_plant": "Comm_plant", "Comm_ai": "Comm_ai", "Comm_historian": "Comm_historian",
               "Comm_opcua": "Comm_opcua", "Last_Poll_OK": "LastPollOK"}
    sysf = {"name": "System", "tagType": "Folder", "tags": [
        {"name": n, "tagType": "AtomicTag", "dataType": dt,
         **({"valueSource": "opc", "opcServer": "DATACORE-X", "opcItemPath": f"ns=2;s=DCX.System.{sys_opc[n]}"}
            if opc else {"valueSource": "memory"})}
        for n, dt in [("Seq", "Int8"), ("Sim_Time_s", "Float8"), ("Sim_Clock", "String"), ("Source", "String"),
                      ("Comm_plant", "String"), ("Comm_ai", "String"), ("Comm_historian", "String"),
                      ("Comm_opcua", "String"), ("Last_Poll_OK", "Boolean")]]}
    fac = {"name": "Facility", "tagType": "Folder", "tags": [
        {"name": t["key"], "tagType": "AtomicTag", "dataType": "Float8", "engUnit": t["unit"], "documentation": t["label"],
         **({"valueSource": "opc", "opcServer": "DATACORE-X", "opcItemPath": f"ns=2;s=DCX.Facility.{t['key']}"}
            if opc else {"valueSource": "memory"})}
        for t in registry_document()["facility_tags"]]}
    return {"name": "DATACORE_X", "tagType": "Folder", "tags": [fac, *folders.values(), sysf]}


def main():
    export_registry(ROOT / "config" / "asset_registry.json")
    with open(ROOT / "config" / "tag_map.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["asset_id", "asset_type", "key", "label", "unit", "ignition_path", "opc_node", "simulink_signal"])
        for a in assets():
            for tg in a["tags"]:
                w.writerow([a["id"], a["type"], tg["key"], tg["label"], tg["unit"], tg["path"], tg["opc_node"],
                            f"DCX_{a['id'].replace('-', '_')}_{tg['key']}"])
    tdir = ROOT / "ignition" / "tags"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "datacorex_opc_tags.json").write_text(json.dumps(ignition_tags(True), indent=1, ensure_ascii=False), encoding="utf-8")
    (tdir / "datacorex_memory_tags.json").write_text(json.dumps(ignition_tags(False), indent=1, ensure_ascii=False), encoding="utf-8")
    print("exported registry, tag map and Ignition tag imports")


if __name__ == "__main__":
    main()
