import asyncio, sys
from playwright.async_api import async_playwright
URL = sys.argv[1]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"])
        pg = await b.new_page(viewport={"width":1600,"height":900})
        errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL); await pg.wait_for_timeout(4000)
        for name, js in [("datahall","DCX.view.goto({pos:[7,8.5,15.5],target:[7,0.8,6]},0)"),("plant","DCX.app.preset('plant'); DCX.view.tween=null; DCX.view.goto({pos:[19,9,16],target:[21,0.5,5.5]},0)"),
                         ("pump","DCX.app.select('P-01'); DCX.view.goto({pos:[25.5,2.2,7.5],target:[23,0.5,4]},0)")]:
            await pg.evaluate(js); await pg.wait_for_timeout(2500)
            await pg.screenshot(path=f"/tmp/v_{name}.png")
        print("errors", errs)
        await b.close()
asyncio.run(main())
