"""Tests for system package installation."""

import contextlib
import io
import json
import os
import stat
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract

FAILED = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{extra}]" if extra and not ok else ""))
    if not ok:
        FAILED.append(label)


work = tempfile.mkdtemp(prefix="ay-syspkg-")
m = _extract.load_module(f"{work}/home")
sp = sys.modules["armada_yomitan.syspackages"]      # addressed directly: "install" is also the name of two submodules
strings = m.strings
bindir = f"{work}/bin"
os.makedirs(bindir)
LOG = f"{work}/calls.log"
os.environ["LOG"] = LOG


def fake(name, body):
    path = f"{bindir}/{name}"
    with open(path, "w") as f:
        f.write("#!/bin/bash\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


fake("gst-launch-1.0", "exit 0")
fake("gst-inspect-1.0", '[[ " ${FAKE_NO_GST:-} " == *" $1 "* ]] && exit 1; exit 0')
fake("tesseract", 'echo "List of available languages:"; echo jpn; [ -z "${NO_VERT:-}" ] && echo jpn_vert; exit 0')
fake("armada-run-bottom", "exit 0")
fake("ldconfig", 'for l in ${FAKE_LIBS:-}; do echo "	$l (libc6,AArch64) => /usr/lib64/$l"; done')
fake("rpm-ostree", 'echo "rpm-ostree $*" >> "$LOG"; echo "Staging deployment... done"; '
                   'if [ -n "${FAIL_FIRST:-}" ] && [ ! -f "$LOG.failed" ]; then touch "$LOG.failed"; '
                   'echo "error: Packages not found: xcb-util-cursor" >&2; exit 1; fi; exit 0')
fake("systemctl", 'echo "systemctl $*" >> "$LOG"; [ -n "${SYSTEMCTL_FAILS:-}" ] && exit 1; exit 0')
# sudo: -n succeeds only when SUDO_NOPASS is set; -S -p "" reads the password from stdin and compares it with SUDO_PASSWORD
fake("sudo", '''echo "sudo $*" >> "$LOG"
if [ "$1" = "-n" ]; then
  shift
  if [ -z "${SUDO_NOPASS:-}" ]; then echo "sudo: a password is required" >&2; exit 1; fi
  [ "$1" = true ] && exit 0
  exec "$@"
fi
if [ "$1" = "-S" ]; then
  shift 3
  read -r pw
  if [ "$pw" != "${SUDO_PASSWORD:-}" ]; then echo "sudo: 1 incorrect password attempt" >&2; exit 1; fi
  exec "$@"
fi
exec "$@"''')
os.environ["PATH"] = f"{bindir}:" + os.environ["PATH"]
sp.have_gtk = lambda: True


def calls():
    return open(LOG).read().splitlines() if os.path.exists(LOG) else []


def reset(**env):
    for f in (LOG, LOG + ".failed"):
        if os.path.exists(f):
            os.remove(f)
    for k in ("FAKE_LIBS", "FAIL_FIRST", "SUDO_NOPASS", "SUDO_PASSWORD", "NO_VERT", "FAKE_NO_GST", "SYSTEMCTL_FAILS"):
        os.environ.pop(k, None)
    os.environ.update(env)


root = os.geteuid() == 0

print("--- what gets layered (the deps script's own cases)")
reset(FAKE_LIBS="")
required, optional = sp.plan(sp.run_checks())
check("libminizip missing -> minizip-ng-compat is required, the optional xcb-util-cursor is offered", "minizip-ng-compat" in required and "xcb-util-cursor" in optional, str((required, optional)))
reset(FAKE_LIBS="libminizip.so.1 libxcb-cursor.so.0")
check("both libraries present -> nothing to install", sp.plan(sp.run_checks()) == ([], []))
reset(FAKE_LIBS="libminizip.so.1")
required, optional = sp.plan(sp.run_checks())
check("only the optional one missing -> only xcb-util-cursor", required == [] and optional == ["xcb-util-cursor"], str((required, optional)))
reset(FAKE_LIBS="")
required, optional = sp.plan(sp.run_checks(anki=False))
check("anki=False (--no-anki) -> none of the Anki libraries", not any("minizip" in p or "xcb" in p for p in required + optional))
reset(FAKE_LIBS="libminizip.so.1 libxcb-cursor.so.0", NO_VERT="1")
check("jpn_vert missing is optional, and vertical=False (--no-vertical) skips it",
      sp.plan(sp.run_checks())[1] == ["tesseract-langpack-jpn_vert"] and sp.plan(sp.run_checks(vertical=False)) == ([], []))
reset(FAKE_LIBS="libminizip.so.1 libxcb-cursor.so.0", FAKE_NO_GST="pipewiresrc pngenc")
required, _ = sp.plan(sp.run_checks())
check("a missing GStreamer plugin -> its package, in the script's order", required == ["gstreamer1-plugins-good", "pipewire-gstreamer"], str(required))
reset(FAKE_LIBS="")
found = sp.missing()
check("missing() lists what the app shows: label, packages, optional", any(l.startswith("libminizip") and p == ["minizip-ng-compat"] and not o for l, p, o in found))

print("\n--- installing, with passwordless sudo" if not root else "\n--- installing (running as root: the sudo cases are skipped)")
if not root:
    reset(FAKE_LIBS="", SUDO_NOPASS="1")
    out = []
    result = sp.install(out.append)
    check("missing libraries -> one rpm-ostree call through `sudo -n`, with the required and the optional packages",
          result == "staged" and any(c.startswith("sudo -n rpm-ostree install --idempotent") and "minizip-ng-compat" in c and "xcb-util-cursor" in c for c in calls()), str(calls()))
    check("its output reached the caller line by line", "Staging deployment... done" in out, str(out))
    reset(FAKE_LIBS="libminizip.so.1 libxcb-cursor.so.0", SUDO_NOPASS="1")
    check("nothing missing -> \"nothing\", no rpm-ostree call at all", sp.install(lambda t: None) == "nothing" and not any("rpm-ostree" in c for c in calls()))
    reset(FAKE_LIBS="", SUDO_NOPASS="1", FAIL_FIRST="1")
    result = sp.install(lambda t: None)
    rpm = [c for c in calls() if c.startswith("rpm-ostree install")]
    check("an optional package that is not found -> retried without it, minizip still installed",
          result == "staged" and len(rpm) == 2 and "minizip-ng-compat" in rpm[1] and "xcb-util-cursor" not in rpm[1], str(rpm))

    print("\n--- sudo asks for a password: the app doesn't handle one any more")
    reset(FAKE_LIBS="", SUDO_PASSWORD="s3cret-pw")
    try:
        sp.install(lambda t: None)
        check("without passwordless sudo the install fails (it is never offered a password)", False)
    except RuntimeError as e:
        check("without passwordless sudo the install fails (it is never offered a password)", str(e) == strings.PKG_INSTALL_FAILED, str(e))
    check("...and sudo was only ever run with -n (no password prompt, no -S)", all(c.startswith("sudo -n") for c in calls() if c.startswith("sudo")) and calls(), str(calls()))

    print("\n--- no sudo at all")
    real_which = sp.shutil.which
    sp.shutil.which = lambda name, *a, **k: None if name == "sudo" else real_which(name, *a, **k)
    reset(FAKE_LIBS="")
    try:
        sp.install(lambda t: None)
        check("no sudo -> a clear RuntimeError", False)
    except RuntimeError as e:
        check("no sudo -> a clear RuntimeError", "sudo isn't available" in str(e))
    sp.shutil.which = real_which

    print("\n--- restarting")
    reset(SUDO_NOPASS="1")
    sp.reboot()
    check("systemctl reboot is tried directly first", calls() == ["systemctl reboot"], str(calls()))
    reset(SUDO_NOPASS="1", SYSTEMCTL_FAILS="1")
    try:
        sp.reboot()
        check("when that fails it is retried through sudo, and a failure is reported", False)
    except RuntimeError as e:
        check("when that fails it is retried through sudo, and a failure is reported", "power menu" in str(e) and "sudo -n systemctl reboot" in calls(), str(calls()))

print("\n--- a restart is pending when rpm-ostree has a deployment the running system isn't")
plain = open(f"{bindir}/rpm-ostree").read()
for label, booted_first, expected in (("the newest deployment isn't the booted one", "false", True), ("the newest deployment is the booted one", "true", False)):
    fake("rpm-ostree", f'echo \'{{"deployments": [{{"booted": {booted_first}}}, {{"booted": {"true" if booted_first == "false" else "false"}}}]}}\'')
    check(label, sp.reboot_pending() is expected)
fake("rpm-ostree", "echo not json")
check("output that isn't JSON counts as nothing pending", sp.reboot_pending() is False)
open(f"{bindir}/rpm-ostree", "w").write(plain)

print("\n--- not an rpm-ostree image")
saved = os.environ["PATH"]
norpm = f"{work}/norpm"
os.makedirs(norpm)
for name in os.listdir(bindir):
    if name != "rpm-ostree":
        os.symlink(f"{bindir}/{name}", f"{norpm}/{name}")
os.environ["PATH"] = norpm + ":" + saved.split(":", 1)[1]
try:
    sp.install(lambda t: None)
    check("no rpm-ostree -> a message listing the packages to install by hand", False)
except RuntimeError as e:
    check("no rpm-ostree -> a message listing the packages to install by hand", "rpm-ostree isn't installed" in str(e) and "minizip-ng-compat" in str(e))
os.environ["PATH"] = saved

print("\n--- the command-line commands (--check-deps, --install-deps)")


def run_cmd(fn, **kw):
    buf, code = io.StringIO(), None
    with contextlib.redirect_stdout(buf):
        try:
            fn(**kw)
        except SystemExit as e:
            code = e.code
    return buf.getvalue(), code


reset(FAKE_LIBS="")
out, code = run_cmd(m.cmd_check_deps)
check("--check-deps lists what is missing and exits 1", "[MISS] libminizip.so.1" in out and "minizip-ng-compat" in out and code == 1, out[-300:])
check("...marks optional ones as a warning, not a failure", "[warn] libxcb-cursor.so.0" in out)
reset(FAKE_LIBS="libminizip.so.1 libxcb-cursor.so.0")
out, code = run_cmd(m.cmd_check_deps)
check("--check-deps with everything present says so and exits 0", "Everything armada-yomitan needs is present." in out and code is None, out[-200:])
if not root:
    reset(FAKE_LIBS="", SUDO_NOPASS="1")
    out, code = run_cmd(m.cmd_install_deps, yes=True)
    check("--install-deps -y lists the packages, layers them and says a reboot is needed",
          "Will layer these packages" in out and "Packages are staged for the next boot." in out and any("rpm-ostree install" in c for c in calls()), out[-300:])
    check("...without --reboot it doesn't restart", not any(c.startswith("systemctl") for c in calls()))
    reset(FAKE_LIBS="", SUDO_NOPASS="1")
    out, code = run_cmd(m.cmd_install_deps, yes=True, reboot=True)
    check("--install-deps -y --reboot restarts when done", "systemctl reboot" in calls(), str(calls()))
    reset(FAKE_LIBS="libminizip.so.1 libxcb-cursor.so.0")
    out, code = run_cmd(m.cmd_install_deps, yes=True)
    check("--install-deps with nothing missing installs nothing", "Nothing to install" in out and not any("rpm-ostree" in c for c in calls()))

print("\n--- --list-deps (what the Decky plugin shows before installing)")
reset(FAKE_LIBS="")
out, code = run_cmd(m.cmd_list_deps)
listed = {p["name"]: p for p in json.loads(out)["packages"]}
check("it prints JSON with every package, whether it is optional and whether it is present",
      listed["minizip-ng-compat"] == {"name": "minizip-ng-compat", "optional": False, "present": False}
      and listed["xcb-util-cursor"]["optional"] is True and listed["xcb-util-cursor"]["present"] is False
      and listed["gstreamer1"]["present"] is True and "pipewire-gstreamer" in listed and "tesseract-langpack-jpn" in listed, out[:400])
out, code = run_cmd(m.cmd_list_deps, anki=False, vertical=False)
check("--no-anki and --no-vertical leave those out", "minizip-ng-compat" not in out and "tesseract-langpack-jpn_vert" not in out, out[:300])

print("\n--- run as root: installs directly, no sudo and no password")
real_geteuid = os.geteuid
os.geteuid = lambda: 0
reset(FAKE_LIBS="")
result = sp.install(lambda t: None)
os.geteuid = real_geteuid
check("as root rpm-ostree is called directly", result == "staged" and any(c.startswith("rpm-ostree install") for c in calls()) and not any(c.startswith("sudo") for c in calls()), str(calls()))

print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
