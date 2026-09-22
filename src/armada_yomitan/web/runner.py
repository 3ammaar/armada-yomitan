"""Running the web interface."""

import os
import shutil
import signal
import subprocess
import sys
import threading
import time

from armada_yomitan import strings
from armada_yomitan.browser import (
    browser_cmd,
    browser_env,
    find_browser,
    reset_profile_state,
    start_browser,
    web_ready,
)
from armada_yomitan.console import log_error
from armada_yomitan.ocr.engine import resolve_engine
from armada_yomitan.ocr.rapid import warm_engine
from armada_yomitan.relaunch import program_command
from armada_yomitan.web.ui import WebUI
from armada_yomitan.yomitan.patch import YOMITAN_ID, apply_ext_patches, kbd_patch_problems


def run_web(cfg):
    browser = find_browser()
    if not web_ready():
        raise RuntimeError("The web interface isn't installed yet. Run: armada-yomitan --setup")
    ui = WebUI(cfg)
    ui.start()
    url = f"http://127.0.0.1:{ui.port}/?t={ui.token}"
    try:
        # SIGTERM (Decky's Stop) does what Quit does
        signal.signal(signal.SIGTERM, lambda number, frame: ui.done.set())
    except ValueError:
        pass

    def warm_up():
        if resolve_engine(cfg) != "rapidocr":
            return
        ui.on_status(strings.LOADING_OCR_MODEL)
        try:
            warm_engine(cfg)
            if not ui.session.active:
                ui.on_status(strings.READY)
        except Exception as e:
            ui.on_status(strings.OCR_MODEL_FAILED.format(error=e))

    threading.Thread(target=warm_up, daemon=True).start()
    threading.Thread(target=ui.cmd_sysdeps_check, daemon=True).start()
    ui.resume_anki()
    apply_ext_patches()
    for problem in kbd_patch_problems():
        log_error("Keyboard for Yomitan's settings: " + problem)
    reset_profile_state()
    first = browser_cmd(browser, url, scale=cfg.ui_scale)
    live = bool(os.environ.get("ARMADA_YOMITAN_BROWSER_LOG"))
    proc = None
    try:
        for attempt, cmd in enumerate((first, first + ["--no-sandbox"])):
            started = time.monotonic()
            proc, tail = start_browser(cmd, live)
            while proc.poll() is None and not ui.done.is_set():
                time.sleep(0.3)
            if ui.done.is_set() or proc.returncode == 0 or time.monotonic() - started > 10:
                break
            time.sleep(0.2)
            print("The browser exited with an error. Its last messages:\n  " + "\n  ".join(tail), file=sys.stderr)
            if attempt == 0:
                print("(retrying without its sandbox)", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        ui.shutdown()
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return ui.after


def cmd_yomitan_settings():
    if not web_ready():
        raise RuntimeError("The web interface isn't installed yet. Run: armada-yomitan --setup")
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        wrapper = shutil.which("armada-run-bottom")
        if wrapper and not os.environ.get("ARMADA_YOMITAN_ON_BOTTOM"):
            print("This shell has no screen (SSH?), so opening Yomitan's settings on the bottom screen instead.")
            os.environ["ARMADA_YOMITAN_ON_BOTTOM"] = "1"
            os.execv(wrapper, [wrapper, "--"] + program_command() + ["--yomitan-settings"])
        raise RuntimeError("No screen is available here (neither DISPLAY nor WAYLAND_DISPLAY is set). "
                           "Use the Settings button in the app instead.")
    print("Opening Yomitan's settings. Close the window when you're done.")
    apply_ext_patches()
    reset_profile_state()
    subprocess.run(browser_cmd(find_browser(), f"chrome-extension://{YOMITAN_ID}/settings.html", settings=True),
                   env=browser_env())
