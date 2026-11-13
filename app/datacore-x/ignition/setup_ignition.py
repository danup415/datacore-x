"""DATACORE-X -> Ignition 8.3 gateway setup (item 8).

Creates the OPC UA client connection "DATACORE-X" to the twin's OPC UA server
and imports the DATACORE-X tag folder, using the Ignition 8.3 Gateway REST API.

Authentication: an API token (Gateway > Platform > Security > API Keys) read
from a file - never pass it on the command line or paste it into chat.
Default token file: %USERPROFILE%\\Documents\\DATACORE-X\\ignition_api_key.txt

    python ignition/setup_ignition.py              # dry run: discover + show plan
    python ignition/setup_ignition.py --apply      # create connection, import tags, verify

The script discovers routes from the gateway's own OpenAPI document (/openapi)
instead of hard-coding them, and builds the new OPC connection by copying the
shape of an existing OPC UA connection on the gateway (8.3 ships one for its
internal server), changing only the name and endpoint. Requires the backend
OPC UA server (DCX_OPCUA=1) to be running for the connection to go Connected.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
DEFAULT_KEY = Path(os.path.expandvars(r"%USERPROFILE%")) / "Documents" / "DATACORE-X" / "ignition_api_key.txt"
TAGS = HERE / "tags" / "datacorex_opc_tags.json"
CONN_NAME = "DATACORE-X"
ENDPOINT = "opc.tcp://localhost:4840/datacorex/"


def log(msg: str) -> None:
    print(msg, flush=True)


class Gateway:
    def __init__(self, url: str, token: str):
        self.c = httpx.Client(base_url=url.rstrip("/"), timeout=30.0,
                              headers={"X-Ignition-API-Token": token, "Accept": "application/json"})

    def get(self, path, **kw):
        r = self.c.get(path, **kw)
        return r

    def send(self, method, path, body=None, **kw):
        return self.c.request(method, path, json=body, **kw)


def load_openapi(gw: Gateway) -> dict:
    for p in ("/openapi", "/openapi.json", "/data/api/v1/openapi"):
        r = gw.get(p)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        if r.status_code in (401, 403):
            sys.exit(f"[auth] {p} -> HTTP {r.status_code}: token rejected or lacks permission "
                     "(give the API key Read+Write access in Platform > Security > API Keys)")
    sys.exit("[openapi] could not fetch the OpenAPI document from the gateway")


def find_paths(spec: dict, *needles: str) -> list[tuple[str, list[str]]]:
    out = []
    for path, ops in spec.get("paths", {}).items():
        if all(n in path for n in needles):
            out.append((path, sorted(k.upper() for k in ops.keys())))
    return out


def list_opc_connections(gw: Gateway, spec: dict) -> list[dict]:
    cands = [p for p, m in find_paths(spec, "opc-connection") if "GET" in m and "{" not in p]
    cands += ["/data/api/v1/resources/list/ignition/opc-connection"]
    for p in dict.fromkeys(cands):
        r = gw.get(p)
        if r.status_code == 200:
            j = r.json()
            items = j.get("items", j) if isinstance(j, dict) else j
            if isinstance(items, list):
                return items
    return []


def build_connection(template: dict) -> dict:
    conn = copy.deepcopy(template)
    for k in ("signature", "collection", "version", "uuid"):
        conn.pop(k, None)
    conn["name"] = CONN_NAME
    conn["enabled"] = True
    cfg = conn.get("config", {})
    settings = cfg.get("settings", cfg)
    # endpoint / discovery URL keys differ between versions; set every one that exists
    hit = False
    def walk(d):
        nonlocal hit
        if isinstance(d, dict):
            for k, v in list(d.items()):
                lk = k.lower()
                if isinstance(v, str) and ("url" in lk) and v.startswith("opc.tcp"):
                    d[k] = ENDPOINT; hit = True
                else:
                    walk(v)
        elif isinstance(d, list):
            for v in d:
                walk(v)
    walk(settings)
    if not hit:
        settings["discoveryUrl"] = ENDPOINT
        settings["endpointUrl"] = ENDPOINT
    # the twin's asyncua server runs unsecured with anonymous access (local development)
    ep = settings.get("endpoint", settings)
    ep["securityPolicy"] = "None"
    ep["securityMode"] = "None"
    settings["authentication"] = {"authenticationType": "ANONYMOUS"}
    conn["description"] = "DATACORE-X digital twin OPC UA server (asyncua)"
    conn.pop("collections", None)
    return conn


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gateway", default="http://localhost:8088")
    ap.add_argument("--key-file", type=Path, default=DEFAULT_KEY)
    ap.add_argument("--provider", default="default")
    ap.add_argument("--apply", action="store_true", help="make changes (default: dry run)")
    a = ap.parse_args()

    if not a.key_file.is_file():
        sys.exit(f"[key] token file not found: {a.key_file}\n"
                 "Create an API key in Gateway > Platform > Security > API Keys and save the token in that file.")
    token = a.key_file.read_text(encoding="utf-8").strip()
    gw = Gateway(a.gateway, token)

    spec = load_openapi(gw)
    log(f"[openapi] {spec.get('info', {}).get('title', '?')} {spec.get('info', {}).get('version', '')}: "
        f"{len(spec.get('paths', {}))} routes")
    opc_routes = find_paths(spec, "opc-connection")
    tag_import = [p for p, m in find_paths(spec, "tags", "import") if "POST" in m]
    tag_export = [p for p, m in find_paths(spec, "tags", "export") if "GET" in m]
    for p, m in opc_routes:
        log(f"  opc-connection route {','.join(m):12s} {p}")
    log(f"  tag import route(s): {tag_import or 'none (needs Ignition 8.3.2+)'}")

    conns = list_opc_connections(gw, spec)
    names = [c.get("name") for c in conns]
    log(f"[opc] existing connections: {names}")
    plan_conn = None
    if CONN_NAME in names:
        log(f"[opc] '{CONN_NAME}' already exists - left unchanged")
    else:
        tmpl = next((c for c in conns if "ua" in json.dumps(c).lower()), None)
        if tmpl is None:
            sys.exit("[opc] no OPC UA connection found to copy the schema from; create "
                     f"'{CONN_NAME}' -> {ENDPOINT} once in Connections > OPC, then re-run for tags")
        plan_conn = build_connection(tmpl)
        log("[opc] will create:\n" + json.dumps(plan_conn, indent=2)[:1500])

    tags = json.loads(TAGS.read_text(encoding="utf-8"))
    n_opc = json.dumps(tags).count('"opcServer"')
    log(f"[tags] {TAGS.name}: folder '{tags.get('name')}', {n_opc} OPC tags -> provider '{a.provider}'")

    if not a.apply:
        log("\nDry run only. Re-run with --apply to make these changes.")
        return

    if plan_conn is not None:
        post = [p for p, m in opc_routes if "POST" in m and "{" not in p and "delete" not in p]
        path = post[0] if post else "/data/api/v1/resources/ignition/opc-connection"
        r = gw.send("POST", path, [plan_conn])
        log(f"[opc] POST {path} -> HTTP {r.status_code} {r.text[:300]}")
        if r.status_code >= 300:
            sys.exit("[opc] connection create failed - see response above")

    if tag_import:
        r = gw.send("POST", tag_import[0], tags,
                    params={"provider": a.provider, "type": "json", "collisionPolicy": "o"})
        log(f"[tags] POST {tag_import[0]} -> HTTP {r.status_code} {r.text[:300]}")
    else:
        log("[tags] no import route; import ignition/tags/datacorex_opc_tags.json in the Designer Tag Browser")

    # ---- verify
    time.sleep(5)
    conns = list_opc_connections(gw, spec)
    mine = next((c for c in conns if c.get("name") == CONN_NAME), None)
    log(f"[verify] connection present: {mine is not None}")
    for p, m in find_paths(spec, "opc-connection", "status"):
        r = gw.get(p.replace("{name}", CONN_NAME))
        log(f"[verify] {p} -> {r.status_code} {r.text[:200]}")
    if tag_export:
        r = gw.get(tag_export[0], params={"provider": a.provider, "type": "json"})
        ok = r.status_code == 200 and '"DATACORE_X"' in r.text
        log(f"[verify] tag folder DATACORE_X in provider '{a.provider}': {ok}")


if __name__ == "__main__":
    main()
