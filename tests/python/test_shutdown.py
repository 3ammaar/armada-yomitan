"""Tests for SIGTERM shutdown."""

import os
import signal
import stat
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


work = tempfile.mkdtemp(prefix="ay-shutdown-")
home = f"{work}/home"
os.makedirs(f"{home}/yomitan")
open(f"{home}/yomitan/manifest.json", "w").write("{}")
pidfile = f"{work}/browser.pid"
browser = f"{work}/fake-chromium"
with open(browser, "w") as f:
    f.write(f'#!/bin/bash\necho $$ > "{pidfile}"\nexec sleep 300\n')
os.chmod(browser, os.stat(browser).st_mode | stat.S_IEXEC)
env = dict(os.environ, ARMADA_YOMITAN_HOME=home, ARMADA_YOMITAN_BROWSER=browser)
env.pop("ARMADA_YOMITAN_ON_BOTTOM", None)
PROGRAM = f"import sys; sys.path.insert(0, {_extract.SRC!r}); from armada_yomitan.cli import main; main()"


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    with open(f"/proc/{pid}/stat") as f:
        return f.read().rsplit(")", 1)[1].split()[0] != "Z"


def start():
    if os.path.exists(pidfile):
        os.remove(pidfile)
    # output to a file, not a pipe: a browser that outlives a killed app would hold a pipe open and hang the test instead of failing it
    proc = subprocess.Popen([sys.executable, "-c", PROGRAM, "--ui", "web", "--touch", "x"], env=env, stdout=open(f"{work}/out.txt", "w"), stderr=subprocess.STDOUT)
    end = time.time() + 20
    while time.time() < end and not os.path.exists(pidfile):
        time.sleep(0.1)
    time.sleep(0.5)
    return proc, int(open(pidfile).read()) if os.path.exists(pidfile) else 0


proc, browser_pid = start()
check("the app starts its browser", browser_pid > 0 and alive(browser_pid), proc.poll())
proc.send_signal(signal.SIGTERM)
try:
    proc.wait(timeout=20)
    err = ""
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()
    err = " [it did not end within 20 s]"
err = open(f"{work}/out.txt").read()[-300:] + err
time.sleep(0.5)
check("SIGTERM ends the app with a normal exit (status 0), not by being killed by the signal", proc.returncode == 0, f"{proc.returncode} {err[-300:]}")
check("...and the browser it started is closed too, not left behind", browser_pid > 0 and not alive(browser_pid), browser_pid)
if browser_pid and alive(browser_pid):
    os.kill(browser_pid, 9)

print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
