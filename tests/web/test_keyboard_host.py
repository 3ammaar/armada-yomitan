"""Tests for the web keyboard as a standalone page."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract
import json, sys, time
from playwright.sync_api import sync_playwright
JS = _extract.kbd_js()
HTML = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<body style="margin:0;font:16px sans-serif">
<input id=hidden style="display:none" autofocus>
<input id=a placeholder=a style="width:90%;margin:8px"><br>
<textarea id=t style="width:90%;margin:8px" rows=3></textarea><br>
<div id=ce contenteditable style="border:1px solid #888;margin:8px;padding:4px;min-height:24px"></div>
<input id=n type=number style="margin:8px"><input id=ro readonly value=ro style="margin:8px"><input id=cb type=checkbox>
<div style="height:1400px">tall page</div><input id=bottom style="margin:8px">
<script>window.log=[]; document.getElementById('a').addEventListener('keydown',e=>{ if(e.key==='Enter') log.push('enter-keydown') }); document.getElementById('a').addEventListener('change',()=>log.push('change'));
document.getElementById('a').addEventListener('input',()=>log.push('input'));</script>"""

def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 472, "height": 411}, device_scale_factor=2.625, has_touch=True)
        page = ctx.new_page(); errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.set_content(HTML); page.add_script_tag(content=JS); page.wait_for_timeout(300)
        is_open = lambda: page.evaluate("window.__armadaYomitanKbd.isOpen()")
        def kb_rect(): return page.evaluate("(()=>{const r=document.getElementById('armada-yomitan-kbd-host').shadowRoot.getElementById('kb').getBoundingClientRect();return [r.left,r.top,r.width,r.height]})()")
        def key_center(label):
            return page.evaluate("(l)=>{const ks=[...document.getElementById('armada-yomitan-kbd-host').shadowRoot.querySelectorAll('.k')];const k=ks.find(x=>x.textContent===l);if(!k)return null;const r=k.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}", label)
        def tap_key(label):
            x, y = key_center(label); page.touchscreen.tap(x, y); page.wait_for_timeout(60)
        def tap_el(sel):
            r = page.evaluate("(s)=>{const r=document.querySelector(s).getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}", sel)
            page.touchscreen.tap(*r); page.wait_for_timeout(450)
        val = lambda sel: page.evaluate("(s)=>document.querySelector(s).value", sel)
        active = lambda: page.evaluate("document.activeElement.id")

        print("autofocus on a hidden field: keyboard open:", is_open())
        page.evaluate("document.getElementById('a').focus()"); page.wait_for_timeout(400)
        print("a page focusing a field by itself (no tap): keyboard open:", is_open())
        page.evaluate("document.activeElement.blur()")
        tap_el("#a"); print("tap on a text field: keyboard open:", is_open(), "| geometry:", [round(v) for v in kb_rect()], "| viewport:", page.evaluate("[innerWidth, innerHeight]"))

        print("\n--- typing")
        for ch in "hello": tap_key(ch)
        tap_key("Shift"); tap_key("W"); tap_key("o")
        print("value after h e l l o, Shift+w (one letter), o:", repr(val("#a")), "| still focused:", active())
        tap_key("Del"); tap_key("Space"); tap_key(","); tap_key(".")
        print("after Del, Space , .:", repr(val("#a")))
        tap_key("123"); [tap_key(c) for c in "42:/@"]; print("symbols page:", repr(val("#a")))
        tap_key("abc"); tap_key("x"); print("back to letters, x:", repr(val("#a")), "| focus kept:", active())
        page.evaluate("log.length=0"); tap_key("Enter"); print("Enter fired keydown+change on the field:", page.evaluate("log"))

        print("\n--- the whole keyboard is touchable: nearest key everywhere")
        kx, ky, kw, kh = kb_rect()
        rects = page.evaluate("[...document.getElementById('armada-yomitan-kbd-host').shadowRoot.querySelectorAll('.k')].map(k=>{const r=k.getBoundingClientRect();return [k.textContent,r.left,r.top,r.right,r.bottom]})")
        pts = [(kx + i, ky + j) for i in range(0, int(kw), 2) for j in range(0, int(kh), 2)]
        got = page.evaluate("(pts)=>pts.map(p=>window.__armadaYomitanKbd.keyAt(p[0],p[1]))", pts)
        def inside(x, y):
            for lab, l, t, r, bt in rects:
                if l <= x < r and t <= y < bt: return lab
        print("swept %d points, none without a key: %s" % (len(pts), all(g is not None for g in got)), "| points on a key go to that key:", all((inside(x, y) is None) or inside(x, y) == g for (x, y), g in zip(pts, got)))
        qx = [r for r in rects if r[0] == "q"][0]; wx = [r for r in rects if r[0] == "w"][0]
        gapx = (qx[3] + wx[1]) / 2 + 1; gapy = (qx[2] + qx[4]) / 2
        before = val("#a"); page.touchscreen.tap(gapx, gapy); page.wait_for_timeout(80); print("real touch in the gap between q and w typed:", repr(val("#a")[len(before):]))
        arow = [r for r in rects if r[0] == "a"][0]; before = val("#a"); page.touchscreen.tap(arow[1] - 8, (arow[2] + arow[4]) / 2); page.wait_for_timeout(80); print("real touch left of the 'a' row's start typed:", repr(val("#a")[len(before):]))
        print("keyboard still open after those:", is_open(), "| focus kept:", active())

        print("\n--- holding Del")
        page.evaluate("document.getElementById('a').value='abcdefghij'")
        cx, cy = key_center("Del")
        page.evaluate("([x,y])=>{const b=document.getElementById('armada-yomitan-kbd-host').shadowRoot.getElementById('kb'); b.dispatchEvent(new PointerEvent('pointerdown',{clientX:x,clientY:y,pointerId:9,bubbles:true,cancelable:true}))}", [cx, cy])
        page.wait_for_timeout(900); mid = val("#a")
        page.evaluate("([x,y])=>{const b=document.getElementById('armada-yomitan-kbd-host').shadowRoot.getElementById('kb'); b.dispatchEvent(new PointerEvent('pointerup',{clientX:x,clientY:y,pointerId:9,bubbles:true,cancelable:true}))}", [cx, cy])
        page.wait_for_timeout(300); end = val("#a"); print("10 chars, held Del ~0.9s ->", repr(mid), "| after release nothing more:", val("#a") == end and len(end) == len(mid), "| deleted more than one:", len(mid) < 9)

        print("\n--- other kinds of field")
        tap_el("#t"); tap_key("h"); tap_key("i"); tap_key("Enter"); tap_key("y"); print("textarea:", repr(val("#t")), "(Enter makes a new line)")
        tap_el("#ce"); tap_key("o"); tap_key("k"); print("contenteditable:", repr(page.evaluate("document.getElementById('ce').textContent")))
        tap_el("#n"); page.wait_for_timeout(100); print("number field opens on the digits page (has '7'):", key_center("7") is not None, "| no letters:", key_center("q") is None)
        tap_key("7"); tap_key("3"); print("number typed:", repr(val("#n")))
        tap_el("#ro"); print("read-only field: keyboard closes:", not is_open())
        tap_el("#a"); tap_el("#cb"); page.wait_for_timeout(400); print("tap a checkbox (not text): keyboard closes:", not is_open())

        print("\n--- hide, and bring it back")
        page.evaluate("(()=>{const g=document.createElement('button');g.id='ghost';g.textContent='under the keyboard';g.style.cssText='position:fixed;left:0;right:0;bottom:0;height:200px;z-index:1';window.ghost=0;g.addEventListener('click',()=>window.ghost++);g.addEventListener('mousedown',()=>window.ghost++);document.body.appendChild(g)})()")
        tap_el("#a"); tap_key("Hide"); page.wait_for_timeout(700); print("Hide key closes it:", not is_open(), "| field still focused:", active() == "a", "| the tap did not fall through to the page underneath:", page.evaluate("window.ghost") == 0)
        page.evaluate("document.getElementById('ghost').remove()")
        tap_el("#a"); print("tap the same (already focused) field again: back:", is_open())
        page.evaluate("window.scrollTo(0,0)"); page.wait_for_timeout(100); page.touchscreen.tap(300, 215); page.wait_for_timeout(500); print("tap on empty page (nothing there): closes:", not is_open(), "| what was tapped:", page.evaluate("document.elementFromPoint(300,215).tagName"))
        print("no leftover spacer:", page.evaluate("document.querySelectorAll('[data-armada-yomitan-kbd-spacer]').length") == 0)

        print("\n--- room: a field at the very bottom of a long page gets scrolled above the keyboard")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)"); page.wait_for_timeout(100)
        tap_el("#bottom"); page.wait_for_timeout(300)
        r = page.evaluate("(()=>{const r=document.getElementById('bottom').getBoundingClientRect();return [r.top, r.bottom, innerHeight]})()"); kx, ky, kw, kh = kb_rect()
        print("field bottom %.0f, keyboard top %.0f -> clear of the keyboard: %s" % (r[1], ky, r[1] <= ky))
        print("page errors:", errors)
        b.close()
main()
