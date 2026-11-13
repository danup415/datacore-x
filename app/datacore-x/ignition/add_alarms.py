"""Add ISA-18.2 style alarms to the DATACORE-X tags in Ignition (native Ignition alarming).

    python ignition/add_alarms.py            # dry run: list the alarms that would be added
    python ignition/add_alarms.py --apply    # export current tags, add alarms, import (overwrite), verify

The script starts from the gateway's CURRENT tag configuration (so history settings
or edits made in the Designer are kept), adds the alarm definitions below, and
re-imports the folder. A backup of the exported tags is written to ignition/_build/.

Alarm philosophy (ISA-18.2 priorities mapped to Ignition priorities):
  Critical  equipment tripped / rack inlet above ASHRAE allowable / twin link lost
  High      pump or fan vibration in ISO 10816 zone D (>= 7.1 mm/s) / rack inlet > 27 C
  Medium    vibration in ISO 10816 zone C (>= 4.5 mm/s) / CHW supply high
  Low       (advisory - not used yet)
Every alarm needs operator acknowledgement (Ack Mode = Manual), so a condition that
clears on its own still shows as "cleared, unacknowledged" until an operator has seen it.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import setup_ignition as S  # noqa: E402

FOLDER = "DATACORE_X"


def alarm(name, mode, sp, priority, label, notes=""):
    return {"name": name, "mode": mode, "setpointA": sp, "priority": priority, "ackMode": "Manual",
            "label": label, "notes": notes}


def plan() -> dict:
    """path (relative to the DATACORE_X folder) -> list of alarms; '+Tripped' entries are new expression tags."""
    p: dict[str, list] = {}
    for i in (1, 2, 3):
        a = f"P-0{i}"
        p[f"Cooling/P_0{i}/vib_mms"] = [
            alarm("Vibration zone C", "AboveValue", 4.5, "Medium", f"{a} vibration in ISO 10816 zone C (>= 4.5 mm/s)",
                  "Plan maintenance; the health-aware controller schedules a changeover."),
            alarm("Vibration zone D", "AboveValue", 7.1, "High", f"{a} vibration in ISO 10816 zone D (>= 7.1 mm/s)",
                  "Damage likely; stop the pump.")]
    for i in (1, 2, 3, 4):
        a = f"CRAH-0{i}"
        p[f"Cooling/CRAH_0{i}/vib_mms"] = [
            alarm("Vibration zone C", "AboveValue", 4.5, "Medium", f"{a} fan vibration in ISO 10816 zone C"),
            alarm("Vibration zone D", "AboveValue", 7.1, "High", f"{a} fan vibration in ISO 10816 zone D")]
    for i in range(1, 9):
        r = f"R-0{i}"
        p[f"DataHall/R_0{i}/inlet_c"] = [
            alarm("Inlet high", "AboveValue", 27.0, "High", f"{r} inlet above 27 C (ASHRAE recommended)"),
            alarm("Inlet high-high", "AboveValue", 32.0, "Critical", f"{r} inlet above 32 C (ASHRAE A1 allowable)")]
    p["Facility/chws_c"] = [alarm("CHW supply high", "AboveValue", 20.5, "Medium", "Chilled-water supply above 20.5 C")]
    p["System/Last_Poll_OK"] = [alarm("Twin link lost", "Equality", 0.0, "Critical", "Digital-twin data link lost")]
    for f, a in [(f"Cooling/P_0{i}", f"P-0{i}") for i in (1, 2, 3)] + [(f"Cooling/CH_0{i}", f"CH-0{i}") for i in (1, 2)] + \
                [(f"Cooling/CRAH_0{i}", f"CRAH-0{i}") for i in (1, 2, 3, 4)]:
        p[f"{f}/+Tripped"] = [alarm("Trip", "Equality", 1.0, "Critical", f"{a} tripped (protection)",
                                    "Unplanned if the asset was on duty.")]
    return p


def find(node: dict, parts: list[str]) -> dict | None:
    for name in parts:
        node = next((c for c in node.get("tags", []) if c.get("name") == name), None)
        if node is None:
            return None
    return node


def apply_plan(folder: dict, p: dict) -> list[str]:
    done = []
    for path, alarms in p.items():
        parts = path.split("/")
        if parts[-1].startswith("+"):
            parent = find(folder, parts[:-1])
            if parent is None:
                done.append(f"MISSING folder {'/'.join(parts[:-1])}")
                continue
            name = parts[-1][1:]
            parent["tags"] = [t for t in parent.get("tags", []) if t.get("name") != name]
            parent["tags"].append({"name": name, "tagType": "AtomicTag", "valueSource": "expr", "dataType": "Boolean",
                                   "expression": "indexOf(upper(toStr({[.]State})), 'TRIP') >= 0",
                                   "documentation": "True while the asset is tripped (derived from State)",
                                   "alarms": alarms})
            done.append(f"{path[:-len(name) - 1]}{name} (new expression tag): {', '.join(a['name'] for a in alarms)}")
            continue
        t = find(folder, parts)
        if t is None:
            done.append(f"MISSING tag {path}")
            continue
        t["alarms"] = alarms
        done.append(f"{path}: {', '.join(a['name'] + ' (' + a['priority'] + ')' for a in alarms)}")
    return done


def count_alarms(node) -> int:
    n = len(node.get("alarms", [])) if isinstance(node, dict) else 0
    for c in node.get("tags", []) if isinstance(node, dict) else []:
        n += count_alarms(c)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", default="http://localhost:8088")
    ap.add_argument("--provider", default="default")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    gw = S.Gateway(a.gateway, S.DEFAULT_KEY.read_text(encoding="utf-8-sig").strip())
    r = gw.get("/data/api/v1/tags/export", params={"provider": a.provider, "type": "json", "path": FOLDER})
    if r.status_code != 200 or '"tags"' not in r.text:
        sys.exit(f"[export] {FOLDER} -> HTTP {r.status_code} {r.text[:300]}")
    cur = r.json()
    build = HERE / "_build"
    build.mkdir(exist_ok=True)
    bk = build / f"tags_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    bk.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    print(f"[export] {FOLDER}: {count_alarms(cur)} alarms configured now; backup -> {bk.name}")

    new = copy.deepcopy(cur)
    for line in apply_plan(new, plan()):
        print("  " + line)
    print(f"[plan] alarms after change: {count_alarms(new)}")
    (build / "tags_with_alarms.json").write_text(json.dumps(new, indent=1), encoding="utf-8")
    if not a.apply:
        print("Dry run only. Re-run with --apply.")
        return
    r = gw.send("POST", "/data/api/v1/tags/import", new,
                params={"provider": a.provider, "type": "json", "collisionPolicy": "o"})
    print(f"[import] HTTP {r.status_code} {r.text[:300]}")
    time.sleep(3)
    r = gw.get("/data/api/v1/tags/export", params={"provider": a.provider, "type": "json", "path": FOLDER})
    print(f"[verify] alarms configured on the gateway: {count_alarms(r.json()) if r.status_code == 200 else 'export failed'}")


if __name__ == "__main__":
    main()
