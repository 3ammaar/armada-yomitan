"""Anki commands of the web interface."""

import os
import subprocess
import threading
import time

from armada_yomitan import strings
from armada_yomitan.anki.discovery import anki_installed_by_app, anki_launcher_in, anki_ready, find_anki_installs
from armada_yomitan.anki.install import install_anki, qt_missing_libs, stop_group
from armada_yomitan.anki.runtime import anki_env, anki_send, prepare_anki
from armada_yomitan.browser import start_browser
from armada_yomitan.console import log_error, looks_like_error
from armada_yomitan.paths import ANKI_VENV
from armada_yomitan.prefs import save_prefs
from armada_yomitan.syslibs import lib_fix, parse_missing_libs


class AnkiControls:
    def _anki_msg(self, status=None, log=True, **more):
        msg = {"type": "anki", "found": [f["label"] for f in self.anki_found], "busy": self._anki_busy}
        if status is not None:
            if log and looks_like_error(status):
                log_error(status)
            msg["status"] = status
        msg.update(more)
        return msg

    def _anki_running(self):
        return self.anki_proc is not None and self.anki_proc.poll() is None

    def cmd_anki(self):
        if not self.prefs["anki_button"]:
            return
        if self._anki_running() or anki_send("ping", 1.0) == "ok":
            self._bring_anki_forward()
        elif anki_ready(self.prefs):
            self._launch_anki()
        else:
            self.cmd_anki_detect()

    def _bring_anki_forward(self):
        if anki_send("show") == "ok":
            self.on_status(strings.ANKI_IN_FRONT)
            if not self._anki_watching:
                self._anki_watching = True
                threading.Thread(target=self._watch_anki_front, daemon=True).start()
        else:
            self.on_status(strings.ANKI_NOT_ANSWERING)

    def _watch_anki_front(self):
        try:
            while anki_send("visible", 1.0) == "yes":
                time.sleep(1)
        finally:
            self._anki_watching = False
        if self.last_status == strings.ANKI_IN_FRONT:
            self.on_status(strings.READY)

    def _stop_anki(self):
        proc = self.anki_proc
        if proc is None or proc.poll() is not None:
            return
        self._anki_quitting = True
        if anki_send("quit") == "ok":
            try:
                proc.wait(timeout=20)
                return
            except subprocess.TimeoutExpired:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def cmd_anki_detect(self):
        self.anki_found = find_anki_installs()
        self.broadcast(self._anki_msg(strings.ANKI_PICK_OR_INSTALL if self.anki_found else strings.ANKI_NOT_FOUND))

    def _set_anki(self, cmd, label):
        self.prefs["anki_cmd"], self.prefs["anki_label"] = list(cmd), label[:60]
        save_prefs(self.prefs)
        self.broadcast(self._prefs_msg())
        self.broadcast(self._anki_msg(strings.ANKI_SET_UP.format(label=label), busy=False, done=True))
        self.on_status(strings.ANKI_SET_UP_TAP.format(label=label))

    def cmd_anki_use(self, index):
        try:
            item = self.anki_found[int(index)]
        except (ValueError, IndexError):
            return
        self._set_anki(item["cmd"], item["label"].replace(strings.ANKI_FOUND_IN_PREFIX, "").replace(strings.ANKI_FOUND_ON_SYSTEM, strings.ANKI_SHORT_SYSTEM))

    def cmd_anki_pick(self, path):
        cmd = anki_launcher_in(path) if path else None
        if not cmd:
            self.broadcast(self._anki_msg(strings.ANKI_NOT_ANKI))
            return
        self._set_anki(cmd, cmd[0].replace(os.path.expanduser("~"), "~", 1))

    def _set_install_proc(self, proc):
        self._anki_install = proc
        if self._anki_cancelled:
            stop_group(proc)

    def cmd_anki_cancel(self):
        self._anki_cancelled = True
        if self._anki_install and self._anki_install.poll() is None:
            stop_group(self._anki_install)

    def cmd_anki_install(self):
        with self._lock:
            if self._anki_busy:
                return
            self._anki_busy, self._anki_cancelled = True, False
        try:
            self.broadcast(self._anki_msg(strings.ANKI_STARTING_INSTALL))
            cmd, missing = install_anki(lambda text: self.broadcast(self._anki_msg(text)), self._set_install_proc)
            self._anki_busy = False
            self._set_anki(cmd, strings.ANKI_INSTALLED_BY_APP)
            if missing:
                short, lines = lib_fix(missing)
                log_error("Anki is installed but can't run yet: " + short, lines)
                self.on_status(strings.ANKI_INSTALLED_NEEDS_LIBS.format(libraries=short), log=False)
        except Exception as e:
            self._anki_busy = False
            if self._anki_cancelled:
                self.broadcast(self._anki_msg(strings.ANKI_INSTALL_CANCELLED))
            else:
                log_error(f"Anki install failed: {e}", getattr(e, "tail", []))
                self.broadcast(self._anki_msg(strings.ANKI_INSTALL_FAILED.format(error=e), log=False))
        finally:
            self._anki_busy = False

    def cmd_anki_reinstall(self):
        if not anki_installed_by_app(self.prefs["anki_cmd"]):
            return
        with self._lock:
            if self._anki_busy:
                return
            self._anki_busy, self._anki_cancelled = True, False
        self._stop_anki()
        try:
            self.broadcast(self._anki_msg(strings.ANKI_REINSTALLING))
            cmd, missing = install_anki(lambda text: self.broadcast(self._anki_msg(text)), self._set_install_proc)
            self._anki_busy = False
            self.prefs["anki_cmd"], self.prefs["anki_label"] = list(cmd), strings.ANKI_INSTALLED_BY_APP[:60]
            save_prefs(self.prefs)
            self.broadcast(self._prefs_msg())
            self.broadcast(self._anki_msg(strings.ANKI_REINSTALLED, busy=False, done=True))
            if missing:
                short, lines = lib_fix(missing)
                log_error("Anki is installed but can't run yet: " + short, lines)
                self.on_status(strings.ANKI_INSTALLED_NEEDS_LIBS.format(libraries=short), log=False)
        except Exception as e:
            self._anki_busy = False
            if self._anki_cancelled:
                self.broadcast(self._anki_msg(strings.ANKI_INSTALL_CANCELLED))
            else:
                log_error(f"Anki install failed: {e}", getattr(e, "tail", []))
                self.broadcast(self._anki_msg(strings.ANKI_INSTALL_FAILED.format(error=e), log=False))
        finally:
            self._anki_busy = False

    def resume_anki(self):
        if not (self.prefs["anki_button"] and self.prefs["anki_resume"] and anki_ready(self.prefs)):
            return
        if self._anki_running() or anki_send("ping", 1.0) == "ok":
            return
        threading.Thread(target=self._run_anki, args=(list(self.prefs["anki_cmd"]), True), daemon=True).start()

    def _set_anki_resume(self, value):
        if self.prefs["anki_resume"] != value:
            self.prefs["anki_resume"] = value
            save_prefs(self.prefs)

    def _launch_anki(self):
        if self._anki_running():
            self._bring_anki_forward()
            return
        self.on_status(strings.ANKI_STARTING)
        threading.Thread(target=self._run_anki, args=(list(self.prefs["anki_cmd"]),), daemon=True).start()

    def _run_anki(self, cmd, background=False):
        proc = tail = None
        scale = self.prefs["anki_scale"]
        prepare_anki(cmd, scale)
        for flags in ("", "--no-sandbox"):                     # if it dies at once, try again without Qt WebEngine's sandbox
            started = time.monotonic()
            try:
                proc, tail = start_browser(cmd, live=False, env=anki_env(self.cfg, flags, scale=scale, background=background))
            except OSError as e:
                self.on_status(strings.ANKI_START_FAILED.format(error=e))
                return
            self.anki_proc = proc
            self._set_anki_resume(True)
            self.broadcast(self._prefs_msg())
            proc.wait()
            time.sleep(0.2)
            if proc.returncode == 0 or time.monotonic() - started > 20:
                break
        if not self._anki_quitting:
            self._set_anki_resume(False)
        self.broadcast(self._prefs_msg())
        if proc.returncode == 0:
            self.on_status(strings.ANKI_CLOSED)
            return
        lines = list(tail)
        libs = parse_missing_libs("\n".join(lines))
        if libs and cmd[0].startswith(ANKI_VENV):
            libs = sorted(set(libs) | set(qt_missing_libs()))
        if libs:
            short, fix = lib_fix(libs)
            log_error(f"Anki can't start: {short}", fix + ["", "Anki's own output:"] + lines[-12:])
            self.on_status(strings.ANKI_CANT_START.format(libraries=short), log=False)
        else:
            log_error(f"Anki exited with an error (code {proc.returncode})", lines[-40:])
            self.on_status((strings.ANKI_CLOSED_WITH_ERROR_DETAIL.format(detail=lines[-1][:80]) if lines else strings.ANKI_CLOSED_WITH_ERROR), log=False)
