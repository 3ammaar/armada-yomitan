"""The Tesseract engine."""

import os
import shutil
import subprocess

from armada_yomitan import strings
from armada_yomitan.ocr.lines import is_vertical, make_line
from armada_yomitan.ocr.types import Word


def run_tesseract(png_bytes, lang, psm, tessdata=""):
    if not shutil.which("tesseract"):
        raise RuntimeError(strings.OCR_TESSERACT_MISSING)
    cmd = ["tesseract", "stdin", "stdout"]
    if tessdata:
        cmd += ["--tessdata-dir", os.path.expanduser(tessdata)]
    cmd += ["-l", lang, "--psm", str(psm), "tsv"]
    r = subprocess.run(cmd, input=png_bytes, capture_output=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(strings.OCR_TESSERACT_FAILED.format(output=r.stderr.decode(errors="replace").strip()[-300:]))
    return parse_tsv(r.stdout.decode("utf-8", errors="replace"))


def parse_tsv(tsv):
    words = []
    for row in tsv.splitlines()[1:]:
        p = row.split("\t", 11)
        if len(p) < 12 or p[0] != "5" or not p[11].strip():
            continue
        try:
            words.append(Word(p[11].strip(), int(p[6]), int(p[7]), int(p[8]), int(p[9]),
                              float(p[10]), int(p[2]), int(p[3]), int(p[4])))
        except ValueError:
            continue
    return words


def _needs_space(a, b):
    return a[-1:].isascii() and a[-1:].isalnum() and b[:1].isascii() and b[:1].isalnum()


def join_with_offsets(words):
    text, offsets = "", []
    for w in words:
        if text and _needs_space(text, w.text):
            text += " "
        offsets.append(len(text))
        text += w.text
    return text, offsets


def lines_from_tesseract(words):
    groups = {}
    for w in words:
        groups.setdefault((w.block, w.par, w.line), []).append(w)
    lines = []
    for ws in groups.values():
        text = join_with_offsets(ws)[0]
        box = (min(w.left for w in ws), min(w.top for w in ws),
               max(w.left + w.width for w in ws), max(w.top + w.height for w in ws))
        lines.append(make_line(text, box, sum(w.conf for w in ws) / len(ws), None, is_vertical(text, box)))
    return lines
