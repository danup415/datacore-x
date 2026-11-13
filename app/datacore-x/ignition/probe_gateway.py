"""Diagnose Ignition API-key access (prints status codes only, never the token)."""
import os, httpx
from pathlib import Path
tok = (Path(os.path.expandvars(r"%USERPROFILE%")) / "Documents" / "DATACORE-X" / "ignition_api_key.txt").read_text().strip()
for auth in ("token", "none"):
    h = {"X-Ignition-API-Token": tok} if auth == "token" else {}
    for p in ["/openapi", "/openapi.json", "/data/api/v1/openapi", "/data/api/v1/gateway-info", "/data/api/v1/overview",
              "/data/api/v1/resources/list/ignition/opc-connection", "/data/api/v1/tags/export?provider=default&type=json",
              "/data/api/v1/modules/healthy"]:
        try:
            r = httpx.get("http://localhost:8088" + p, headers=h, timeout=15)
            print(f"{auth:5s} {r.status_code} {p} :: {r.headers.get('content-type','')[:30]} :: {r.text[:160]!r}")
        except Exception as e:
            print(auth, "ERR", p, e)
