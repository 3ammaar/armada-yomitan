"""Checks that all user-facing text lives in strings.py."""

import ast
import os
import re
import string
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract

sys.path.insert(0, _extract.SRC)
from armada_yomitan import assets, console, strings

FAILED = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{extra}]" if extra and not ok else ""))
    if not ok:
        FAILED.append(label)


PKG = os.path.join(_extract.SRC, "armada_yomitan")
DECKY = os.path.join(_extract.ROOT, "decky-plugin")
CONSTANTS = {n: v for n, v in vars(strings).items() if n.isupper() and isinstance(v, str)}


def python_files():
    for base in (PKG, DECKY):
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ("data", "__pycache__", "node_modules")]
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(root, name)


def fields(template):
    return {name.split(".")[0].split("[")[0] for _, name, _, _ in string.Formatter().parse(template) if name is not None}


uses, calls, problems = {}, [], []
for path in python_files():
    if path.endswith("strings.py"):
        continue
    source = open(path, encoding="utf-8").read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "strings":
            uses.setdefault(node.attr, []).append(path)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
            for sub in ast.walk(node.func.value):
                if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id == "strings"
                        and sub.attr in CONSTANTS):
                    calls.append((path, sub.attr, {k.arg for k in node.keywords}, node.lineno))

page_text = assets.PAGE_HTML
page_names = set(re.findall(r"@@([A-Z0-9_]+)@@", page_text)) | set(re.findall(r"\bS\.(PAGE_[A-Z0-9_]+)", page_text))
addon_names = set(re.findall(r'TEXT\["(ADDON_[A-Z0-9_]+)"\]', open(os.path.join(PKG, "data", "anki_touch_addon.py"), encoding="utf-8").read()))
decky_ts = open(os.path.join(DECKY, "src", "index.tsx"), encoding="utf-8").read()
decky_names = set(re.findall(r"\b(DECKY_[A-Z0-9_]+)\b", decky_ts))
in_strings_itself = {}
for node in ast.walk(ast.parse(open(os.path.join(PKG, "strings.py"), encoding="utf-8").read())):
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
        in_strings_itself[node.value.id] = node.targets[0].id

unused = sorted(n for n in CONSTANTS
                if n not in uses and n not in page_names and n not in addon_names and n not in decky_names
                and n not in in_strings_itself and n != "ERROR_STARTS")
check("every constant in strings.py is used", not unused, str(unused))
unknown = sorted(n for n in uses if not hasattr(strings, n))
check("everything the code takes from strings.py exists", not unknown, str(unknown))
missing_page = sorted(n for n in page_names - {"PAGE_SCRIPT_TEXTS"} if n not in CONSTANTS)
check("every text the page names exists", not missing_page, str(missing_page))
missing_addon = sorted(n for n in addon_names if n not in CONSTANTS)
check("every text the Anki add-on names exists", not missing_addon, str(missing_addon))
check("the page's texts use the PAGE_ names, the add-on's the ADDON_ names",
      all(n.startswith("PAGE_") for n in page_names) and all(n.startswith("ADDON_") for n in addon_names))
missing_decky = sorted(n for n in decky_names if n not in CONSTANTS)
check("every text the Decky panel names exists", not missing_decky, str(missing_decky))
aliased_wrong = sorted(n for n in uses if n in CONSTANTS and n.startswith(("PAGE_", "ADDON_", "DECKY_")) and n not in page_names | addon_names)
check("PAGE_/ADDON_ texts are not used by Python code (except through their own consumers)", not [n for n in aliased_wrong if n.startswith(("PAGE_", "ADDON_"))],
      str(aliased_wrong))

bad = []
for path, name, given, line in calls:
    want = fields(CONSTANTS[name]) if name in CONSTANTS else None
    if want is not None and want != given:
        bad.append(f"{os.path.relpath(path, _extract.ROOT)}:{line} {name} wants {sorted(want)}, gets {sorted(given)}")
check("every call fills exactly the placeholders of its template", not bad, "; ".join(bad))
needs_fill = [n for n, v in CONSTANTS.items() if fields(v) and n not in page_names and n not in decky_names and n not in in_strings_itself.values()]
never_formatted = sorted(n for n in needs_fill if not any(c[1] == n for c in calls) and n not in addon_names)
check("every template with placeholders is formatted by someone", not never_formatted, str(never_formatted))
for n in sorted(page_names):
    if fields(CONSTANTS.get(n, "")):
        js_use = re.findall(r"fmt\(\s*[^,]*\b" + n + r"\b[^,]*,\s*\{([^}]*)\}", page_text)
        check(f"the page fills the placeholders of {n}", bool(js_use) and all(fields(CONSTANTS[n]) <= set(re.findall(r"(\w+)\s*:", u)) for u in js_use), str(js_use))

SHOWN = {"on_status", "say", "report", "_nodes_note", "_anki_msg", "set_text", "set_label", "RuntimeError", "PasswordError", "InstallError",
         "BlankImage", "result", "Button", "Window", "toast"}
loose = []
for path in python_files():
    if path.endswith("strings.py"):
        continue
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if name not in SHOWN:
            continue
        for arg in list(node.args) + [k.value for k in node.keywords]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and re.search(r"[A-Za-z]{3}.* [A-Za-z]", sub.value):
                    loose.append(f"{os.path.relpath(path, _extract.ROOT)}:{sub.lineno} {sub.value[:50]!r}")
ALLOWED = ("The web interface isn't installed yet", "No screen is available here")
loose = [x for x in loose if not any(a in x for a in ALLOWED)]
print("   (literals handed to the message calls:", len(loose), ")")
for x in loose:
    print("   loose:", x)
check("no message text is written out at the places messages are shown", not loose, "; ".join(loose[:6]))

page = assets.render_texts(assets.PAGE_HTML)
check("the rendered page has no placeholder left", "@@" not in page)
check("the page's script gets exactly the texts it uses",
      set(re.findall(r'"(PAGE_[A-Z0-9_]+)":', page)) == set(re.findall(r"\bS\.(PAGE_[A-Z0-9_]+)", page_text)))
check("a text with markup characters can't break out of the page", "<" not in re.search(r"const S = (\{.*?\});", page, re.S).group(1))
check("the add-on renders with its texts and compiles", "__ADDON_TEXTS__" not in assets.ANKI_TOUCH_ADDON
      and compile(assets.ANKI_TOUCH_ADDON, "addon", "exec") is not None and strings.ADDON_BACK_TO_OCR in assets.ANKI_TOUCH_ADDON)
check("the add-on's version marker is 13 (bump it when the add-on changes)", "armada-yomitan-touch 13)" in assets.ANKI_TOUCH_ADDON.splitlines()[0])

check("an error message from strings.py is recognised as one", console.looks_like_error(strings.SCAN_FAILED.format(error="x"))
      and console.looks_like_error(strings.ANKI_START_FAILED.format(error="x")) and console.looks_like_error(strings.NO_OCR_AREAS))
check("progress and guidance are not", not any(console.looks_like_error(t) for t in (strings.READY, strings.BACK_TO_GAME, strings.DRAW_HINT,
                                                                                     strings.CAPTURING_TOP_SCREEN, strings.ANKI_STARTING)))
check("a template with a literal brace is written with doubled braces", strings.CAPTURE_BAD_COMMAND.format(reason="x").endswith("only use {node}."))
check("the by_count helper picks one/many", strings.by_count(1, "a", "b") == "a" and strings.by_count(2, "a", "b") == "b"
      and strings.by_count(0, "a", "b") == "b")

print()
print("FAILED: " + ", ".join(FAILED) if FAILED else "ALL PASSED")
sys.exit(1 if FAILED else 0)
