"""Decky Loader plugin backend."""

import asyncio
import glob
import grp
import importlib.util
import json
import logging
import os
import pwd
import re
import shlex
import shutil
import signal
import subprocess
import threading

import decky


def load_strings():
    spec = importlib.util.spec_from_file_location("armada_yomitan_strings", os.path.join(decky.DECKY_PLUGIN_DIR, "strings.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


strings = load_strings()

APP_MARKER = "from armada_yomitan.entry import main"    # in the `python -c` bootstrap the app runs under: how its process is recognised
WRAPPER = "armada-run-bottom"
PYTHON = "/usr/bin/python3"                              # the system Python: Decky's own (bundled) one must not run the app
STANDARD_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
# an allowlist: Decky's and Steam's environment must not reach the app
SESSION_VARIABLES = ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE", "XDG_SESSION_ID", "XDG_SEAT",
                     "XDG_VTNR", "XDG_CURRENT_DESKTOP", "XDG_DATA_DIRS", "XDG_CONFIG_DIRS", "DBUS_SESSION_BUS_ADDRESS", "LANG", "LC_ALL")
LEFTOVER_MARKERS = (".local/share/armada-yomitan/browser-profile", ".local/share/armada-yomitan/anki/venv")
SETTLE = 2.0
TERM_WAIT = 40.0
KILL_WAIT = 5.0

log = logging.getLogger("armada-yomitan-plugin")

# (key, flag, kind, choices, default)
OPTIONS = (
    ("rotation", "--rotation", "choice", ("0", "90", "180", "270"), "270"),
    ("touch", "--touch", "text", (), "top_touchscreen"),
    ("node", "--node", "number", (), ""),
    ("mode", "--mode", "choice", ("screen", "tap", "manual"), ""),
    ("engine", "--engine", "choice", ("auto", "rapidocr", "tesseract"), ""),
    ("scan_length", "--scan-length", "number", (), ""),
    ("ui_scale", "--ui-scale", "decimal", (), ""),
    ("no_grab", "--no-grab", "toggle", (), False),
)
LAUNCH_ARGS_ENV = "ARMADA_YOMITAN_LAUNCH_ARGS"
VIA_DECKY_ENV = "ARMADA_YOMITAN_VIA_DECKY"                # tells the app it was started from here


def default_settings():
    return {key: default for key, _flag, _kind, _choices, default in OPTIONS}


def clean_value(kind, choices, value):
    if kind == "toggle":
        return value is True
    text = str(value if value is not None else "").strip()
    if kind == "choice":
        return text if text in choices else ""
    if kind == "text":
        return re.sub(r"[\x00-\x1f\x7f]", "", text).lstrip("-")[:100]          # never something argparse would take for a flag
    if kind == "number":
        return text if re.fullmatch(r"\d{1,9}", text) else ""
    if kind == "decimal":
        return text if re.fullmatch(r"\d{1,2}(\.\d{1,3})?", text) and 0 < float(text) <= 10 else ""
    return ""


def clean_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    return {key: clean_value(kind, choices, raw[key]) if key in raw else default
            for key, _flag, kind, choices, default in OPTIONS}


def settings_file():
    return os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")


def load_settings():
    try:
        with open(settings_file(), encoding="utf-8") as f:
            return clean_settings(json.load(f))
    except (OSError, ValueError):
        return default_settings()


def save_settings(values):
    values = clean_settings(values)
    os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
    with open(settings_file(), "w", encoding="utf-8") as f:
        json.dump(values, f, indent=1)
    return values


def settings_answer(values):
    return {"values": values,
            "options": [{"key": key, "kind": kind, "choices": list(choices)} for key, _flag, kind, choices, _default in OPTIONS]}


def launch_arguments(values):
    args = []
    for key, flag, kind, _choices, _default in OPTIONS:
        value = values.get(key)
        if kind == "toggle":
            if value:
                args.append(flag)
        elif value not in ("", None):
            args += [flag, str(value)]
    return args


def result(ok, message):
    return {"ok": ok, "message": message}


def read_processes():
    procs = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            with open(f"/proc/{pid}/stat") as f:
                stat = f.read()
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                raw = f.read()
        except OSError:
            continue
        procs[pid] = (int(stat.rsplit(")", 1)[1].split()[1]), [a.decode(errors="replace") for a in raw.split(b"\0") if a])
    return procs


def alive(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] not in ("Z", "X")
    except OSError:
        return False


def descendants(root, procs):
    children = {}
    for pid, (ppid, _) in procs.items():
        children.setdefault(ppid, []).append(pid)
    found, todo = set(), [root]
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in found:
                found.add(child)
                todo.append(child)
    return found


def is_app(args):
    return any(APP_MARKER in a for a in args)


def is_wrapper(args):
    return any(os.path.basename(a) == WRAPPER for a in args[:2])          # "armada-run-bottom ..." or "bash armada-run-bottom ..."


def find_instance(procs):
    me = os.getpid()
    apps = {pid for pid, (_, args) in procs.items() if pid != me and is_app(args)}
    tree = set()
    for app in apps:
        root, pid = app, app
        while pid in procs and procs[pid][0] in procs and procs[pid][0] > 1:
            pid = procs[pid][0]
            if is_wrapper(procs[pid][1]):
                root = pid
        tree |= {root} | descendants(root, procs)
    return apps, tree


def leftovers(procs, exclude):
    me = os.getpid()
    return {pid for pid, (_, args) in procs.items()
            if pid != me and pid not in exclude and any(m in a for a in args for m in LEFTOVER_MARKERS)}


def session_environment(procs, home, user):
    uid = pwd.getpwnam(user).pw_uid
    env = {"HOME": home, "USER": user, "LOGNAME": user, "PATH": f"{STANDARD_PATH}:{home}/.local/bin",
           "XDG_RUNTIME_DIR": f"/run/user/{uid}"}
    for pid in sorted(procs, reverse=True):
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip() != "steam" or os.stat(f"/proc/{pid}").st_uid != uid:
                    continue
            with open(f"/proc/{pid}/environ", "rb") as f:
                theirs = dict(item.split(b"=", 1) for item in f.read().split(b"\0") if b"=" in item)
        except OSError:
            continue
        for key in SESSION_VARIABLES:
            if key.encode() in theirs:
                env[key] = theirs[key.encode()].decode(errors="replace")
        break
    bus = f"/run/user/{uid}/bus"
    if "DBUS_SESSION_BUS_ADDRESS" not in env and os.path.exists(bus):
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"
    return env


def spawn_options(user):
    if os.geteuid() != 0:
        return {}
    pw = pwd.getpwnam(user)
    return {"user": pw.pw_uid, "group": pw.pw_gid, "extra_groups": os.getgrouplist(user, pw.pw_gid)}


def describe_access(user):
    pw = pwd.getpwnam(user)
    names = []
    for gid in os.getgrouplist(user, pw.pw_gid):
        try:
            names.append(grp.getgrgid(gid).gr_name)
        except KeyError:
            names.append(str(gid))
    owners = set()
    for device in glob.glob("/dev/input/event*"):
        try:
            owners.add(grp.getgrgid(os.stat(device).st_gid).gr_name)
        except (OSError, KeyError):
            pass
    text = (f"the plugin runs as uid {os.geteuid()}; the app runs as {user} (uid {pw.pw_uid}) with groups {sorted(names)}; "
            f"/dev/input devices belong to group(s) {sorted(owners) or '?'}")
    if os.geteuid() != 0 and set(os.getgrouplist(user, pw.pw_gid)) - set(os.getgroups()):
        text += " -- WARNING: the plugin is not root, so the app lacks groups the user has (touchscreen access will fail); plugin.json needs the root flag"
    return text


def find_executable():
    bundled = os.path.join(decky.DECKY_PLUGIN_DIR, "bin", "armada-yomitan")
    if os.path.isfile(bundled):
        return bundled
    return shutil.which("armada-yomitan", path=f"{STANDARD_PATH}:{decky.DECKY_USER_HOME}/.local/bin")


INSTALL = {"running": False, "done": False, "ok": None, "line": "", "message": ""}
INSTALL_TASKS = set()


def user_environment(procs):
    return session_environment(procs, decky.DECKY_USER_HOME, decky.DECKY_USER)


async def run_streamed(argv, env, user=None):
    """Run a command, keep its latest output line in INSTALL and all of it in the install log; returns the exit status."""
    proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.STDOUT, env=env, **(spawn_options(user) if user else {}))
    with open(os.path.join(decky.DECKY_PLUGIN_LOG_DIR, "install-output.log"), "ab") as out:
        async for raw in proc.stdout:
            for line in raw.decode(errors="replace").replace("\r", "\n").splitlines():
                if line.strip():
                    INSTALL["line"] = line.strip()[:160]
                    out.write((line.rstrip() + "\n").encode())
                    out.flush()
    return await proc.wait()


async def read_dependencies(exe, env):
    proc = await asyncio.create_subprocess_exec(PYTHON, exe, "--list-deps", stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE, env=env, **spawn_options(decky.DECKY_USER))
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError((err or out).decode(errors="replace").strip()[-200:])
    return json.loads(out.decode())["packages"]


async def install_dependencies_job(exe):
    INSTALL.update(running=True, done=False, ok=None, line="", message="")
    try:
        env = user_environment(read_processes())
        missing = any(not package["present"] for package in await read_dependencies(exe, env))
        if await run_streamed([PYTHON, exe, "--install-deps", "-y"], {"PATH": STANDARD_PATH, "HOME": "/root"}) != 0:
            raise RuntimeError(INSTALL["line"])
        if await run_streamed([PYTHON, exe, "--setup", "--no-system"], env, decky.DECKY_USER) != 0:
            raise RuntimeError(INSTALL["line"])
        INSTALL.update(ok=True, message=strings.DECKY_INSTALL_DONE_REBOOT if missing else strings.DECKY_INSTALL_DONE)
    except Exception as e:
        log.exception("installing the dependencies failed")
        INSTALL.update(ok=False, message=strings.DECKY_INSTALL_FAILED.format(error=e))
    finally:
        INSTALL.update(running=False, done=True)


async def start_install():
    if INSTALL["running"]:
        return result(False, strings.DECKY_INSTALL_BUSY)
    if find_instance(read_processes())[1]:
        return result(False, strings.DECKY_INSTALL_STOP_FIRST)
    exe = find_executable()
    if not exe:
        return result(False, strings.DECKY_NOT_BUNDLED)
    task = asyncio.get_running_loop().create_task(install_dependencies_job(exe))
    INSTALL_TASKS.add(task)
    task.add_done_callback(INSTALL_TASKS.discard)
    INSTALL["running"] = True
    return result(True, strings.DECKY_INSTALL_STARTED)


async def launch_app():
    procs = read_processes()
    if INSTALL["running"]:
        return result(False, strings.DECKY_LAUNCH_INSTALLING)
    if find_instance(procs)[1]:
        return result(False, strings.DECKY_ALREADY_RUNNING)
    exe = find_executable()
    if not exe:
        return result(False, strings.DECKY_NOT_BUNDLED)
    user, home = decky.DECKY_USER, decky.DECKY_USER_HOME                    # the real user, whatever this backend runs as
    env = session_environment(procs, home, user)
    args = launch_arguments(load_settings())
    env[LAUNCH_ARGS_ENV] = shlex.join(args)
    env[VIA_DECKY_ENV] = "1"
    output = os.path.join(decky.DECKY_PLUGIN_LOG_DIR, "app-output.log")
    log.info(describe_access(user))
    log.info("launch arguments: %s", args)
    with open(output, "ab") as out:
        proc = subprocess.Popen([PYTHON, exe], env=env, cwd=home, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True, **spawn_options(user))
    threading.Thread(target=proc.wait, daemon=True).start()                 # reaps it when it ends: no zombie left in Decky
    log.info("started %s %s (pid %s)", PYTHON, exe, proc.pid)
    await asyncio.sleep(SETTLE)
    code = proc.poll()
    if code is not None:
        return result(False, strings.DECKY_STOPPED_AT_ONCE.format(code=code, output=output))
    return result(True, strings.DECKY_STARTING)


def send(pids, sig):
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


async def wait_gone(pids, seconds):
    end = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < end:
        if not any(alive(pid) for pid in pids):
            return True
        await asyncio.sleep(0.2)
    return not any(alive(pid) for pid in pids)


async def stop_app():
    procs = read_processes()
    apps, tree = find_instance(procs)
    strays = leftovers(procs, tree)
    if not tree and not strays:
        return result(False, strings.DECKY_NOT_RUNNING)
    log.info("stopping: app %s, tree %s, leftovers %s", sorted(apps), sorted(tree), sorted(strays))
    send(apps, signal.SIGTERM)
    if not await wait_gone(tree, TERM_WAIT):
        send([p for p in tree if alive(p)], signal.SIGTERM)
        if not await wait_gone(tree, KILL_WAIT):
            send([p for p in tree if alive(p)], signal.SIGKILL)
            await wait_gone(tree, KILL_WAIT)
    procs = read_processes()
    strays = leftovers(procs, set())
    if strays:
        send(strays, signal.SIGTERM)
        if not await wait_gone(strays, KILL_WAIT):
            send([p for p in strays if alive(p)], signal.SIGKILL)
            await wait_gone(strays, KILL_WAIT)
    left = [p for p in tree | strays if alive(p)]
    if left:
        return result(False, strings.DECKY_COULD_NOT_STOP_ALL.format(pids=sorted(left)))
    return result(True, strings.DECKY_STOPPED)


class Plugin:
    async def launch(self):
        try:
            return await launch_app()
        except Exception as e:                                             # a failure must reach the panel, not vanish in Decky's log
            decky.logger.exception("launch failed")
            return result(False, strings.DECKY_LAUNCH_FAILED.format(error=e))

    async def get_dependencies(self):
        exe = find_executable()
        if not exe:
            return {"ok": False, "message": strings.DECKY_NOT_BUNDLED, "packages": []}
        try:
            return {"ok": True, "message": "", "packages": await read_dependencies(exe, user_environment(read_processes()))}
        except Exception as e:
            decky.logger.exception("reading the dependency list failed")
            return {"ok": False, "message": strings.DECKY_DEPENDENCIES_UNREADABLE.format(error=e), "packages": []}

    async def install_dependencies(self):
        try:
            return await start_install()
        except Exception as e:
            decky.logger.exception("starting the install failed")
            return result(False, strings.DECKY_INSTALL_FAILED.format(error=e))

    async def install_status(self):
        return dict(INSTALL)

    async def get_settings(self):
        return settings_answer(load_settings())

    async def set_settings(self, values):
        return settings_answer(save_settings(values))

    async def reset_settings(self):
        return settings_answer(save_settings(default_settings()))

    async def stop(self):
        try:
            return await stop_app()
        except Exception as e:
            decky.logger.exception("stop failed")
            return result(False, strings.DECKY_STOP_FAILED.format(error=e))

    async def _main(self):
        log.addHandler(logging.NullHandler())
        for handler in decky.logger.handlers:
            log.addHandler(handler)
        log.setLevel(logging.INFO)
        decky.logger.info("armada-yomitan plugin loaded")

    async def _unload(self):
        decky.logger.info("armada-yomitan plugin unloaded (a running app is left running)")

    async def _uninstall(self):
        decky.logger.info("armada-yomitan plugin uninstalled")
