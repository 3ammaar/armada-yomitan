"""The first-run install window."""

import time

from armada_yomitan import strings, syspackages
from armada_yomitan.gtk_env import prefer_x11
from armada_yomitan.installer import SetupJob
from armada_yomitan.logfile import note


def stylesheet(scale):
    """The page's look (colours, radii, control sizes) at the browser's device scale: its CSS px become device px here."""
    def px(n):
        return round(n * scale)

    return f"""
window {{ background: #15171a; color: #e8e8e8; }}
label {{ font-size: {px(16)}px; }}
label.title {{ font-size: {px(22)}px; font-weight: 600; }}
label.info {{ color: #99aaaa; }}
label.question {{ color: #e8e8e8; font-size: {px(18)}px; font-weight: 600; }}
label.status {{ color: #99aaaa; font-size: {px(14)}px; }}
button {{ min-height: {px(56)}px; padding: 0 {px(10)}px; border: none; border-radius: {px(10)}px; background: #2f6feb; background-image: none;
         box-shadow: none; text-shadow: none; color: #ffffff; font-size: {px(18)}px; font-weight: 600; }}
button:active {{ background: #5b8df0; }}
button:disabled {{ opacity: 0.4; }}
button.secondary {{ background: #3a3f47; }}
button.secondary:active {{ background: #5a606a; }}
button.danger {{ background: #b3261e; }}
button.danger:active {{ background: #d1463d; }}
progressbar trough {{ min-height: {px(6)}px; border: none; border-radius: {px(3)}px; background: #2a2e33; }}
progressbar progress {{ min-height: {px(6)}px; border: none; border-radius: {px(3)}px; background: #2f6feb; }}
scrolledwindow {{ border: 1px solid #3a3f47; border-radius: {px(6)}px; }}
scrolledwindow, scrolledwindow viewport {{ background-color: #1b1e22; }}
label.log {{ color: #99aaaa; font-family: monospace; font-size: {px(13)}px; padding: {px(6)}px; }}
"""


def run_setup_gui(cfg, blocked=False, missing=None):
    prefer_x11()
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib, Gtk, Pango

    css = Gtk.CssProvider()
    css.load_from_data(stylesheet(cfg.ui_scale).encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    margin = round(8 * cfg.ui_scale)
    result = {"value": "quit"}
    win = Gtk.Window(title=strings.APP_NAME)

    def on_destroy(*_):
        if Gtk.main_level():
            Gtk.main_quit()

    win.connect("destroy", on_destroy)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=margin)
    box.set_border_width(margin)
    win.add(box)

    def label(text, css_class):
        lb = Gtk.Label(label=text)
        lb.set_xalign(0)
        lb.set_hexpand(True)
        lb.set_line_wrap(True)
        lb.set_max_width_chars(1)
        lb.get_style_context().add_class(css_class)
        return lb

    title, info, status = label(strings.SETUP_WINDOW_TITLE, "title"), label(strings.SETUP_WINDOW_INFO, "info"), label("", "status")
    progress = Gtk.ProgressBar()
    log = label("", "log")
    log.set_max_width_chars(-1)
    log.set_yalign(0)
    log.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.add(log)
    log.show()
    scroller.set_vexpand(True)
    install = Gtk.Button(label=strings.SETUP_INSTALL)
    quit_btn = Gtk.Button(label=strings.QUIT)
    quit_btn.get_style_context().add_class("danger")

    def make_confirm():
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=margin)
        text = label("", "question")
        row = Gtk.Box(spacing=margin, homogeneous=True)
        yes_btn = Gtk.Button(label=strings.YES)
        no_btn = Gtk.Button(label=strings.NO)
        no_btn.get_style_context().add_class("secondary")
        for w in (yes_btn, no_btn):
            row.pack_start(w, True, True, 0)
        for w in (text, row):
            panel.pack_start(w, False, True, 0)
        panel.set_no_show_all(True)
        for w in (text, row, yes_btn, no_btn):
            w.show()
        return panel, text, yes_btn, no_btn

    install_confirm, install_question, install_yes, install_no = make_confirm()
    quit_confirm, quit_question, quit_yes, quit_no = make_confirm()
    middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=margin)
    for w in (progress, status):
        middle.pack_start(w, False, True, 0)
    middle.pack_start(scroller, True, True, 0)
    for w in (title, info, install, install_confirm):
        box.pack_start(w, False, True, 0)
    box.pack_start(middle, True, True, 0)
    for w in (quit_confirm, quit_btn):
        box.pack_start(w, False, True, 0)
    for w in (progress, status, scroller):
        w.set_no_show_all(True)

    running = {"on": False}

    def pulse():
        progress.pulse()
        return running["on"]

    def set_running(on):
        running["on"] = on
        if on:
            GLib.timeout_add(120, pulse)
        else:
            progress.set_fraction(0)

    def ui(fn, *args):
        GLib.idle_add(lambda: (fn(*args), False)[1])

    lines = []

    def add_line(text):
        lines.append(text)
        del lines[:-300]
        log.set_text("\n".join(lines))
        adjustment = scroller.get_vadjustment()
        GLib.idle_add(lambda: (adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size()), False)[1])
        status.set_text(text[:120])

    action = {"name": "install"}

    def finished():
        set_running(False)
        if job.reboot_needed:
            status.set_text(strings.SETUP_REBOOT_NEEDED)
            action["name"] = "restart"
            install.set_label(strings.SETUP_RESTART_DEVICE)
            install.set_sensitive(True)
            return
        result["value"] = "installed"
        Gtk.main_quit()

    def restart_device():
        try:
            syspackages.reboot()
        except RuntimeError as e:
            status.set_text(str(e)[:160])

    def failed(message):
        set_running(False)
        add_line(message)
        status.set_text(message[:160])
        install.set_label(strings.SETUP_TRY_AGAIN)
        install.set_sensitive(True)

    job = SetupJob(lambda text: ui(add_line, text), lambda: ui(finished), lambda message: ui(failed, message))

    pending = {"on_yes": None}

    def close_questions():
        for panel in (install_confirm, quit_confirm):
            panel.hide()
        if not blocked:
            install.show()
        quit_btn.show()

    def ask(button, panel, text_label, text, on_yes):
        close_questions()
        pending["on_yes"] = on_yes
        text_label.set_text(text)
        button.hide()
        panel.show()

    def answered(yes_pressed):
        close_questions()
        if yes_pressed and pending["on_yes"]:
            pending["on_yes"]()

    def start_install():
        install.set_sensitive(False)
        status.set_text(strings.SETUP_STARTING)
        for w in (progress, status, scroller):
            w.show()
        set_running(True)
        job.start()

    def quit_now():
        if running["on"]:
            job.cancel()
        win.destroy()

    def install_clicked(*_):
        if action["name"] == "restart":
            ask(install, install_confirm, install_question, strings.SETUP_CONFIRM_RESTART, restart_device)
        else:
            ask(install, install_confirm, install_question, strings.SETUP_CONFIRM_INSTALL, start_install)

    install.connect("clicked", install_clicked)
    quit_btn.connect("clicked", lambda *_: ask(quit_btn, quit_confirm, quit_question,
                                               strings.SETUP_CONFIRM_QUIT_RUNNING if running["on"] else strings.SETUP_CONFIRM_QUIT, quit_now))
    for yes_btn, no_btn in ((install_yes, install_no), (quit_yes, quit_no)):
        yes_btn.connect("clicked", lambda *_: answered(True))
        no_btn.connect("clicked", lambda *_: answered(False))
    def trace(text):
        note("first-run window: " + text)

    buttons = (install, quit_btn, install_yes, install_no, quit_yes, quit_no)
    taps = {"begins": [], "clicked_at": 0.0}
    seen_events = {"left": 40}
    tap_slop = round(15 * cfg.ui_scale)

    def button_at(x, y):
        for candidate in buttons:
            if candidate.is_visible() and candidate.get_sensitive():
                origin = candidate.translate_coordinates(win, 0, 0)
                size = candidate.get_allocation()
                if origin and origin[0] <= x < origin[0] + size.width and origin[1] <= y < origin[1] + size.height:
                    return candidate
        return None

    def set_pressed(target, on):
        if target is None:
            return
        if on:
            target.set_state_flags(Gtk.StateFlags.ACTIVE, False)
        else:
            target.unset_state_flags(Gtk.StateFlags.ACTIVE)

    def tap_click(target):
        if target is not None and time.monotonic() - taps["clicked_at"] > 0.4:
            target.clicked()
        return False

    def position(event):
        """The touch in the window's own coordinates (widgets' input windows report theirs, relative to themselves)."""
        x, y = event.touch.x, event.touch.y
        source = event.touch.window
        top = win.get_window()
        if source is not None and top is not None and source != top:
            x, y = source.get_root_coords(int(x), int(y))
            _, origin_x, origin_y = top.get_origin()
            return x - origin_x, y - origin_y
        return x, y

    def on_event(_widget, event):
        # on the device GTK receives touches but doesn't click buttons: a tap is decided by where the finger went down and up
        kind = event.type
        if kind in (Gdk.EventType.TOUCH_BEGIN, Gdk.EventType.TOUCH_END, Gdk.EventType.TOUCH_CANCEL) and seen_events["left"] > 0:
            seen_events["left"] -= 1
            x, y = position(event)
            target = button_at(x, y)
            trace(f"{event.type.value_nick} raw {event.touch.x:.0f},{event.touch.y:.0f} window {x:.0f},{y:.0f} "
                  f"on {target.get_label() if target else 'nothing'}")
        if kind == Gdk.EventType.TOUCH_BEGIN:
            x, y = position(event)
            taps["begins"].append((x, y))
            set_pressed(button_at(x, y), True)
        elif kind in (Gdk.EventType.TOUCH_END, Gdk.EventType.TOUCH_CANCEL) and taps["begins"]:
            x, y = position(event)
            start = min(taps["begins"], key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)
            taps["begins"].remove(start)
            for candidate in buttons:
                set_pressed(candidate, False)
            target = button_at(x, y)
            if kind == Gdk.EventType.TOUCH_END and target is not None and target is button_at(*start) and abs(start[0] - x) + abs(start[1] - y) <= 2 * tap_slop:
                GLib.idle_add(tap_click, target)
        return False

    def describe():
        allocation = win.get_allocation()
        trace(f"{type(Gdk.Display.get_default()).__name__}, screen {screen.get_width()}x{screen.get_height()}, "
              f"window {allocation.width}x{allocation.height}, scale {win.get_scale_factor()}, ui_scale {cfg.ui_scale}")
        return False

    def on_clicked(widget):
        taps["clicked_at"] = time.monotonic()
        trace("pressed " + widget.get_label())

    for pressed in buttons:
        pressed.connect("clicked", on_clicked)
    if blocked:
        title.set_text(missing.title() if missing else strings.NEEDS_ROOT)
        info.set_text(strings.MISSING_HEADING)
        install.set_no_show_all(True)
        install.hide()
        if missing and missing.any():
            log.set_text("\n".join(f"\u2022 {line}" for line in missing.lines()))
            scroller.set_no_show_all(False)
        else:
            info.set_no_show_all(True)
            info.hide()
    win.add_events(Gdk.EventMask.TOUCH_MASK | Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK)
    win.connect("event", on_event)
    screen = Gdk.Screen.get_default()
    win.set_default_size(screen.get_width(), screen.get_height())
    win.fullscreen()
    win.show_all()
    GLib.timeout_add(1000, describe)
    Gtk.main()
    win.destroy()
    return result["value"]
