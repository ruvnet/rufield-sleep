"""Exercise the static console under the GitHub project path, or at its public URL."""
import argparse
import functools
import json
import os
import tempfile
import threading
from contextlib import ExitStack
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect
from build_pages import build

def check(url, browser):
    for width in (1280,390):
        context=browser.new_context(viewport={"width":width,"height":844},accept_downloads=True)
        page=context.new_page()
        requests=[]
        errors=[]
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on("request",lambda req:requests.append(req.url))
        page.goto(url,wait_until="domcontentloaded")
        expect(page.locator("#edition")).to_have_text("BROWSER CONSOLE")
        expect(page.locator("#bed")).to_have_text("22:30")
        expect(page.locator("#usb")).to_be_hidden()
        expect(page.locator("#hostingNote")).to_be_visible()
        assert page.locator('.brand').evaluate('(a)=>a.href')==url
        assert page.locator('body').evaluate('(b)=>getComputedStyle(b).backgroundColor')!="rgba(0, 0, 0, 0)"
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        page.locator("#preview").click()
        expect(page.locator("#preview")).to_have_text("Stop sample")
        expect(page.locator("#preview")).to_have_text("Hear a sample",timeout=6000)
        page.get_by_role("button",name="Preferences",exact=True).click()
        page.locator("#newForm input").fill("Test sleeper")
        page.get_by_role("button",name="Create profile").click()
        expect(page.locator("#notice")).to_have_text("Profile created.")
        page.get_by_role("button",name="Sleep diary",exact=True).click()
        for day,t in [("2024-01-01","23:55"),("2024-01-02","00:05"),("2024-01-03","00:10")]:
            form=page.locator("#nightForm")
            for key,value in dict(date=day,bedtime=t,minutes="8").items():
                form.locator(f"[name={key}]").fill(value)
            form.locator("[name=comfort]").select_option("4")
            form.locator("button").click()
            expect(page.locator("#history")).to_contain_text(day)
        page.get_by_role("button",name="Room",exact=True).click()
        page.locator("#adopt").click()
        expect(page.locator("#bed")).to_have_text("00:05")
        expect(page.locator("#timer")).to_have_text("8 min")
        page.locator("#play").click()
        expect(page.locator("#speakerInfo")).to_contain_text("Pink noise playing")
        page.locator("#stop").click()
        expect(page.locator("#stop")).to_be_disabled()
        page.reload()
        page.locator("#profiles").select_option(label="Test sleeper")
        expect(page.locator("#bed")).to_have_text("00:05")
        page.get_by_role("button",name="Preferences",exact=True).click()
        with page.expect_download() as download:
            page.locator("#exportDiary").click()
        data=Path(download.value.path()).read_bytes()
        assert len(json.loads(data)["profiles"][1]["nights"])==3
        page.on("dialog",lambda dialog:dialog.accept())
        page.locator("#forget").click()
        expect(page.locator("#notice")).to_have_text("Diary erased.")
        page.locator("#diaryFile").set_input_files({"name":"restored.json","mimeType":"application/json","buffer":data})
        expect(page.locator("#notice")).to_have_text("Diary restored in this tab.")
        page.locator("#profiles").select_option(label="Test sleeper")
        page.get_by_role("button",name="Sleep diary",exact=True).click()
        expect(page.locator("#history")).to_contain_text("2024-01-03")
        assert not errors, errors
        assert all(urlsplit(u).netloc==urlsplit(url).netloc and "/api/" not in urlsplit(u).path for u in requests), requests
        context.close()
        print(f"PASS {width}px: audio, profile, diary, suggestions, restore and project assets",flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url",help="Published URL ending in /")
    args=parser.parse_args()
    with ExitStack() as stack:
        if args.url:
            url=args.url
        else:
            tmp=Path(stack.enter_context(tempfile.TemporaryDirectory()))
            build(tmp/"rufield-sleep")
            handler=functools.partial(SimpleHTTPRequestHandler,directory=str(tmp))
            server=ThreadingHTTPServer(("127.0.0.1",0),handler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            stack.callback(server.server_close)
            stack.callback(server.shutdown)
            url=f"http://127.0.0.1:{server.server_port}/rufield-sleep/"
        pw=stack.enter_context(sync_playwright())
        browser=pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH") or None)
        stack.callback(browser.close)
        check(url,browser)

if __name__=="__main__":
    main()
