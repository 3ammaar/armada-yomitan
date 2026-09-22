"""Running Anki."""

import os
import shutil
import socket

from armada_yomitan.assets import ANKI_TOUCH_ADDON
from armada_yomitan.browser import browser_env
from armada_yomitan.console import log_error
from armada_yomitan.paths import HOME_DIR


def anki_env(cfg, extra_flags="", scale=None, background=False):
    env = browser_env()
    env.setdefault("QT_QPA_PLATFORM", "xcb")
    scale = scale or cfg.anki_scale
    # Anki replaces QT_SCALE_FACTOR with the UI size from its own preferences as it starts, so this alone does nothing; prepare_anki() sets it too
    env["QT_SCALE_FACTOR"] = f"{scale:g}"
    env["ARMADA_YOMITAN_ANKI_SCALE_TARGET"] = f"{scale:g}"
    env["ARMADA_YOMITAN_ANKI_SOCK"] = anki_socket_path()
    if background:
        env["ARMADA_YOMITAN_ANKI_BACKGROUND"] = "1"
    flags = env.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    for flag in ("--disable-gpu", extra_flags):
        if flag and flag not in flags:
            flags = (flags + " " + flag).strip()
    env["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
    return env


ANKI_ADDON_ID = "armada_yomitan_touch"


def anki_socket_path():
    path = os.path.join(HOME_DIR, "anki.sock")
    if len(path.encode()) > 100:
        path = f"/tmp/armada-yomitan-{os.getuid()}-anki.sock"
    return path


def anki_send(word, timeout=3.0):
    """Returns "ok", or None if nothing is listening."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(timeout)
            conn.connect(anki_socket_path())
            conn.sendall(word.encode() + b"\n")
            return conn.recv(64).decode(errors="replace").strip()
    except OSError:
        return None


def anki_base_dir(cmd):
    for i, part in enumerate(cmd):
        if part in ("-b", "--base") and i + 1 < len(cmd):
            return os.path.expanduser(cmd[i + 1])
        if part.startswith("--base="):
            return os.path.expanduser(part[len("--base="):])
    if any("net.ankiweb.Anki" in part for part in cmd):        # the Flatpak keeps it in its own data folder
        return os.path.expanduser("~/.var/app/net.ankiweb.Anki/data/Anki2")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "Anki2")


def install_anki_touch_addon(base):
    folder = os.path.join(base, "addons21", ANKI_ADDON_ID)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "__init__.py")
    try:
        with open(path) as f:
            if f.read() == ANKI_TOUCH_ADDON:
                return False
    except OSError:
        pass
    with open(path, "w") as f:
        f.write(ANKI_TOUCH_ADDON)
    return True


def set_anki_ui_scale(base, scale):
    """Returns "changed", "unchanged" or "no-prefs"."""
    import pickle
    import sqlite3
    path = os.path.join(base, "prefs21.db")
    if not os.path.exists(path):
        return "no-prefs"
    con = sqlite3.connect(path, timeout=5)
    try:
        row = con.execute("select cast(data as blob) from profiles where name = '_global'").fetchone()
        if not row:
            return "no-prefs"
        meta = pickle.loads(row[0])
        if not isinstance(meta, dict):
            raise ValueError("the global preferences aren't in the expected format")
        if abs(float(meta.get("uiScale", 1.0)) - scale) < 0.005:
            return "unchanged"
        backup = path + ".armada-yomitan.bak"
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        meta["uiScale"] = float(scale)
        con.execute("update profiles set data = ? where name = '_global'", (pickle.dumps(meta, protocol=4),))
        con.commit()
        return "changed"
    finally:
        con.close()


def prepare_anki(cmd, scale):
    base = anki_base_dir(cmd)
    try:
        if os.environ.get("ARMADA_YOMITAN_ANKI_TOUCH") == "0":
            shutil.rmtree(os.path.join(base, "addons21", ANKI_ADDON_ID), ignore_errors=True)
        else:
            install_anki_touch_addon(base)
    except OSError as e:
        log_error(f"Couldn't install the Anki touch helper into {base}: {e}",
                  ["Anki will still start, but its windows won't get a Close button."])
    try:
        set_anki_ui_scale(base, scale)
    except Exception as e:
        log_error(f"Couldn't set Anki's UI size: {e}",
                  ["Anki will still start; its touch helper sets the size from inside, for the next start."])
