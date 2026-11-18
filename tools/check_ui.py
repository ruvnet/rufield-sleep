"""Optional browser acceptance. Requires Playwright and an installed Chromium."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    server=subprocess.Popen([sys.executable,str(root/"app.py"),"--port","0","--db",tmp+"/test.db"],stdout=subprocess.PIPE,text=True)
    try:
        url=server.stdout.readline().split()[-1]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH") or None)
            page=browser.new_page(viewport={"width":1280,"height":1000})
            errors=[]
            page.on("pageerror",lambda error:errors.append(str(error)))
            page.goto(url)
            expect(page.locator("#bed")).to_have_text("22:30")
            if os.getenv("UI_SCREENSHOT"):
                page.screenshot(path=os.environ["UI_SCREENSHOT"],full_page=True)
            page.locator("#preview").click()
            expect(page.locator("#preview")).to_have_text("Stop sample")
            expect(page.locator("#preview")).to_have_text("Hear a sample",timeout=6000)
            page.get_by_role("button",name="Preferences",exact=True).click()
            page.locator("#newForm input").fill("Example sleeper")
            page.get_by_role("button",name="Create profile").click()
            expect(page.locator("#notice")).to_have_text("Profile created.")
            page.get_by_role("button",name="Sleep diary",exact=True).click()
            for day,time in [("2024-01-01","23:55"),("2024-01-02","00:05"),("2024-01-03","00:10")]:
                form=page.locator("#nightForm")
                for key,value in dict(date=day,bedtime=time,minutes="8").items():
                    form.locator(f"[name={key}]").fill(value)
                form.locator("[name=comfort]").select_option("4")
                form.locator("button").click()
                expect(page.locator("#history")).to_contain_text(day)
            page.get_by_role("button",name="Room",exact=True).click()
            expect(page.locator("#suggestion")).to_contain_text("00:05")
            page.locator("#adopt").click()
            expect(page.locator("#bed")).to_have_text("00:05")
            expect(page.locator("#timer")).to_have_text("8 min")
            page.locator("#profiles").select_option("1")
            expect(page.locator("#bed")).to_have_text("22:30")
            page.set_viewport_size({"width":390,"height":844})
            page.reload()
            expect(page.locator("#bed")).to_have_text("22:30")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator("#sensorBtn").click()
            expect(page.locator("#sensorBtn")).to_have_text("Disconnect feed")
            page.locator("#sensorBtn").click()
            expect(page.locator("#sensorBtn")).to_have_text("Connect feed")
            page.locator("#usb").click()
            expect(page.locator("#notice")).to_contain_text("--speaker")
            assert not errors,errors
            browser.close()
            print("PASS: desktop and 390px mobile, profile isolation, audio preview, diary, apply suggestion, sensor and USB controls.")
    finally:
        server.terminate()
        server.wait(timeout=5)
