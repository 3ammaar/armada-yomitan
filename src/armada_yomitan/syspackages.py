"""System packages and their installation."""

import glob
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from armada_yomitan import strings

TIMEOUT = 900
VIA_DECKY_ENV = "ARMADA_YOMITAN_VIA_DECKY"


def via_decky():
    return bool(os.environ.get(VIA_DECKY_ENV))


def can_install_here():
    """Root, and not started by the Decky plugin (which installs for the app)."""
    return os.geteuid() == 0 and not via_decky()


@dataclass
class Check:
    label: str
    ok: bool
    packages: list = field(default_factory=list)
    optional: bool = False
    note: str = ""


def have_cmd(name):
    return shutil.which(name) is not None


def have_gst(element):
    if not have_cmd("gst-inspect-1.0"):
        return False
    return subprocess.run(["gst-inspect-1.0", element], capture_output=True).returncode == 0


def have_lang(lang):
    if not have_cmd("tesseract"):
        return False
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
    return lang in out.splitlines()


def have_lib(name):
    try:
        out = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True).stdout
    except OSError:
        out = ""
    if name in out:
        return True
    return bool(glob.glob(f"/usr/lib*/{name}") or glob.glob(f"/usr/lib/*/{name}"))


def have_gtk():
    code = ("import gi\ngi.require_version('Gtk', '3.0')\ngi.require_version('GdkPixbuf', '2.0')\n"
            "from gi.repository import Gtk, GdkPixbuf\n")
    return subprocess.run([sys.executable, "-c", code], capture_output=True).returncode == 0


def run_checks(anki=True, vertical=True):
    checks = [
        Check(strings.CHECK_GST_LAUNCH, have_cmd("gst-launch-1.0"), ["gstreamer1"]),
        Check(strings.CHECK_GST_VIDEOCONVERT, have_gst("videoconvert"), ["gstreamer1-plugins-base"]),
        Check(strings.CHECK_GST_PNGENC, have_gst("pngenc"), ["gstreamer1-plugins-good"]),
        Check(strings.CHECK_GST_PIPEWIRESRC, have_gst("pipewiresrc"), ["pipewire-gstreamer"], note="reboot after installing"),
        Check(strings.CHECK_TESSERACT, have_cmd("tesseract"), ["tesseract"]),
        Check(strings.CHECK_TESSERACT_JPN, have_lang("jpn"), ["tesseract-langpack-jpn"]),
        Check(strings.CHECK_GTK, have_gtk(), ["python3-gobject", "gtk3"]),
    ]
    if vertical:
        checks.append(Check(strings.CHECK_TESSERACT_JPN_VERT, have_lang("jpn_vert"),
                            ["tesseract-langpack-jpn_vert"], optional=True))
    if anki:
        checks.append(Check(strings.CHECK_MINIZIP, have_lib("libminizip.so.1"), ["minizip-ng-compat"]))
        checks.append(Check(strings.CHECK_XCB_CURSOR, have_lib("libxcb-cursor.so.0"),
                            ["xcb-util-cursor"], optional=True))
    checks.append(Check(strings.CHECK_RUN_BOTTOM, have_cmd("armada-run-bottom"), optional=True))
    return checks


def plan(checks):
    """(required, optional) packages still to layer."""
    required, optional = [], []
    for c in checks:
        if not c.ok:
            (optional if c.optional else required).extend(p for p in c.packages if p not in required + optional)
    return required, optional


def missing(anki=True, vertical=True):
    return [(c.label, c.packages, c.optional) for c in run_checks(anki, vertical) if not c.ok]


def run_privileged(cmd, on_line=None):
    if os.geteuid() == 0:
        argv = list(cmd)
    else:
        sudo = shutil.which("sudo")
        if not sudo:
            raise RuntimeError(strings.PKG_NO_SUDO)
        argv = [sudo] + list(cmd) if on_line is None else [sudo, "-n"] + list(cmd)
    if on_line is None:
        return subprocess.run(argv).returncode
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    for line in proc.stdout:
        if line.strip():
            on_line(line.rstrip())
    proc.wait(timeout=TIMEOUT)
    return proc.returncode


def install(on_line=None, anki=True, vertical=True):
    """Returns "nothing" or "staged"."""
    if not have_cmd("rpm-ostree"):
        raise RuntimeError(strings.PKG_NO_RPM_OSTREE)
    required, optional = plan(run_checks(anki, vertical))
    if not required and not optional:
        return "nothing"
    say = on_line or (lambda text: print(text, flush=True))
    say(strings.PKG_LAYERING.format(packages=" ".join(required + optional)))
    base = ["rpm-ostree", "install", "--idempotent"]
    code = run_privileged(base + required + optional, on_line)
    if code != 0 and optional and required:
        say(strings.PKG_RETRY_WITHOUT_OPTIONAL.format(packages=" ".join(optional)))
        code = run_privileged(base + required, on_line)
    if code != 0:
        raise RuntimeError(strings.PKG_INSTALL_FAILED)
    return "staged"


def reboot_pending():
    """True when rpm-ostree has a deployment staged that the running system isn't."""
    if not have_cmd("rpm-ostree"):
        return False
    try:
        out = subprocess.run(["rpm-ostree", "status", "--json"], capture_output=True, text=True, timeout=60).stdout
        deployments = json.loads(out)["deployments"]
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return False
    return bool(deployments) and not deployments[0].get("booted", True)


def reboot():
    try:
        if subprocess.run(["systemctl", "reboot"], capture_output=True).returncode == 0:
            return
    except OSError:
        pass
    if run_privileged(["systemctl", "reboot"], lambda text: None) != 0:
        raise RuntimeError(strings.PKG_REBOOT_FAILED)
