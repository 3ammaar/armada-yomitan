"""The plain GTK window."""

import os
import select
import threading

from armada_yomitan import strings
from armada_yomitan.capture import capture_png
from armada_yomitan.console import log_error, looks_like_error
from armada_yomitan.gtk_env import prefer_x11
from armada_yomitan.ocr.engine import resolve_engine
from armada_yomitan.ocr.image import analyze, marked_pixbuf, pixbuf_from_bytes, preview_pixbuf
from armada_yomitan.ocr.rapid import warm_engine
from armada_yomitan.sessions import ScreenSession
from armada_yomitan.touch import map_touch, open_touch, wait_for_tap

CSS = b"""
button.lookup { font-size: 30px; padding: 24px; }
label.status  { font-size: 18px; color: #888888; }
"""


def run_gui(cfg):
    prefer_x11()
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

    screen_mode = cfg.mode != "tap"

    css = Gtk.CssProvider()
    css.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    win = Gtk.Window(title=strings.APP_NAME)
    win.connect("destroy", Gtk.main_quit)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_border_width(12)
    win.add(box)

    def label(css_class, selectable=False):
        lb = Gtk.Label()
        lb.set_xalign(0)
        lb.set_line_wrap(True)
        lb.set_selectable(selectable)
        lb.get_style_context().add_class(css_class)
        return lb

    btn = Gtk.Button(label=strings.SIMPLE_BTN_SCAN if screen_mode else strings.SIMPLE_BTN_IDLE)
    btn.get_style_context().add_class("lookup")
    done_btn = Gtk.Button(label=strings.SIMPLE_BTN_DONE)
    done_btn.set_sensitive(False)
    status = label("status")
    status.set_text(strings.READY)
    preview = Gtk.Image()
    quit_btn = Gtk.Button(label=strings.QUIT)
    quit_btn.connect("clicked", lambda *_: win.destroy())

    top_widgets = (btn, done_btn) if screen_mode else (btn,)
    for w in top_widgets + (status,):
        box.pack_start(w, False, False, 0)
    box.pack_start(preview, True, True, 0)
    box.pack_start(quit_btn, False, False, 0)

    def ui(fn, *args):
        GLib.idle_add(lambda: (fn(*args), False)[1])

    def say(text):
        if looks_like_error(text):
            log_error(text)
        ui(status.set_text, text)

    def render(pb, hit, none_status):
        if pb.get_width() > 1100:
            pb = pb.scale_simple(1100, int(pb.get_height() * 1100 / pb.get_width()),
                                 GdkPixbuf.InterpType.BILINEAR)
        preview.set_from_pixbuf(pb)
        if hit:
            status.set_text((strings.SIMPLE_CONFIDENCE if hit.line.exact else strings.SIMPLE_CONFIDENCE_ESTIMATED).format(
                                engine=resolve_engine(cfg), confidence=hit.line.conf))
        else:
            status.set_text(none_status)

    def warm_up():
        if resolve_engine(cfg) != "rapidocr":
            return
        say(strings.LOADING_OCR_MODEL)
        try:
            warm_engine(cfg)
            if not (screen_mode and session.active):
                say(strings.READY)
        except Exception as e:
            say(strings.OCR_MODEL_FAILED.format(error=e))

    if screen_mode:
        def on_hit(frame, px, py, hit, lines):
            try:
                pb = preview_pixbuf(frame, px, py, hit, cfg)
                ui(render, pb, hit, strings.SIMPLE_NO_TEXT_NEAR_TAP)
            except Exception as e:
                say(strings.ERROR.format(error=e))

        session = ScreenSession(cfg, say, on_hit)

        def on_scan(_):
            try:
                session.start()
            except Exception as e:
                say(strings.ERROR.format(error=e))
                return
            btn.set_label(strings.SIMPLE_BTN_RESCAN)
            done_btn.set_sensitive(True)

        def on_done(_):
            session.stop()
            btn.set_label(strings.SIMPLE_BTN_SCAN)
            done_btn.set_sensitive(False)
            status.set_text(strings.BACK_TO_GAME)

        btn.connect("clicked", on_scan)
        done_btn.connect("clicked", on_done)
        win.connect("destroy", lambda *_: session.stop())
    else:
        session = None
        state = {"busy": False}
        cancel_r, cancel_w = os.pipe()

        def show_result(crop, tap, hit, lines):
            if hit:
                l, t, r, b = hit.box
                box_ = (int(l), int(t), int(r - l), int(b - t))
            else:
                box_ = None
            pb = marked_pixbuf(crop, box_, tap)
            render(pb, hit,
                   strings.SIMPLE_NO_TEXT_NEAR_TAP if lines else
                   strings.SIMPLE_NO_TEXT_IN_REGION)

        def reset():
            state["busy"] = False
            btn.set_label(strings.SIMPLE_BTN_IDLE)

        def worker():
            dev = None
            try:
                while select.select([cancel_r], [], [], 0)[0]:
                    os.read(cancel_r, 64)
                dev = open_touch(cfg)
                dev.drain()
                if cfg.grab:
                    try:
                        dev.grab(True)
                    except OSError:
                        say(strings.TOUCH_GRAB_FAILED_TAP)
                raw = wait_for_tap(dev, cancel_r, cfg.wait_seconds)
                if cfg.grab:
                    try:
                        dev.grab(False)
                    except OSError:
                        pass
                if raw is None:
                    say(strings.CANCELLED_OR_TIMED_OUT)
                    return
                say(strings.CAPTURING_TOP_SCREEN)
                pb = pixbuf_from_bytes(capture_png(cfg))
                px, py = map_touch(*raw, dev.info, cfg.rotation, pb.get_width(), pb.get_height())
                say(strings.SIMPLE_RUNNING_OCR)
                crop, tap, lines, hit = analyze(pb, px, py, cfg)
                ui(show_result, crop, tap, hit, lines)
            except Exception as e:
                say(strings.ERROR.format(error=e))
            finally:
                if dev:
                    dev.close()
                ui(reset)

        def on_lookup(_):
            if state["busy"]:
                os.write(cancel_w, b"x")
                return
            state["busy"] = True
            btn.set_label(strings.SIMPLE_BTN_BUSY)
            status.set_text(strings.WAITING_FOR_TAP)
            threading.Thread(target=worker, daemon=True).start()

        btn.connect("clicked", on_lookup)

    threading.Thread(target=warm_up, daemon=True).start()
    win.fullscreen()
    win.show_all()
    Gtk.main()
