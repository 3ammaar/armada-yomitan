"""Tap-to-character lookup."""

import statistics

from armada_yomitan.ocr.types import Hit


def reading_order(lines):
    if not lines:
        return []
    if sum(ln.vertical for ln in lines) * 2 > len(lines):
        size = statistics.median(ln.box[2] - ln.box[0] for ln in lines)
        return sorted(lines, key=lambda ln: (-round((ln.box[0] + ln.box[2]) / 2 / max(size * 0.7, 1)),
                                             ln.box[1]))
    size = statistics.median(ln.box[3] - ln.box[1] for ln in lines)
    return sorted(lines, key=lambda ln: (round((ln.box[1] + ln.box[3]) / 2 / max(size * 0.7, 1)),
                                         ln.box[0]))


def rect_distance(box, x, y):
    l, t, r, b = box
    dx = max(l - x, 0, x - r)
    dy = max(t - y, 0, y - b)
    return (dx * dx + dy * dy) ** 0.5


def find_hit(lines, x, y, scan_len=20, max_dist=80):
    if not lines:
        return None
    line = min(lines, key=lambda ln: rect_distance(ln.box, x, y))
    if rect_distance(line.box, x, y) > max_dist:
        return None
    cands = [i for i, c in enumerate(line.text) if not c.isspace()] or list(range(len(line.text)))
    if not cands:
        return None
    idx = min(cands, key=lambda i: (rect_distance(line.glyphs[i], x, y), i))
    ordered = reading_order(lines)
    before = next(i for i, ln in enumerate(ordered) if ln is line)
    offset = sum(len(ln.text) + 1 for ln in ordered[:before]) + idx
    return Hit(line, idx, line.text[idx], "\n".join(ln.text for ln in ordered), offset,
               line.text[idx:idx + scan_len], line.glyphs[idx], (x, y))


def crop_rect(px, py, W, H, cw, ch):
    cw, ch = min(cw, W), min(ch, H)
    return min(max(px - cw // 2, 0), W - cw), min(max(py - ch // 2, 0), H - ch), cw, ch


def find_hit_near(lines, x, y, cfg):
    l, t = x - cfg.crop_w / 2, y - cfg.crop_h / 2
    r, b = x + cfg.crop_w / 2, y + cfg.crop_h / 2
    near = [ln for ln in lines if ln.box[2] >= l and ln.box[0] <= r and ln.box[3] >= t and ln.box[1] <= b]
    return find_hit(near, x, y, scan_len=cfg.scan_len)


def hit_boxes(hit, ox, oy):
    def rel(b):
        return (int(b[0] - ox), int(b[1] - oy), int(b[2] - b[0]), int(b[3] - b[1]))

    g = hit.line.glyphs[hit.index:hit.index + len(hit.scan_text)]
    span = (min(b[0] for b in g), min(b[1] for b in g), max(b[2] for b in g), max(b[3] for b in g))
    return rel(hit.box), rel(span)
