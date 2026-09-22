"""Tests for starting on the bottom screen."""

import json
import os
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


SRC = _extract.SRC
work = tempfile.mkdtemp(prefix="ay-launcher-")
home = f"{work}/home"
bindir = f"{work}/bin"
os.makedirs(bindir)
RECORD = f"{work}/call"
LOG = f"{home}/armada-yomitan.log"


def script(path, body):
    with open(path, "w") as f:
        f.write("#!/bin/bash\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


script(f"{bindir}/armada-run-bottom", '''for a in "$@"; do printf 'ARG %s\\n' "$a"; done > "$RECORD"
printf 'ENV ON_BOTTOM=%s\\nENV LD_LIBRARY_PATH=%s\\nENV PYTHONPATH=%s\\nENV PID=%s\\n' "${ARMADA_YOMITAN_ON_BOTTOM-}" "${LD_LIBRARY_PATH-}" "${PYTHONPATH-}" "$$" >> "$RECORD"
echo "hello from the wrapper" >&2
sleep "${STAY:-1.0}"''')

PROGRAM = f"import sys; sys.path.insert(0, {SRC!r}); from armada_yomitan.cli import main; main()"
MODULES = f"import sys; sys.path.insert(0, {SRC!r}); import armada_yomitan.launcher as L; "


def env(**more):
    e = {k: v for k, v in os.environ.items() if k not in ("ARMADA_YOMITAN_ON_BOTTOM", "PYTHONPATH", "LD_PRELOAD", "SYSTEM_LD_LIBRARY_PATH", "STAY")}
    e.update(ARMADA_YOMITAN_HOME=home, PATH=f"{bindir}:" + e["PATH"], RECORD=RECORD)
    e.update(more)
    return e


def reset():
    for path in (RECORD, LOG):
        if os.path.exists(path):
            os.remove(path)


def wait_for(path, seconds=8):
    end = time.time() + seconds
    while time.time() < end and not os.path.exists(path):
        time.sleep(0.05)
    return os.path.exists(path)


def recorded():
    if not wait_for(RECORD):
        return [], {}
    time.sleep(0.3)
    lines = open(RECORD).read().splitlines()
    return [l[4:] for l in lines if l.startswith("ARG ")], dict(l[4:].split("=", 1) for l in lines if l.startswith("ENV "))


def log_text():
    return open(LOG).read() if os.path.exists(LOG) else ""


print("--- no arguments: the program becomes armada-run-bottom, in place")
reset()
t0 = time.time()
launcher = subprocess.Popen([sys.executable, "-c", PROGRAM], env=env(STAY="1.0"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=work)
out, err = launcher.communicate(timeout=60)
took = time.time() - t0
args, environ = recorded()
check("armada-run-bottom is called, with `--`, a python -c bootstrap and this program's package root",
      args[:1] == ["--"] and args[2] == "-c" and args[4] == SRC, str(args) + err[-200:])
check("...and the arguments the Steam shortcut used to carry: --touch top_touchscreen --rotation 270",
      args[-4:] == ["--touch", "top_touchscreen", "--rotation", "270"], str(args))
check("the new process is marked as being on the bottom screen", environ.get("ON_BOTTOM") == "1", str(environ))
check("no PYTHONPATH is set for it", environ.get("PYTHONPATH") == "", str(environ))
check("it IS this process (same PID): the launcher was replaced, nothing is left running next to it",
      int(environ.get("PID", 0)) == launcher.pid, f"{environ.get('PID')} vs {launcher.pid}")
check("...so the launcher lasts exactly as long as the app (it runs 1 s) and ends with its status", launcher.returncode == 0 and took >= 1.0, f"exit {launcher.returncode} after {took:.2f}s")
check("the log says how it was started and what it did", "started with no arguments" in log_text() and "starting armada-run-bottom in place" in log_text(), log_text()[-300:])

print("\n--- ARMADA_YOMITAN_LAUNCH_ARGS replaces the arguments (the Decky plugin's settings), an empty value means none")
for label, value, want in (("its arguments, quoted as written", "--rotation 90 --touch 'my touch screen' --no-grab", ["--rotation", "90", "--touch", "my touch screen", "--no-grab"]),
                           ("an empty value: no arguments at all", "", []),
                           ("an invalid value falls back to the old default", "--touch 'oops", ["--touch", "top_touchscreen", "--rotation", "270"])):
    reset()
    launcher = subprocess.Popen([sys.executable, "-c", PROGRAM], env=env(STAY="0.2", ARMADA_YOMITAN_LAUNCH_ARGS=value), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=work)
    launcher.communicate(timeout=60)
    args, environ = recorded()
    check(f"{label}", args[args.index("-c") + 3:] == want, str(args))
check("...and the variable isn't passed on to the program", "ARMADA_YOMITAN_LAUNCH_ARGS" not in open(RECORD).read())
check("...the log says which arguments were used", "with arguments" in log_text(), log_text()[-200:])

print("\n--- when it must not relaunch")
reset()
r = subprocess.run([sys.executable, "-c", PROGRAM, "--check-deps", "--no-anki", "--no-vertical"], env=env(), capture_output=True, text=True, cwd=work)
check("any argument at all means \"run as asked\": armada-run-bottom is not called", not os.path.exists(RECORD) and "Checking armada-yomitan requirements" in r.stdout, r.stderr[-300:])
count_file = f"{work}/start-count"
probe = MODULES + f"calls = []; L.run_in_place = lambda *a: calls.append(a)\nL.maybe_start_on_bottom([])\nopen({count_file!r}, 'w').write(str(len(calls)))"


def start_count():
    if not os.path.exists(count_file):
        return ""
    with open(count_file) as f:
        value = f.read()
    os.remove(count_file)
    return value


reset()
r = subprocess.run([sys.executable, "-c", probe], env=env(ARMADA_YOMITAN_ON_BOTTOM="1"), capture_output=True, text=True, cwd=work)
check("already marked as on the bottom screen: not relaunched (no loop)", start_count() == "0", r.stdout + r.stderr[-300:])
check("...and the log (which didn't exist before) says how it was started and why it did nothing", "started with no arguments" in log_text() and "ARMADA_YOMITAN_ON_BOTTOM is set" in log_text(), log_text())
no_wrapper = f"{work}/no-wrapper-bin"
os.makedirs(no_wrapper)
reset()
r = subprocess.run([sys.executable, "-c", probe], env=env(PATH=no_wrapper + ":/usr/bin:/bin"), capture_output=True, text=True, cwd=work)
check("no armada-run-bottom on this machine: the program just runs where it is", start_count() == "0", r.stdout + r.stderr[-300:])
check("...and the log says armada-run-bottom wasn't found, and shows the PATH it looked in", "armada-run-bottom was not found on PATH" in log_text() and f"PATH={no_wrapper}" in log_text(), log_text())
r = subprocess.run([sys.executable, "-c", probe], env=env(), capture_output=True, text=True, cwd=work)
check("(sanity) with the wrapper on PATH and nothing else in the way, the same probe DOES start it", start_count() == "1", r.stdout + r.stderr[-300:])
probe_fail = MODULES + "L.run_in_place = lambda *a: (_ for _ in ()).throw(OSError('no such thing')); L.maybe_start_on_bottom([]); print('carried on')"
r = subprocess.run([sys.executable, "-c", probe_fail], env=env(), capture_output=True, text=True, cwd=work)
check("if it can't be started at all, the program says so and carries on running here (it doesn't vanish)", "carried on" in r.stdout and "couldn't start armada-run-bottom" in r.stderr, r.stdout + r.stderr[-300:])

print("\n--- someone already ran `armada-run-bottom -- armada-yomitan` by hand")
ancestor_probe = MODULES + "print(L.started_by_wrapper())"
os.makedirs(f"{work}/ancestor")
script(f"{work}/ancestor/armada-run-bottom", f'"{sys.executable}" -c "{ancestor_probe}"')
r = subprocess.run([f"{work}/ancestor/armada-run-bottom"], env=env(), capture_output=True, text=True, cwd=work)
check("armada-run-bottom as a parent process is recognised (so it is not wrapped a second time)", r.stdout.strip() == "True", r.stdout + r.stderr[-300:])
reset()
script(f"{work}/ancestor/armada-run-bottom", f'"{sys.executable}" -c "{probe}"')
r = subprocess.run([f"{work}/ancestor/armada-run-bottom"], env=env(), capture_output=True, text=True, cwd=work)
check("...and started that way, it does nothing and the log says so", start_count() == "0" and "one of my ancestor processes" in log_text(), r.stderr[-300:] + log_text())
r = subprocess.run([sys.executable, "-c", ancestor_probe], env=env(), capture_output=True, text=True, cwd=work)
check("started from anywhere else it is not", r.stdout.strip() == "False", r.stdout + r.stderr[-300:])

print("\n--- what Steam puts in the environment of a game")
r = subprocess.run([sys.executable, "-c", MODULES + "import json; print(json.dumps(L.without_steam_libraries({"
                    "'LD_LIBRARY_PATH': '/steam/runtime', 'SYSTEM_LD_LIBRARY_PATH': '/usr/lib64', "
                    "'LD_PRELOAD': '/a/gameoverlayrenderer.so:/b/keep.so /c/gameoverlayrenderer.so', 'HOME': '/h'})))"],
                   env=env(), capture_output=True, text=True)
cleaned = json.loads(r.stdout or "{}")
check("its runtime library path is replaced by the system's own, and the overlay is dropped from LD_PRELOAD (others kept)",
      cleaned.get("LD_LIBRARY_PATH") == "/usr/lib64" and cleaned.get("LD_PRELOAD") == "/b/keep.so" and cleaned.get("HOME") == "/h", r.stdout + r.stderr[-200:])
r = subprocess.run([sys.executable, "-c", MODULES + "import json; print(json.dumps(L.without_steam_libraries({'LD_LIBRARY_PATH': '/x', 'SYSTEM_LD_LIBRARY_PATH': '', "
                    "'LD_PRELOAD': '/a/gameoverlayrenderer.so'})))"], env=env(), capture_output=True, text=True)
cleaned = json.loads(r.stdout or "{}")
check("an empty original library path means none at all; an LD_PRELOAD with only the overlay is removed", "LD_LIBRARY_PATH" not in cleaned and "LD_PRELOAD" not in cleaned, r.stdout)
r = subprocess.run([sys.executable, "-c", MODULES + "import json; print(json.dumps(L.without_steam_libraries({'LD_LIBRARY_PATH': '/mine', 'HOME': '/h'})))"],
                   env=env(), capture_output=True, text=True)
check("outside Steam (no SYSTEM_LD_LIBRARY_PATH) nothing is touched", json.loads(r.stdout or "{}") == {"LD_LIBRARY_PATH": "/mine", "HOME": "/h"}, r.stdout)

print("\n--- no terminal (Steam): the output goes to a log file")
reset()
os.makedirs(home, exist_ok=True)
with open(LOG, "w") as f:
    f.write("x" * (600 * 1024))
launcher = subprocess.run([sys.executable, "-c", PROGRAM], env=env(STAY="0.5"), capture_output=True, text=True, cwd=work)      # pipes: not a terminal
check("what the app (and the wrapper) print lands in ~/.local/share/armada-yomitan/armada-yomitan.log", "hello from the wrapper" in log_text() and "started with no arguments" in log_text(), log_text()[-200:])
check("...not on the (invisible) console", "hello from the wrapper" not in launcher.stderr and "hello from the wrapper" not in launcher.stdout, launcher.stderr)
check("an oversized log is started afresh instead of growing for ever", len(log_text()) < 10 * 1024, str(len(log_text())))

print("\n--- the entry point leaves a trace when the program can't even load, or crashes")
reset()
ENTRY = f"import sys; sys.path.insert(0, {SRC!r}); "
r = subprocess.run([sys.executable, "-c", ENTRY + "sys.modules['armada_yomitan.cli'] = None; from armada_yomitan.entry import main; main()"],
                   env=env(), capture_output=True, text=True, cwd=work)
check("a program that fails to load: the traceback is in the log, and the failure still ends the process",
      r.returncode != 0 and "the program failed to load" in log_text() and "None in sys.modules" in log_text() and "Traceback" in log_text(), r.stderr[-300:] + log_text())
reset()
r = subprocess.run([sys.executable, "-c", ENTRY + "import types; m = types.ModuleType('armada_yomitan.cli'); m.main = lambda: 1 / 0; sys.modules['armada_yomitan.cli'] = m; "
                    "from armada_yomitan.entry import main; main()"], env=env(), capture_output=True, text=True, cwd=work)
check("a program that crashes: the traceback is in the log", r.returncode != 0 and "the program crashed" in log_text() and "ZeroDivisionError" in log_text(), r.stderr[-300:] + log_text())
reset()
r = subprocess.run([sys.executable, "-c", ENTRY + "import types; m = types.ModuleType('armada_yomitan.cli'); m.main = lambda: sys.exit(3); sys.modules['armada_yomitan.cli'] = m; "
                    "from armada_yomitan.entry import main; main()"], env=env(), capture_output=True, text=True, cwd=work)
check("a normal exit (even with a status) is not reported as a crash", r.returncode == 3 and "crashed" not in log_text(), log_text())
FAKE_CLI = "import types; m = types.ModuleType('armada_yomitan.cli'); m.main = lambda: %s; sys.modules['armada_yomitan.cli'] = m; "
for label, body, want in (("returns", "None", "the program exited normally"), ("exits with a status", "sys.exit(3)", "the program exited with status 3")):
    reset()
    subprocess.run([sys.executable, "-c", ENTRY + FAKE_CLI % body + "from armada_yomitan.entry import main; main()"], env=env(ARMADA_YOMITAN_ON_BOTTOM="1"),
                   capture_output=True, text=True, cwd=work)
    check(f"started on the bottom screen, a program that {label} says so in the log", want in log_text(), log_text())
reset()
subprocess.run([sys.executable, "-c", ENTRY + FAKE_CLI % "None" + "from armada_yomitan.entry import main; main()"], env=env(), capture_output=True, text=True, cwd=work)
check("...but a command run by hand writes nothing to the log", not os.path.exists(LOG), log_text())
reset()
r = subprocess.run([sys.executable, "-c", ENTRY + FAKE_CLI % "os.kill(os.getpid(), signal.SIGSEGV)" + "import os, signal; from armada_yomitan.entry import main; main()"],
                   env=env(ARMADA_YOMITAN_ON_BOTTOM="1"), capture_output=True, text=True, cwd=work)
check("a native crash (a segfault) leaves a Python traceback in stderr, which the launcher sends to the log",
      r.returncode != 0 and "Fatal Python error: Segmentation fault" in r.stderr and "line" in r.stderr, r.stderr[-300:])
reset()
r = subprocess.run([sys.executable, "-c", ENTRY + FAKE_CLI % "os.kill(os.getpid(), signal.SIGTERM)" + "import os, signal; from armada_yomitan.entry import main; main()"],
                   env=env(ARMADA_YOMITAN_ON_BOTTOM="1"), capture_output=True, text=True, cwd=work)
check("being killed by SIGTERM still ends the process, with a traceback showing where it was", r.returncode == -15 and "most recent call first" in r.stderr, f"{r.returncode} {r.stderr[-200:]}")
reset()
r = subprocess.run([sys.executable, "-c", ENTRY + "from armada_yomitan.logfile import note; note('a line')"], env=env(HOME="/nonexistent/x", ARMADA_YOMITAN_HOME="/proc/no/such/place"),
                   capture_output=True, text=True, cwd=work)
check("if the log can't even be written, nothing raises (the program still runs)", r.returncode == 0, r.stderr[-300:])

print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
