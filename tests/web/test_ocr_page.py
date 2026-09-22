"""Tests for the served page's node number box."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract
import struct, io, time, zlib, tempfile
m = _extract.load_module(os.path.join(tempfile.gettempdir(), "armada-yomitan-test-home"))
strings = m.strings
from playwright.sync_api import sync_playwright

def png(w, h):
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00" + b"\x00\x00\x00" * w)) + chunk(b"IEND", b"")

mode = {"v": "ok"}
def fake_capture(cfg, node=None, timeout=8):
    if mode["v"] == "ok": return png(1920, 1080)
    if mode["v"] == "text": return b"not a picture at all, just some bytes"
    raise RuntimeError("no such stream (node %s)" % node)
m.capture_png = fake_capture
m.list_capture_nodes = lambda: []
ui = m.WebUI(m.Config()); ui.start()
err = io.StringIO(); real_stderr = sys.stderr; sys.stderr = err

with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 472, "height": 411}, device_scale_factor=2.625, has_touch=True); page = ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(f"http://127.0.0.1:{ui.port}/?t={ui.token}"); page.wait_for_timeout(1500)
    def center(sel): return page.evaluate("(s)=>{const r=document.querySelector(s).getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}", sel)
    def tap(sel): page.touchscreen.tap(*center(sel)); page.wait_for_timeout(350)
    def key(l): return page.evaluate("(l)=>{const k=[...document.getElementById('armada-yomitan-kbd-host').shadowRoot.querySelectorAll('.k')].find(x=>x.textContent===l);const r=k.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}", l)
    def tap_key(l): page.touchscreen.tap(*key(l)); page.wait_for_timeout(70)
    is_open = lambda: page.evaluate("window.__armadaYomitanKbd.isOpen()")
    hidden = lambda sel: page.evaluate("(s)=>document.querySelector(s).hidden", sel)

    tap("#cfg"); tap("#srcbtn"); page.wait_for_timeout(500)
    print("Settings > Top screen source > Choose... opens the list:", not hidden("#sources"))
    print("the node number box is there:", page.evaluate("!!document.getElementById('snode') && getComputedStyle(document.getElementById('snode')).display !== 'none'"), "| status line:", repr(page.evaluate("document.getElementById('sstatus').textContent")))
    page.screenshot(path="/tmp/armada_yomitan_sources_closed.png")
    tap("#snode"); page.wait_for_timeout(500)
    print("tap the box: the keyboard opens:", is_open(), "| on the digits page (no letters):", page.evaluate("[...document.getElementById('armada-yomitan-kbd-host').shadowRoot.querySelectorAll('.k')].every(k=>k.textContent!=='q')"))
    page.screenshot(path="/tmp/armada_yomitan_sources_keyboard.png")
    tap_key("3"); tap_key("4"); print("typed:", repr(page.evaluate("document.getElementById('snode').value")), "| the box is still visible above the keyboard:", page.evaluate("document.getElementById('snode').getBoundingClientRect().bottom <= document.getElementById('armada-yomitan-kbd-host').shadowRoot.getElementById('kb').getBoundingClientRect().top"))
    ui.on_status("")
    page.touchscreen.tap(*key("Enter")); page.wait_for_timeout(1200)
    print("\n--- Enter on the keyboard submits (a working node)")
    print("the node is in use:", ui.cfg.capture_node, "| size remembered:", ui.prefs["capture_size"], "| label:", ui.prefs["capture_label"], "| saved:", m.load_prefs()["capture_size"])
    print("the list closed itself:", hidden("#sources"), "| status:", ui.last_status)

    print("\n--- a node that gives no picture")
    mode["v"] = "fail"; tap("#srcbtn"); page.wait_for_timeout(300)
    page.evaluate("document.getElementById('snode').value=''"); tap("#snode"); tap_key("9"); tap_key("9"); tap_key("9")
    page.touchscreen.tap(*center("#suse")) if False else None
    page.evaluate("document.getElementById('suse').click()"); page.wait_for_timeout(900)
    print("the list stays open, the box keeps the number:", not hidden("#sources"), page.evaluate("document.getElementById('snode').value"))
    print("the reason is on the page:", repr(page.evaluate("document.getElementById('sstatus').textContent")))
    print("and printed to the console:", strings.NODE_NO_FRAME.split(":")[0].format(node=999) in err.getvalue(), "| the node in use is unchanged:", ui.cfg.capture_node)
    mode["v"] = "text"; page.evaluate("document.getElementById('suse').click()"); page.wait_for_timeout(900); print("bytes that aren't a picture:", repr(page.evaluate("document.getElementById('sstatus').textContent")))
    print("\n--- input that isn't a number")
    page.evaluate("document.getElementById('snode').value='abc'; document.getElementById('suse').click()"); page.wait_for_timeout(300); print("page says:", repr(page.evaluate("document.getElementById('sstatus').textContent")), "| nothing was sent:", ui.cfg.capture_node == "34")
    page.evaluate("document.getElementById('snode').value=''; document.getElementById('suse').click()"); page.wait_for_timeout(300); print("empty:", repr(page.evaluate("document.getElementById('sstatus').textContent")))
    ui.cmd_node_manual("12ab"); page.wait_for_timeout(300); print("the server refuses non-digits too:", repr(page.evaluate("document.getElementById('sstatus').textContent")))

    print("\n--- the check on Yomitan's settings page (its helper can't load here: no extension)")
    n0 = ui._kbdlog; tap("#back") if not hidden("#sources") else None
    page.evaluate("document.getElementById('sources').hidden = true; document.getElementById('prefs').hidden = false")
    page.evaluate("document.getElementById('yset').click()"); page.wait_for_timeout(7000)
    print("no hello from the frame -> the page reported it:", ui._kbdlog > n0, "| status line:", ui.last_status)
    print("console:", [l for l in err.getvalue().splitlines() if "Keyboard:" in l][-1:])
    print("page errors:", [e for e in errs if "postMessage" not in e])
    b.close()
sys.stderr = real_stderr
ui.shutdown()
