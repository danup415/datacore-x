import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"])
        pg = await b.new_page(viewport={"width":1600,"height":900})
        errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(sys.argv[1]); await pg.wait_for_timeout(3000)
        await pg.evaluate("DCX.source.setFps(5); DCX.source.seek(420)"); await pg.wait_for_timeout(4000)
        await pg.evaluate("DCX.source.setFps(1)")
        await pg.evaluate("DCX.app.select('R-06'); DCX.view.goto({pos:[11.5,3.6,10.8],target:[7.4,1.4,6.6]},0)"); await pg.wait_for_timeout(2500)
        await pg.screenshot(path="/tmp/r_hotspot.png")
        checks = await pg.evaluate("DCX.app.runChecks()")
        for c in checks: print("PASS" if c["pass"] else ("FAIL" if c["pass"] is False else "N/A "), c["name"], "—", c["info"])
        print("errors", errs)
        await b.close()
asyncio.run(main())
