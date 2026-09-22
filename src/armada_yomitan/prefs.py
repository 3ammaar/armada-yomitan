"""Saved settings."""

import json
import re

from armada_yomitan.config import Config
from armada_yomitan.paths import PREFS_PATH

SCAN_DETAIL = {"fast": 960, "balanced": 1280, "full": 0}   # longest side (px) the text detector works at; 0 = native


PREF_DEFAULTS = {"scan_detail": "balanced",   # how sharp the whole-screen scan is: fast | balanced | full
                 "yomi_zoom": 1.2,
                 "mode": "screen",
                 "areas": [],               # the manual-selection rectangles: [left, top, right, bottom] as screen fractions
                 "show_preview": False,
                 "anki_button": False,
                 "anki_scale": Config.anki_scale,
                 "anki_resume": False,
                 "anki_cmd": [],
                 "anki_label": "",
                 "capture_size": "",
                 "capture_label": "",
                 "capture_node": ""}


def clamp_anki_scale(value):
    return round(min(4.0, max(1.5, float(value))) * 4) / 4


def clean_areas(value, limit=16):
    out = []
    for a in value if isinstance(value, list) else []:
        try:
            u0, v0, u1, v1 = (float(t) for t in a)
        except (TypeError, ValueError):
            continue
        if 0 <= u0 < u1 <= 1 and 0 <= v0 < v1 <= 1 and len(out) < limit:
            out.append([round(u0, 4), round(v0, 4), round(u1, 4), round(v1, 4)])
    return out


def load_prefs(forced_mode=""):
    prefs = dict(PREF_DEFAULTS)
    try:
        with open(PREFS_PATH) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = {}
    if isinstance(saved.get("yomi_zoom"), (int, float)) and not isinstance(saved["yomi_zoom"], bool):
        prefs["yomi_zoom"] = min(2.0, max(0.7, float(saved["yomi_zoom"])))
    if saved.get("mode") in ("screen", "tap", "manual"):
        prefs["mode"] = saved["mode"]
    prefs["areas"] = clean_areas(saved.get("areas"))
    if isinstance(saved.get("anki_button"), bool):
        prefs["anki_button"] = saved["anki_button"]
    if isinstance(saved.get("anki_scale"), (int, float)) and not isinstance(saved["anki_scale"], bool):
        prefs["anki_scale"] = clamp_anki_scale(saved["anki_scale"])
    if isinstance(saved.get("anki_resume"), bool):
        prefs["anki_resume"] = saved["anki_resume"]
    cmd = saved.get("anki_cmd")
    if isinstance(cmd, list) and 0 < len(cmd) <= 8 and all(isinstance(c, str) and 0 < len(c) <= 400 for c in cmd):
        prefs["anki_cmd"] = cmd
        if isinstance(saved.get("anki_label"), str):
            prefs["anki_label"] = saved["anki_label"][:60]
    if saved.get("scan_detail") in SCAN_DETAIL:
        prefs["scan_detail"] = saved["scan_detail"]
    if isinstance(saved.get("show_preview"), bool):
        prefs["show_preview"] = saved["show_preview"]
    if isinstance(saved.get("capture_size"), str) and re.fullmatch(r"\d{2,5}x\d{2,5}", saved["capture_size"]):
        prefs["capture_size"] = saved["capture_size"]
        if isinstance(saved.get("capture_label"), str):
            prefs["capture_label"] = saved["capture_label"][:60]
    if isinstance(saved.get("capture_node"), str) and re.fullmatch(r"\d{1,9}", saved["capture_node"]):
        prefs["capture_node"] = saved["capture_node"]
    if forced_mode in ("screen", "tap", "manual"):       # --mode / ARMADA_YOMITAN_MODE beats the saved setting
        prefs["mode"] = forced_mode
    return prefs


def save_prefs(prefs):
    try:
        with open(PREFS_PATH, "w") as f:
            json.dump(prefs, f)
    except OSError:
        pass
