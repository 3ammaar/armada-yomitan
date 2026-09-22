"""Installing Anki."""

import collections
import glob
import json
import os
import shutil
import signal
import subprocess

from armada_yomitan import strings
from armada_yomitan.paths import ANKI_VENV, HOME_DIR
from armada_yomitan.syslibs import missing_libs
from armada_yomitan.toolchain import download, ensure_uv

AQT_PYPI_API = "https://pypi.org/pypi/aqt/json"


class InstallError(RuntimeError):
    def __init__(self, message, tail=()):
        super().__init__(message)
        self.tail = list(tail)


def qt_missing_libs():
    roots = glob.glob(os.path.join(ANKI_VENV, "lib", "python*", "site-packages", "PyQt6"))
    if not roots:
        return []
    files = (glob.glob(os.path.join(roots[0], "Qt6", "plugins", "platforms", "libqxcb.so"))
             + glob.glob(os.path.join(roots[0], "Qt6", "lib", "libQt6WebEngineCore.so*"))
             + glob.glob(os.path.join(roots[0], "QtWebEngineCore*.so")))
    missing = set()
    for path in sorted({os.path.realpath(f) for f in files})[:6]:
        missing.update(missing_libs(path))
    return sorted(missing)


def install_anki(on_line, on_proc=None):
    os.makedirs(HOME_DIR, exist_ok=True)
    free = shutil.disk_usage(HOME_DIR).free
    if free < 3 * 1024 ** 3:
        raise RuntimeError(strings.ANKI_NOT_ENOUGH_SPACE.format(free=free / 1e9))
    uv = ensure_uv()
    env = dict(os.environ, UV_PYTHON_DOWNLOADS="automatic")
    shutil.rmtree(ANKI_VENV, ignore_errors=True)
    py = os.path.join(ANKI_VENV, "bin", "python")
    steps = ((strings.ANKI_STEP_PYTHON, [uv, "venv", "--python", "3.13", ANKI_VENV]),
             (strings.ANKI_STEP_DOWNLOAD,
              [uv, "pip", "install", "--python", py, "aqt", "PyQt6", "PyQt6-WebEngine"]))
    for title, cmd in steps:
        on_line(strings.ANKI_STEP_RUNNING.format(title=title))
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                errors="replace", start_new_session=True)     # own process group, so cancelling stops helpers too
        if on_proc:
            on_proc(proc)
        last, tail = "", collections.deque(maxlen=40)
        for line in proc.stdout:
            if line.strip():
                last = line.strip()
                tail.append(last)
                on_line(strings.ANKI_STEP_OUTPUT.format(title=title, line=last[:80]))
        proc.wait()
        if proc.returncode != 0:
            reason = last[:120] or strings.ANKI_STEP_EXIT_CODE.format(code=proc.returncode)
            raise InstallError(strings.ANKI_STEP_FAILED.format(title=title, reason=reason), tail)
    launcher = os.path.join(ANKI_VENV, "bin", "anki")
    command = [launcher] if os.access(launcher, os.X_OK) else [py, "-m", "aqt"]
    return command, qt_missing_libs()


def installed_aqt_version():
    py = os.path.join(ANKI_VENV, "bin", "python")
    if not os.access(py, os.X_OK):
        return None
    try:
        out = subprocess.run([py, "-c", "import importlib.metadata as m; print(m.version('aqt'))"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def anki_up_to_date():
    """True/False, or None when the installed or the latest version couldn't be determined."""
    installed = installed_aqt_version()
    if not installed:
        return None
    try:
        latest = json.loads(download(AQT_PYPI_API))["info"]["version"]
    except (RuntimeError, ValueError, KeyError):
        return None
    return installed == latest


def stop_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        proc.terminate()
