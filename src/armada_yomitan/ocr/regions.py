"""OCR of parts of a frame."""

from dataclasses import replace

from armada_yomitan.ocr.hit import crop_rect
from armada_yomitan.ocr.image import BlankImage, ocr_pixbuf


def ocr_region(pixbuf, px, py, cfg):
    W, H = pixbuf.get_width(), pixbuf.get_height()
    x, y, cw, ch = crop_rect(px, py, W, H, cfg.crop_w, cfg.crop_h)
    lines = ocr_pixbuf(pixbuf.new_subpixbuf(x, y, cw, ch), cfg)

    def shift(b):
        return (b[0] + x, b[1] + y, b[2] + x, b[3] + y)

    return [replace(ln, box=shift(ln.box), glyphs=[shift(g) for g in ln.glyphs]) for ln in lines]


def shift_lines(lines, dx, dy):
    def shift(b):
        return (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)

    return [replace(ln, box=shift(ln.box), glyphs=[shift(g) for g in ln.glyphs]) for ln in lines]


def merge_areas(areas):
    rects = [list(a) for a in areas]
    changed = True
    while changed:
        changed, out = False, []
        for r in rects:
            for o in out:
                if r[0] < o[2] and r[2] > o[0] and r[1] < o[3] and r[3] > o[1]:
                    o[:] = [min(o[0], r[0]), min(o[1], r[1]), max(o[2], r[2]), max(o[3], r[3])]
                    changed = True
                    break
            else:
                out.append(r)
        rects = out
    return rects


def ocr_areas(frame, areas, cfg):
    W, H = frame.get_width(), frame.get_height()
    lines = []
    for u0, v0, u1, v1 in merge_areas(areas):
        x0, y0 = max(0, int(u0 * W)), max(0, int(v0 * H))
        x1, y1 = min(W, int(round(u1 * W))), min(H, int(round(v1 * H)))
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        try:
            found = ocr_pixbuf(frame.new_subpixbuf(x0, y0, x1 - x0, y1 - y0), cfg)
        except BlankImage:
            continue
        lines.extend(shift_lines(found, x0, y0))
    return lines
