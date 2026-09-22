"""Tests for the Decky plugin backend."""

import asyncio
import importlib.util
import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract

FAILED = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{extra}]" if extra and not ok else ""))
    if not ok:
        FAILED.append(label)


work = tempfile.mkdtemp(prefix="ay-decky-")
home = f"{work}/home"
plugin_dir, log_dir, fakebin = f"{work}/plugin", f"{work}/logs", f"{work}/fakebin"
for d in (home, f"{plugin_dir}/bin", log_dir, fakebin):
    os.makedirs(d)
user = pwd.getpwuid(os.getuid()).pw_name

import logging
decky = types.ModuleType("decky")
# With the "root" flag Decky reports HOME=/root and USER=root for the backend itself; the app's user is DECKY_USER / DECKY_USER_HOME.
decky.HOME, decky.USER = "/nonexistent-root-home", "root"
decky.DECKY_USER, decky.DECKY_USER_HOME = user, home
decky.DECKY_PLUGIN_DIR, decky.DECKY_PLUGIN_LOG_DIR = plugin_dir, log_dir
decky.DECKY_PLUGIN_SETTINGS_DIR = f"{work}/settings"
decky.logger = logging.getLogger("decky-test")
sys.modules["decky"] = decky
shutil.copy2(os.path.join(_extract.SRC, "armada_yomitan", "strings.py"), plugin_dir)
spec = importlib.util.spec_from_file_location("decky_plugin_main", os.path.join(_extract.ROOT, "decky-plugin", "main.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
strings = plugin.strings
plugin.PYTHON = sys.executable
plugin.STANDARD_PATH = fakebin + ":" + plugin.STANDARD_PATH
plugin.SETTLE = 1.0
plugin.TERM_WAIT, plugin.KILL_WAIT = 8.0, 2.0

FLAG, CHILD_PID, ENVDUMP = f"{work}/graceful", f"{work}/child.pid", f"{work}/env.txt"


def write(path, text, mode=0o755):
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, mode)


def install_fake_app(ignore_term=False, exe_body=None):
    app = f'''# from armada_yomitan.entry import main   (the marker the plugin recognises the app by)
import os, signal, subprocess, sys, time
child = subprocess.Popen(["sleep", "300"])                # stands in for Chromium
open({CHILD_PID!r}, "w").write(str(child.pid))
def on_term(number, frame):
    open({FLAG!r}, "w").write("graceful")
    child.terminate(); child.wait(); sys.exit(143)
signal.signal(signal.SIGTERM, signal.SIG_IGN if {ignore_term!r} else on_term)
time.sleep(300)
'''
    write(f"{work}/fake-app.py", app, 0o644)
    write(f"{fakebin}/armada-run-bottom", f'#!/bin/bash\nenv > "{ENVDUMP}"\n"{sys.executable}" -c "$(cat "{work}/fake-app.py")"\n')
    write(f"{plugin_dir}/bin/armada-yomitan", exe_body or "import os\nos.execvp('armada-run-bottom', ['armada-run-bottom', '--'])\n", 0o644)


def instance():
    return plugin.find_instance(plugin.read_processes())


def wait_for(cond, seconds=10):
    end = time.time() + seconds
    while time.time() < end and not cond():
        time.sleep(0.1)
    return cond()


def run(coro):
    return asyncio.run(coro)


def clean_up():
    for pid in instance()[1] | plugin.leftovers(plugin.read_processes(), set()):
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    for f in (FLAG, CHILD_PID, ENVDUMP):
        if os.path.exists(f):
            os.remove(f)


print("--- what the app is started with")
steam = f"{work}/steam"
shutil.copy("/bin/sleep", steam)
fake_steam = subprocess.Popen([steam, "300"], env={"PATH": "/usr/bin:/bin", "DISPLAY": ":9", "WAYLAND_DISPLAY": "wayland-9", "XDG_RUNTIME_DIR": "/run/user/4242",
                                                    "LD_LIBRARY_PATH": "/steam/runtime", "LD_PRELOAD": "/steam/overlay.so", "SteamGameId": "1", "PYTHONHOME": "/x"})
time.sleep(0.3)
env = plugin.session_environment(plugin.read_processes(), home, user)
check("the fixed basics: HOME, USER, LOGNAME, a standard PATH that includes ~/.local/bin", env["HOME"] == home and env["USER"] == user and env["LOGNAME"] == user
      and env["PATH"].endswith(f"{home}/.local/bin") and "/usr/bin" in env["PATH"], str(env))
check("the display/session variables come from the user's running Steam client", env.get("DISPLAY") == ":9" and env.get("WAYLAND_DISPLAY") == "wayland-9" and env.get("XDG_RUNTIME_DIR") == "/run/user/4242", str(env))
check("...and nothing else of Steam's does: no library path, no overlay, no game id, no PYTHONHOME",
      not any(k in env for k in ("LD_LIBRARY_PATH", "LD_PRELOAD", "SteamGameId", "PYTHONHOME")), str(sorted(env)))
fake_steam.kill()
fake_steam.wait()
env = plugin.session_environment(plugin.read_processes(), home, user)
check("with no Steam client running it still has a usable environment", env["HOME"] == home and env["XDG_RUNTIME_DIR"] == f"/run/user/{os.getuid()}", str(env))

print("\n--- launch")
install_fake_app()
os.environ["LD_LIBRARY_PATH"] = "/decky/bundled/python/lib"
os.environ["PYTHONHOME"] = "/decky/bundled/python"
r = run(plugin.launch_app())
check("launch reports that it is starting", r["ok"] and r["message"] == strings.DECKY_STARTING, str(r))
check("the app appears, as a tree that starts at armada-run-bottom and includes its child (the stand-in for Chromium)",
      wait_for(lambda: instance()[0] and wait_for(lambda: os.path.exists(CHILD_PID), 5)), str(instance()))
apps, tree = instance()
procs = plugin.read_processes()
roots = [p for p in tree if plugin.is_wrapper(procs[p][1])]
check("its root is the armada-run-bottom process, above the app", len(roots) == 1 and roots[0] not in apps and all(a in plugin.descendants(roots[0], procs) for a in apps), str(roots))
child = int(open(CHILD_PID).read())
check("the child is part of the tree", child in tree, f"{child} not in {sorted(tree)}")
wait_for(lambda: os.path.exists(ENVDUMP))
dumped = dict(line.split("=", 1) for line in open(ENVDUMP).read().splitlines() if "=" in line)
check("Decky's own environment did NOT reach the app (its library path and PYTHONHOME would break the system Python)",
      "LD_LIBRARY_PATH" not in dumped and "PYTHONHOME" not in dumped and dumped.get("HOME") == home, str({k: v for k, v in dumped.items() if k in ("LD_LIBRARY_PATH", "PYTHONHOME", "HOME")}))
check("it runs in its own session: not tied to the plugin's process group", os.getsid(next(iter(apps))) != os.getsid(0))
del os.environ["LD_LIBRARY_PATH"], os.environ["PYTHONHOME"]        # they would break this test's own Python subprocesses (which is exactly why the app must not get them)

print("\n--- who the app runs as (the plugin's backend runs as root; the app must not, and needs the user's groups)")
check("the app gets the real user's HOME and USER, not the root ones Decky reports for the backend", dumped.get("HOME") == home and dumped.get("USER") == user,
      str({k: dumped.get(k) for k in ("HOME", "USER")}))
check("not root: no user/group options are passed (the backend is already the user)", os.geteuid() == 0 or plugin.spawn_options(user) == {})
real_geteuid = os.geteuid
os.geteuid = lambda: 0
try:
    options = plugin.spawn_options(user)
finally:
    os.geteuid = real_geteuid
pw = pwd.getpwnam(user)
check("as root the app is started as the user, with the user's primary group and the FULL group list (what a login gives it)",
      options == {"user": pw.pw_uid, "group": pw.pw_gid, "extra_groups": os.getgrouplist(user, pw.pw_gid)} and pw.pw_gid in options["extra_groups"], str(options))
info = plugin.describe_access(user)
check("the plugin's log says who the app runs as, with which groups, and which group owns the input devices",
      f"app runs as {user}" in info and "groups [" in info and "/dev/input devices belong to group" in info, info)
real_getgroups = os.getgroups
os.getgroups = lambda: []
os.geteuid = lambda: 1000
try:
    warned = plugin.describe_access(user)
finally:
    os.getgroups, os.geteuid = real_getgroups, real_geteuid
check("a backend that is NOT root and lacks the user's groups is called out (this is exactly what breaks the touchscreen)", "WARNING" in warned and "root flag" in warned, warned)
manifest = json.load(open(os.path.join(_extract.ROOT, "decky-plugin", "plugin.json")))
check("plugin.json asks Decky for the root flag (Decky's name for it is exactly \"root\")", "root" in manifest["flags"], str(manifest))

print("\n--- a second launch")
r = run(plugin.launch_app())
apps2, tree2 = instance()
check("is refused, and no second app was started", not r["ok"] and r["message"] == strings.DECKY_ALREADY_RUNNING and apps2 == apps, f"{r} {apps2} vs {apps}")

print("\n--- stop: politely")
r = run(plugin.stop_app())
check("stop reports success", r["ok"] and r["message"] == strings.DECKY_STOPPED, str(r))
check("the app itself was asked (SIGTERM reached it and it shut down its own child), not just killed", os.path.exists(FLAG) and open(FLAG).read() == "graceful")
left = sorted(p for p in tree | {child} if plugin.alive(p))
check("nothing of the app is left: not the app, not its wrapper, not its child", not instance()[1] and not left, str(left))
r = run(plugin.stop_app())
check("stopping again says it isn't running", not r["ok"] and r["message"] == strings.DECKY_NOT_RUNNING, str(r))
clean_up()

print("\n--- stop: an app that ignores the polite request")
install_fake_app(ignore_term=True)
plugin.TERM_WAIT, plugin.KILL_WAIT = 1.0, 1.0
run(plugin.launch_app())
wait_for(lambda: os.path.exists(CHILD_PID))
apps, tree = instance()
child = int(open(CHILD_PID).read())
t0 = time.time()
r = run(plugin.stop_app())
check("it is escalated (SIGTERM to all, then SIGKILL) and everything ends", r["ok"] and not any(plugin.alive(p) for p in tree | {child}), f"{r} {sorted(p for p in tree | {child} if plugin.alive(p))}")
check("...within the waiting times, not hanging", time.time() - t0 < 12, f"{time.time() - t0:.1f}s")
plugin.TERM_WAIT, plugin.KILL_WAIT = 8.0, 2.0
clean_up()

print("\n--- nothing is left behind, even a browser or Anki whose parent is gone")
stray = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)", f"--user-data-dir={home}/.local/share/armada-yomitan/browser-profile"], start_new_session=True)
anki = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)", f"{home}/.local/share/armada-yomitan/anki/venv/bin/anki"], start_new_session=True)
bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)", f"{home}/.local/share/somebody-else/browser-profile"], start_new_session=True)
time.sleep(0.5)
r = run(plugin.stop_app())
time.sleep(0.3)
check("with only such leftovers running, stop finds and ends them", r["ok"] and stray.poll() is not None and anki.poll() is not None, f"{r} {stray.poll()} {anki.poll()}")
check("...and leaves an unrelated process alone", bystander.poll() is None)
bystander.kill()
bystander.wait()

print("\n--- a start that fails")
os.remove(f"{plugin_dir}/bin/armada-yomitan")
r = run(plugin.launch_app())
check("no bundled executable: a clear message", not r["ok"] and r["message"] == strings.DECKY_NOT_BUNDLED, str(r))
write(f"{plugin_dir}/bin/armada-yomitan", "import sys\nprint('cannot start')\nsys.exit(3)\n", 0o644)
r = run(plugin.launch_app())
check("an executable that dies at once: reported with its status and where to look", not r["ok"] and r["message"] == strings.DECKY_STOPPED_AT_ONCE.format(code=3, output=f"{log_dir}/app-output.log"), str(r))
check("...and its output was kept in the plugin's log", "cannot start" in open(f"{log_dir}/app-output.log").read())

print("\n--- what Decky calls")
install_fake_app()
real = plugin.launch_app


async def boom():
    raise RuntimeError("something odd")


plugin.launch_app = boom
r = run(plugin.Plugin().launch())
check("an unexpected error reaches the panel as a message instead of vanishing", not r["ok"] and r["message"] == strings.DECKY_LAUNCH_FAILED.format(error="something odd"), str(r))
plugin.launch_app = real
r = run(plugin.Plugin().launch())
check("Plugin.launch and Plugin.stop are what the panel's buttons call", r["ok"], str(r))
wait_for(lambda: os.path.exists(CHILD_PID))
r = run(plugin.Plugin().stop())
check("...and Plugin.stop ends it", r["ok"], str(r))
clean_up()

print("\n--- Advanced Settings: what is passed to the app")
P_ = plugin.Plugin()
answer = run(P_.get_settings())
check("nothing saved yet: the defaults are rotation 270 and touch top_touchscreen, everything else nothing",
      answer["values"] == {"rotation": "270", "touch": "top_touchscreen", "node": "", "mode": "", "engine": "", "scan_length": "", "ui_scale": "", "no_grab": False}, str(answer["values"]))
check("the panel is told what to draw: every setting with its kind, and the choices of the choice ones",
      [o["key"] for o in answer["options"]] == list(answer["values"]) and {o["key"]: o["choices"] for o in answer["options"]}["rotation"] == ["0", "90", "180", "270"]
      and {o["key"]: o["kind"] for o in answer["options"]}["no_grab"] == "toggle", str(answer["options"]))
check("the defaults become the arguments the Steam shortcut used to carry", plugin.launch_arguments(answer["values"]) == ["--rotation", "270", "--touch", "top_touchscreen"])
saved = run(P_.set_settings({"rotation": "90", "touch": " my touch screen ", "node": "34", "mode": "tap", "engine": "tesseract", "scan_length": "30", "ui_scale": "2.5", "no_grab": True}))["values"]
check("settings are stored and cleaned (spaces trimmed)", saved["touch"] == "my touch screen" and saved["rotation"] == "90" and saved["no_grab"] is True
      and json.load(open(f"{work}/settings/settings.json")) == saved, str(saved))
check("...and become arguments, in the order of the table",
      plugin.launch_arguments(saved) == ["--rotation", "90", "--touch", "my touch screen", "--node", "34", "--mode", "tap", "--engine", "tesseract",
                                         "--scan-length", "30", "--ui-scale", "2.5", "--no-grab"], str(plugin.launch_arguments(saved)))
check("they survive the plugin being loaded again (they are read from the file)", plugin.load_settings() == saved)
bad = run(P_.set_settings({"rotation": "45", "touch": "--evil\nname", "node": "12ab", "mode": "x", "engine": 5, "scan_length": "-3", "ui_scale": "99", "no_grab": "yes", "junk": 1}))["values"]
check("invalid values mean nothing (not an error, not passed on), a touch name can't look like a flag, unknown keys are dropped",
      bad == {"rotation": "", "touch": "evilname", "node": "", "mode": "", "engine": "", "scan_length": "", "ui_scale": "", "no_grab": False}, str(bad))
check("a setting missing from what is sent keeps its default (an older panel)", run(P_.set_settings({"node": "7"}))["values"]["rotation"] == "270")
open(f"{work}/settings/settings.json", "w").write("{ not json")
check("a damaged settings file means the defaults, not a crash", plugin.load_settings() == plugin.default_settings())
run(P_.set_settings({"rotation": "0", "node": "5"}))
reset = run(P_.reset_settings())["values"]
check("Default resets everything to nothing except rotation 270 and touch top_touchscreen, and saves that",
      reset == plugin.default_settings() and plugin.load_settings() == reset, str(reset))

print("\n--- ...and they reach the app: launched with saved settings")
install_fake_app()
run(P_.set_settings({"rotation": "180", "touch": "my touch screen", "node": "34", "no_grab": True}))
r = run(plugin.launch_app())
check("launch works with saved settings", r["ok"], str(r))
wait_for(lambda: os.path.exists(ENVDUMP))
dumped = dict(line.split("=", 1) for line in open(ENVDUMP).read().splitlines() if "=" in line)
check("the app is told it was started from the plugin", dumped.get("ARMADA_YOMITAN_VIA_DECKY") == "1", str(dumped.get("ARMADA_YOMITAN_VIA_DECKY")))
check("the app's environment carries them, shell-quoted, for its launcher (it is started with no arguments of its own)",
      dumped.get("ARMADA_YOMITAN_LAUNCH_ARGS") == "--rotation 180 --touch 'my touch screen' --node 34 --no-grab", str(dumped.get("ARMADA_YOMITAN_LAUNCH_ARGS")))
run(plugin.stop_app())
clean_up()

print("\n--- the Install System Dependencies button: root installs the system packages, then the parts as the user")
INSTALL_LOG = f"{work}/install-calls.log"
INSTALLER = f"""
import json, os, sys, time
open({INSTALL_LOG!r}, "a").write(json.dumps({{"argv": sys.argv[1:], "home": os.environ.get("HOME")}}) + "\\n")
if "--list-deps" in sys.argv:
    every = os.path.exists({work!r} + "/all-present")
    print(json.dumps({{"packages": [{{"name": "gstreamer1", "optional": False, "present": True}},
                                    {{"name": "minizip-ng-compat", "optional": False, "present": every}},
                                    {{"name": "xcb-util-cursor", "optional": True, "present": every}}]}}))
elif "--install-deps" in sys.argv:
    print("Layering with rpm-ostree: minizip-ng-compat")
    if os.path.exists({work!r} + "/slow"):
        time.sleep(1.5)
    if os.path.exists({work!r} + "/fail-system"):
        print("error: could not reach the repository"); sys.exit(1)
elif "--setup" in sys.argv:
    print("Downloading Chromium (one time) ...")
    print("Downloading progress 10%\\rDownloading progress 90%")
    if os.path.exists({work!r} + "/fail-parts"):
        print("Install failed: no space"); sys.exit(1)
else:
    os.execvp("armada-run-bottom", ["armada-run-bottom", "--"])
"""
install_fake_app(exe_body=INSTALLER)
INSTALL_CALLS = lambda: [json.loads(l) for l in open(INSTALL_LOG).read().splitlines()] if os.path.exists(INSTALL_LOG) else []
reset_install = lambda: (plugin.INSTALL.update(running=False, done=False, ok=None, line="", message=""), os.path.exists(INSTALL_LOG) and os.remove(INSTALL_LOG),
                         [os.path.exists(f"{work}/{f}") and os.remove(f"{work}/{f}") for f in ("all-present", "slow", "fail-system", "fail-parts")])


async def install_and_wait():
    started = await plugin.start_install()
    while plugin.INSTALL["running"]:
        await asyncio.sleep(0.05)
    return started


reset_install()
answer = run(P_.get_dependencies())
check("the panel gets the system packages with optional and installed flags (only what needs root)",
      answer["ok"] and [p["name"] for p in answer["packages"]] == ["gstreamer1", "minizip-ng-compat", "xcb-util-cursor"] and answer["packages"][2]["optional"] is True
      and answer["packages"][0]["present"] is True and answer["packages"][1]["present"] is False, str(answer))
os.remove(INSTALL_LOG)
started = run(install_and_wait())
calls = INSTALL_CALLS()
check("pressing it installs: first the system packages (--install-deps -y), then the parts without the system packages (--setup --no-system)",
      started["ok"] and started["message"] == strings.DECKY_INSTALL_STARTED
      and [c["argv"] for c in calls] == [["--list-deps"], ["--install-deps", "-y"], ["--setup", "--no-system"]], str(calls))
check("the system step runs with root's home, the parts with the user's", calls[1]["home"] == "/root" and calls[2]["home"] == home, str(calls))
check("packages were missing, so it says a restart is needed", plugin.INSTALL["ok"] is True and plugin.INSTALL["message"] == strings.DECKY_INSTALL_DONE_REBOOT, str(plugin.INSTALL))
check("the panel can read the last output line (progress-bar carriage returns split into lines)", plugin.INSTALL["line"] == "Downloading progress 90%", plugin.INSTALL["line"])
check("all of the output is kept in the install log", "Layering with rpm-ostree" in open(f"{log_dir}/install-output.log").read() and "Downloading Chromium" in open(f"{log_dir}/install-output.log").read())
status = run(P_.install_status())
check("install_status tells the panel it is finished", status["running"] is False and status["done"] is True and status["ok"] is True, str(status))

reset_install()
open(f"{work}/all-present", "w").close()
run(install_and_wait())
check("nothing was missing: no restart is asked for", plugin.INSTALL["message"] == strings.DECKY_INSTALL_DONE, str(plugin.INSTALL))

reset_install()
open(f"{work}/fail-system", "w").close()
run(install_and_wait())
check("a failing system step is reported with its last line, and the parts are not installed", plugin.INSTALL["ok"] is False
      and plugin.INSTALL["message"] == strings.DECKY_INSTALL_FAILED.format(error="error: could not reach the repository")
      and not any(c["argv"][:1] == ["--setup"] for c in INSTALL_CALLS()), str(plugin.INSTALL))

reset_install()
open(f"{work}/fail-parts", "w").close()
run(install_and_wait())
check("a failing parts step is reported too", plugin.INSTALL["ok"] is False and "Install failed: no space" in plugin.INSTALL["message"], str(plugin.INSTALL))

reset_install()
open(f"{work}/slow", "w").close()


async def while_installing():
    first = await plugin.start_install()
    second = await plugin.start_install()
    launched = await plugin.launch_app()
    while plugin.INSTALL["running"]:
        await asyncio.sleep(0.05)
    return first, second, launched


first, second, launched = run(while_installing())
check("a second press while installing is refused", first["ok"] and not second["ok"] and second["message"] == strings.DECKY_INSTALL_BUSY, str((first, second)))
check("launching is refused while installing", not launched["ok"] and launched["message"] == strings.DECKY_LAUNCH_INSTALLING, str(launched))

reset_install()
r = run(plugin.launch_app())
check("(the fake app starts)", r["ok"], str(r))
started = run(plugin.start_install())
check("installing is refused while the app runs (it would replace what the app is using)", not started["ok"] and started["message"] == strings.DECKY_INSTALL_STOP_FIRST, str(started))
run(plugin.stop_app())
clean_up()

reset_install()
os.rename(f"{plugin_dir}/bin/armada-yomitan", f"{plugin_dir}/bin/armada-yomitan.off")
answer = run(P_.get_dependencies())
started = run(plugin.start_install())
check("without the bundled app there is nothing to install with, and the panel is told", not answer["ok"] and answer["message"] == strings.DECKY_NOT_BUNDLED
      and not started["ok"] and started["message"] == strings.DECKY_NOT_BUNDLED, str((answer, started)))
os.rename(f"{plugin_dir}/bin/armada-yomitan.off", f"{plugin_dir}/bin/armada-yomitan")

print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
