"""Image helpers."""

from dataclasses import replace

from armada_yomitan import strings
from armada_yomitan.ocr.engine import ocr_lines, resolve_engine, scale_lines
from armada_yomitan.ocr.hit import crop_rect, find_hit, hit_boxes
from armada_yomitan.ocr.rapid import run_rapidocr_array


def pixbuf_to_bgr(pb):
    import numpy as np
    w, h, rs, n = pb.get_width(), pb.get_height(), pb.get_rowstride(), pb.get_n_channels()
    rgb = np.ndarray((h, w, 3), dtype=np.uint8, buffer=pb.get_pixels(), strides=(rs, n, 1))
    return np.ascontiguousarray(rgb[:, :, ::-1])


GREEN, RED, YELLOW = (0, 200, 0), (255, 0, 0), (255, 200, 0)


def draw_marks(data, w, h, rowstride, nchan, box, tap, span=None):
    def put(x, y, c):
        if 0 <= x < w and 0 <= y < h:
            o = y * rowstride + x * nchan
            data[o:o + 3] = bytes(c)

    def outline(b, color, thickness):
        l, t, bw, bh = b
        for th in range(thickness):
            for x in range(l - th, l + bw + th + 1):
                put(x, t - th, color)
                put(x, t + bh + th, color)
            for y in range(t - th, t + bh + th + 1):
                put(l - th, y, color)
                put(l + bw + th, y, color)

    if span:
        outline(span, YELLOW, 2)
    if box:
        outline(box, GREEN, 3)
    tx, ty = tap
    for d in range(-12, 13):
        for th in (-1, 0, 1):
            put(tx + d, ty + th, RED)
            put(tx + th, ty + d, RED)


def marked_pixbuf(pb, box, tap, span=None):
    from gi.repository import GdkPixbuf, GLib
    data = bytearray(pb.get_pixels())
    w, h, rs, n = pb.get_width(), pb.get_height(), pb.get_rowstride(), pb.get_n_channels()
    draw_marks(data, w, h, rs, n, box, tap, span)
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(data)), pb.get_colorspace(),
                                           pb.get_has_alpha(), pb.get_bits_per_sample(), w, h, rs)


INVERT_TABLE = bytes(255 - i for i in range(256))


def strip_alpha_bytes(data, w, h, rowstride, nchan):
    """Alpha is ignored, not composited."""
    out = bytearray(w * h * 3)
    for y in range(h):
        row = data[y * rowstride: y * rowstride + w * nchan]
        o = y * w * 3
        for c in range(3):
            out[o + c:o + w * 3:3] = row[c::nchan][:w]
    return bytes(out)


class BlankImage(RuntimeError):
    pass


def is_blank(pixels):
    return len(set(pixels[::max(1, len(pixels) // 4096)])) <= 1


def preprocess(pb, scale, invert):
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib
    w, h = pb.get_width(), pb.get_height()
    if pb.get_has_alpha():   # drop alpha (copy_area refuses RGBA -> RGB and would leave a blank image)
        rgb = strip_alpha_bytes(pb.get_pixels(), w, h, pb.get_rowstride(), pb.get_n_channels())
        pb = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(rgb), GdkPixbuf.Colorspace.RGB, False, 8,
                                             w, h, w * 3)
    if scale and scale != 1:
        w, h = int(w * scale), int(h * scale)
        pb = pb.scale_simple(w, h, GdkPixbuf.InterpType.HYPER)
    if invert:
        inv = bytes(pb.get_pixels()).translate(INVERT_TABLE)
        pb = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(inv), GdkPixbuf.Colorspace.RGB, False, 8,
                                             w, h, pb.get_rowstride())
    return pb


def ocr_pixbuf(pixbuf, cfg):
    engine = resolve_engine(cfg)
    scale = (cfg.scale if engine == "tesseract" else cfg.rapid_scale) or 1
    if engine == "rapidocr" and scale == 1:
        img = pixbuf_to_bgr(pixbuf)
        if is_blank(img.reshape(-1)):
            raise BlankImage(strings.OCR_IMAGE_BLANK)
        return run_rapidocr_array(img, cfg)
    invert = cfg.invert == "on" and engine == "tesseract"
    prepared = preprocess(pixbuf, scale, invert)
    if is_blank(prepared.get_pixels()):
        raise BlankImage(strings.OCR_IMAGE_BLANK)
    ok, png = prepared.save_to_bufferv("png", [], [])
    if not ok:
        raise RuntimeError(strings.OCR_IMAGE_NOT_ENCODED)
    return scale_lines(ocr_lines(png, cfg, engine), scale)


def mirror_jpeg(frame, width=640):
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    pb = preprocess(frame, 1, False)
    height = max(1, round(pb.get_height() * width / pb.get_width()))
    ok, data = pb.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR).save_to_bufferv("jpeg", ["quality"], ["80"])
    if not ok:
        raise RuntimeError(strings.OCR_SCREEN_NOT_ENCODED)
    return data, width, height


def analyze(pixbuf, px, py, cfg):
    W, H = pixbuf.get_width(), pixbuf.get_height()
    x, y, cw, ch = crop_rect(px, py, W, H, cfg.crop_w, cfg.crop_h)
    crop = pixbuf.new_subpixbuf(x, y, cw, ch)
    lines = ocr_pixbuf(crop, cfg)
    tap = (px - x, py - y)
    return crop, tap, lines, find_hit(lines, *tap, scan_len=cfg.scan_len)


def ocr_frame(pixbuf, cfg):
    if resolve_engine(cfg) == "tesseract" and cfg.psm == "6":
        cfg = replace(cfg, psm="11")
    return ocr_pixbuf(pixbuf, cfg)


def pixbuf_from_bytes(data):
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    loader = GdkPixbuf.PixbufLoader()
    loader.write(data)
    loader.close()
    return loader.get_pixbuf()


def preview_pixbuf(frame, px, py, hit, cfg):
    W, H = frame.get_width(), frame.get_height()
    x, y, cw, ch = crop_rect(px, py, W, H, cfg.crop_w, cfg.crop_h)
    crop = frame.new_subpixbuf(x, y, cw, ch)
    box, span = hit_boxes(hit, x, y) if hit else (None, None)
    return marked_pixbuf(crop, box, (px - x, py - y), span)
