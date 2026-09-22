"""Bring-up and debug commands."""

import os
import sys
import time
from dataclasses import replace

from armada_yomitan.anki.install import qt_missing_libs
from armada_yomitan.capture import capture_png, list_capture_nodes
from armada_yomitan.ocr.engine import ocr_lines, resolve_engine
from armada_yomitan.ocr.image import analyze, ocr_frame, pixbuf_from_bytes
from armada_yomitan.ocr.rapid import LAST_TIMING, get_rapid
from armada_yomitan.paths import ANKI_VENV
from armada_yomitan.syslibs import lib_fix
from armada_yomitan.touch import list_input_devices, normalize, open_touch, read_abs_info, wait_for_tap


def cmd_warmup(cfg):
    print("python:", sys.executable)
    if resolve_engine(cfg) == "rapidocr":
        get_rapid(cfg)
        print("OCR models ready.")
    else:
        print("rapidocr isn't installed; nothing to warm up.")


def cmd_list():
    print("Input devices (MT = reports multitouch coordinates):")
    for name, path in list_input_devices():
        tag = ""
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            info = read_abs_info(fd)
            os.close(fd)
            tag = f"  MT/abs range x {info.x_min}-{info.x_max}, y {info.y_min}-{info.y_max}" if info else ""
        except PermissionError:
            tag = "  (no permission to query)"
        except OSError:
            pass
        print(f"  {path}  {name}{tag}")


def cmd_probe(cfg):
    dev = open_touch(cfg)
    r, w = os.pipe()
    print(f"{dev.path}: x {dev.info.x_min}-{dev.info.x_max}, y {dev.info.y_min}-{dev.info.y_max}")
    print("Tap the top-left corner of the screen you see, then the bottom-right. Ctrl+C to stop.")
    print("The rotation whose (u, v) is ~(0,0) then ~(1,1) is the right one.\n")
    try:
        while True:
            tap = wait_for_tap(dev, r, 3600)
            if tap is None:
                continue
            row = "  ".join(f"rot{rot}: ({u:.2f},{v:.2f})"
                            for rot in (0, 90, 180, 270)
                            for u, v in [normalize(*tap, dev.info, rot)])
            print(f"raw={tap}  {row}")
    except KeyboardInterrupt:
        pass


def cmd_capture_test(cfg):
    nodes = [(cfg.capture_node, "given")] if cfg.capture_node else list_capture_nodes()
    if not nodes and not cfg.image:
        print("No gamescope PipeWire nodes found. Find the node id another way and pass --node ID.")
    for nid, name in nodes or [("-", "image")]:
        try:
            pb = pixbuf_from_bytes(capture_png(cfg, node=nid))
            try:
                ok, png = pb.save_to_bufferv("png", [], [])
                text = " ".join(ln.text for ln in ocr_lines(png, cfg))[:70]
            except RuntimeError as e:
                text = f"(OCR unavailable: {e})"
            print(f"node {nid} ({name}): {pb.get_width()}x{pb.get_height()}  text: {text or '(none)'}")
        except RuntimeError as e:
            print(f"node {nid} ({name}) failed: {e}")
            if "pipewiresrc" in str(e):
                break


def cmd_sweep(cfg, x, y):
    pb = pixbuf_from_bytes(capture_png(cfg))
    W, H = pb.get_width(), pb.get_height()
    px, py = (int(x * (W - 1)), int(y * (H - 1))) if x <= 1 and y <= 1 else (int(x), int(y))
    if resolve_engine(cfg) == "rapidocr":
        return sweep_rapid(cfg, pb, px, py)
    base = replace(cfg, engine="tesseract")
    print(f"frame {W}x{H}, region centred on ({px},{py}), engine=tesseract, lang={cfg.lang}"
          + (f", tessdata={cfg.tessdata}" if cfg.tessdata else ""), flush=True)
    for scale in (1, 2, 3):
        for inv in ("off", "on"):
            for psm in ("6", "7", "11"):
                try:
                    _, _, lines, _ = analyze(pb, px, py, replace(base, scale=scale, invert=inv, psm=psm))
                except RuntimeError as e:
                    print("error:", e)
                    return
                conf = sum(ln.conf for ln in lines) / len(lines) if lines else 0
                text = " ".join(ln.text for ln in lines).replace("\n", " ")[:70]
                print(f"scale={scale} invert={inv:<3} psm={psm:<2} conf={conf:3.0f}  {text or '(nothing)'}",
                      flush=True)


def sweep_rapid(cfg, pb, px, py):
    W, H = pb.get_width(), pb.get_height()
    print(f"frame {W}x{H}, region centred on ({px},{py}), engine=rapidocr", flush=True)
    print("(the first run of the 'server' model downloads it; that can take a while)", flush=True)
    # (model, detector thresh, box thresh, scale, region)
    variants = [("mobile", None, None, 1, "crop"),
                ("mobile", 0.2, 0.3, 1, "crop"),
                ("mobile", 0.1, 0.2, 1, "crop"),
                ("mobile", 0.2, 0.3, 2, "crop"),
                ("server", None, None, 1, "crop"),
                ("server", 0.2, 0.3, 1, "crop"),
                ("mobile", None, None, 1, "full"),
                ("server", None, None, 1, "full")]
    for model, th, bth, scale, region in variants:
        c = replace(cfg, engine="rapidocr", rapid_model=model, rapid_thresh=th, rapid_box_thresh=bth,
                    rapid_scale=scale)
        if region == "full":
            c = replace(c, crop_w=W, crop_h=H)
        label = (f"{model:<6} thresh={'default' if th is None else th:<7} "
                 f"box={'default' if bth is None else bth:<7} scale={scale} region={region:<4}")
        started = time.monotonic()
        try:
            _, _, lines, hit = analyze(pb, px, py, c)
        except Exception as e:
            print(f"{label} error: {e}", flush=True)
            continue
        conf = sum(ln.conf for ln in lines) / len(lines) if lines else 0
        text = " / ".join(ln.text for ln in lines)[:60]
        print(f"{label} {time.monotonic() - started:4.1f}s lines={len(lines):<2} conf={conf:3.0f}  "
              f"{text or '(nothing)'}" + (f"   tap->{hit.scan_text[:12]}" if hit else ""), flush=True)


def cmd_anki_check():
    if not os.path.isdir(ANKI_VENV):
        print(f"No Anki installed by this app (looked in {ANKI_VENV}).")
        return
    libs = qt_missing_libs()
    if not libs:
        print("Every system library Anki's Qt needs is present.")
        return
    print("\n".join(lib_fix(libs)[1]))


def cmd_speed_test(cfg):
    t0 = time.monotonic()
    png = capture_png(cfg)
    grab = time.monotonic() - t0
    frame = pixbuf_from_bytes(png)
    print(f"frame {frame.get_width()}x{frame.get_height()}, grabbed in {grab:.2f}s "
          "(threads 0 = all cores, side 0 = native size)", flush=True)
    print("threads  side   scan  lines  detect/read", flush=True)
    for threads in (0, 4, 5, 8):
        for side in (0, 1280, 960):
            c = replace(cfg, engine="rapidocr", rapid_threads=threads, rapid_max_side=side)
            try:
                ocr_frame(frame, c)
                t = time.monotonic()
                lines = ocr_frame(frame, c)
                took = time.monotonic() - t
            except Exception as e:
                print(f"{threads:>7}  {side:>4}  error: {e}", flush=True)
                continue
            detail = f"{LAST_TIMING['detect']:.1f}/{LAST_TIMING['read']:.1f}s" if LAST_TIMING else ""
            print(f"{threads:>7}  {side:>4}  {took:4.1f}s  {len(lines):>5}  {detail}", flush=True)


def print_analysis(cfg, lines, hit):
    print(f"engine: {resolve_engine(cfg)}")
    for ln in lines:
        box = tuple(int(v) for v in ln.box)
        print(f"  [{ln.conf:3.0f}] {ln.text}   box={box} chars={'engine' if ln.exact else 'estimated'}"
              + (" vertical" if ln.vertical else ""))
    if not lines:
        print("  (nothing recognised)")
    if hit:
        print(f"tapped char: {hit.char}   scan text: {hit.scan_text}")
        print("context:", hit.context.replace("\n", " / "))
    else:
        print("nothing near the tap")


def cmd_ocr_test(cfg, path, x, y):
    with open(path, "rb") as f:
        pb = pixbuf_from_bytes(f.read())
    _, _, lines, hit = analyze(pb, x, y, cfg)
    print_analysis(cfg, lines, hit)


def cmd_ocr_live(cfg, x, y):
    pb = pixbuf_from_bytes(capture_png(cfg))
    W, H = pb.get_width(), pb.get_height()
    px, py = (int(x * (W - 1)), int(y * (H - 1))) if x <= 1 and y <= 1 else (int(x), int(y))
    print(f"frame {W}x{H}, tap at ({px},{py})")
    _, _, lines, hit = analyze(pb, px, py, cfg)
    print_analysis(cfg, lines, hit)
