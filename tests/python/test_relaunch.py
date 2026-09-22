"""Tests for the program re-running itself."""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract

sys.path.insert(0, os.path.join(_extract.ROOT, "tools"))
import build_all

FAILED = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{extra}]" if extra and not ok else ""))
    if not ok:
        FAILED.append(label)


SRC = _extract.SRC
work = tempfile.mkdtemp(prefix="armada-yomitan-relaunch-")
home = f"{work}/home"
log = f"{work}/venv-python.log"
decoy = f"{work}/decoy-cwd"
os.makedirs(decoy)
open(f"{decoy}/armada_yomitan.py", "w").write("raise SystemExit('the decoy armada_yomitan.py in the working directory was imported')\n")

subprocess.run([sys.executable, "-m", "venv", "--without-pip", f"{home}/venv"], check=True)
vbin = f"{home}/venv/bin"
os.rename(f"{vbin}/python", f"{vbin}/python.real")
with open(f"{vbin}/python", "w") as f:
    f.write('#!/bin/sh\nprintf "PYTHONPATH=%s\\nARGV:" >> "$LOGFILE"; printf " [%s]" "$@" >> "$LOGFILE"; echo >> "$LOGFILE"\n'
            'exec "$(dirname "$0")/python.real" "$@"\n')
os.chmod(f"{vbin}/python", 0o755)


def env(**more):
    e = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "ARMADA_YOMITAN_NO_VENV", "DISPLAY", "WAYLAND_DISPLAY")}
    e.update(ARMADA_YOMITAN_HOME=home, LOGFILE=log, **more)
    return e


def launch(args, e=None, cwd=decoy):
    code = f"import sys; sys.path.insert(0, {SRC!r}); from armada_yomitan.cli import main; main()"
    return subprocess.run([sys.executable, "-c", code] + args, env=e or env(), cwd=cwd, capture_output=True, text=True)


def started():
    return open(log).read().splitlines() if os.path.exists(log) else []


print("--- into the OCR environment (a real venv)")
direct = launch(["--list"], env(ARMADA_YOMITAN_NO_VENV="1"))
check("ARMADA_YOMITAN_NO_VENV=1: it runs where it is and the venv python is not used", direct.returncode == 0 and started() == [], direct.stderr[-300:])
r = launch(["--list"])
lines = started()
check("started normally, it is re-run by the venv's python, exactly once", r.returncode == 0 and len(lines) == 2, r.stderr[-300:] + str(lines))
check("...with the -c bootstrap, the package root and the original arguments",
      len(lines) == 2 and lines[1].startswith("ARGV: [-c] [") and lines[1].endswith(f"[{SRC}] [--list]"), str(lines))
check("...and no PYTHONPATH was added for the new process", len(lines) == 2 and lines[0] == "PYTHONPATH=", str(lines))
check("it did the same work as the direct run", r.stdout == direct.stdout and r.stdout.startswith("Input devices"))
check("the decoy armada_yomitan.py in the working directory was never imported", "decoy" not in r.stdout + r.stderr)
os.remove(log)
r = launch(["--setup", "--help"])
check("--setup is never re-run in the venv (it is what builds it)", "usage:" in r.stdout and started() == [], r.stderr[-300:])
check("--help names the program armada-yomitan", r.stdout.startswith("usage: armada-yomitan "))

print("\n--- base_python: the interpreter a venv was made from (so an install never builds on the venv it is replacing)")
code = f"import sys; sys.path.insert(0, {SRC!r}); from armada_yomitan.relaunch import base_python; print(base_python())"
outside = subprocess.run([sys.executable, "-c", code], env=env(), capture_output=True, text=True).stdout.strip()
inside = subprocess.run([f"{vbin}/python.real", "-c", code], env=env(), capture_output=True, text=True).stdout.strip()
check("outside a venv it is the running interpreter", outside == sys.executable, outside)
check("inside the venv it is the interpreter the venv was made from, not the venv's own python",
      inside != f"{vbin}/python.real" and not inside.startswith(home) and os.path.exists(inside), inside)

print("\n--- the single-file build (zipapp)")
pyz = build_all.build_executable(f"{work}/armada-yomitan")
if os.path.exists(log):
    os.remove(log)
r = subprocess.run([sys.executable, str(pyz), "--list"], env=env(), cwd=decoy, capture_output=True, text=True)
lines = started()
check("the single file runs, is re-run by the venv's python and does the same work",
      r.returncode == 0 and r.stdout == direct.stdout and len(lines) == 2 and lines[1].endswith(f"[{pyz}] [--list]"), r.stderr[-300:] + str(lines))
hint = subprocess.run([sys.executable, "-c", f"import sys; sys.path.append({str(pyz)!r}); from armada_yomitan.relaunch import program_hint; print(program_hint())"],
                      capture_output=True, text=True, cwd=work).stdout.strip()
check("its 'how to run me' hint is the file itself", hint == f"python3 {pyz}", hint)
hint = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {SRC!r}); from armada_yomitan.relaunch import program_hint; print(program_hint())"],
                      capture_output=True, text=True, cwd=work).stdout.strip()
check("from a checkout the hint puts src on PYTHONPATH", hint == f"env PYTHONPATH={SRC} python3 -m armada_yomitan", hint)

print("\n--- --yomitan-settings over SSH (no screen): re-run on the bottom screen")
os.makedirs(f"{home}/yomitan", exist_ok=True)
open(f"{home}/yomitan/manifest.json", "w").write("{}")
os.makedirs(f"{work}/bin")
recorded = f"{work}/armada-args.txt"
with open(f"{work}/bin/armada-run-bottom", "w") as f:
    f.write(f'#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done > "{recorded}"\n')
os.chmod(f"{work}/bin/armada-run-bottom", 0o755)
e = env(ARMADA_YOMITAN_BROWSER="/bin/true", PATH=f"{work}/bin:" + os.environ["PATH"])
r = launch(["--yomitan-settings"], e)
argv = open(recorded).read().splitlines() if os.path.exists(recorded) else []
check("it hands the bottom-screen wrapper a command that runs this program (under the OCR environment's python)", argv[:1] == ["--"] and argv[1].startswith(f"{home}/venv/bin/python") and argv[2] == "-c" and argv[-2:] == [SRC, "--yomitan-settings"],
      r.stderr[-300:] + str(argv))
again = subprocess.run(argv[1:-1] + ["--list"], env=env(), cwd=decoy, capture_output=True, text=True)
check("...and that command really starts the program (run here with --list instead)", again.returncode == 0 and again.stdout == direct.stdout, again.stderr[-300:])

print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
