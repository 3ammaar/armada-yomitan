"""Finding Anki."""

import glob
import os
import shutil
import subprocess

from armada_yomitan import strings
from armada_yomitan.paths import ANKI_VENV

ANKI_NAMES = ("anki", "Anki", "anki.sh", "AppRun", "bin/anki", "venv/bin/anki", ".venv/bin/anki")


def anki_launcher_in(path):
    path = os.path.realpath(os.path.expanduser(path))
    if os.path.isfile(path):
        if path.endswith(".AppImage") and not os.access(path, os.X_OK):
            try:
                os.chmod(path, os.stat(path).st_mode | 0o111)      # a downloaded AppImage often lacks the executable bit
            except OSError:
                pass
        return [path] if os.access(path, os.X_OK) else None
    if os.path.isdir(path):
        for name in ANKI_NAMES:
            candidate = os.path.join(path, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return [candidate]
        for candidate in sorted(glob.glob(os.path.join(path, "*.AppImage"))):
            cmd = anki_launcher_in(candidate)
            if cmd:
                return cmd
    return None


def find_anki_installs():
    found, seen = [], set()

    def add(label, cmd):
        if cmd and tuple(cmd) not in seen:
            seen.add(tuple(cmd))
            found.append({"label": label, "cmd": list(cmd)})

    own = os.path.join(ANKI_VENV, "bin", "anki")
    if os.access(own, os.X_OK):
        add(strings.ANKI_INSTALLED_BY_APP, [own])
    if shutil.which("anki"):
        add(strings.ANKI_FOUND_ON_SYSTEM, [shutil.which("anki")])
    if shutil.which("flatpak"):
        try:
            if subprocess.run(["flatpak", "info", "net.ankiweb.Anki"], capture_output=True, timeout=10).returncode == 0:
                add(strings.ANKI_FOUND_FLATPAK, ["flatpak", "run", "net.ankiweb.Anki"])
        except (OSError, subprocess.TimeoutExpired):
            pass
    home = os.path.expanduser("~")
    for pattern in ("Applications/*nki*", "Downloads/*nki*", "anki*", ".local/share/AnkiProgramFiles",
                    "/opt/anki*", "/opt/Anki*", "/usr/local/anki*"):
        full = pattern if pattern.startswith("/") else os.path.join(home, pattern)
        for candidate in sorted(glob.glob(full)):
            cmd = anki_launcher_in(candidate)
            if cmd:
                add(strings.ANKI_FOUND_IN.format(path=candidate.replace(home, "~", 1)), cmd)
    return found


def anki_ready(prefs):
    cmd = prefs.get("anki_cmd") or []
    if not cmd:
        return False
    return os.access(cmd[0], os.X_OK) if os.path.isabs(cmd[0]) else bool(shutil.which(cmd[0]))


def anki_installed_by_app(cmd):
    return bool(cmd) and cmd[0].startswith(ANKI_VENV + os.sep)


def list_dir(path):
    real = os.path.realpath(os.path.expanduser(path or "~"))
    if not os.path.isdir(real):
        real = os.path.expanduser("~")
    items = []
    try:
        entries = sorted(os.scandir(real), key=lambda e: (not e.is_dir(), e.name.lower()))
    except OSError:
        entries = []
    for entry in entries:
        if entry.name.startswith(".") and entry.name != ".local":
            continue
        try:
            is_dir = entry.is_dir()
            program = (not is_dir) and (os.access(entry.path, os.X_OK) or entry.name.endswith(".AppImage"))
        except OSError:
            continue
        if is_dir or program:
            items.append({"name": entry.name, "dir": is_dir})
        if len(items) >= 400:
            break
    return {"path": real, "parent": os.path.dirname(real) if real != "/" else None, "items": items}
