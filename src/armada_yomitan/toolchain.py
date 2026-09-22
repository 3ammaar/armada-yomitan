"""Downloads and setup steps."""

import os
import shlex
import shutil
import signal
import subprocess
import threading

from armada_yomitan import strings
from armada_yomitan.paths import HOME_DIR

UV_INSTALLER = "https://astral.sh/uv/install.sh"


class Cancelled(RuntimeError):
    pass


_current = {"proc": None, "cancelled": False}


def cancel():
    """Stop the running step (and what it started) and make every later step refuse to start."""
    _current["cancelled"] = True
    proc = _current["proc"]
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass


def allow_steps():
    _current["cancelled"] = False


def check_cancelled():
    if _current["cancelled"]:
        raise Cancelled("cancelled")


def report(say, text):
    if say is None:
        print(text, flush=True)
    else:
        say(text)


def run_step(cmd, env=None, say=None, **kw):
    report(say, "+ " + " ".join(shlex.quote(str(c)) for c in cmd))
    try:
        if say is None:
            subprocess.run(cmd, env=env, check=True, **kw)
        else:
            _run_streaming(cmd, env, say, kw.get("input"))
    except subprocess.CalledProcessError as e:
        raise RuntimeError(strings.SETUP_STEP_FAILED.format(code=e.returncode, command=" ".join(str(c) for c in cmd[:3])))


def _run_streaming(cmd, env, say, stdin_bytes=None):
    check_cancelled()
    proc = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE if stdin_bytes is not None else None,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
    _current["proc"] = proc
    if stdin_bytes is not None:
        def feed():
            try:
                proc.stdin.write(stdin_bytes.decode(errors="replace") if isinstance(stdin_bytes, bytes) else stdin_bytes)
                proc.stdin.close()
            except OSError:
                pass
        threading.Thread(target=feed, daemon=True).start()
    for line in proc.stdout:
        if line.strip():
            say(line.rstrip())
    proc.wait()
    _current["proc"] = None
    check_cancelled()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


def download(url, timeout=30):
    err = strings.SETUP_CURL_MISSING
    curl = shutil.which("curl")
    if curl:
        r = subprocess.run([curl, "-fsSL", "--max-time", str(timeout), url], capture_output=True)
        if r.returncode == 0 and r.stdout:
            return r.stdout
        err = r.stderr.decode(errors="replace").strip() or strings.SETUP_EXIT_CODE.format(code=r.returncode)
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; armada-yomitan)"})
    try:
        return urllib.request.urlopen(req, timeout=timeout).read()
    except OSError as e:
        raise RuntimeError(strings.SETUP_DOWNLOAD_FAILED.format(url=url, curl=err, urllib=e))


def ensure_uv(say=None):
    os.makedirs(HOME_DIR, exist_ok=True)
    uv = shutil.which("uv") or os.path.join(HOME_DIR, "bin", "uv")
    if not os.path.exists(uv):
        report(say, strings.SETUP_DOWNLOADING_UV.format(url=UV_INSTALLER))
        script = download(UV_INSTALLER)
        env = dict(os.environ, UV_UNMANAGED_INSTALL=os.path.join(HOME_DIR, "bin"), UV_NO_MODIFY_PATH="1")
        run_step(["sh"], env=env, say=say, input=script)
    if not os.path.exists(uv):
        raise RuntimeError(strings.SETUP_UV_NOT_FOUND.format(path=uv))
    return uv
