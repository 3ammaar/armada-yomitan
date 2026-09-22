"""Tests for Re-install dependencies in the served page's Settings."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract
from playwright.sync_api import sync_playwright

home = tempfile.mkdtemp(prefix="ay-reinstall-")
m = _extract.load_module(home)
strings = m.strings
FAILED = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{extra}]" if extra and not ok else ""))
    if not ok:
        FAILED.append(label)


m.install_state.mark(*m.install_state.STEPS)
ui = m.WebUI(m.Config())
ui.start()

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 472, "height": 411}, device_scale_factor=2.625, has_touch=True).new_page()
    page.goto(f"http://127.0.0.1:{ui.port}/?t={ui.token}")
    page.wait_for_timeout(1200)

    def tap(selector):
        page.evaluate("(s)=>document.querySelector(s).scrollIntoView({block: 'center'})", selector)
        page.wait_for_timeout(150)
        x, y = page.evaluate("(s)=>{const r=document.querySelector(s).getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}", selector)
        page.touchscreen.tap(x, y)
        page.wait_for_timeout(350)

    hidden = lambda selector: page.evaluate("(s)=>document.querySelector(s).hidden", selector)
    tap("#cfg")
    tap("#reinstall")
    check("Re-install dependencies asks first, with the question and Yes and No",
          not hidden("#confirm") and page.inner_text("#cq") == strings.PAGE_REINSTALL_CONFIRM
          and page.inner_text("#cyes") == strings.YES and page.inner_text("#cno") == strings.NO)
    tap("#cno")
    check("No closes the question and does nothing", hidden("#confirm") and ui.after is None and not ui.done.is_set() and m.install_state.complete())
    tap("#reinstall")
    tap("#cyes")
    page.wait_for_timeout(500)
    check("Yes clears what is recorded as installed, so the next start opens the install window", m.install_state.load() == set())
    check("...and ends the app with a request to start again", ui.after == "restart" and ui.done.is_set(), str(ui.after))
    os.environ["ARMADA_YOMITAN_VIA_DECKY"] = "1"
    ui_decky = m.WebUI(m.Config())
    ui_decky.start()
    decky_page = browser.new_context(viewport={"width": 472, "height": 411}, device_scale_factor=2.625, has_touch=True).new_page()
    decky_page.goto(f"http://127.0.0.1:{ui_decky.port}/?t={ui_decky.token}")
    decky_page.wait_for_timeout(1200)
    check("started from the Decky plugin the app has no Re-install dependencies button (the plugin installs)",
          decky_page.evaluate("document.getElementById('reinstall').parentElement.hidden") is True)
    check("...and by hand it is there", page.evaluate("document.getElementById('reinstall').parentElement.hidden") is False)
    del os.environ["ARMADA_YOMITAN_VIA_DECKY"]
    ui_decky.httpd.server_close()
    browser.close()

ui.httpd.server_close()
print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
