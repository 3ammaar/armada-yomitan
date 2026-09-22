"""Tests for the web keyboard across an iframe."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract
import http.server, threading, socketserver
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

rows = "".join(f'<div style="height:60px"><input id=i{n} placeholder="setting {n}" style="width:80%"></div>' for n in range(24))
FRAME = f'''<body style="margin:0;overflow:hidden;height:100vh;font:16px sans-serif"><div id=content style="height:100vh;overflow-y:auto">
<h3>Yomitan Settings</h3>{rows}<div style="height:60px"><input id=num type=number style="width:40%"><textarea id=ta></textarea></div><div style="height:60px"><input id=last style="width:80%"></div></div>
<script>window.ev=[];for(const id of ['i0','last']){{const e=document.getElementById(id);for(const t of ['input','change','keydown'])e.addEventListener(t,x=>ev.push(id+':'+t+(x.key?':'+x.key:'')))}}</script>
<script src="/kbd.js" defer></script>'''

with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 472, "height": 411}, device_scale_factor=2.625, has_touch=True); errs = []
    s2, p2 = serve({"/frame.html": (FRAME, "text/html"), "/kbd.js": (JS, "application/javascript")})
    parent_html = f'''<body style="margin:0;background:#15171a"><div id=head style="height:40px;background:#333;color:#fff">armada-yomitan</div><input id=own style="width:90%;margin:4px">
      <div id=ov style="position:fixed;top:70px;left:0;right:0;bottom:0;display:flex;flex-direction:column"><button id=back style="height:30px">Back</button><iframe id=fr src="http://127.0.0.1:{p2}/frame.html" style="flex:1;border:0;width:100%"></iframe></div>
      <script>window.ARMADA_YOMITAN_KBD_TRUST=['http://127.0.0.1:{p2}'];window.reports=[];window.armadaYomitanKbdReport=m=>reports.push(m)</script><script src="/kbd.js"></script>'''
    s1, p1 = serve({"/": (parent_html, "text/html"), "/kbd.js": (JS, "application/javascript")})
    page = ctx.new_page(); page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(f"http://127.0.0.1:{p1}/"); page.wait_for_timeout(900)
    fr = [f for f in page.frames if f != page.main_frame][0]
    off = lambda: page.evaluate("(()=>{const r=document.getElementById('fr').getBoundingClientRect();return [r.left,r.top,r.bottom]})()")
    finner = lambda sel: fr.evaluate("(s)=>{const r=document.querySelector(s).getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2,r.bottom]}", sel)
    def tap_field(sel):
        o = off(); c = finner(sel); page.touchscreen.tap(o[0] + c[0], o[1] + c[1]); page.wait_for_timeout(600)
    pk = lambda: page.evaluate("window.__armadaYomitanKbd.isOpen()")
    def key(l): return page.evaluate("(l)=>{const k=[...document.getElementById('armada-yomitan-kbd-host').shadowRoot.querySelectorAll('.k')].find(x=>x.textContent===l);const r=k.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}", l)
    def tap_key(l): page.touchscreen.tap(*key(l)); page.wait_for_timeout(80)
    kb_top = lambda: page.evaluate("document.getElementById('armada-yomitan-kbd-host').shadowRoot.getElementById('kb').getBoundingClientRect().top")
    fval = lambda sel: fr.evaluate("(s)=>document.querySelector(s).value", sel)

    print("=== an embedded page (Yomitan's settings) with its keyboard drawn by the page around it")
    print("page and frame are different origins:", page.evaluate("location.origin") != fr.evaluate("location.origin"))
    print("inside the frame the script is an agent:", fr.evaluate("window.__armadaYomitanKbd.role()"), "| the outer page is the host:", page.evaluate("window.__armadaYomitanKbd.role()"))
    print("the outer page heard from the frame (hello/ack):", page.evaluate("window.__armadaYomitanKbd.heardFrom(document.getElementById('fr'))"))
    tap_field("#i0")
    print("tap a field in the frame: the OUTER page's keyboard opens:", pk(), "| nothing is drawn inside the frame:", fr.evaluate("!document.getElementById('armada-yomitan-kbd-host')"))
    for ch in "http": tap_key(ch)
    tap_key("123"); tap_key(":"); tap_key("/"); tap_key("/")
    print("typed through the outer keyboard into the frame's field:", repr(fval("#i0")), "| the field kept focus in the frame:", fr.evaluate("document.activeElement.id"))
    tap_key("abc"); tap_key("Del"); print("Del:", repr(fval("#i0")))
    print("frame saw input events (a real edit, not a value poke):", fr.evaluate("ev.filter(x=>x==='i0:input').length"))
    fr.evaluate("ev.length=0"); tap_key("Enter"); print("Enter reached the field as keydown + change:", fr.evaluate("ev.filter(x=>x.startsWith('i0:')).join(' ')"))
    kx = page.evaluate("document.getElementById('armada-yomitan-kbd-host').getBoundingClientRect().left"); print("the keyboard spans the whole screen width:", kx == 0)

    print("\n--- room for a field at the bottom of the frame's scroller")
    fr.evaluate("document.getElementById('content').scrollTop = 1e6"); page.wait_for_timeout(100)
    tap_field("#last"); page.wait_for_timeout(400)
    o = off(); fb = o[1] + finner("#last")[2]; print("field bottom %.0f (outer page), keyboard top %.0f -> clear: %s" % (fb, kb_top(), fb <= kb_top()))
    print("room added inside the frame's scroller:", fr.evaluate("document.querySelectorAll('[data-armada-yomitan-kbd-spacer]').length"))
    tap_key("z"); print("typed:", repr(fval("#last")))

    print("\n--- closing")
    tap_key("Hide"); page.wait_for_timeout(200)
    page.wait_for_timeout(500)
    print("Hide: keyboard closed:", not pk(), "| the frame took its room back:", fr.evaluate("document.querySelectorAll('[data-armada-yomitan-kbd-spacer]').length") == 0, "| field still focused:", fr.evaluate("document.activeElement.id"))
    tap_field("#last"); print("tap the focused field again: keyboard back:", pk())
    tap_field("#num"); print("a number field in the frame opens on the digits page:", key("7") is not None and page.evaluate("[...document.getElementById('armada-yomitan-kbd-host').shadowRoot.querySelectorAll('.k')].every(k=>k.textContent!=='q')"))
    tap_key("4"); tap_key("2"); print("number typed:", repr(fval("#num")))
    o = off(); fw = fr.evaluate("innerWidth"); page.touchscreen.tap(o[0] + fw * 0.96, o[1] + 80); page.wait_for_timeout(600)
    print("tap an empty spot inside the frame: keyboard closes:", not pk(), "| tapped:", fr.evaluate("document.elementFromPoint(%f, 80).tagName" % (fw * 0.96)))
    tap_field("#i0"); page.touchscreen.tap(100, 20); page.wait_for_timeout(300); print("tap the outer page's own header: keyboard closes:", not pk())
    tap_field("#i0"); page.evaluate("document.getElementById('ov').style.display='none'"); page.wait_for_timeout(900); print("the frame goes away (settings dismissed): keyboard closes by itself:", not pk())
    page.evaluate("document.getElementById('ov').style.display='flex'"); page.wait_for_timeout(300)

    print("\n--- the outer page's own field still works alongside")
    own = page.evaluate("(()=>{const r=document.getElementById('own').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()"); page.touchscreen.tap(*own); page.wait_for_timeout(600)
    print("tap the page's own field: keyboard opens:", pk()); tap_key("o"); tap_key("k"); print("typed:", repr(page.evaluate("document.getElementById('own').value")))
    page.touchscreen.tap(100, 20); page.wait_for_timeout(500)

    print("\n--- diagnostics")
    fr.evaluate("window.dispatchEvent(new ErrorEvent('error', {message:'boom in the helper', filename:'http://x/armada-yomitan-kbd.js'}))"); page.wait_for_timeout(200)
    print("a script error inside the frame's helper reaches the outer page's report hook:", page.evaluate("reports"))

    print("\n=== a frame whose outer page has NO keyboard host: it draws its own")
    s3, p3 = serve({"/": (f'<body><iframe id=fr src="http://127.0.0.1:{p2}/frame.html" style="position:fixed;inset:0;border:0;width:100%;height:100%"></iframe>', "text/html")})
    page3 = ctx.new_page(); page3.goto(f"http://127.0.0.1:{p3}/"); page3.wait_for_timeout(2200)
    fr3 = [f for f in page3.frames if f != page3.main_frame][0]
    print("after 1.5 s with no answer the script becomes its own host:", fr3.evaluate("window.__armadaYomitanKbd.role()"))
    c = fr3.evaluate("(()=>{const r=document.getElementById('i0').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()"); page3.touchscreen.tap(*c); page3.wait_for_timeout(600)
    print("tap a field: the keyboard opens inside the frame:", fr3.evaluate("window.__armadaYomitanKbd.isOpen()"))
    print("page errors:", errs)
    b.close()
