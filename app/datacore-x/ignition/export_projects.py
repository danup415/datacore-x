import os, io, zipfile, httpx, sys
from pathlib import Path
tok = (Path(os.path.expandvars(r"%USERPROFILE%")) / "Documents" / "DATACORE-X" / "ignition_api_key.txt").read_text().strip()
c = httpx.Client(base_url="http://localhost:8088", headers={"X-Ignition-API-Token": tok}, timeout=60)
out = Path(__file__).resolve().parent / "_export"; out.mkdir(exist_ok=True)
for name in sys.argv[1:]:
    r = c.get(f"/data/api/v1/projects/export/{name}")
    print(name, r.status_code, r.headers.get("content-type"), len(r.content))
    (out / f"{name}.zip").write_bytes(r.content)
