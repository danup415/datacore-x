import os, json, httpx, sys
from pathlib import Path
tok = (Path(os.path.expandvars(r"%USERPROFILE%")) / "Documents" / "DATACORE-X" / "ignition_api_key.txt").read_text().strip()
c = httpx.Client(base_url="http://localhost:8088", headers={"X-Ignition-API-Token": tok}, timeout=30)
spec = c.get("/openapi.json").json()
lp = [p for p in spec["paths"] if "log" in p.lower() and "get" in spec["paths"][p]]
print(lp)
for p in lp:
    if "{" in p: continue
    r = c.get(p, params={"limit": 200})
    if r.status_code != 200: print(p, r.status_code); continue
    txt = r.text
    try:
        j = r.json(); items = j.get("items", j) if isinstance(j, dict) else j
    except Exception:
        print(p, txt[:300]); continue
    if isinstance(items, list):
        for it in items:
            s = json.dumps(it)
            if any(k in s.lower() for k in ("perspective", "datacore", "page", "view", "project")):
                print(s[:400])
