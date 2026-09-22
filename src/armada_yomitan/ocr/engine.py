"""OCR engine selection."""

import importlib.util
from dataclasses import replace

from armada_yomitan.ocr.rapid import run_rapidocr
from armada_yomitan.ocr.tesseract import lines_from_tesseract, run_tesseract


def resolve_engine(cfg):
    if cfg.engine in ("tesseract", "rapidocr"):
        return cfg.engine
    return "rapidocr" if importlib.util.find_spec("rapidocr") else "tesseract"


def ocr_lines(png_bytes, cfg, engine=None):
    engine = engine or resolve_engine(cfg)
    if engine == "rapidocr":
        return run_rapidocr(png_bytes, cfg)
    return lines_from_tesseract(run_tesseract(png_bytes, cfg.lang, cfg.psm, cfg.tessdata))


def scale_lines(lines, s):
    if s == 1:
        return lines
    def f(b):
        return tuple(v / s for v in b)
    return [replace(ln, box=f(ln.box), glyphs=[f(g) for g in ln.glyphs]) for ln in lines]
