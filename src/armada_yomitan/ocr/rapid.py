"""The RapidOCR engine."""

import numbers
import sys
import threading

from armada_yomitan import strings
from armada_yomitan.ocr.lines import estimate_glyphs, is_vertical, make_line

_rapid = {}


_rapid_lock = threading.Lock()


LAST_TIMING = {}


def _rapid_params(cfg, tuned=True):
    try:
        from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion
        kind = ModelType.SERVER if cfg.rapid_model == "server" else ModelType.MOBILE
        params = {"Det.engine_type": EngineType.ONNXRUNTIME, "Det.lang_type": LangDet.CH,
                  "Det.model_type": kind, "Det.ocr_version": OCRVersion.PPOCRV5,
                  "Rec.engine_type": EngineType.ONNXRUNTIME,
                  "Rec.lang_type": getattr(LangRec, cfg.rapid_lang.upper(), LangRec.CH),
                  "Rec.model_type": kind, "Rec.ocr_version": OCRVersion.PPOCRV5}
        for key, val in (("Det.thresh", cfg.rapid_thresh), ("Det.box_thresh", cfg.rapid_box_thresh),
                         ("Det.unclip_ratio", cfg.rapid_unclip)):
            if val is not None:
                params[key] = val
        if tuned:
            if cfg.rapid_max_side > 0:
                params["Det.limit_type"] = "max"
                params["Det.limit_side_len"] = cfg.rapid_max_side
            if cfg.rapid_threads > 0:
                params["EngineConfig.onnxruntime.intra_op_num_threads"] = cfg.rapid_threads
        return params
    except (ImportError, AttributeError):
        return None


def get_rapid(cfg):
    key = (cfg.rapid_model, cfg.rapid_lang, cfg.rapid_thresh, cfg.rapid_box_thresh, cfg.rapid_unclip,
           cfg.rapid_threads, cfg.rapid_max_side)
    with _rapid_lock:
        if key not in _rapid:
            try:
                from rapidocr import RapidOCR
            except ImportError:
                raise RuntimeError(strings.OCR_RAPIDOCR_MISSING)
            engine, tried = None, []
            for tuned in (True, False):
                params = _rapid_params(cfg, tuned)
                if not params or params in tried:
                    continue
                tried.append(params)
                try:
                    engine = RapidOCR(params=params)
                    break
                except Exception as e:
                    print(f"(rapidocr: {'the speed settings were' if tuned else 'the requested models were'} "
                          f"not accepted ({e}); trying again with fewer settings)", file=sys.stderr)
            _rapid[key] = engine or RapidOCR()
        return _rapid[key]


def warm_engine(cfg):
    get_rapid(cfg)
    try:
        import cv2
        import numpy as np
        img = np.full((720, 1280, 3), 255, np.uint8)
        cv2.putText(img, "Hello 123", (80, 300), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 6)
        run_rapidocr_array(img, cfg)
    except Exception:
        pass


def _poly_box(poly):
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _word_entries(word_results):
    out = []

    def walk(o):
        if isinstance(o, (list, tuple)):
            if len(o) == 3 and isinstance(o[0], str) and isinstance(o[1], numbers.Real):
                out.append(o)
            else:
                for x in o:
                    walk(x)
    if word_results is not None:
        walk(word_results)
    return out


def _glyphs_from_entries(text, entries, ei, vertical):
    want = text.replace(" ", "")
    got, used, j = "", [], ei
    while len(got) < len(want) and j < len(entries):
        got += entries[j][0].replace(" ", "")
        used.append(entries[j])
        j += 1
    if got != want:
        return None, j
    glyphs, k = [], 0
    for word, _, poly in used:
        try:
            l, t, r, b = _poly_box(poly)
        except (TypeError, IndexError, ValueError):
            return None, j
        while k < len(text) and text[k] == " ":
            if vertical:
                e = glyphs[-1][3] if glyphs else t
                glyphs.append((l, e, r, e))
            else:
                e = glyphs[-1][2] if glyphs else l
                glyphs.append((e, t, e, b))
            k += 1
        chars = word.replace(" ", "")
        glyphs.extend(estimate_glyphs(chars, (l, t, r, b), vertical))
        k += len(chars)
    return (glyphs if len(glyphs) == len(text) else None), j


def lines_from_rapid(res):
    txts = getattr(res, "txts", None) or ()
    boxes = getattr(res, "boxes", None)
    scores = getattr(res, "scores", None) or ()
    if boxes is None or not len(txts):
        return []
    entries = _word_entries(getattr(res, "word_results", None))
    lines, ei = [], 0
    for i, text in enumerate(txts):
        box = _poly_box(boxes[i])
        vertical = is_vertical(text, box)
        glyphs, ei = _glyphs_from_entries(text, entries, ei, vertical) if entries else (None, ei)
        lines.append(make_line(text, box, (scores[i] * 100) if i < len(scores) else 0, glyphs, vertical))
    return lines


def run_rapidocr(png_bytes, cfg):
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise RuntimeError(strings.OCR_OPENCV_MISSING)
    img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(strings.OCR_CROP_NOT_DECODED)
    return run_rapidocr_array(img, cfg)


def run_rapidocr_array(img, cfg):
    engine = get_rapid(cfg)
    for kwargs in ({"use_cls": False, "return_word_box": True, "return_single_char_box": True},
                   {"use_cls": False, "return_word_box": True},
                   {"return_word_box": True, "return_single_char_box": True},                     # no use_cls option
                   {"return_word_box": True},
                   {"use_cls": False},
                   {}):                                                                            # older versions
        try:
            res = engine(img, **kwargs)
            break
        except TypeError:
            continue
    LAST_TIMING.clear()
    try:                                             # [detect, classify, read] seconds, when reported
        times = list(getattr(res, "elapse_list", None) or [])
        if len(times) >= 3:
            LAST_TIMING.update(detect=float(times[0] or 0), read=float(times[2] or 0))
    except (TypeError, ValueError):
        pass
    return lines_from_rapid(res)
