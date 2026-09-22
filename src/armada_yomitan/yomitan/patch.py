"""Patching Yomitan."""

import json
import os
import shutil

from armada_yomitan.assets import KBD_JS, YOMI_CSS, YOMI_JS
from armada_yomitan.paths import EXT_DIR

# a public key that only pins the extension ID; nothing is signed with it
YOMITAN_KEY = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA7FUqZazOagWCy32fFBgty64JWeBG/loxEmvy8ltU5w9Ja5Cym1wX0IkRY3EJwgIT7rmGYlogzH34bYn+z3/Kk1kWHuHOWquFDLCVKXgdNtcgIDAnwTNMO2/E1a5qpzuYhrtK85gtiuL2EMzMu7mUmvAzIgLjK9RgXLhaT+RdFhi4zdJHJuzeeXHFMhQXnUXZ4wcqBndN5oJrW3xMoYbZdy78gZoy0LD1qXK+kabCsEU/LzFqHfX0rDcfKLO6yrn8UBOIdH3r3kqAdG6m2M+em1vFpA2qoZ4/8wmo7UT0vjv1+6LgIjuv8jOHgLDntdPYPIpWPDvOz41Y9Ub68t2KawIDAQAB"


YOMITAN_ID = "mamldpidbmfomkolljejmgioalloiofd"


EMBED_PAGES = ["search.html", "settings.html"]


EMBED_MATCHES = ["http://127.0.0.1/*", "http://localhost/*"]


def patch_manifest(manifest):
    manifest["key"] = YOMITAN_KEY
    for script in manifest.get("content_scripts", []):
        excluded = script.setdefault("exclude_matches", [])
        excluded += [pattern for pattern in EMBED_MATCHES if pattern not in excluded]
    war = manifest.setdefault("web_accessible_resources", [])
    if manifest.get("manifest_version", 3) == 2:              # Manifest V2: a plain list of paths
        war += [p for p in EMBED_PAGES if p not in war]
    else:                                                     # Manifest V3: {resources, matches} entries
        entry = {"resources": list(EMBED_PAGES), "matches": list(EMBED_MATCHES)}
        if entry not in war:
            war.append(entry)
    return manifest


WELCOME_MARKER = "armada-yomitan-close-tab.js"


WELCOME_STUB = f'<!doctype html>\n<meta charset="utf-8">\n<title>Yomitan</title>\n<script src="{WELCOME_MARKER}"></script>\n'


CLOSE_TAB_JS = ("// Written by armada-yomitan: Yomitan's welcome guide would otherwise open on every browser start\n"
                "// and cover the bottom screen. Close this tab the moment it opens.\n"
                "chrome.tabs.getCurrent(function (tab) {\n"
                "  if (tab) { chrome.tabs.remove(tab.id); } else { window.close(); }\n"
                "});\n")


YOMI_CSS_NAME = "armada-yomitan.css"


YOMI_LINK = f'<link rel="stylesheet" type="text/css" href="/{YOMI_CSS_NAME}">'


YOMI_JS_NAME = "armada-yomitan.js"


YOMI_SCRIPT = f'<script src="/{YOMI_JS_NAME}" defer></script>'


KBD_JS_NAME = "armada-yomitan-kbd.js"


KBD_ENABLED = os.environ.get("ARMADA_YOMITAN_KEYBOARD") != "0"


KBD_SCRIPT = f'<script src="/{KBD_JS_NAME}" defer></script>'


KBD_PAGES = ("settings.html",)


KBD_OFF_JS = "// Written by armada-yomitan: ARMADA_YOMITAN_KEYBOARD=0, so the on-screen keyboard is off.\n"


KBD_PAGE_SCRIPT = f"<script>{KBD_JS}</script>" if KBD_ENABLED else ""


def kbd_patch_problems():
    if not KBD_ENABLED:
        return []
    problems = []
    for name in KBD_PAGES:
        try:
            with open(os.path.join(EXT_DIR, name)) as f:
                page = f.read()
        except OSError:
            problems.append(f"{name} isn't in {EXT_DIR}")
            continue
        if KBD_SCRIPT not in page:
            problems.append(f"{name} doesn't load {KBD_JS_NAME} (no </head> to put it before?)")
    try:
        with open(os.path.join(EXT_DIR, KBD_JS_NAME)) as f:
            if f.read() != KBD_JS:
                problems.append(f"{KBD_JS_NAME} in {EXT_DIR} isn't the current version")
    except OSError:
        problems.append(f"{KBD_JS_NAME} is missing from {EXT_DIR}")
    return problems


def apply_ext_patches():
    manifest_path = os.path.join(EXT_DIR, "manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)
    patched = patch_manifest(json.loads(json.dumps(manifest)))
    if patched != manifest:
        with open(manifest_path, "w") as f:
            json.dump(patched, f, indent=2)
    welcome = os.path.join(EXT_DIR, "welcome.html")
    if os.path.exists(welcome):
        with open(welcome) as f:
            current = f.read()
        if WELCOME_MARKER not in current and not os.path.exists(welcome + ".orig"):
            shutil.copyfile(welcome, welcome + ".orig")
    search = os.path.join(EXT_DIR, "search.html")
    if os.path.exists(search):
        with open(search) as f:
            page = f.read()
        extra = "".join(tag + "\n" for tag in (YOMI_LINK, YOMI_SCRIPT) if tag not in page)
        if extra and "</head>" in page:
            if not os.path.exists(search + ".orig"):
                shutil.copyfile(search, search + ".orig")
            with open(search, "w") as f:
                f.write(page.replace("</head>", extra + "</head>", 1))
    for name in KBD_PAGES:
        page_path = os.path.join(EXT_DIR, name)
        if not os.path.exists(page_path):
            continue
        with open(page_path) as f:
            page = f.read()
        if KBD_SCRIPT not in page and "</head>" in page:
            if not os.path.exists(page_path + ".orig"):
                shutil.copyfile(page_path, page_path + ".orig")
            with open(page_path, "w") as f:
                f.write(page.replace("</head>", KBD_SCRIPT + "\n</head>", 1))
    for name, text in (("welcome.html", WELCOME_STUB), (WELCOME_MARKER, CLOSE_TAB_JS), (YOMI_CSS_NAME, YOMI_CSS),
                       (YOMI_JS_NAME, YOMI_JS), (KBD_JS_NAME, KBD_JS if KBD_ENABLED else KBD_OFF_JS)):
        path = os.path.join(EXT_DIR, name)
        try:
            with open(path) as f:
                if f.read() == text:
                    continue
        except OSError:
            pass
        with open(path, "w") as f:
            f.write(text)
    return patched.get("version", "?")
