"""Tests that Yomitan's page scanner skips our page."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract
import json, shutil, socketserver, threading, http.server, tempfile
m = _extract.load_module(os.path.join(tempfile.gettempdir(), "armada-yomitan-test-home"))
from playwright.sync_api import sync_playwright
CHROME = os.environ.get("CHROME_PATH", "")          # a FULL Chromium (extensions do not load in the headless shell)

def make_ext(path, patch):
    shutil.rmtree(path, ignore_errors=True); os.makedirs(path)
    manifest = {"manifest_version": 3, "name": "scanner stand-in", "version": "1",
                "content_scripts": [{"matches": ["<all_urls>"], "js": ["cs.js"], "run_at": "document_start", "all_frames": True, "match_about_blank": True},
                                    {"matches": ["https://docs.google.com/*"], "js": ["cs.js"]}],
                "web_accessible_resources": [{"resources": ["page.html"], "matches": ["http://127.0.0.1/*", "http://localhost/*"]}]}
    if patch: manifest = m.patch_manifest(manifest)
    json.dump(manifest, open(path + "/manifest.json", "w"))
    open(path + "/cs.js", "w").write("document.documentElement.setAttribute('data-scanner', 'yes')")
    open(path + "/page.html", "w").write("<body><p id=t>an extension page (like Yomitan's search page)</p><script src='own.js'></script>")
    open(path + "/own.js", "w").write("document.documentElement.setAttribute('data-own', 'yes')")

def serve(host):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(b"<body><p>some text to touch</p>")
        def log_message(self, *a): pass
    srv = socketserver.TCPServer((host, 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv.server_address[1]

ports = {h: serve(h) for h in ("127.0.0.1", "127.0.0.2")}
def run(patch):
    d = f"/tmp/csext_{'patched' if patch else 'plain'}"; make_ext(d, patch)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(f"/tmp/csprof_{patch}", executable_path=CHROME or p.chromium.executable_path, headless=False, args=["--headless=new", "--no-sandbox", f"--disable-extensions-except={d}", f"--load-extension={d}"])
        page = ctx.new_page(); res = {}
        for name, url in (("127.0.0.1 (our page)", f"http://127.0.0.1:{ports['127.0.0.1']}/?t=abc"), ("localhost (our page, other spelling)", f"http://localhost:{ports['127.0.0.1']}/"), ("127.0.0.2 (any other page)", f"http://127.0.0.2:{ports['127.0.0.2']}/")):
            page.goto(url); page.wait_for_timeout(500); res[name] = page.evaluate("document.documentElement.getAttribute('data-scanner')")
        sw = ctx.service_workers; ext_id = None
        pages_ok = None
        try:
            bg = ctx.background_pages
        except Exception: pass
        ctx.close()
    return res
for patch in (False, True):
    shutil.rmtree(f"/tmp/csprof_{patch}", ignore_errors=True)
    print("manifest", "PATCHED by armada_yomitan" if patch else "as shipped", "-> the page scanner was injected into:")
    for k, v in run(patch).items(): print("   %-40s %s" % (k, "yes" if v else "no"))
m2 = json.load(open("/tmp/csext_patched/manifest.json")); print("\npatched content scripts' exclusions:", [c.get("exclude_matches") for c in m2["content_scripts"]])
print("patching twice adds nothing more:", m.patch_manifest(json.loads(json.dumps(m2))) == m2)
