"""Tests for the first-run window."""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract

FAILED = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{extra}]" if extra and not ok else ""))
    if not ok:
        FAILED.append(label)


if not shutil.which("broadwayd"):
    print("SKIP  broadwayd isn't installed, so GTK can't be run headless here")
    sys.exit(0)
try:
    import gi
    gi.require_version("Gtk", "3.0")
except (ImportError, ValueError):
    print("SKIP  PyGObject/GTK3 isn't available")
    sys.exit(0)

work = tempfile.mkdtemp(prefix="ay-gtk-")
broadway = subprocess.Popen(["broadwayd", ":47"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(broadway.terminate)
time.sleep(1.0)
os.environ.update(GDK_BACKEND="broadway", BROADWAY_DISPLAY=":47")
os.environ.pop("DISPLAY", None)
os.environ.pop("WAYLAND_DISPLAY", None)

m = _extract.load_module(f"{work}/home")
strings = m.strings
from gi.repository import GLib, Gtk  # noqa: E402

gtk_setup = sys.modules["armada_yomitan.gtk_setup"]
outcome = {"value": None}


def widgets(root, kind):
    found = []

    def walk(w):
        if isinstance(w, kind):
            found.append(w)
        if isinstance(w, Gtk.Container):
            for child in w.get_children():
                walk(child)

    walk(root)
    return found


def window():
    return Gtk.Window.list_toplevels()[0]


def button(label):
    found = [b for b in widgets(window(), Gtk.Button) if b.get_label() == label]
    return next((b for b in found if b.is_visible()), found[0] if found else None)


def top(w):
    return w.translate_coordinates(window(), 0, 0)[1]


def labels():
    return [w.get_text() for w in widgets(window(), Gtk.Label)]


def question_text():
    asked = (strings.SETUP_CONFIRM_INSTALL, strings.SETUP_CONFIRM_QUIT, strings.SETUP_CONFIRM_QUIT_RUNNING)
    return next((w.get_text() for w in widgets(window(), Gtk.Label) if w.is_visible() and w.get_text() in asked), None)


def log_text():
    view = next(w for w in widgets(window(), Gtk.Label) if w.get_style_context().has_class("log"))
    return view.get_text()


def run(script, fake_install, blocked=False):
    m.install_components = fake_install
    steps = iter(script)

    def tick():
        try:
            next(steps)()
        except StopIteration:
            return False
        return True

    ticker = GLib.timeout_add(400, tick)
    limit = GLib.timeout_add(20000, Gtk.main_quit)
    outcome = gtk_setup.run_setup_gui(m.Config(), blocked=blocked)
    for source in (ticker, limit):
        GLib.source_remove(source)
    return outcome


seen = {}


def fake_ok(say=None, **kw):
    for text in ("Downloading the uv installer ...", "+ uv venv --system-site-packages", "Resolved 12 packages", strings.SETUP_DOWNLOADING_CHROMIUM):
        say(text)
        time.sleep(0.15)
    if "capture" in seen:
        GLib.idle_add(lambda: (after(), False)[1])
        time.sleep(0.6)


print("--- Install: live progress, then the app starts")
def before_install():
    seen["title"] = [t for t in labels() if "needs to download" in t]
    seen["install_btn"] = button(strings.SETUP_INSTALL) is not None
    seen["buttons"] = sorted(b.get_label() for b in widgets(window(), Gtk.Button) if b.is_visible())
    seen["size_idle"] = window().get_preferred_height_for_width(1240)[0]
    seen["progress_hidden"] = not any(w.is_visible() for w in widgets(window(), Gtk.ProgressBar) + widgets(window(), Gtk.ScrolledWindow))
    seen["button_height"] = button(strings.SETUP_INSTALL).get_preferred_height()[0]
    seen["log_empty"] = log_text() == ""
    button(strings.SETUP_INSTALL).clicked()


def ask_then_no():
    seen["asked"] = question_text()
    seen["install_yes_top"] = top(button(strings.YES))
    seen["install_top"] = 0
    seen["asked_buttons"] = sorted(b.get_label() for b in widgets(window(), Gtk.Button) if b.is_visible())
    button(strings.NO).clicked()


def declined():
    seen["declined_ok"] = (sorted(b.get_label() for b in widgets(window(), Gtk.Button) if b.is_visible()) == sorted([strings.SETUP_INSTALL, strings.QUIT])
                           and log_text() == "" and button(strings.SETUP_INSTALL).get_sensitive())
    button(strings.SETUP_INSTALL).clicked()
    button(strings.YES).clicked()


def during():
    seen["locked"] = not button(strings.SETUP_INSTALL).get_sensitive() and button(strings.QUIT).get_sensitive()
    seen["size_running"] = window().get_preferred_height_for_width(1240)[0]
    seen["progress_shown"] = all(w.is_visible() for w in widgets(window(), Gtk.ProgressBar) + widgets(window(), Gtk.ScrolledWindow)
                                 + [w for w in widgets(window(), Gtk.Label) if w.get_style_context().has_class("log")])


def after():
    seen["log"] = log_text()
    seen["status"] = [t for t in labels() if "Chromium" in t]


seen["capture"] = True
result = run([before_install, ask_then_no, declined, during], fake_ok)
del seen["capture"]
check("the window offers a big Install button and says what is about to happen", seen["install_btn"] and seen["title"] and seen["log_empty"], str(seen))
check("Install asks first: the question with Yes and No takes Install's place (Quit stays)", seen["asked"] == strings.SETUP_CONFIRM_INSTALL and seen["asked_buttons"] == sorted([strings.YES, strings.NO, strings.QUIT]), str(seen))
check("answering No changes nothing (Install and Quit are back, nothing started)", seen["declined_ok"], str(seen))
check("only Install and Quit are offered, and no progress is shown before it starts", seen["buttons"] == sorted([strings.SETUP_INSTALL, strings.QUIT]) and seen["progress_hidden"], str(seen))
check("once started, a progress bar, the status line and the log are visible", seen["progress_shown"], str(seen))
check("while it runs, Install is locked (no second press) and Quit still works", seen["locked"], str(seen))
check("at the bottom screen's 1240 px width the window needs no more than its 1080 px height, before and while installing",
      seen["size_idle"] <= 1080 and seen["size_running"] <= 1080, f"{seen['size_idle']} {seen['size_running']}")
check("the Install button is a big touch target: at least 9 mm (about 149 px at 420 ppi), like the page's main buttons", seen["button_height"] >= 140, str(seen["button_height"]))
check("the progress lines appear in the window as they arrive", "Resolved 12 packages" in seen["log"] and "Chromium" in seen["log"], seen["log"])
check("...and the latest one is the status line", bool(seen["status"]))
check("when the install finishes the window ends with \"installed\" (the program then restarts into the app)", result == "installed", str(result))

print("\n--- a failure: shown, and Try again works")
attempts = {"n": 0}


def fake_flaky(say=None, **kw):
    attempts["n"] += 1
    say("Downloading Chromium ...")
    if attempts["n"] == 1:
        raise RuntimeError(strings.SETUP_STEP_FAILED.format(code=2, command="uv pip install"))


def click_install():
    button(strings.SETUP_INSTALL).clicked()
    button(strings.YES).clicked()


def failed_state():
    seen["fail_labels"] = labels()
    seen["retry"] = button("Try again")
    seen["retry_enabled"] = seen["retry"] is not None and seen["retry"].get_sensitive()
    seen["fail_log"] = log_text()
    seen["retry"].clicked()
    button(strings.YES).clicked()


result = run([click_install, lambda: None, lambda: None, failed_state, lambda: None, lambda: None, lambda: None], fake_flaky)
check("the error is shown in the window (short) and the button becomes Try again", seen["retry"] is not None and any(t.startswith(strings.SETUP_FAILED.split("{")[0]) for t in seen["fail_labels"]), str(seen["fail_labels"]))
check("Try again is usable again after a failure", seen["retry_enabled"])
check("pressing Try again runs the install again, and this time the window ends \"installed\"", attempts["n"] == 2 and result == "installed", f"{attempts} {result}")

print("\n--- Quit")
def quit_tapped():
    seen["quit_top"] = top(button("Quit"))
    button("Quit").clicked()


def quit_asked():
    seen["quit_asked"] = question_text()
    seen["quit_yes_top"] = top(button(strings.YES))
    seen["quit_yes_visible_buttons"] = sorted(b.get_label() for b in widgets(window(), Gtk.Button) if b.is_visible())
    button(strings.NO).clicked()


def quit_declined():
    seen["still_open"] = button("Quit") is not None and button("Quit").is_visible()
    button("Quit").clicked()
    button(strings.YES).clicked()


result = run([quit_tapped, quit_asked, quit_declined], fake_ok)
check("Quit asks first; No keeps the window, Yes ends it with \"quit\"", seen["quit_asked"] == strings.SETUP_CONFIRM_QUIT and seen["still_open"] and result == "quit", f"{seen} {result}")
check("the question appears where the button was tapped: Quit's at the bottom of the window (Install stays), Install's at the top",
      abs(seen["quit_yes_top"] - seen["quit_top"]) < 200 and seen["quit_yes_top"] > seen["install_yes_top"] + 300
      and strings.SETUP_INSTALL in seen["quit_yes_visible_buttons"] and strings.QUIT not in seen["quit_yes_visible_buttons"], str(seen))

log_lines = open(m.LOG_PATH).read() if os.path.exists(m.LOG_PATH) else ""
check("the window records what it runs on (display, sizes) and every button press, for diagnosing touch problems on the device",
      "first-run window:" in log_lines and "screen " in log_lines and "pressed Install" in log_lines and "pressed Yes" in log_lines and "pressed Quit" in log_lines, log_lines[-400:])

print("\n--- touch: taps are decided by where the finger goes down and up (GTK doesn't click buttons for touches on the device)")
from gi.repository import Gdk


def touch(kind, x, y):
    event = Gdk.Event.new(kind)
    event.touch.x, event.touch.y = x, y
    window().emit("event", event)


def centre(b):
    x, y = b.translate_coordinates(window(), 0, 0)
    a = b.get_allocation()
    return x + a.width / 2, y + a.height / 2


def tap(b, end_dx=0, end_dy=0, start=None):
    x, y = start or centre(b)
    touch(Gdk.EventType.TOUCH_BEGIN, x, y)
    touch(Gdk.EventType.TOUCH_END, x + end_dx, y + end_dy)


def input_window_of(b):
    """The Gdk child window whose geometry is the button's (where the real display server delivers a touch on it), if there is one."""
    x, y = b.translate_coordinates(window(), 0, 0)
    a = b.get_allocation()
    for child in window().get_window().get_children():
        cx, cy = child.get_position()
        if (cx, cy, child.get_width(), child.get_height()) == (x, y, a.width, a.height):
            return child
    return None


def flags():
    return {"Install": button(strings.SETUP_INSTALL).is_visible(), "asked": question_text()}


def t_tap_install():
    tap(button(strings.SETUP_INSTALL))


def t_asked():
    seen["tap_asked"] = question_text()
    seen["tap_press_look"] = None
    tap(button(strings.NO), end_dx=600)                 # a swipe that starts on No and ends elsewhere


def t_swipe_ignored():
    seen["swipe_ignored"] = question_text() == strings.SETUP_CONFIRM_INSTALL
    tap(button(strings.NO), start=(3, 3))               # down and up on empty space
    tap(button(strings.NO))


def t_declined():
    seen["tap_no"] = question_text() is None and button(strings.SETUP_INSTALL).is_visible()
    tap(button(strings.QUIT))


def t_quit_asked():
    seen["tap_quit_asked"] = question_text() == strings.SETUP_CONFIRM_QUIT
    touch(Gdk.EventType.TOUCH_BEGIN, *centre(button(strings.YES)))
    seen["pressed_look"] = bool(button(strings.YES).get_state_flags() & Gtk.StateFlags.ACTIVE)
    touch(Gdk.EventType.TOUCH_END, *centre(button(strings.YES)))


def t_child_window_tap():
    target = button(strings.QUIT)
    child = input_window_of(target)
    seen["child_found"] = child is not None
    if child is not None:
        for kind in (Gdk.EventType.TOUCH_BEGIN, Gdk.EventType.TOUCH_END):
            event = Gdk.Event.new(kind)
            event.touch.window = child
            event.touch.x, event.touch.y = child.get_width() / 2, child.get_height() / 2
            window().emit("event", event)


def t_child_asked():
    seen["child_tap_asked"] = question_text() == strings.SETUP_CONFIRM_QUIT
    button(strings.NO).clicked()


result = run([t_tap_install, t_asked, t_swipe_ignored, t_declined, t_quit_asked], fake_ok)
run([t_child_window_tap, t_child_asked], fake_ok)
if seen["child_found"]:
    check("a touch reported relative to a button's own input window (as the display server does) is placed correctly in the window", seen["child_tap_asked"], str(seen))
else:
    print("SKIP  this display has no input windows for the buttons")
check("a tap on Install opens its question", seen["tap_asked"] == strings.SETUP_CONFIRM_INSTALL, str(seen))
check("a touch that starts on a button but ends elsewhere (a swipe), or that starts and ends on empty space, does nothing", seen["swipe_ignored"], str(seen))
check("a tap on No closes the question", seen["tap_no"], str(seen))
check("a tap on Quit opens its question; the finger down shows the button pressed; a tap on Yes ends the window",
      seen["tap_quit_asked"] and seen["pressed_look"] and result == "quit", f"{seen} {result}")

print("\n--- Quit while installing stops the install")
from armada_yomitan import toolchain
reached = {"cancelled": False, "failed_shown": False}


def fake_blocking(say=None, **kw):
    say("Downloading Chromium ...")
    end = time.time() + 8
    while time.time() < end:
        toolchain.check_cancelled()
        time.sleep(0.05)


def quit_while_running():
    seen["running_quit_asked"] = None
    button("Quit").clicked()
    seen["running_quit_asked"] = question_text()
    button(strings.YES).clicked()


result = run([click_install, lambda: None, lambda: None, quit_while_running], fake_blocking)
time.sleep(0.3)
check("the question says the install is stopped and continues next time", seen["running_quit_asked"] == strings.SETUP_CONFIRM_QUIT_RUNNING, str(seen))
check("quitting mid-install ends the window with \"quit\" and cancels the running install (no failure is reported)",
      result == "quit" and toolchain._current["cancelled"] is True, str(result))

print("\n--- blocked: the app needs root or the Decky plugin")


def blocked_look():
    seen["blocked_buttons"] = sorted(b.get_label() for b in widgets(window(), Gtk.Button) if b.is_visible())
    seen["blocked_labels"] = [w.get_text() for w in widgets(window(), Gtk.Label) if w.is_visible() and w.get_text()]
    button("Quit").clicked()


def blocked_asked():
    seen["blocked_asked"] = question_text()
    seen["blocked_asked_buttons"] = sorted(b.get_label() for b in widgets(window(), Gtk.Button) if b.is_visible())
    button(strings.NO).clicked()


def blocked_declined():
    seen["blocked_declined_buttons"] = sorted(b.get_label() for b in widgets(window(), Gtk.Button) if b.is_visible())
    button("Quit").clicked()
    button(strings.YES).clicked()


result = run([blocked_look, blocked_asked, blocked_declined], fake_ok, blocked=True)
check("while Quit asks (and after No) Install never appears: there is no way to install from here",
      strings.SETUP_INSTALL not in seen["blocked_asked_buttons"] and seen["blocked_asked_buttons"] == sorted([strings.YES, strings.NO])
      and seen["blocked_declined_buttons"] == [strings.QUIT], str(seen))
check("the message is shown, with only Quit (no Install, no progress)", seen["blocked_labels"] == [strings.NEEDS_ROOT, strings.QUIT] or
      (strings.NEEDS_ROOT in seen["blocked_labels"] and seen["blocked_buttons"] == [strings.QUIT]), str(seen))
check("Quit asks first, and Yes ends it", seen["blocked_asked"] == strings.SETUP_CONFIRM_QUIT and result == "quit", str(result))

print("\n--- as root the install also installs the system packages; if a restart is needed the window offers it")
syspackages = sys.modules["armada_yomitan.syspackages"]
real_geteuid = os.geteuid
os.geteuid = lambda: 0
system_calls = []
syspackages.install = lambda on_line=None, **kw: (system_calls.append("install"), on_line and on_line("Layering with rpm-ostree: x"), "staged")[2]
syspackages.reboot = lambda: system_calls.append("reboot")


def root_install():
    click_install()


def root_installed():
    seen["restart_offered"] = button(strings.SETUP_RESTART_DEVICE) is not None and button(strings.SETUP_RESTART_DEVICE).get_sensitive()
    seen["reboot_status"] = [w.get_text() for w in widgets(window(), Gtk.Label) if w.is_visible() and w.get_text() == strings.SETUP_REBOOT_NEEDED]
    button(strings.SETUP_RESTART_DEVICE).clicked()


def root_restart_asked():
    seen["restart_asked"] = question_text_any()
    button(strings.YES).clicked()


def root_quit():
    button("Quit").clicked()
    button(strings.YES).clicked()


def question_text_any():
    asked = (strings.SETUP_CONFIRM_RESTART, strings.SETUP_CONFIRM_INSTALL, strings.SETUP_CONFIRM_QUIT)
    return next((w.get_text() for w in widgets(window(), Gtk.Label) if w.is_visible() and w.get_text() in asked), None)


result = run([root_install, lambda: None, lambda: None, root_installed, root_restart_asked, root_quit], fake_ok)
check("the system packages were installed after the parts, in the same run", system_calls[:1] == ["install"], str(system_calls))
check("staged packages: the window stays (no restart into the app), says a restart is needed and the button becomes Restart the device",
      result == "quit" and seen["restart_offered"] and seen["reboot_status"], f"{result} {seen}")
check("the restart asks first, and Yes restarts the device", seen["restart_asked"] == strings.SETUP_CONFIRM_RESTART and "reboot" in system_calls, f"{seen} {system_calls}")
os.geteuid = real_geteuid

broadway.terminate()
print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
