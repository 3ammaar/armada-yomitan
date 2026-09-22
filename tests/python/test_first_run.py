"""Tests for the first-run flow in main()."""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract

FAILED = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{extra}]" if extra and not ok else ""))
    if not ok:
        FAILED.append(label)


if not shutil.which("broadwayd"):
    print("SKIP  broadwayd isn't installed, so GTK can't be run headless here")
    sys.exit(0)
try:
    import gi
    gi.require_version("Gtk", "3.0")
except (ImportError, ValueError):
    print("SKIP  PyGObject/GTK3 isn't available")
    sys.exit(0)

work = tempfile.mkdtemp(prefix="ay-firstrun-")
broadway = subprocess.Popen(["broadwayd", ":48"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(broadway.terminate)
time.sleep(1.0)
os.environ.update(GDK_BACKEND="broadway", BROADWAY_DISPLAY=":48")
for k in ("DISPLAY", "WAYLAND_DISPLAY", "ARMADA_YOMITAN_BROWSER", "ARMADA_YOMITAN_UI"):
    os.environ.pop(k, None)
home = f"{work}/home"
m = _extract.load_module(home)
strings = m.strings
from gi.repository import GLib, Gtk  # noqa: E402

cli = sys.modules["armada_yomitan.cli"]
calls = []
cli.restart = lambda: calls.append("restart")
cli.run_gui = lambda cfg: calls.append("simple window")
cli.run_web = lambda cfg: calls.append("web app")
m.install_components = lambda say=None, **kw: say("Downloading ...")
sysmissing = [[]]
syspackages = sys.modules["armada_yomitan.syspackages"]
pending = [False]
syspackages.run_checks = lambda *a, **k: [syspackages.Check(f"check {name}", False, [name]) for name in sysmissing[0]]
syspackages.reboot_pending = lambda: pending[0]
real_geteuid = os.geteuid
os.geteuid = lambda: 1000
seen = {}
os.environ["PATH"] = f"{work}/nothing:" + os.environ["PATH"]


def start(argv, press=None, look=False):
    calls.clear()
    sources = []
    sys.argv = ["armada-yomitan"] + argv
    if look:
        def snapshot():
            top = Gtk.Window.list_toplevels()[0]
            seen["buttons"] = sorted(b.get_label() for b in _buttons(top) if b.is_visible())
            seen["labels"] = [w.get_text() for w in _labels(top) if w.is_visible()]
            return False
        sources.append(GLib.timeout_add(300, snapshot))
    if press:
        def click():
            for label in ([press] if isinstance(press, str) else press):
                btn = next((b for b in _buttons(Gtk.Window.list_toplevels()[0]) if b.get_label() == label), None)
                btn.clicked()
            return False
        sources.append(GLib.timeout_add(500, click))
    timer = GLib.timeout_add(15000, Gtk.main_quit)
    cli.main()
    for source in sources + [timer]:
        GLib.source_remove(source)
    return list(calls)


def _labels(w):
    out = [w] if isinstance(w, Gtk.Label) else []
    if isinstance(w, Gtk.Container):
        for c in w.get_children():
            out += _labels(c)
    return out


def _buttons(w):
    out = [w] if isinstance(w, Gtk.Button) else []
    if isinstance(w, Gtk.Container):
        for c in w.get_children():
            out += _buttons(c)
    return out


check("not installed yet: the install window opens, Install runs it, then the program restarts into the app", start(["--touch", "t"], ("Install", "Yes")) == ["restart"])
check("...Quit starts nothing", start(["--touch", "t"], ("Quit", "Yes")) == [])
check("--ui gtk asks for the plain window directly: no install window", start(["--ui", "gtk"]) == ["simple window"])
check("--ui web with nothing installed is left to run_web (which reports it), also without the install window", start(["--ui", "web"]) == ["web app"])

fake_browser = f"{work}/chromium"
open(fake_browser, "w").write("#!/bin/sh\n")
os.chmod(fake_browser, 0o755)
os.environ["ARMADA_YOMITAN_BROWSER"] = fake_browser
os.makedirs(f"{home}/yomitan", exist_ok=True)
open(f"{home}/yomitan/manifest.json", "w").write("{}")
check("installed: straight to the web app, no install window", start(["--touch", "t"]) == ["web app"])

del os.environ["ARMADA_YOMITAN_BROWSER"]
os.makedirs(f"{home}/browsers/chromium-1/linux", exist_ok=True)
open(f"{home}/browsers/chromium-1/linux/chrome", "w").write("#!/bin/sh\n")
os.chmod(f"{home}/browsers/chromium-1/linux/chrome", 0o755)
m.install_state.mark("ocr")
check("an install that was stopped (Chromium and Yomitan are there, but not every step finished) opens the install window, not the app",
      start(["--touch", "t"], ("Install", "Yes")) == ["restart"])
m.install_state.mark(*m.install_state.STEPS)
check("every step finished: straight to the app", start(["--touch", "t"]) == ["web app"])
cli.run_web = lambda cfg: (calls.append("web app"), "restart")[1]
check("when the app asks to be started again (Re-install dependencies), the program restarts", start(["--touch", "t"]) == ["web app", "restart"])

cli.run_web = lambda cfg: calls.append("web app")
print("\n--- system packages: no password, no install without root")
sysmissing[0] = ["gstreamer1"]
check("every step is installed but a required system package is missing, and this is not root: the message and only Quit (no password, no Install)",
      start(["--touch", "t"], ("Quit", "Yes"), look=True) == [] and strings.NEEDS_ROOT in seen["labels"] and seen["buttons"] == [strings.QUIT], str(seen))
check("...and the app itself is not started", "web app" not in start(["--touch", "t"], ("Quit", "Yes")))
sysmissing[0] = ["gstreamer1", "tesseract"]
start(["--touch", "t"], ("Quit", "Yes"), look=True)
check("the message lists exactly what is missing: each required package, and nothing else",
      seen["labels"] == [strings.NEEDS_ROOT, strings.MISSING_HEADING, "\u2022 check gstreamer1 (package gstreamer1)\n\u2022 check tesseract (package tesseract)", strings.QUIT], str(seen))
pending[0] = True
start(["--touch", "t"], ("Quit", "Yes"), look=True)
check("packages that are staged but not active yet: the message says to restart the device", strings.SETUP_REBOOT_NEEDED in seen["labels"] and strings.NEEDS_ROOT not in seen["labels"], str(seen))
pending[0] = False
sysmissing[0] = ["gstreamer1"]
sysmissing[0] = []
os.environ["ARMADA_YOMITAN_VIA_DECKY"] = "1"
m.install_state.reset()
check("started from the Decky plugin with parts missing (the plugin's button installs them): the same message and only Quit, not the install window",
      start(["--touch", "t"], ("Quit", "Yes"), look=True) == [] and strings.NEEDS_ROOT in seen["labels"] and seen["buttons"] == [strings.QUIT], str(seen))
check("...and the list names the parts that are missing",
      seen["labels"][2] == "\u2022 " + "\n\u2022 ".join([strings.MISSING_OCR, strings.MISSING_CHROMIUM, strings.MISSING_YOMITAN]), str(seen))
del os.environ["ARMADA_YOMITAN_VIA_DECKY"]
check("started by hand with only the parts missing: the install window as before", start(["--touch", "t"], look=True) == [] and strings.SETUP_INSTALL in seen["buttons"], str(seen))
m.install_state.mark(*m.install_state.STEPS)
os.environ["ARMADA_YOMITAN_VIA_DECKY"] = "1"
check("started from the plugin with everything installed: straight to the app", start(["--touch", "t"]) == ["web app"])
del os.environ["ARMADA_YOMITAN_VIA_DECKY"]

print("\n--- as root: the install window installs the system packages with everything else")
os.geteuid = lambda: 0
sysmissing[0] = ["gstreamer1"]
os.environ["ARMADA_YOMITAN_VIA_DECKY"] = "1"
check("even as root, started from the Decky plugin there is no install: the message and only Quit",
      start(["--touch", "t"], ("Quit", "Yes"), look=True) == [] and strings.NEEDS_ROOT in seen["labels"] and seen["buttons"] == [strings.QUIT], str(seen))
del os.environ["ARMADA_YOMITAN_VIA_DECKY"]
sysmissing[0] = ["gstreamer1"]
installed = []
syspackages.install = lambda on_line=None, **kw: (installed.append("system"), "nothing")[1]
check("root with a required package missing: the install window (Install and Quit), not the message",
      start(["--touch", "t"], ("Install", "Yes"), look=True) == ["restart"] and strings.SETUP_INSTALL in seen["buttons"] and strings.NEEDS_ROOT not in seen["labels"], str(seen))
check("...and Install also installed the system packages", installed == ["system"], str(installed))
os.geteuid = real_geteuid

broadway.terminate()
print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
