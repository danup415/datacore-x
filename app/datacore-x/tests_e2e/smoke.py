import asyncio, sys, json
from playwright.async_api import async_playwright
URL = sys.argv[1]; SHOT = sys.argv[2]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader","--ignore-gpu-blocklist"])
        pg = await b.new_page(viewport={"width":1600,"height":900})
        errs=[]
        pg.on("console", lambda m: errs.append(m.type+": "+m.text) if m.type in ("error","warning") else None)
        pg.on("pageerror", lambda e: errs.append("PAGEERROR: "+str(e)))
        await pg.goto(URL); await pg.wait_for_timeout(6000)
        await pg.screenshot(path=SHOT)
        print("errors:", errs[:10])
        print(await pg.evaluate("JSON.stringify({seq: DCX.store.snap && DCX.store.snap.seq, link: DCX.store.link, fps: DCX.app.fps})"))
        await b.close()
asyncio.run(main())
