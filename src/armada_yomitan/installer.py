"""Installing the program's components."""

import json
import os
import shutil
import sys
import threading

from armada_yomitan import install_state, strings, syspackages
from armada_yomitan.browser import find_browser, missing_parts
from armada_yomitan.console import log_error
from armada_yomitan.paths import BROWSERS_DIR, EXT_DIR, VENV_DIR, VENV_PY
from armada_yomitan.relaunch import base_python, program_command, program_hint
from armada_yomitan.syslibs import missing_libs
from armada_yomitan.toolchain import Cancelled, allow_steps, cancel, check_cancelled, ensure_uv, report, run_step
from armada_yomitan.yomitan.install import install_yomitan
from armada_yomitan.yomitan.patch import YOMITAN_ID


def install_components(web_only=False, say=None):
    uv = ensure_uv(say)
    env = dict(os.environ, UV_PYTHON_DOWNLOADS="never")      # use the system Python, never a downloaded one
    if web_only:
        install_state.unmark("chromium", "yomitan")
    if os.path.exists(VENV_PY) and (web_only or install_state.is_done("ocr")):
        install_state.mark("ocr")
        report(say, strings.SETUP_OCR_PRESENT)
    else:
        shutil.rmtree(VENV_DIR, ignore_errors=True)
        run_step([uv, "venv", "--system-site-packages", "--python", base_python(), VENV_DIR], env=env, say=say)
        run_step([uv, "pip", "install", "--python", VENV_PY, "rapidocr", "onnxruntime"], env=env, say=say)
        report(say, strings.SETUP_DOWNLOADING_OCR_MODELS)
        run_step(program_command(VENV_PY) + ["--warmup"], env=dict(os.environ, ARMADA_YOMITAN_NO_VENV="1"), say=say)
        install_state.mark("ocr")
    setup_web(uv, env, say)


def missing_system_packages():
    return syspackages.plan(syspackages.run_checks())[0]


PART_TEXTS = {"ocr": strings.MISSING_OCR, "chromium": strings.MISSING_CHROMIUM, "yomitan": strings.MISSING_YOMITAN}


class Missing:
    """What keeps the app from starting: required system packages, install steps, a pending restart."""

    def __init__(self):
        self.checks = [c for c in syspackages.run_checks() if not c.ok and not c.optional]
        self.parts = missing_parts()
        self.reboot = bool(self.checks) and syspackages.reboot_pending()

    def any(self):
        return bool(self.checks or self.parts)

    def lines(self):
        lines = [strings.MISSING_PACKAGE.format(label=c.label, packages=" ".join(c.packages)) for c in self.checks]
        return lines + [PART_TEXTS[step] for step in self.parts]

    def title(self):
        return strings.SETUP_REBOOT_NEEDED if self.reboot else strings.NEEDS_ROOT


def start_state(missing=None):
    """"ready", "install" (the install window can do it) or "blocked" (needs root, or the Decky plugin)."""
    missing = missing or Missing()
    if not missing.any():
        return "ready"
    if syspackages.via_decky() or missing.reboot:
        return "blocked"
    if os.geteuid() == 0:
        return "install"
    return "blocked" if missing.checks else "install"


class SetupJob:
    def __init__(self, on_line, on_done, on_fail):
        self.on_line, self.on_done, self.on_fail = on_line, on_done, on_fail
        self.running = False
        self.reboot_needed = False

    def start(self):
        if self.running:
            return
        self.running = True
        allow_steps()
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        cancel()

    def _run(self):
        try:
            install_components(say=self.on_line)
            if os.geteuid() == 0:
                self.reboot_needed = syspackages.install(on_line=self.on_line) == "staged"
        except Cancelled:
            self.running = False
            return
        except Exception as e:
            log_error(strings.SETUP_FAILED.format(error=e))
            self.running = False
            self.on_fail(strings.SETUP_FAILED.format(error=e))
            return
        self.running = False
        self.on_done()


def cmd_list_deps(anki=True, vertical=True):
    packages = {}
    for check in syspackages.run_checks(anki, vertical):
        for name in check.packages:
            packages.setdefault(name, {"name": name, "optional": check.optional, "present": check.ok})
    print(json.dumps({"packages": list(packages.values())}))


def cmd_setup(web_only=False, yes=False, system=True):
    install_components(web_only)
    if not web_only and system:
        print()
        try:
            cmd_install_deps(yes=yes)
        except RuntimeError as e:
            print(f"\nThe system packages weren't installed: {e}\nRun again later with: armada-yomitan --install-deps", file=sys.stderr)
    script = program_hint()
    print("\nDone. To start it from Steam, add this file as a non-Steam game (no launch options needed). Or run it on the bottom screen:\n"
          f"    armada-run-bottom -- {script} --touch top_touchscreen --rotation 270\n"
          "Then tap Settings in the app to import your dictionaries and set up Anki (Yomitan's own settings page).\n"
          f"If Yomitan reports a CORS error talking to Anki, allow chrome-extension://{YOMITAN_ID} in "
          "AnkiConnect's config (in Anki: Tools > Add-ons > AnkiConnect > Config, webCorsOriginList).")


def setup_web(uv, env, say=None):
    run_step([uv, "pip", "install", "--python", VENV_PY, "playwright"], env=env, say=say)
    if install_state.is_done("chromium") and find_browser():
        report(say, strings.SETUP_CHROMIUM_PRESENT)
    else:
        benv = dict(env, PLAYWRIGHT_BROWSERS_PATH=BROWSERS_DIR)
        report(say, strings.SETUP_DOWNLOADING_CHROMIUM)
        try:
            run_step([VENV_PY, "-m", "playwright", "install", "--no-shell", "chromium"], env=benv, say=say)
        except Cancelled:
            raise
        except RuntimeError:
            run_step([VENV_PY, "-m", "playwright", "install", "chromium"], env=benv, say=say)
        browser = find_browser()
        if not browser:
            raise RuntimeError(strings.SETUP_CHROMIUM_NOT_FOUND.format(folder=BROWSERS_DIR))
        missing = missing_libs(browser)
        if missing:
            report(say, strings.SETUP_CHROMIUM_LIBS_MISSING.format(libraries=", ".join(missing)))
        install_state.mark("chromium")
    check_cancelled()
    if install_state.is_done("yomitan") and os.path.exists(os.path.join(EXT_DIR, "manifest.json")):
        report(say, strings.SETUP_YOMITAN_PRESENT)
    else:
        install_yomitan(say)
        install_state.mark("yomitan")


def cmd_check_deps(anki=True, vertical=True):
    print("Checking armada-yomitan requirements:")
    failed = False
    for c in syspackages.run_checks(anki, vertical):
        if c.ok:
            print(f"  [ ok ] {c.label}")
        elif c.optional:
            print(f"  [warn] {c.label} not installed" + (f" (optional; package: {' '.join(c.packages)})" if c.packages else ""))
        else:
            failed = True
            print(f"  [MISS] {c.label} (package: {' '.join(c.packages)}{'; ' + c.note if c.note else ''})")
    print()
    if failed:
        print("Something is missing. If you already installed the packages, reboot first: layered packages only appear after a reboot.")
        sys.exit(1)
    print("Everything armada-yomitan needs is present.")


def cmd_install_deps(yes=False, reboot=False, anki=True, vertical=True):
    if not syspackages.have_cmd("rpm-ostree"):
        syspackages.install(anki=anki, vertical=vertical)
    required, optional = syspackages.plan(syspackages.run_checks(anki, vertical))
    if not required and not optional:
        print("Nothing to install: every system package is present.")
        return
    print("Will layer these packages with rpm-ostree:")
    for p in required + optional:
        print(f"  {p}")
    print("\nThey are staged into a new deployment and only take effect after a reboot.")
    if not yes and input("Proceed? [Y/n] ").strip().lower().startswith("n"):
        raise RuntimeError("Aborted.")
    syspackages.install(None, anki=anki, vertical=vertical)
    print("\nDone. Packages are staged for the next boot.")
    if reboot:
        print("Rebooting now...")
        syspackages.reboot()
    else:
        print("Reboot when ready (systemctl reboot), then verify with:  armada-yomitan --check-deps")
