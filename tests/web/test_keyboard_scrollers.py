"""Tests for the web keyboard with scrolling layouts."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract
import http.server, threading, socketserver, time, os
from playwright.sync_api import sync_playwright
JS = _extract.kbd_js()

def serve(files):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body, ctype = files.get(self.path.split("?")[0], (None, None))
            if body is None: self.send_response(404); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body.encode())
        def log_message(self, *a): pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv, srv.server_address[1]

def helpers(page_or_frame, page):
    f = page_or_frame
    def rect_of(sel): return f.evaluate("(s)=>{const r=document.querySelector(s).getBoundingClientRect();return [r.left,r.top,r.right,r.bottom]}", sel)
    def kb_top(): return f.evaluate("document.getElementById('armada-yomitan-kbd-host').shadowRoot.getElementById('kb').getBoundingClientRect().top")
    def key_center(label): return f.evaluate("(l)=>{const k=[...document.getElementById('armada-yomitan-kbd-host').shadowRoot.querySelectorAll('.k')].find(x=>x.textContent===l);const r=k.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}", label)
    return rect_of, kb_top, key_center

with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 472, "height": 411}, device_scale_factor=2.625, has_touch=True); page = ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    print("=== a Yomitan-style layout: body doesn't scroll, an inner container does; plus a fixed modal with its own scroller")
    rows = "".join(f'<div style="height:60px"><input id=i{n} placeholder="setting {n}" style="width:80%"></div>' for n in range(30))
    tas = "".join(f'<div style="height:90px"><textarea id=m{n} style="width:90%;height:70px"></textarea></div>' for n in range(12))
    page.set_content(f"""<body style="margin:0;overflow:hidden;height:100vh"><div id=main style="height:100vh;overflow-y:auto">{rows}</div>
      <div id=modal style="display:none;position:fixed;top:10px;left:10px;right:10px;bottom:10px;background:#dde;overflow:auto;border:2px solid #446">{tas}</div>""")
    page.add_script_tag(content=JS); page.wait_for_timeout(200)
    rect_of, kb_top, key_center = helpers(page, page)
    page.evaluate("document.getElementById('main').scrollTop = 1e6"); page.wait_for_timeout(100)
    page.touchscreen.tap(100, rect_of("#i29")[1] + 10); page.wait_for_timeout(700)
    r = rect_of("#i29"); print("last setting at the bottom of the scroller: field bottom %.0f, keyboard top %.0f -> clear: %s" % (r[3], kb_top(), r[3] <= kb_top()))
    print("the extra room went inside the scroller, not the page:", page.evaluate("document.getElementById('main').querySelectorAll('[data-armada-yomitan-kbd-spacer]').length"), page.evaluate("[...document.body.children].filter(c=>c.hasAttribute('data-armada-yomitan-kbd-spacer')).length"))
    page.touchscreen.tap(*key_center("z")); page.wait_for_timeout(80); print("typed into it:", repr(page.evaluate("document.getElementById('i29').value")))
    page.touchscreen.tap(*key_center("Hide")); page.wait_for_timeout(700)
    print("after Hide the scroller is back to normal size:", page.evaluate("document.querySelectorAll('[data-armada-yomitan-kbd-spacer]').length") == 0)
    page.evaluate("document.getElementById('modal').style.display='block'; document.getElementById('modal').scrollTop=1e6"); page.wait_for_timeout(100)
    page.touchscreen.tap(100, rect_of("#m11")[1] + 20); page.wait_for_timeout(700)
    r = rect_of("#m11"); print("a field at the bottom of a fixed modal: bottom %.0f, keyboard top %.0f -> clear: %s" % (r[3], kb_top(), r[3] <= kb_top()), "| room inside the modal:", page.evaluate("document.getElementById('modal').querySelectorAll('[data-armada-yomitan-kbd-spacer]').length"))
    page.touchscreen.tap(*key_center("q")); page.wait_for_timeout(80); print("typed into the modal field:", repr(page.evaluate("document.getElementById('m11').value")))
    page.touchscreen.tap(440, 100); page.wait_for_timeout(600)
    print("tap elsewhere in the modal: keyboard closes, room removed:", not page.evaluate("window.__armadaYomitanKbd.isOpen()"), page.evaluate("document.querySelectorAll('[data-armada-yomitan-kbd-spacer]').length") == 0)

    print('page errors:', errs)
    b.close()
