"""Starting on the bottom screen."""

import os
import shlex
import shutil
import sys

from armada_yomitan.capture import ancestor_pids
from armada_yomitan.logfile import note, open_append
from armada_yomitan.relaunch import program_command

WRAPPER = "armada-run-bottom"
LAUNCH_ARGS = ["--touch", "top_touchscreen", "--rotation", "270"]
ON_BOTTOM = "ARMADA_YOMITAN_ON_BOTTOM"
LAUNCH_ARGS_ENV = "ARMADA_YOMITAN_LAUNCH_ARGS"


def launch_args(env):
    text = env.get(LAUNCH_ARGS_ENV)
    if text is None:
        return list(LAUNCH_ARGS)
    try:
        return shlex.split(text)
    except ValueError as e:
        note(f"{LAUNCH_ARGS_ENV} isn't valid ({e}); using the default arguments")
        return list(LAUNCH_ARGS)


def started_by_wrapper():
    for pid in ancestor_pids() - {os.getpid()}:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                args = f.read().split(b"\0")
        except OSError:
            continue
        if any(os.path.basename(a.decode(errors="replace")) == WRAPPER for a in args[:2]):     # "wrapper ..." or "bash wrapper ..."
            return True
    return False


def without_steam_libraries(env):
    env = dict(env)
    if "SYSTEM_LD_LIBRARY_PATH" in env:
        if env["SYSTEM_LD_LIBRARY_PATH"]:
            env["LD_LIBRARY_PATH"] = env["SYSTEM_LD_LIBRARY_PATH"]
        else:
            env.pop("LD_LIBRARY_PATH", None)
    preload = [p for p in env.get("LD_PRELOAD", "").replace(":", " ").split() if "gameoverlayrenderer" not in p]
    if preload:
        env["LD_PRELOAD"] = " ".join(preload)
    else:
        env.pop("LD_PRELOAD", None)
    return env


def open_log():
    if os.isatty(1) or os.isatty(2):
        return None
    return open_append()


def run_in_place(argv, env, log):
    """Replaces this process; returns only on failure."""
    if log is not None:
        os.dup2(log, 1)
        os.dup2(log, 2)
    os.execve(argv[0], argv, env)


def describe_start():
    keys = ("SteamGameId", "SteamAppId", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "HOME")
    ttys = "".join("T" if os.isatty(fd) else "-" for fd in (0, 1, 2))
    return (f"started with no arguments: python {sys.version.split()[0]} ({sys.executable}), program {sys.argv[0]!r}, cwd {os.getcwd()!r}, "
            f"stdin/out/err terminals [{ttys}], " + ", ".join(f"{k}={os.environ.get(k, '-')}" for k in keys)
            + f", PATH={os.environ.get('PATH', '-')}")


def maybe_start_on_bottom(args):
    if args:
        return
    note(describe_start())
    if os.environ.get(ON_BOTTOM):
        note(f"{ON_BOTTOM} is set (already on the bottom screen): running here")
        return
    wrapper = shutil.which(WRAPPER)
    if not wrapper:
        note(f"{WRAPPER} was not found on PATH: running on THIS screen instead of the bottom one")
        return
    if started_by_wrapper():
        note(f"{WRAPPER} is one of my ancestor processes (already on the bottom screen): running here")
        return
    env = without_steam_libraries(os.environ)
    env[ON_BOTTOM] = "1"
    args = launch_args(env)
    env.pop(LAUNCH_ARGS_ENV, None)
    log = open_log()
    note(f"starting {WRAPPER} in place of this process, with arguments {args}")
    try:
        run_in_place([wrapper, "--"] + program_command() + args, env, log)
    except OSError as e:
        note(f"couldn't start {WRAPPER}: {e}; running here instead")
        print(f"(couldn't start {WRAPPER}: {e}; running here instead)", file=sys.stderr)
    finally:
        if log is not None:
            os.close(log)
