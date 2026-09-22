"""Tests for the installer and SetupJob."""

import contextlib
import subprocess
import time
import io
import json
import os
import stat
import sys
import tempfile
import threading
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract

FAILED = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{extra}]" if extra and not ok else ""))
    if not ok:
        FAILED.append(label)


work = tempfile.mkdtemp(prefix="ay-installer-")
home = f"{work}/home"
m = _extract.load_module(home)
strings = m.strings
bindir = f"{work}/bin"
os.makedirs(bindir)
LOG = f"{work}/uv.log"
os.environ["LOG"], os.environ["REAL_PY"] = LOG, sys.executable


def script(path, body):
    with open(path, "w") as f:
        f.write("#!/bin/bash\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


script(f"{bindir}/uv", r'''echo "uv $*" >> "$LOG"
case "$1" in
  venv)
    dir="${@: -1}"; mkdir -p "$dir/bin"
    cat > "$dir/bin/python" <<'PY'
#!/bin/bash
if [ "$1" = "-m" ] && [ "$2" = "playwright" ]; then
  if [ -n "${FAKE_PW_FAILS:-}" ]; then echo "playwright: download failed" >&2; exit 1; fi
  echo "Downloading Chromium 1 of 1"
  mkdir -p "$PLAYWRIGHT_BROWSERS_PATH/chromium-1/linux"; printf '#!/bin/sh\n' > "$PLAYWRIGHT_BROWSERS_PATH/chromium-1/linux/chrome"
  chmod +x "$PLAYWRIGHT_BROWSERS_PATH/chromium-1/linux/chrome"; exit 0
fi
exec "$REAL_PY" "$@"
PY
    chmod +x "$dir/bin/python"; echo "Using CPython 3.13" ;;
  pip)
    if [ -n "${FAKE_UV_PIP_FAILS:-}" ]; then echo "error: no matching distribution for onnxruntime" >&2; exit 2; fi
    printf 'Resolved 12 packages\rDownloading rapidocr\rInstalled 12 packages\n' ;;
esac''')
os.environ["PATH"] = f"{bindir}:" + os.environ["PATH"]


def fake_yomitan_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("yomitan/manifest.json", json.dumps({"manifest_version": 3, "version": "9.9"}))
        for name in ("search.html", "settings.html", "welcome.html"):
            z.writestr(f"yomitan/{name}", f"<html><head></head><body>{name}</body></html>")
    return buf.getvalue()


def fake_download(url, timeout=30):
    if "api.github.com" in url:
        return json.dumps({"assets": [{"name": "yomitan-chrome.zip", "browser_download_url": "https://example.invalid/y.zip"}]}).encode()
    return fake_yomitan_zip()


m.download = fake_download

print("--- run_step reports every line, and fails as before")
got = []
m.run_step(["bash", "-c", "echo one; printf 'two\\rthree\\n'; echo err >&2"], say=got.append)
check("output is handed over line by line (a progress bar's carriage returns count), stderr included",
      got[0].startswith("+ bash") and got[1:] == ["one", "two", "three", "err"], str(got))
got = []
try:
    m.run_step(["bash", "-c", "echo before; exit 3"], say=got.append)
    check("a failing step raises the usual message", False)
except RuntimeError as e:
    check("a failing step raises the usual message", str(e).startswith(strings.SETUP_STEP_FAILED.split("{")[0]) and "before" in got, str(e))
got = []
m.run_step(["cat"], say=got.append, input=b"fed on stdin\n")
check("input= is still fed to the step", "fed on stdin" in got, str(got))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    m.run_step(["echo", "console"])
check("with no `say` it works as before: the command line is printed and the step writes to the real console itself",
      buf.getvalue() == "+ echo console\n", repr(buf.getvalue()))

print("\n--- the whole install, reported to a callback")
os.environ["FAKE_UV_PIP_FAILS"] = ""
lines = []
m.install_components(say=lines.append)
text = "\n".join(lines)
steps = [l for l in lines if l.startswith("+ ")]
check("uv makes the venv on the system Python with system site packages", any("uv venv --system-site-packages --python" in l for l in steps), str(steps[:2]))
check("RapidOCR + onnxruntime, then the OCR model warm-up, then playwright and Chromium, in that order",
      [("rapidocr" in l) or ("--warmup" in l) or ("playwright" in l) for l in steps].count(True) >= 4 and
      text.index("rapidocr onnxruntime") < text.index("Downloading the OCR models") < text.index("Downloading Chromium"), text[-600:])
check("the warm-up is this program re-run through the -c bootstrap, and it really ran", "-c" in text and "rapidocr isn't installed; nothing to warm up." in text, text[-800:])
check("Chromium's download output is passed on", "Downloading Chromium 1 of 1" in lines)
check("Yomitan is downloaded, unpacked and patched", strings.SETUP_DOWNLOADING_YOMITAN in lines and any(l.startswith(strings.SETUP_YOMITAN_READY.format(version="9.9", folder="").rstrip()) for l in lines), text[-300:])
check("...so the web interface is now ready to start", m.web_ready() is True)
check("progress-bar output (uv's carriage returns) arrived as separate lines", "Resolved 12 packages" in lines and "Installed 12 packages" in lines)

print("\n--- SetupJob (what the first-run window drives)")
import shutil
shutil.rmtree(home, ignore_errors=True)
events, done = [], threading.Event()
job = m.SetupJob(lambda t: events.append(("line", t)), lambda: (events.append(("done",)), done.set()), lambda msg: (events.append(("fail", msg)), done.set()))
job.start()
job.start()
check("it finishes and reports done exactly once", done.wait(60) and [e for e in events if e[0] in ("done", "fail")] == [("done",)], str(events[-3:]))
check("progress lines came through before that", sum(1 for e in events if e[0] == "line") > 5)
check("it is no longer marked as running", job.running is False)

print("\n--- a failing step: shown in the window, printed to the console, and the button can try again")
shutil.rmtree(home, ignore_errors=True)
os.environ["FAKE_UV_PIP_FAILS"] = "1"
events, done = [], threading.Event()
err = io.StringIO()
job = m.SetupJob(lambda t: events.append(("line", t)), lambda: (events.append(("done",)), done.set()), lambda msg: (events.append(("fail", msg)), done.set()))
with contextlib.redirect_stderr(err):
    job.start()
    finished = done.wait(60)
fails = [e[1] for e in events if e[0] == "fail"]
check("on_fail gets a short message, on_done is never called", finished and len(fails) == 1 and fails[0].startswith(strings.SETUP_FAILED.format(error=strings.SETUP_STEP_FAILED.split("{")[0])) and ("done",) not in events, str(events[-3:]))
check("uv's own error line was shown as progress before that", any("no matching distribution for onnxruntime" in e[1] for e in events if e[0] == "line"))
check("the failure is also on the console (the log file, from Steam)", strings.SETUP_FAILED.format(error=strings.SETUP_STEP_FAILED.split("{")[0]) in err.getvalue(), err.getvalue())
os.environ["FAKE_UV_PIP_FAILS"] = ""
events, done = [], threading.Event()
job2 = m.SetupJob(lambda t: None, lambda: (events.append("done"), done.set()), lambda msg: (events.append(msg), done.set()))
job2.start()
check("pressing Try again works after a failure", done.wait(60) and events == ["done"], str(events))

print("\n--- an install that failed or was stopped continues where it left off, and skips what is present")
shutil.rmtree(home, ignore_errors=True)
open(LOG, "w").close()
uv_venv_calls = lambda: sum(1 for l in open(LOG) if l.startswith("uv venv"))
manifest = f"{home}/yomitan/manifest.json"


def run_install(**kw):
    out = []
    m.install_components(say=out.append, **kw)
    return out


os.environ["FAKE_UV_PIP_FAILS"] = "1"
try:
    run_install()
except RuntimeError:
    pass
check("failing while installing OCR: nothing is recorded, so the web interface is not ready (the install window opens next time)",
      m.install_state.load() in (None, set()) and m.web_ready() is False)
os.environ["FAKE_UV_PIP_FAILS"], os.environ["FAKE_PW_FAILS"] = "", "1"
try:
    run_install()
except RuntimeError:
    pass
check("failing at Chromium: the OCR step is recorded, the rest is not, and it is still not ready", m.install_state.load() == {"ocr"} and m.web_ready() is False, str(m.install_state.load()))
check("...and the missing parts are named: Chromium and Yomitan, not OCR", m.missing_parts() == ["chromium", "yomitan"], str(m.missing_parts()))
venvs = uv_venv_calls()
os.environ["FAKE_PW_FAILS"] = ""
lines = run_install()
check("continuing: the OCR environment is kept (said so, and not built again)", strings.SETUP_OCR_PRESENT in lines and uv_venv_calls() == venvs, str(lines[:3]))
check("...Chromium and Yomitan are installed now, everything is recorded and the web interface is ready",
      m.install_state.complete() and m.web_ready() is True and os.path.exists(manifest))
lines = run_install()
check("running it again changes nothing: all three are reported as present and nothing is downloaded",
      [strings.SETUP_OCR_PRESENT, strings.SETUP_CHROMIUM_PRESENT, strings.SETUP_YOMITAN_PRESENT] == [l for l in lines if "already installed" in l]
      and strings.SETUP_DOWNLOADING_CHROMIUM not in lines and strings.SETUP_DOWNLOADING_YOMITAN not in lines, str(lines))
m.install_state.unmark("yomitan")
os.remove(manifest)
lines = run_install()
check("with only Yomitan missing, only Yomitan is installed", strings.SETUP_DOWNLOADING_YOMITAN in lines and strings.SETUP_DOWNLOADING_CHROMIUM not in lines
      and strings.SETUP_CHROMIUM_PRESENT in lines and os.path.exists(manifest) and m.install_state.complete(), str(lines))
lines = run_install(web_only=True)
check("--setup-web redoes Chromium and Yomitan but keeps the OCR environment",
      strings.SETUP_DOWNLOADING_CHROMIUM in lines and strings.SETUP_DOWNLOADING_YOMITAN in lines and strings.SETUP_OCR_PRESENT in lines and uv_venv_calls() == venvs)
os.remove(m.INSTALL_STATE_PATH)
check("an install from before the steps were recorded counts as complete (and is recorded now)", m.web_ready() is True and m.install_state.complete())
m.install_state.reset()
check("after a reset (Re-install dependencies) it is not ready until installed again", m.web_ready() is False)
run_install()
check("...and installing then rebuilds the OCR environment and everything else", uv_venv_calls() == venvs + 1 and m.web_ready() is True)

print("\n--- cancelling stops the running step and what it started")
got, outcome = [], {}


def slow():
    try:
        m.run_step(["bash", "-c", "echo started; sleep 30 & wait"], say=got.append)
        outcome["r"] = "finished"
    except m.Cancelled:
        outcome["r"] = "cancelled"


t = threading.Thread(target=slow)
t.start()
end = time.time() + 5
while "started" not in got and time.time() < end:
    time.sleep(0.05)
t0 = time.time()
m.cancel()
t.join(5)
check("the step ends at once as cancelled", outcome.get("r") == "cancelled" and time.time() - t0 < 3, f"{outcome} {time.time() - t0:.1f}s")
check("nothing is left running (the sleep it started is gone)", subprocess.run(["pgrep", "-f", "sleep 30"], capture_output=True).returncode != 0)
try:
    m.run_step(["echo", "hello"], say=got.append)
    check("after a cancel no further step starts", False)
except m.Cancelled:
    check("after a cancel no further step starts", True)
m.allow_steps()
m.run_step(["echo", "again"], say=got.append)
check("...until the next install is started", "again" in got)

print("\n--- SetupJob and the system packages: only as root, and a staged install needs a restart")
sp = sys.modules["armada_yomitan.syspackages"]
system_calls = []
m.install_components = lambda say=None, **kw: None


def run_job():
    done, outcome = threading.Event(), {}
    job = m.SetupJob(lambda t: None, lambda: (outcome.update(done=True), done.set()), lambda msg: (outcome.update(fail=msg), done.set()))
    job.start()
    done.wait(30)
    return job, outcome


sp.install = lambda on_line=None, **kw: (system_calls.append("install"), "staged")[1]
job, outcome = run_job()
check("not root: the job installs only the parts (no system packages, no password prompt, no sudo)", outcome == {"done": True} and system_calls == [] and job.reboot_needed is False, f"{outcome} {system_calls}")
real_geteuid = os.geteuid
os.geteuid = lambda: 0
job, outcome = run_job()
check("as root the system packages are installed after the parts, and staged packages mean a restart is needed",
      outcome == {"done": True} and system_calls == ["install"] and job.reboot_needed is True, f"{outcome} {system_calls}")
sp.install = lambda on_line=None, **kw: "nothing"
job, outcome = run_job()
check("as root with nothing to layer no restart is needed", outcome == {"done": True} and job.reboot_needed is False)


def failing_install(on_line=None, **kw):
    raise RuntimeError(strings.PKG_INSTALL_FAILED)


sp.install = failing_install
job, outcome = run_job()
check("as root a failing system install is reported like any other failure", outcome.get("fail") == strings.SETUP_FAILED.format(error=strings.PKG_INSTALL_FAILED), str(outcome))
os.geteuid = real_geteuid

print("\n--- --setup --no-system (what the Decky plugin runs as the user)")
recorded = []
m.cmd_install_deps = lambda **kw: recorded.append("system")
with contextlib.redirect_stdout(io.StringIO()):
    m.cmd_setup(yes=True, system=False)
check("--no-system installs the parts and leaves the system packages alone", recorded == [], str(recorded))
with contextlib.redirect_stdout(io.StringIO()):
    m.cmd_setup(yes=True)
check("--setup as before also installs the system packages", recorded == ["system"], str(recorded))

print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
