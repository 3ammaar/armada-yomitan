"""The command line."""

import argparse
import sys

from armada_yomitan.config import Config
from armada_yomitan.diagnostics import (
    cmd_anki_check,
    cmd_capture_test,
    cmd_list,
    cmd_ocr_live,
    cmd_ocr_test,
    cmd_probe,
    cmd_speed_test,
    cmd_sweep,
    cmd_warmup,
)
from armada_yomitan.gtk_setup import run_setup_gui
from armada_yomitan.gtk_ui import run_gui
from armada_yomitan.installer import Missing, cmd_check_deps, cmd_install_deps, cmd_list_deps, cmd_setup, start_state
from armada_yomitan.launcher import maybe_start_on_bottom
from armada_yomitan.relaunch import maybe_reexec_into_venv, restart
from armada_yomitan.web.runner import cmd_yomitan_settings, run_web

DESCRIPTION = """\
Bottom-screen OCR, Yomitan and Anki for the AYN Thor.

With no arguments, start on the bottom screen as
armada-run-bottom -- armada-yomitan --touch top_touchscreen --rotation 270.
With any argument, run as asked. X and Y are pixels, or fractions of the frame when both are at most 1.
"""

EPILOG = """\
Files:
  ~/.local/share/armada-yomitan    everything the program installs (ARMADA_YOMITAN_HOME)
  ~/.local/share/armada-yomitan/armada-yomitan.log
"""


def main():
    ap = argparse.ArgumentParser(prog="armada-yomitan", usage="armada-yomitan [OPTION]...", description=DESCRIPTION, epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter, add_help=False)
    ap.add_argument("-h", "--help", action="help", help="show this help and exit")
    setup = ap.add_argument_group("Setup")
    setup.add_argument("--setup", action="store_true", help="install OCR, Chromium, Yomitan and the system packages")
    setup.add_argument("--setup-web", action="store_true", help="install only Chromium and Yomitan")
    setup.add_argument("--no-system", action="store_true", help="with --setup: leave out the system packages")
    setup.add_argument("--install-deps", action="store_true", help="install the missing system packages")
    setup.add_argument("--list-deps", action="store_true", help="print the system packages as JSON, with which are present")
    setup.add_argument("--check-deps", action="store_true", help="list the system packages present and missing")
    setup.add_argument("-y", "--yes", action="store_true", help="do not ask before installing")
    setup.add_argument("--reboot", action="store_true", help="reboot after --install-deps")
    setup.add_argument("--no-anki", action="store_true", help="leave out the libraries Anki needs")
    setup.add_argument("--no-vertical", action="store_true", help="leave out the vertical-text OCR data")
    ui = ap.add_argument_group("Interface")
    ui.add_argument("--ui", choices=("auto", "web", "gtk"), help="interface to show (default auto)")
    ui.add_argument("--ui-scale", type=float, metavar="SCALE", help="browser device scale factor (default 2.625)")
    ui.add_argument("--mode", choices=("screen", "tap", "manual"), help="scan mode for this run")
    ui.add_argument("--yomitan-settings", action="store_true", help="open Yomitan's settings in a window")
    screen = ap.add_argument_group("Screen and touch")
    screen.add_argument("--touch", metavar="NAME", help="part of the top touchscreen's device name")
    screen.add_argument("--rotation", type=int, choices=(0, 90, 180, 270), help="touchscreen rotation in degrees")
    screen.add_argument("--node", metavar="ID", help="PipeWire node of the top screen")
    screen.add_argument("--no-grab", action="store_true", help="do not grab the touchscreen")
    screen.add_argument("--image", metavar="FILE", help="use an image instead of the top screen")
    ocr = ap.add_argument_group("OCR")
    ocr.add_argument("--engine", choices=("auto", "rapidocr", "tesseract"), help="OCR engine (default auto)")
    ocr.add_argument("--scan-length", type=int, metavar="N", help="characters sent to the dictionary (default 20)")
    ocr.add_argument("--rapid-model", choices=("mobile", "server"), help="RapidOCR model size")
    ocr.add_argument("--rapid-lang", metavar="LANG", help="RapidOCR recognition language (default ch)")
    ocr.add_argument("--rapid-threads", type=int, metavar="N", help="RapidOCR threads (default 4, 0 for all cores)")
    ocr.add_argument("--rapid-max-side", type=int, metavar="PIXELS", help="longest side the detector sees (default 1280, 0 for native)")
    ocr.add_argument("--rapid-thresh", type=float, metavar="X", help="RapidOCR detector threshold")
    ocr.add_argument("--rapid-box-thresh", type=float, metavar="X", help="RapidOCR box score threshold")
    ocr.add_argument("--rapid-unclip", type=float, metavar="X", help="RapidOCR box expansion ratio")
    ocr.add_argument("--scale", type=float, metavar="X", help="Tesseract upscale factor (default 2)")
    ocr.add_argument("--invert", choices=("on", "off"), help="invert the crop before OCR")
    ocr.add_argument("--tessdata", metavar="DIR", help="directory of .traineddata files")
    ocr.add_argument("--lang", metavar="LANG", help="Tesseract language")
    ocr.add_argument("--psm", metavar="MODE", help="Tesseract page segmentation mode")
    diag = ap.add_argument_group("Diagnostics")
    diag.add_argument("--list", action="store_true", help="list input devices")
    diag.add_argument("--probe", action="store_true", help="print touch coordinates and rotation candidates")
    diag.add_argument("--capture-test", action="store_true", help="capture a frame from each gamescope node")
    diag.add_argument("--ocr-test", nargs=3, metavar=("IMAGE", "X", "Y"), help="OCR an image at a pixel")
    diag.add_argument("--ocr-live", nargs=2, type=float, metavar=("X", "Y"), help="OCR the top screen around a point")
    diag.add_argument("--sweep", nargs=2, type=float, metavar=("X", "Y"), help="try many OCR settings around a point")
    diag.add_argument("--speed-test", action="store_true", help="time whole-screen scans")
    diag.add_argument("--warmup", action="store_true", help="load the OCR models and exit")
    diag.add_argument("--anki-check", action="store_true", help="list the libraries Anki still needs")
    maybe_start_on_bottom(sys.argv[1:])
    maybe_reexec_into_venv()
    a = ap.parse_args()

    cfg = Config()
    if a.touch: cfg.touch_name = a.touch
    if a.rotation is not None: cfg.rotation = a.rotation
    if a.lang: cfg.lang = a.lang
    if a.psm: cfg.psm = a.psm
    if a.mode: cfg.mode = a.mode
    if a.ui: cfg.ui = a.ui
    if a.ui_scale: cfg.ui_scale = a.ui_scale
    if a.engine: cfg.engine = a.engine
    if a.rapid_model: cfg.rapid_model = a.rapid_model
    if a.rapid_lang: cfg.rapid_lang = a.rapid_lang
    if a.scan_length: cfg.scan_len = a.scan_length
    if a.rapid_threads is not None: cfg.rapid_threads = a.rapid_threads
    if a.rapid_max_side is not None: cfg.rapid_max_side = a.rapid_max_side
    if a.rapid_thresh is not None: cfg.rapid_thresh = a.rapid_thresh
    if a.rapid_box_thresh is not None: cfg.rapid_box_thresh = a.rapid_box_thresh
    if a.rapid_unclip is not None: cfg.rapid_unclip = a.rapid_unclip
    if a.scale: cfg.scale = a.scale
    if a.invert: cfg.invert = a.invert
    if a.tessdata: cfg.tessdata = a.tessdata
    if a.node: cfg.capture_node = a.node
    if a.image: cfg.image = a.image
    if a.no_grab: cfg.grab = False

    try:
        if a.setup:
            cmd_setup(yes=a.yes, system=not a.no_system)
        elif a.list_deps:
            cmd_list_deps(anki=not a.no_anki, vertical=not a.no_vertical)
        elif a.install_deps:
            cmd_install_deps(yes=a.yes, reboot=a.reboot, anki=not a.no_anki, vertical=not a.no_vertical)
        elif a.check_deps:
            cmd_check_deps(anki=not a.no_anki, vertical=not a.no_vertical)
        elif a.setup_web:
            cmd_setup(web_only=True)
        elif a.yomitan_settings:
            cmd_yomitan_settings()
        elif a.warmup:
            cmd_warmup(cfg)
        elif a.list:
            cmd_list()
        elif a.probe:
            cmd_probe(cfg)
        elif a.capture_test:
            cmd_capture_test(cfg)
        elif a.anki_check:
            cmd_anki_check()
        elif a.speed_test:
            cmd_speed_test(cfg)
        elif a.sweep:
            cmd_sweep(cfg, *a.sweep)
        elif a.ocr_live:
            cmd_ocr_live(cfg, *a.ocr_live)
        elif a.ocr_test:
            cmd_ocr_test(cfg, a.ocr_test[0], int(a.ocr_test[1]), int(a.ocr_test[2]))
        else:
            missing = Missing() if cfg.ui == "auto" else None
            state = start_state(missing) if missing else "ready"
            if state != "ready":
                if run_setup_gui(cfg, blocked=state == "blocked", missing=missing) == "installed":
                    restart()
            else:
                ui = cfg.ui if cfg.ui != "auto" else "web"
                if ui != "web":
                    run_gui(cfg)
                elif run_web(cfg) == "restart":
                    restart()
    except RuntimeError as e:
        sys.exit(str(e))
