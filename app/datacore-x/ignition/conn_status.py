"""Print the gateway's health/status for the DATACORE-X OPC UA connection."""
import os, json, httpx
from pathlib import Path
tok = (Path(os.path.expandvars(r"%USERPROFILE%")) / "Documents" / "DATACORE-X" / "ignition_api_key.txt").read_text().strip()
c = httpx.Client(base_url="http://localhost:8088", headers={"X-Ignition-API-Token": tok}, timeout=20)
j = c.get("/data/api/v1/resources/list/ignition/opc-connection").json()
for it in j["items"]:
    ep = it.get("config", {}).get("settings", {}).get("endpoint", {})
    print(it["name"], "| enabled", it.get("enabled"), "|", ep.get("endpointUrl"), ep.get("securityPolicy"), ep.get("securityMode"))
    print("   health:", json.dumps(it.get("healthchecks")), "| metrics:", json.dumps(it.get("metrics"))[:300])
