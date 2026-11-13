"""Check the DATACORE-X OPC connection status and live tag values on the gateway."""
import os, json, httpx, time
from pathlib import Path
tok = (Path(os.path.expandvars(r"%USERPROFILE%")) / "Documents" / "DATACORE-X" / "ignition_api_key.txt").read_text().strip()
c = httpx.Client(base_url="http://localhost:8088", headers={"X-Ignition-API-Token": tok}, timeout=20)
spec = c.get("/openapi.json").json()
paths = [p for p in spec["paths"] if any(k in p.lower() for k in ("status", "browse", "diagnos", "/tags/", "opcua", "opc-ua"))]
print(len(paths))
print("candidate routes:", *paths, sep="\n  ")
for p in paths:
    if "{" in p:
        p2 = p.replace("{name}", "DATACORE-X").replace("{connectionName}", "DATACORE-X")
        if "{" in p2: continue
    else:
        p2 = p
    if "get" not in spec["paths"][p]: continue
    if not any(k in p.lower() for k in ("opc", "browse")): continue
    r = c.get(p2, params={"provider": "default", "path": "[default]DATACORE_X/Facility"} if "tags" in p else None)
    print(f"\nGET {p2} -> {r.status_code}\n{r.text[:900]}")
