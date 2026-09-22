"""Tests for Yomitan patching."""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract

FAILED = []


def check(label, ok):
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        FAILED.append(label)


home = tempfile.mkdtemp(prefix="armada-yomitan-home-")
m = _extract.load_module(home)
ext = tempfile.mkdtemp(prefix="armada-yomitan-ext-")
m.EXT_DIR = ext
manifest = {"manifest_version": 3, "name": "Yomitan", "version": "9.9",
            "web_accessible_resources": [{"resources": ["x"], "matches": ["<all_urls>"]}],
            "content_scripts": [{"matches": ["<all_urls>"], "js": ["a.js"]}, {"matches": ["https://docs.google.com/*"], "js": ["b.js"]}],
            "background": {"service_worker": "sw.js"}}
json.dump(manifest, open(ext + "/manifest.json", "w"))
for name in ("settings.html", "search.html", "welcome.html"):
    open(f"{ext}/{name}", "w").write(f"<html><head><title>{name}</title></head><body></body></html>")

check("before patching, the keyboard problems are listed", len(m.kbd_patch_problems()) == 2)
m.apply_ext_patches()
patched = json.load(open(ext + "/manifest.json"))
check("the extension ID is pinned (manifest key set)", patched.get("key") == m.YOMITAN_KEY)
check("search/settings pages are embeddable by our local page", any(set(e.get("resources", [])) >= set(m.EMBED_PAGES) for e in patched["web_accessible_resources"] if isinstance(e, dict)))
check("every content script excludes our own page (127.0.0.1 and localhost)",
      all(c.get("exclude_matches") == m.EMBED_MATCHES for c in patched["content_scripts"]))
before = open(ext + "/manifest.json").read()
m.apply_ext_patches()
check("running the patch again changes nothing", open(ext + "/manifest.json").read() == before)
check("welcome guide replaced by a self-closing stub", "chrome.tabs" in open(ext + "/" + m.WELCOME_MARKER).read() and m.WELCOME_MARKER in open(ext + "/welcome.html").read())
se = open(ext + "/search.html").read()
check("search page links our CSS and script", m.YOMI_LINK in se and m.YOMI_SCRIPT in se)
st = open(ext + "/settings.html").read()
check("settings page links the keyboard script exactly once", st.count(m.KBD_SCRIPT) == 1 and m.KBD_SCRIPT not in se)
check("originals are backed up", os.path.exists(ext + "/settings.html.orig") and os.path.exists(ext + "/search.html.orig"))
check("no keyboard problems once patched", m.kbd_patch_problems() == [])
check("ONE keyboard implementation: the page's inline script and Yomitan's file are the same text",
      open(ext + "/armada-yomitan-kbd.js").read() == m.KBD_JS and m.KBD_PAGE_SCRIPT == f"<script>{m.KBD_JS}</script>" and m.KBD_JS == _extract.kbd_js())
check("the served page carries the keyboard", "<!--ARMADA_YOMITAN_KBD-->" in m.PAGE_HTML)
os.remove(ext + "/armada-yomitan-kbd.js")
check("a missing script file is reported", any("missing" in p for p in m.kbd_patch_problems()))
open(ext + "/armada-yomitan-kbd.js", "w").write("old")
check("an out-of-date script file is reported", any("current version" in p for p in m.kbd_patch_problems()))
m.apply_ext_patches()
check("relaunching repairs both", m.kbd_patch_problems() == [])

out = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import _extract; m = _extract.load_module(%r); print(m.KBD_PAGE_SCRIPT == '', m.kbd_patch_problems() == [])" % (os.path.dirname(_extract.__file__), home)],
                     env=dict(os.environ, ARMADA_YOMITAN_KEYBOARD="0"), capture_output=True, text=True).stdout.strip()
check("ARMADA_YOMITAN_KEYBOARD=0: no script in the page, no problems reported", out == "True True")
print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
