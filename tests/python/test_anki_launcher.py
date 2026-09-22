"""Tests for the Anki controls and console error output."""

import contextlib
import http.client
import io
import json
import os
import pickle
import shutil
import sqlite3
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


def capture_stderr(fn):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        fn()
    return buf.getvalue()


def wait(cond, t=8):
    end = time.time() + t
    while time.time() < end and not cond():
        time.sleep(0.05)
    return cond()


work = tempfile.mkdtemp(prefix="armada-yomitan-anki-test-")
home, xdg, fakehome = f"{work}/home", f"{work}/xdg", f"{work}/fakehome"
for d in (home, xdg, fakehome):
    os.makedirs(d)
os.environ["XDG_DATA_HOME"] = xdg
os.environ["HOME"] = fakehome
m = _extract.load_module(home)
strings = m.strings
base = f"{xdg}/Anki2"

print("--- errors are also printed to the console")
check("error-like texts are recognised", all(m.looks_like_error(t) for t in (strings.ERROR.format(error="x"), strings.SCAN_FAILED.format(error="y"), strings.TOUCH_GRAB_FAILED_TAP, strings.SETUP_FAILED.format(error="z"), strings.ANKI_CLOSED_WITH_ERROR, strings.OCR_MODEL_FAILED.format(error="q"))))
check("progress and guidance are not errors", not any(m.looks_like_error(t) for t in (strings.READY, strings.CAPTURING_TOP_SCREEN, strings.ANKI_CLOSED, strings.ANKI_INSTALL_CANCELLED)))
ui = m.WebUI(m.Config())
failure = strings.SCAN_FAILED.format(error="nothing came back")
out = capture_stderr(lambda: (ui.on_status(strings.CAPTURING_TOP_SCREEN), ui.on_status(failure), ui.on_status(strings.READY)))
check("on_status prints only the failure, with a timestamp", failure in out and strings.CAPTURING_TOP_SCREEN not in out and strings.READY not in out and out.startswith("[armada-yomitan "))
check("log=False stays quiet (used when the full detail was printed already)", capture_stderr(lambda: ui.on_status(strings.ANKI_CLOSED_WITH_ERROR_DETAIL.format(detail="x"), log=False)) == "")
check("the status still reaches the page", ui.last_status.startswith(strings.ANKI_CLOSED_WITH_ERROR.rstrip(".")))

print("\n--- missing system libraries")
libs = m.parse_missing_libs("ImportError: libminizip.so.1: cannot open shared object file: No such file or directory")
short, lines = m.lib_fix(libs)
check("the ImportError names the library", libs == ["libminizip.so.1"])
check("the suggested Fedora package is minizip-ng-compat (there is no minizip-compat)", "minizip-ng-compat" in short and "sudo rpm-ostree install minizip-ng-compat" in "\n".join(lines) and "minizip-compat " not in "\n".join(lines))
check("unknown libraries are listed without a guess", "libweird.so.9" in "\n".join(m.lib_fix(["libweird.so.9"])[1]))

print("\n--- Anki size setting")
check("clamp: 1.5..4 in quarter steps", [m.clamp_anki_scale(v) for v in (0.5, 1.6, 2.4, 2.9, 9)] == [1.5, 1.5, 2.5, 3.0, 4.0])
for v in ("3", "3.3", "abc", "99"):
    ui.cmd_pref("anki_scale", v)
check("cmd_pref applies it (bad text ignored) and it is saved", ui.prefs["anki_scale"] == 4.0 and m.load_prefs()["anki_scale"] == 4.0)
json.dump({"anki_scale": "big"}, open(m.PREFS_PATH, "w"))
check("garbage in ui.json falls back to the default", m.load_prefs()["anki_scale"] == m.Config.anki_scale)
env = m.anki_env(m.Config(), scale=3.0)
check("anki_env sets QT_SCALE_FACTOR and the add-on's target", env["QT_SCALE_FACTOR"] == "3" and env["ARMADA_YOMITAN_ANKI_SCALE_TARGET"] == "3" and env["ARMADA_YOMITAN_ANKI_SOCK"] == m.anki_socket_path())

print("\n--- where Anki keeps its data; its UI size lives in prefs21.db (Anki overwrites QT_SCALE_FACTOR from it)")
check("default base, Flatpak base, -b/--base", (m.anki_base_dir(["/x/anki"]), m.anki_base_dir(["flatpak", "run", "net.ankiweb.Anki"]), m.anki_base_dir(["a", "-b", "/d"]), m.anki_base_dir(["a", "--base=/e"])) ==
      (base, os.path.join(fakehome, ".var/app/net.ankiweb.Anki/data/Anki2"), "/d", "/e"))
os.makedirs(base)
db = base + "/prefs21.db"
check("no prefs21.db yet: nothing to change", m.set_anki_ui_scale(base, 2.5) == "no-prefs")
meta = {"ver": 0, "uiScale": 1.0, "defaultLang": "ja", "disabledAddons": [], "id": 1234}
con = sqlite3.connect(db)
con.execute("create table profiles (name text primary key collate nocase, data blob not null)")
con.execute("insert into profiles values ('_global', ?)", (pickle.dumps(meta, protocol=4),))
con.execute("insert into profiles values ('User 1', ?)", (pickle.dumps({"mainWindowGeom": b"abc"}, protocol=4),))
con.commit(); con.close()
row = lambda name, path=db: pickle.loads(sqlite3.connect(path).execute("select cast(data as blob) from profiles where name=?", (name,)).fetchone()[0])
check("uiScale is written, every other key and the profile row untouched", m.set_anki_ui_scale(base, 2.5) == "changed" and row("_global") == dict(meta, uiScale=2.5) and row("User 1") == {"mainWindowGeom": b"abc"})
check("a backup of the original is made once", row("_global", db + ".armada-yomitan.bak")["uiScale"] == 1.0)
check("same value: unchanged", m.set_anki_ui_scale(base, 2.5) == "unchanged")
m.set_anki_ui_scale(base, 3.0)
check("a later change keeps the ORIGINAL backup", row("_global", db + ".armada-yomitan.bak")["uiScale"] == 1.0 and row("_global")["uiScale"] == 3.0)
con = sqlite3.connect(db); con.execute("update profiles set data=? where name='_global'", (pickle.dumps(["not", "a", "dict"]),)); con.commit(); con.close()
out = capture_stderr(lambda: m.prepare_anki(["/x/anki"], 2.5))
check("an unexpected format is reported to the console, not fatal", "Couldn't set Anki's UI size" in out)
con = sqlite3.connect(db); con.execute("update profiles set data=? where name='_global'", (pickle.dumps(meta, protocol=4),)); con.commit(); con.close()

print("\n--- the touch-helper add-on file")
addon = f"{base}/addons21/armada_yomitan_touch/__init__.py"
check("prepare_anki installs it and it is exactly the embedded source", os.path.exists(addon) and open(addon).read() == _extract.anki_addon())
open(addon, "w").write("old version")
check("an outdated copy is replaced", m.install_anki_touch_addon(base) is True and open(addon).read() == _extract.anki_addon())
check("an identical copy is left alone", m.install_anki_touch_addon(base) is False)
os.environ["ARMADA_YOMITAN_ANKI_TOUCH"] = "0"
m.prepare_anki(["/x/anki"], 2.5)
check("ARMADA_YOMITAN_ANKI_TOUCH=0 removes it", not os.path.exists(addon))
del os.environ["ARMADA_YOMITAN_ANKI_TOUCH"]

print("\n--- a fake Anki that listens on the add-on's socket like the real add-on does")
fake = f"{work}/fake_anki"
os.makedirs(fake)
open(f"{fake}/anki", "w").write('''#!/usr/bin/env python3
import os, socket, sys, time
path = os.environ["ARMADA_YOMITAN_ANKI_SOCK"]; log = open(os.environ["FAKE_LOG"], "a", buffering=1)
if os.environ.get("FAKE_DEAF"):
    log.write("started deaf\\n"); time.sleep(60); sys.exit(0)
try: os.unlink(path)
except OSError: pass
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.bind(path); s.listen(4)
log.write("started scale=%s\\n" % os.environ.get("ARMADA_YOMITAN_ANKI_SCALE_TARGET"))
if os.environ.get("ARMADA_YOMITAN_ANKI_BACKGROUND") == "1": log.write("background\\n")
shown = os.environ.get("ARMADA_YOMITAN_ANKI_BACKGROUND") != "1"
while True:
    c, _ = s.accept(); w = c.recv(32).decode().strip()
    if w == "show": shown = True
    if w == "hide": shown = False
    if w == "visible":
        c.sendall(b"yes\\n" if shown else b"no\\n")
    else:
        log.write(w + "\\n"); c.sendall(b"ok\\n")
    c.close()
    if w == "quit": sys.exit(0)
''')
os.chmod(f"{fake}/anki", 0o755)
os.environ["FAKE_LOG"] = f"{work}/fake.log"
log = lambda: open(os.environ["FAKE_LOG"]).read().split() if os.path.exists(os.environ["FAKE_LOG"]) else []
check("nothing listening -> anki_send returns None", m.anki_send("ping", 1) is None)
ui = m.WebUI(m.Config()); ui.start()
ui.prefs.update(anki_button=True, anki_cmd=[f"{fake}/anki"], anki_scale=3.0)
msgs = []; orig = ui.broadcast; ui.broadcast = lambda x: (msgs.append(x), orig(x))[1]
running = lambda: [x for x in msgs if x.get("type") == "prefs"][-1]["anki_running"] if any(x.get("type") == "prefs" for x in msgs) else None
ui.cmd_anki()
check("the Anki button starts it, with the size passed along", wait(lambda: log()[:2] == ["started", "scale=3"]))
wait(lambda: m.anki_send("ping", 1) == "ok")
check("the page is told Anki is running (the button turns blue)", wait(lambda: running() is True))
ui.cmd_anki()
check("pressing it again brings Anki forward (show) rather than starting another", wait(lambda: "show" in log()) and log().count("started") == 1 and ui.last_status == strings.ANKI_IN_FRONT)
m.anki_send("hide")
check("tapping Back to OCR inside Anki (hide, no app interaction) clears the stale status by itself", wait(lambda: ui.last_status == strings.READY, 4), ui.last_status)
t0 = time.time(); proc = ui.anki_proc; ui.shutdown()
check("quitting armada-yomitan asks Anki to quit properly, and it exits at once", "quit" in log() and proc.returncode == 0 and time.time() - t0 < 5)
check("the page is told it stopped", running() is False)

print("\n--- Anki that was running when the program ended starts again by itself, in the background")
check("the flag was saved while it ran, and the program's own quit of Anki didn't clear it", ui.prefs["anki_resume"] is True and m.load_prefs()["anki_resume"] is True)
os.remove(os.environ["FAKE_LOG"])
ui5 = m.WebUI(m.Config()); ui5.start()
ui5.resume_anki()
check("it is started at once, and told to keep every window off the screen", wait(lambda: "background" in log()) and log().count("started") == 1)
wait(lambda: m.anki_send("ping", 1) == "ok")
ui5.resume_anki()
check("asked again while it runs, it isn't started twice", log().count("started") == 1)
ui5.cmd_anki()
check("the Anki button then brings it forward as usual", wait(lambda: "show" in log()))
m.anki_send("quit")
check("closed inside Anki: it ends and the flag is cleared and saved", wait(lambda: not ui5._anki_running()) and wait(lambda: m.load_prefs()["anki_resume"] is False))
os.remove(os.environ["FAKE_LOG"])
ui6 = m.WebUI(m.Config()); ui6.start(); ui6.resume_anki(); time.sleep(0.5)
check("so the next start doesn't bring it back", log() == [] and not ui6._anki_running())
ui6.prefs.update(anki_resume=True, anki_button=False); ui6.resume_anki(); time.sleep(0.5)
check("with the Anki button switched off nothing is started either", log() == [])
ui5.shutdown(); ui6.shutdown()
if os.path.exists(m.anki_socket_path()):
    os.remove(m.anki_socket_path())

print("\n--- an Anki left over from an earlier session; one that doesn't answer")
if os.path.exists(os.environ["FAKE_LOG"]):
    os.remove(os.environ["FAKE_LOG"])
leftover = subprocess.Popen([f"{fake}/anki"], env=dict(os.environ, ARMADA_YOMITAN_ANKI_SOCK=m.anki_socket_path()))
wait(lambda: m.anki_send("ping", 1) == "ok")
ui2 = m.WebUI(m.Config()); ui2.start(); ui2.prefs.update(anki_button=True, anki_cmd=[f"{fake}/anki"])
ui2.cmd_anki()
check("it is found by ping and brought forward, not launched a second time", "show" in log() and log().count("started") == 1)
check("...the status says so, even though this instance never tracked the process (anki_proc is None)", ui2.anki_proc is None and ui2.last_status == strings.ANKI_IN_FRONT)
m.anki_send("hide")
check("Back to OCR on a leftover, untracked Anki still clears the status by itself", wait(lambda: ui2.last_status == strings.READY, 4), ui2.last_status)
ui2.shutdown(); leftover.terminate(); leftover.wait()
os.remove(os.environ["FAKE_LOG"])
if os.path.exists(m.anki_socket_path()):
    os.remove(m.anki_socket_path())
os.environ["FAKE_DEAF"] = "1"
ui3 = m.WebUI(m.Config()); ui3.start(); ui3.prefs.update(anki_button=True, anki_cmd=[f"{fake}/anki"])
ui3.cmd_anki(); wait(lambda: ui3._anki_running()); time.sleep(0.5); ui3.cmd_anki()
check("running but not answering: the page is told to wait", ui3.last_status == strings.ANKI_NOT_ANSWERING)
p3 = ui3.anki_proc; ui3.shutdown()
check("no answer to quit -> it is terminated", p3.returncode is not None and p3.returncode != 0)
del os.environ["FAKE_DEAF"]
check("a long ARMADA_YOMITAN_HOME still gives a usable socket path", (setattr(m, "HOME_DIR", "/tmp/" + "x" * 120), len(m.anki_socket_path().encode()) < 108)[1])
m.HOME_DIR = home

print("\n--- launches that fail: the full output goes to the console, the screen gets the short version")
open(f"{fake}/bad", "w").write("#!/bin/sh\necho 'Traceback (most recent call last):' >&2\necho 'ImportError: libminizip.so.1: cannot open shared object file: No such file or directory' >&2\nexit 1\n")
open(f"{fake}/bad2", "w").write("#!/bin/sh\nfor i in 1 2 3; do echo \"log line $i\" >&2; done\necho 'Qt: could not load the platform plugin xcb' >&2\nexit 1\n")
for f in ("bad", "bad2"):
    os.chmod(f"{fake}/{f}", 0o755)
ui4 = m.WebUI(m.Config())
out = capture_stderr(lambda: ui4._run_anki([f"{fake}/bad"]))
check("a missing library: named, with the command to fix it, and Anki's own output", "minizip-ng-compat" in out and "Anki's own output" in out and "ImportError" in out)
check("...and a short, complete message on screen (not cut at 80 characters)", "libminizip.so.1" in ui4.last_status and ui4.last_status.endswith(strings.ANKI_CANT_START.split("{libraries}")[1]))
out = capture_stderr(lambda: ui4._run_anki([f"{fake}/bad2"]))
check("any other failure: every log line reaches the console", all(f"log line {i}" in out for i in (1, 2, 3)) and "platform plugin" in out)

print("\n--- the Anki install (fake uv)")
os.makedirs(f"{work}/fakeuv")
open(f"{work}/fakeuv/uv", "w").write('''#!/bin/sh
case "$1" in
  venv) mkdir -p "$4/bin"; printf '#!/bin/sh\\n' > "$4/bin/python"; chmod +x "$4/bin/python"; echo "Using CPython 3.13.5" ;;
  pip) echo "Resolved 41 packages"; echo "  x Failed to download PyQt6-WebEngine-Qt6==6.9.0"; echo "  Caused by: HTTP status client error (404 Not Found)"; echo "error: no wheel for aarch64" >&2; exit 2 ;;
esac
''')
os.chmod(f"{work}/fakeuv/uv", 0o755)
m.ensure_uv = lambda: f"{work}/fakeuv/uv"
ui5 = m.WebUI(m.Config()); ui5.start(); shown = []; ob = ui5.broadcast; ui5.broadcast = lambda x: (shown.append(x), ob(x))[1]
out = capture_stderr(ui5.cmd_anki_install)
check("a failing install prints uv's last lines to the console, once", "Failed to download PyQt6-WebEngine-Qt6" in out and out.count("install failed") == 1)
check("the setup view gets the short reason", any(x.get("status", "").startswith(strings.ANKI_INSTALL_FAILED.split("{")[0]) for x in shown if x.get("type") == "anki"))
ui5.shutdown()

print("\n--- checking Anki's version against PyPI")
shutil.rmtree(m.ANKI_VENV, ignore_errors=True)
check("no venv at all: nothing to read", m.installed_aqt_version() is None)
check("...so up to date is unknown", m.anki_up_to_date() is None)
venv_py = f"{m.ANKI_VENV}/bin/python"
os.makedirs(os.path.dirname(venv_py))
open(venv_py, "w").write("#!/bin/sh\necho 25.09\n")
os.chmod(venv_py, 0o755)
check("a version is read from the venv's python", m.installed_aqt_version() == "25.09")
m.download = lambda url, timeout=30: json.dumps({"info": {"version": "25.09"}}).encode()
check("matching PyPI: up to date", m.anki_up_to_date() is True)
m.download = lambda url, timeout=30: json.dumps({"info": {"version": "26.01"}}).encode()
check("a newer version on PyPI: not up to date", m.anki_up_to_date() is False)
m.download = lambda url, timeout=30: (_ for _ in ()).throw(RuntimeError("offline"))
check("PyPI unreachable: unknown, not a crash", m.anki_up_to_date() is None)
check("anki_installed_by_app looks at the command's path", m.anki_installed_by_app([f"{m.ANKI_VENV}/bin/anki"]) is True
      and m.anki_installed_by_app(["/usr/bin/anki"]) is False and m.anki_installed_by_app([]) is False)

print("\n--- reinstalling Anki: only the app's own install, stops a running copy first, its data is left alone")
os.makedirs(f"{work}/fakeuv2")
open(f"{work}/fakeuv2/uv", "w").write('''#!/bin/sh
case "$1" in
  venv) mkdir -p "$4/bin"; printf '#!/bin/sh\\necho 25.10\\n' > "$4/bin/python"; chmod +x "$4/bin/python" ;;
  pip) echo "Resolved 3 packages" ;;
esac
''')
os.chmod(f"{work}/fakeuv2/uv", 0o755)
m.ensure_uv = lambda: f"{work}/fakeuv2/uv"

ui7 = m.WebUI(m.Config()); ui7.start()
ui7.prefs.update(anki_button=True, anki_cmd=["/somewhere/else/anki"], anki_label="Anki on this system")
ui7.cmd_anki_reinstall()
check("an Anki not installed by the app: reinstall does nothing", ui7.prefs["anki_cmd"] == ["/somewhere/else/anki"])

os.environ["FAKE_LOG"] = f"{work}/fake2.log"
running = subprocess.Popen([f"{fake}/anki"], env=dict(os.environ, ARMADA_YOMITAN_ANKI_SOCK=m.anki_socket_path()))
wait(lambda: m.anki_send("ping", 1) == "ok")
ui7.anki_proc = running
ui7.prefs.update(anki_cmd=[f"{m.ANKI_VENV}/bin/anki"], anki_label=strings.ANKI_INSTALLED_BY_APP)
before = list(ui7.prefs["anki_cmd"])
ui7._anki_busy = True
ui7.cmd_anki_reinstall()
check("busy: a second request is ignored", ui7.prefs["anki_cmd"] == before)
ui7._anki_busy = False
ui7.cmd_anki_reinstall()
check("the running copy is stopped first", wait(lambda: "quit" in log()) and running.returncode == 0)
check("it reinstalls under the app's own venv and updates the pointer",
      ui7.prefs["anki_cmd"][0].startswith(m.ANKI_VENV + os.sep) and ui7.prefs["anki_label"] == strings.ANKI_INSTALLED_BY_APP)
check("Anki's own data folder and add-on are untouched", os.path.exists(base) and os.path.exists(addon))
ui7.shutdown()
os.remove(os.environ["FAKE_LOG"])
if os.path.exists(m.anki_socket_path()):
    os.remove(m.anki_socket_path())

print("\n--- the web endpoints for the version check and the reinstall")
shutil.rmtree(m.ANKI_VENV, ignore_errors=True)
ui8 = m.WebUI(m.Config()); ui8.start()
conn = http.client.HTTPConnection("127.0.0.1", ui8.port)
conn.request("GET", "/anki_update_check", headers={"X-Token": ui8.token})
resp = conn.getresponse()
check("/anki_update_check answers with up_to_date", resp.status == 200 and json.loads(resp.read()) == {"up_to_date": None})
conn.close()
calls = []
ui8.cmd_anki_reinstall = lambda: calls.append("reinstall")
conn = http.client.HTTPConnection("127.0.0.1", ui8.port)
conn.request("POST", "/anki_reinstall", headers={"X-Token": ui8.token})
resp = conn.getresponse(); resp.read()
check("/anki_reinstall dispatches to cmd_anki_reinstall", resp.status == 204 and wait(lambda: calls == ["reinstall"]))
conn.close()
ui8.shutdown()

print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
