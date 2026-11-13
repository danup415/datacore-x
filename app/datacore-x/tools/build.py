"""Build the frontend bundle and the standalone (no-backend) replay demo.

    python tools/build.py            # bundle + standalone demo
Requires: npm install (three, esbuild) and a replay file from
    cd backend && python -m datacorex.tools.record_replay --out ../dist/replay.json
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run(["npx", "esbuild", "frontend/src/main.js", "--bundle", "--minify", "--format=iife",
                    "--target=es2020", "--outfile=frontend/dist/app.js"], cwd=ROOT, check=True)
    replay = ROOT / "dist" / "replay.json"
    if not replay.exists():
        print("no dist/replay.json — skipping standalone demo", file=sys.stderr)
        return
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "dist" / "app.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    data = replay.read_text(encoding="utf-8").replace("</", "<\\/")
    json.loads(replay.read_text(encoding="utf-8"))  # validate
    html = html.replace("<!--DCX_REPLAY-->", f"<script>window.DCX_REPLAY={data};</script>")
    html = html.replace('<script src="dist/app.js?v=20261110b"></script>', f"<script>{js}</script>")
    out = ROOT / "dist" / "datacorex_3d_twin_demo.html"
    out.write_text(html, encoding="utf-8")
    print(f"standalone demo: {out} ({out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
