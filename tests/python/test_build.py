"""Tests for tools/build_all.py."""

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract

sys.path.insert(0, os.path.join(_extract.ROOT, "tools"))
import build_all

FAILED = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{extra}]" if extra and not ok else ""))
    if not ok:
        FAILED.append(label)


work = pathlib.Path(tempfile.mkdtemp(prefix="ay-build-"))
build_all.DIST = work / "dist"
build_all.CACHE = work / "cache"
fake_panel = work / "index.js"
fake_panel.write_text("/* the built panel */\n")
real_build_panel = build_all.build_panel
build_all.build_panel = lambda: fake_panel

print("--- the single file")
exe = build_all.build_executable(work / "one" / "armada-yomitan")
check("it is an executable zipapp with a python3 shebang", exe.exists() and os.access(exe, os.X_OK) and zipfile.is_zipfile(exe) and exe.read_bytes().startswith(b"#!/usr/bin/env python3\n"))
names = zipfile.ZipFile(exe).namelist()
check("it holds the package, its entry point and its data files, and no bytecode",
      "__main__.py" in names and "armada_yomitan/entry.py" in names and "armada_yomitan/data/page.html" in names and not any("__pycache__" in n or n.endswith(".pyc") for n in names))
r = subprocess.run([sys.executable, str(exe), "--help"], capture_output=True, text=True, env=dict(os.environ, ARMADA_YOMITAN_HOME=str(work / "home")))
check("it runs", r.returncode == 0 and r.stdout.startswith("usage: armada-yomitan"), r.stderr[-200:])

print("\n--- both, into dist/")
(build_all.DIST / "decky" / "armada-yomitan").mkdir(parents=True)
(build_all.DIST / "decky" / "armada-yomitan" / "main.py").write_text("old")
built = build_all.build()
files = sorted(p.name for p in build_all.DIST.iterdir())
check("dist/ holds exactly the two files (the old unpacked folder is gone)", files == ["armada-yomitan", "armada-yomitan-decky.zip"], str(files))
check("both were reported as built", [p.name for p in built] == ["armada-yomitan", "armada-yomitan-decky.zip"], str(built))
z = zipfile.ZipFile(build_all.DIST / "armada-yomitan-decky.zip")
info = {i.filename: i for i in z.infolist()}
check("the zip has the plugin under a top-level folder named like it",
      sorted(info) == ["armada-yomitan/bin/armada-yomitan", "armada-yomitan/dist/index.js", "armada-yomitan/main.py",
                       "armada-yomitan/package.json", "armada-yomitan/plugin.json", "armada-yomitan/strings.py"], str(sorted(info)))
check("the app inside it is executable, the rest is not",
      oct(info["armada-yomitan/bin/armada-yomitan"].external_attr >> 16) == "0o755" and oct(info["armada-yomitan/main.py"].external_attr >> 16) == "0o644")
check("the app inside it is byte for byte the single file in dist/", z.read("armada-yomitan/bin/armada-yomitan") == (build_all.DIST / "armada-yomitan").read_bytes())
manifest = json.loads(z.read("armada-yomitan/plugin.json"))
own = json.loads((build_all.PLUGIN / "plugin.json").read_text())
check("the backend is the project's own file", z.read("armada-yomitan/main.py") == (build_all.PLUGIN / "main.py").read_bytes())
check("the metadata is the project's own, with the name Decky shows taken from strings.py (DECKY_NAME)",
      manifest == {**own, "name": build_all.load_strings().DECKY_NAME}, str(manifest))
custom = work / "custom-strings.py"
custom.write_text(re.sub(r'^DECKY_NAME = ".*?"', 'DECKY_NAME = "Yomitan OCR"', build_all.STRINGS_PY.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
real_strings = build_all.STRINGS_PY
build_all.STRINGS_PY = custom
try:
    custom_stage = build_all.assemble_plugin(work / "custom-stage", fake_panel, exe)
    custom_manifest = json.loads((custom_stage / "plugin.json").read_text())
    custom_ts = build_all.panel_strings()
finally:
    build_all.STRINGS_PY = real_strings
check("a different DECKY_NAME reaches plugin.json and the panel, while the folder inside the zip stays armada-yomitan",
      custom_manifest["name"] == "Yomitan OCR" and 'DECKY_NAME = "Yomitan OCR"' in custom_ts and "armada-yomitan/main.py" in z.namelist(), str(custom_manifest))
check("the app's strings.py is in the plugin, for its backend", z.read("armada-yomitan/strings.py") == build_all.STRINGS_PY.read_bytes())
ts = build_all.panel_strings()
check("the panel's generated strings module has the DECKY_ texts and nothing else",
      'export const DECKY_LAUNCH = "Launch";' in ts and 'export const DECKY_STOP = "Stop";' in ts
      and all(line.startswith(("//", "export const DECKY_")) for line in ts.splitlines()) and ts.endswith("\n"), ts[:300])
check("the panel is the built one", z.read("armada-yomitan/dist/index.js") == fake_panel.read_bytes())

print("\n--- the panel is built with the manifest that goes into the zip (its calls to the backend are addressed by the name in it)")
seen = {}
def fake_run(step, cwd=None, env=None, **kw):
    if step[1:] == ["run", "build"]:
        seen["manifest"] = json.loads((pathlib.Path(cwd) / "plugin.json").read_text())
        (pathlib.Path(cwd) / "dist").mkdir(exist_ok=True)
        (pathlib.Path(cwd) / "dist" / "index.js").write_text("/* built */")
    return subprocess.CompletedProcess(step, 0)
real_run, real_find = build_all.subprocess.run, build_all.find_npm
build_all.subprocess.run, build_all.find_npm = fake_run, lambda: ("npm", {})
try:
    real_build_panel()
finally:
    build_all.subprocess.run, build_all.find_npm = real_run, real_find
check("build_panel puts the display name (DECKY_NAME) in the plugin.json it builds with",
      seen.get("manifest", {}).get("name") == build_all.load_strings().DECKY_NAME, str(seen))
check("...and the src/strings.ts it builds with holds the DECKY_ texts", "export const DECKY_NAME" in (build_all.CACHE / "build" / "src" / "strings.ts").read_text())

print("\n--- --only")
for f in build_all.DIST.iterdir():
    f.unlink()
build_all.build("executable")
check("--only executable builds just the single file (and never touches the panel)", [p.name for p in build_all.DIST.iterdir()] == ["armada-yomitan"])
for f in build_all.DIST.iterdir():
    f.unlink()
build_all.build("plugin")
check("--only plugin builds just the zip, with the app inside it", [p.name for p in build_all.DIST.iterdir()] == ["armada-yomitan-decky.zip"]
      and "armada-yomitan/bin/armada-yomitan" in zipfile.ZipFile(build_all.DIST / "armada-yomitan-decky.zip").namelist())

print("\n--- no Node")
for f in build_all.DIST.iterdir():
    f.unlink()
os.environ["PATH"], real_path = str(work / "empty"), os.environ["PATH"]
os.makedirs(work / "empty")
build_all.build_panel = real_build_panel
try:
    code = build_all.main([])
finally:
    os.environ["PATH"] = real_path
check("the single file is still built, the plugin isn't, and the exit status says so", code == 1 and [p.name for p in build_all.DIST.iterdir()] == ["armada-yomitan"], str(list(build_all.DIST.iterdir())))
check("...and --only executable works without Node", (lambda: (build_all.main(["--only", "executable"]) == 0))())

print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
