"""The private Chromium: locating, launching and profile handling."""

import collections
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

from armada_yomitan import install_state
from armada_yomitan.paths import BROWSERS_DIR, EXT_DIR, PROFILE_DIR, VENV_PY


def find_browser():
    if os.environ.get("ARMADA_YOMITAN_BROWSER"):
        return os.environ["ARMADA_YOMITAN_BROWSER"]
    for pattern in ("chromium-*/*/chrome", "chromium-*/chrome"):
        hits = sorted(glob.glob(os.path.join(BROWSERS_DIR, pattern)))
        if hits:
            return hits[-1]
    return shutil.which("chromium") or shutil.which("chromium-browser")


def missing_parts():
    """The install steps ("ocr", "chromium", "yomitan") that aren't done."""
    missing = set()
    if not find_browser():
        missing.add("chromium")
    if not os.path.exists(os.path.join(EXT_DIR, "manifest.json")):
        missing.add("yomitan")
    if os.environ.get("ARMADA_YOMITAN_BROWSER"):
        return [step for step in install_state.STEPS if step in missing]
    if install_state.load() is None:                       # an install from before the steps were recorded
        if not os.path.exists(VENV_PY):
            missing.add("ocr")
        if missing:
            return [step for step in install_state.STEPS if step in missing]
        install_state.mark(*install_state.STEPS)
    missing |= set(install_state.STEPS) - install_state.load()
    return [step for step in install_state.STEPS if step in missing]


def web_ready():
    return not missing_parts()


def _profile_pids():
    want = f"--user-data-dir={PROFILE_DIR}".encode()
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == os.getpid():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                if want in f.read().split(b"\0"):
                    pids.append(int(entry))
        except OSError:
            continue
    return pids


def reset_profile_state():
    pids = _profile_pids()
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in pids:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        deadline = time.monotonic() + 3
        while pids and time.monotonic() < deadline:
            time.sleep(0.1)
            pids = [pid for pid in pids if os.path.exists(f"/proc/{pid}")]
        if not pids:
            break
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        path = os.path.join(PROFILE_DIR, name)
        if os.path.lexists(path):
            os.remove(path)
    default = os.path.join(PROFILE_DIR, "Default")
    for name in ("Sessions", "Current Session", "Current Tabs", "Last Session", "Last Tabs"):
        path = os.path.join(default, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)
    prefs = os.path.join(default, "Preferences")
    try:
        with open(prefs) as f:
            data = json.load(f)
        data.setdefault("profile", {}).update(exit_type="Normal", exited_cleanly=True)
        data.setdefault("translate", {})["enabled"] = False
        with open(prefs, "w") as f:
            json.dump(data, f)
    except (OSError, ValueError):
        pass


def browser_env():
    env = dict(os.environ)
    if os.path.exists("/etc/fonts/fonts.conf"):
        if not os.path.exists(env.get("FONTCONFIG_FILE", "")):
            env["FONTCONFIG_FILE"] = "/etc/fonts/fonts.conf"
        if not os.path.isdir(env.get("FONTCONFIG_PATH", "")):
            env["FONTCONFIG_PATH"] = "/etc/fonts"
    return env


def start_browser(cmd, live=False, env=None):
    tail = collections.deque(maxlen=80)
    proc = subprocess.Popen(cmd, env=env or browser_env(), stderr=subprocess.PIPE, text=True, errors="replace")

    def pump():
        for line in proc.stderr:
            tail.append(line.rstrip())
            if live:
                print(line, end="", file=sys.stderr, flush=True)

    threading.Thread(target=pump, daemon=True).start()
    return proc, tail


def browser_cmd(browser, url, settings=False, scale=None):
    base = [browser, f"--user-data-dir={PROFILE_DIR}", f"--load-extension={EXT_DIR}",
            f"--disable-extensions-except={EXT_DIR}", "--no-first-run", "--no-default-browser-check",
            "--password-store=basic", "--disable-session-crashed-bubble", "--disable-infobars",
            "--disable-features=Translate,TranslateUI", "--disable-translate",   # no "Translate this page?" bubble
            "--disable-background-networking", "--disable-sync", "--disable-component-update",
            "--disable-default-apps", "--disable-domain-reliability", "--no-pings"]   # no calls to Google's services
    if settings:
        wayland_only = os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY")
        return base + (["--ozone-platform=wayland"] if wayland_only else []) + [url]
    gpu = [] if os.environ.get("ARMADA_YOMITAN_GPU") else ["--disable-gpu"]
    zoom = [f"--force-device-scale-factor={scale}"] if scale else []   # the panel is ~420 ppi; X11 would say 96
    return base + gpu + zoom + ["--ozone-platform=x11", "--start-fullscreen", f"--app={url}"]
