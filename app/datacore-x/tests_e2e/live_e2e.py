"""End-to-end validation of the 3D twin against the live integration service (8A-G)."""
import asyncio, json, sys
from playwright.async_api import async_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"])
        pg = await b.new_page(viewport={"width":1600,"height":900})
        errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await pg.goto(URL); await pg.wait_for_timeout(4000)
        await pg.select_option("#role", "engineer")
        # G8: commands with acknowledgement (accepted+confirmed, interlock reject)
        r1 = await pg.evaluate("DCX.source.command({command:'pump_start', asset:'P-03'})")
        r2 = await pg.evaluate("DCX.source.command({command:'crah_disable', asset:'CRAH-01'}).then(()=>DCX.source.command({command:'crah_disable', asset:'CRAH-02'})).then(()=>DCX.source.command({command:'crah_disable', asset:'CRAH-03'}))")
        await pg.wait_for_timeout(4000)
        cmds = await pg.evaluate("DCX.store.snap.commands.map(c=>[c.command,c.asset,c.status,c.reason])")
        print("COMMANDS:"); [print("  ", c) for c in cmds]
        await pg.evaluate("Promise.all(['CRAH-01','CRAH-02'].map(a=>DCX.source.command({command:'crah_enable', asset:a})))")
        # what-if S11 through the UI
        await pg.click("#tabs button[data-t=whatif]"); await pg.wait_for_timeout(500)
        await pg.select_option("#w-sel", "S11"); await pg.wait_for_timeout(300)
        await pg.click("#w-req"); await pg.wait_for_timeout(500)
        await pg.click("text=Approve & execute")
        await pg.wait_for_selector("#w-3d", timeout=60000)
        await pg.screenshot(path=f"{OUT}/e2e_whatif_result.png")
        await pg.click("#w-3d"); await pg.wait_for_timeout(500)
        await pg.evaluate("DCX.app.playback.playing=false; DCX.app.playback.i=DCX.app.playback.frames.baseline.length-1; DCX.app.select('P-01'); DCX.app.onSnapshot(); DCX.view.goto({pos:[26.5,3.2,9],target:[23,0.6,5]},0)")
        await pg.wait_for_timeout(2000)
        await pg.screenshot(path=f"{OUT}/e2e_whatif_3d.png")
        g7 = await pg.evaluate("DCX.app.runChecks().then(c=>c.find(x=>x.name.startsWith('G7')))")
        print("G7:", g7)
        await pg.click("#tl-exit"); await pg.wait_for_timeout(500)
        # G9 comm loss & recovery
        await pg.click("#tabs button[data-t=diag]")
        await pg.click("#d-loss"); await pg.wait_for_timeout(5500)
        stale = await pg.evaluate("DCX.store.link")
        await pg.screenshot(path=f"{OUT}/e2e_comm_loss.png")
        await pg.wait_for_timeout(6000)
        rec = await pg.evaluate("DCX.store.link")
        print("comm loss: during =", stale, "after =", rec)
        await pg.click("#d-cons"); await pg.wait_for_timeout(1500)
        print("consistency:", await pg.inner_text("#d-cons-out"))
        checks = await pg.evaluate("DCX.app.runChecks()")
        print("CHECKS:"); [print("  ", "PASS" if c["pass"] else ("FAIL" if c["pass"] is False else "N/A "), c["name"], "—", c["info"]) for c in checks]
        await pg.evaluate("DCX.app.select('R-06'); DCX.app.preset('datahall')"); await pg.wait_for_timeout(2500)
        await pg.screenshot(path=f"{OUT}/e2e_live_datahall.png")
        print("page errors:", errs)
        json.dump(checks, open(f"{OUT}/e2e_checks.json","w"), indent=1)
        await b.close()
asyncio.run(main())
