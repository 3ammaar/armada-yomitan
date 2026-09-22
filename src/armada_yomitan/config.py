"""Runtime configuration."""

import os
from dataclasses import dataclass

# {node} is the PipeWire node id; the command must write one PNG to stdout
DEFAULT_CAPTURE_CMD = (
    "gst-launch-1.0 -q pipewiresrc path={node} num-buffers=1 "
    "! videoconvert ! pngenc compression-level=1 ! fdsink fd=1"
)


def _envf(name):
    return float(os.environ[name]) if name in os.environ else None


@dataclass
class Config:
    lang: str = os.environ.get("ARMADA_YOMITAN_LANG", "jpn+eng")
    psm: str = os.environ.get("ARMADA_YOMITAN_PSM", "6")          # 6=block, 5=vertical block, 7=one line
    touch_name: str = os.environ.get("ARMADA_YOMITAN_TOUCH", "")
    rotation: int = int(os.environ.get("ARMADA_YOMITAN_ROT", "0"))
    grab: bool = os.environ.get("ARMADA_YOMITAN_GRAB", "1") != "0"
    capture_node: str = os.environ.get("ARMADA_YOMITAN_NODE", "")
    capture_size: str = ""
    node_auto: bool = False
    capture_cmd: str = os.environ.get("ARMADA_YOMITAN_CAPTURE_CMD", DEFAULT_CAPTURE_CMD)
    image: str = os.environ.get("ARMADA_YOMITAN_IMAGE", "")
    scale: float = float(os.environ.get("ARMADA_YOMITAN_SCALE", "2"))
    invert: str = os.environ.get("ARMADA_YOMITAN_INVERT", "off")
    tessdata: str = os.environ.get("ARMADA_YOMITAN_TESSDATA", "")
    engine: str = os.environ.get("ARMADA_YOMITAN_ENGINE", "auto")       # auto | rapidocr | tesseract
    rapid_model: str = os.environ.get("ARMADA_YOMITAN_RAPID_MODEL", "mobile")  # mobile (fast) | server (accurate)
    rapid_lang: str = os.environ.get("ARMADA_YOMITAN_RAPID_LANG", "ch")  # PP-OCRv5 "ch" model also reads Japanese + English
    rapid_scale: float = float(os.environ.get("ARMADA_YOMITAN_RAPID_SCALE", "1"))
    rapid_threads: int = int(os.environ.get("ARMADA_YOMITAN_RAPID_THREADS", "4"))     # ONNX Runtime threads; 0 = all cores
    rapid_max_side: int = int(os.environ.get("ARMADA_YOMITAN_RAPID_MAX_SIDE", "1280"))  # longest side the text detector sees; 0 = as is
    rapid_thresh: float = _envf("ARMADA_YOMITAN_RAPID_THRESH")            # text detector thresholds; lower = finds more
    rapid_box_thresh: float = _envf("ARMADA_YOMITAN_RAPID_BOX_THRESH")
    rapid_unclip: float = _envf("ARMADA_YOMITAN_RAPID_UNCLIP")
    anki_scale: float = float(os.environ.get("ARMADA_YOMITAN_ANKI_SCALE", "2.5"))
    ui_scale: float = float(os.environ.get("ARMADA_YOMITAN_UI_SCALE", "2.625"))   # browser device scale: 420 dpi = Android's 2.625
    preview_w: int = 300
    preview_h: int = 300
    ui: str = os.environ.get("ARMADA_YOMITAN_UI", "auto")
    mode: str = os.environ.get("ARMADA_YOMITAN_MODE", "")               # "" = the saved setting (default screen) | screen | tap
    scan_len: int = int(os.environ.get("ARMADA_YOMITAN_SCAN_LEN", "20"))
    crop_w: int = 1200
    crop_h: int = 360
    wait_seconds: float = 20.0
