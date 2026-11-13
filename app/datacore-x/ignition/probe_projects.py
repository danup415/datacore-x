import os, json, httpx
from pathlib import Path
tok = (Path(os.path.expandvars(r"%USERPROFILE%")) / "Documents" / "DATACORE-X" / "ignition_api_key.txt").read_text().strip()
c = httpx.Client(base_url="http://localhost:8088", headers={"X-Ignition-API-Token": tok}, timeout=30)
spec = c.get("/openapi.json").json()
for p, ops in spec["paths"].items():
    if "project" in p.lower() and "fsql" not in p:
        for m, o in ops.items():
            params = [x.get("name") for x in o.get("parameters", [])]
            print(m.upper(), p, params, (o.get("summary") or "")[:60])
print(c.get("/data/api/v1/projects/list").text[:800] if "/data/api/v1/projects/list" in spec["paths"] else "")
