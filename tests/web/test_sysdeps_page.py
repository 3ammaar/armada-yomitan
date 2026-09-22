"""Tests for the system-packages view."""

import os
import stat
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract
from playwright.sync_api import sync_playwright

work = tempfile.mkdtemp(prefix="ay-sysdeps-page-")
m = _extract.load_module(f"{work}/home")
strings = m.strings
sp = sys.modules["armada_yomitan.syspackages"]
bindir, LOG = f"{work}/bin", f"{work}/calls.log"
os.makedirs(bindir)
os.environ["LOG"] = LOG


def fake(name, body):
    path = f"{bindir}/{name}"
    open(path, "w").write("#!/bin/bash\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


fake("gst-launch-1.0", "exit 0")
fake("gst-inspect-1.0", "exit 0")
fake("tesseract", 'echo "List of available languages:"; echo jpn; echo jpn_vert')
fake("armada-run-bottom", "exit 0")
fake("ldconfig", 'for l in ${FAKE_LIBS:-}; do echo "	$l (libc6,AArch64) => /usr/lib64/$l"; done')
fake("rpm-ostree", 'echo "rpm-ostree $*" >> "$LOG"; echo "Staging deployment... done"; exit 0')
fake("systemctl", 'echo "systemctl $*" >> "$LOG"; exit 0')
os.environ["PATH"] = f"{bindir}:" + os.environ["PATH"]
sp.have_gtk = lambda: True
os.environ["FAKE_LIBS"] = ""


def calls():
    return open(LOG).read().splitlines() if os.path.exists(LOG) else []


def serve():
    ui = m.WebUI(m.Config())
    ui.start()
    ui.cmd_sysdeps_check()
    return ui


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 472, "height": 411}, device_scale_factor=2.625, has_touch=True)
    page, errs = ctx.new_page(), []
    page.on("pageerror", lambda e: errs.append(str(e)))
    ui = serve()
    page.goto(f"http://127.0.0.1:{ui.port}/?t={ui.token}")
    page.wait_for_timeout(1500)
    hidden = lambda sel: page.evaluate("(s)=>document.querySelector(s).hidden", sel)
    text = lambda sel: page.evaluate("(s)=>document.querySelector(s).textContent", sel)

    def center(sel):
        return page.evaluate("(s)=>{const r=document.querySelector(s).getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}", sel)

    def tap(sel):
        page.touchscreen.tap(*center(sel))
        page.wait_for_timeout(350)

    def key(l):
        return page.evaluate("(l)=>{const k=[...document.getElementById('armada-yomitan-kbd-host').shadowRoot.querySelectorAll('.k')].find(x=>x.textContent===l);const r=k.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}", l)

    print("--- not root, something is missing: the view opens by itself and says what to do (no password, no install)")
    print("the view is showing:", not hidden("#sysdeps"))
    print("it says what is missing and which package fixes it:", "libminizip.so.1" in text("#sdmissing") and "minizip-ng-compat" in text("#sdmissing"))
    print("optional ones are marked optional:", "optional" in text("#sdmissing"))
    print("it says to run as sudo or use the Decky plugin:", text("#sdinfo") == strings.NEEDS_ROOT, repr(text("#sdinfo")))
    print("there is no password field and no Install button:", page.evaluate("!document.getElementById('sdpass')") and hidden("#sdgo"))
    print("Settings shows the count:", "needed" in text("#sdnow"), "|", repr(text("#sdnow")))
    ui.cmd_sysdeps_install()
    print("asking the server to install anyway does nothing:", not any(c.startswith("rpm-ostree") for c in calls()))

    print("\n--- root: installing needs no password")
    real_geteuid = os.geteuid
    os.geteuid = lambda: 0
    ui_root = serve()
    page_root = ctx.new_page()
    page_root.goto(f"http://127.0.0.1:{ui_root.port}/?t={ui_root.token}")
    page_root.wait_for_timeout(1500)
    hidden = lambda sel: page_root.evaluate("(s)=>document.querySelector(s).hidden", sel)
    text = lambda sel: page_root.evaluate("(s)=>document.querySelector(s).textContent", sel)
    page = page_root
    print("the view offers Install and says what will happen:", not hidden("#sdgo") and text("#sdinfo") == strings.SYSDEPS_SOME_MISSING, repr(text("#sdinfo")))
    page.click("#sdgo")
    page.wait_for_timeout(2000)
    print("it installed, and says a restart is needed:", "Restart the device" in text("#sdinfo"), "|", repr(text("#sdinfo")))
    print("rpm-ostree's output is shown as it came:", "Staging deployment... done" in text("#sdlog"))
    print("the Restart button replaced Install:", not hidden("#sdrebootrow") and hidden("#sdgo"))
    layered = [c for c in calls() if c.startswith("rpm-ostree install")]
    print("rpm-ostree was asked for minizip-ng-compat, directly (no sudo):", len(layered) == 1 and "minizip-ng-compat" in layered[0] and not any(c.startswith("sudo") for c in calls()), layered)

    print("\n--- restart")
    page.click("#sdreboot")
    page.wait_for_timeout(1000)
    print("systemctl reboot was run:", "systemctl reboot" in calls(), calls()[-2:])

    print("\n--- Back / reopening from Settings")
    page.evaluate("document.getElementById('sdlater').click()")
    print("Back closes the view:", hidden("#sysdeps"))
    page.evaluate("document.getElementById('sdbtn').click()")
    page.wait_for_timeout(1500)
    print("the Settings row reopens it and re-checks:", not hidden("#sysdeps"))
    print("after the install it still offers the restart, and doesn't claim nothing was done:", not hidden("#sdrebootrow") and hidden("#sdgo") and "waiting for a restart" in text("#sdinfo"), repr(text("#sdinfo")))
    print("page errors:", errs)
    os.environ["ARMADA_YOMITAN_VIA_DECKY"] = "1"
    ui_decky = serve()
    page_decky = ctx.new_page()
    page_decky.goto(f"http://127.0.0.1:{ui_decky.port}/?t={ui_decky.token}")
    page_decky.wait_for_timeout(1500)
    print("even as root, started from the Decky plugin there is no Install, only the message:",
          page_decky.evaluate("document.getElementById('sdgo').hidden") and page_decky.evaluate("document.getElementById('sdinfo').textContent") == strings.NEEDS_ROOT)
    del os.environ["ARMADA_YOMITAN_VIA_DECKY"]
    os.geteuid = real_geteuid

    print("\n--- nothing missing: the view stays away")
    os.environ["FAKE_LIBS"] = "libminizip.so.1 libxcb-cursor.so.0"
    ui2 = serve()
    page2 = ctx.new_page()
    page2.goto(f"http://127.0.0.1:{ui2.port}/?t={ui2.token}")
    page2.wait_for_timeout(1500)
    print("no view:", page2.evaluate("document.getElementById('sysdeps').hidden"))
    print("Settings says all present:", page2.evaluate("document.getElementById('sdnow').textContent") == strings.PAGE_PACKAGES_ALL_PRESENT)
    b.close()
