"""Building OCR lines."""

from armada_yomitan.ocr.types import Line


def _weight(ch):
    return 0.3 if ch == " " else 0.55 if ord(ch) < 128 else 1.0


def estimate_glyphs(text, box, vertical):
    l, t, r, b = box
    weights = [_weight(c) for c in text]
    total = sum(weights) or 1.0
    out, pos = [], 0.0
    for w in weights:
        a, z = pos / total, (pos + w) / total
        pos += w
        out.append((l, t + (b - t) * a, r, t + (b - t) * z) if vertical
                   else (l + (r - l) * a, t, l + (r - l) * z, b))
    return out


def make_line(text, box, conf, glyphs, vertical):
    exact = glyphs is not None and len(glyphs) == len(text)
    if not exact:
        glyphs = estimate_glyphs(text, box, vertical)
    return Line(text, tuple(float(v) for v in box), [tuple(float(v) for v in g) for g in glyphs],
                float(conf), exact, vertical)


def is_vertical(text, box):
    l, t, r, b = box
    return len(text) > 1 and (b - t) > 1.4 * (r - l)
