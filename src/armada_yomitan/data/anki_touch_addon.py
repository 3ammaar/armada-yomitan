# armada-yomitan touch helper (armada-yomitan-touch 13). armada-yomitan rewrites this file every time it starts Anki.
# Touch helper for Anki on the Thor's bottom screen: close strip, on-screen keyboard and a socket taking show, hide, quit and ping.
import atexit
import os
import socket
import sys
import threading
import time
import traceback


def _log(text):
    print("[armada-yomitan touch] " + text, file=sys.stderr, flush=True)


TEXT = __ADDON_TEXTS__

BAR = 44            # height of the strip, in Qt's (already scaled) pixels
BAR_CSS = '''
#armadaYomitanBar { background: #1f2933; }
#armadaYomitanBar QLabel { color: #e4e7eb; font-size: 15px; padding-left: 8px; }
#armadaYomitanBar QToolButton { background: #3e4c59; color: #ffffff; border: none; border-radius: 8px;
                          padding: 0 18px; font-size: 16px; font-weight: 600; }
#armadaYomitanBar QToolButton:pressed { background: #616e7c; }
'''
KBD_CSS = '''
#armadaYomitanKbd { background: #1f2933; }
#armadaYomitanKbd QPushButton { background: #3e4c59; color: #ffffff; border: none; border-radius: 6px;
                          font-size: 17px; padding: 0; }
#armadaYomitanKbd QPushButton[special="true"] { background: #2b3a47; font-size: 14px; }
#armadaYomitanKbd QPushButton[on="true"] { background: #2f6feb; }
#armadaYomitanKbd QPushButton:pressed { background: #7b8794; }
'''
KBD_JS = '''<script>
(function () {
  if (window.__armadaYomitanKbd) return;
  window.__armadaYomitanKbd = 1;
  var send = function (v) { try { (window.pycmd || window.bridgeCommand)('armada_yomitan_kbd:' + v); } catch (e) {} };
  var editable = function (el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.isContentEditable) return true;
    if (el.tagName === 'TEXTAREA') return !el.readOnly && !el.disabled;
    if (el.tagName === 'INPUT')
      return !el.readOnly && !el.disabled && !/^(button|checkbox|radio|submit|reset|file|image|range|color)$/i.test(el.type);
    return false;
  };
  var target = function (e) { return (e.composedPath && e.composedPath()[0]) || e.target; };
  document.addEventListener('focusin', function (e) { send(editable(target(e)) ? '1' : '0'); }, true);
  document.addEventListener('focusout', function () { send('0'); }, true);
})();
</script>'''
LETTER_ROWS = ('qwertyuiop', 'asdfghjkl', 'zxcvbnm')
SYMBOL_ROWS = ('1234567890', '@#$&*-+=_%', '()/:;!?' + chr(39) + chr(34))


def keyboard_rows(layer, shift):
    # Each key: (label, action, width); action None = blank space. Rows are 20 units wide.
    def letters(chars):
        return [((c.upper() if shift else c), ('text', c.upper() if shift else c), 2) for c in chars]
    if layer == 'abc':
        rows = [letters(LETTER_ROWS[0]),
                [('', None, 1)] + letters(LETTER_ROWS[1]) + [('', None, 1)],
                [('Shift', ('shift',), 3)] + letters(LETTER_ROWS[2]) + [('Del', ('key', 'backspace'), 3)]]
    else:
        def plain(chars):
            return [(c, ('text', c), 2) for c in chars]
        rows = [plain(SYMBOL_ROWS[0]),
                [('', None, 1)] + plain(SYMBOL_ROWS[1]) + [('', None, 1)],
                [('', None, 0)] + plain(SYMBOL_ROWS[2]) + [('Del', ('key', 'backspace'), 2)]]
    rows.append([('123' if layer == 'abc' else 'abc', ('layer', 'sym' if layer == 'abc' else 'abc'), 3),
                 (',', ('text', ','), 2), ('Space', ('key', 'space'), 7), ('.', ('text', '.'), 2),
                 ('Enter', ('key', 'enter'), 3), ('Hide', ('hide',), 3)])
    return rows


TOUCH_CSS = '''
QMenu::item { padding: 9px 26px 9px 18px; }
QMenu::item:selected { background: palette(highlight); color: palette(highlighted-text); }
QMenuBar::item { padding: 8px 12px; }
QMenuBar::item:selected { background: palette(highlight); color: palette(highlighted-text); }
'''
_KEEP = []


def _setup():
    import aqt
    from aqt import gui_hooks
    from aqt.qt import (QApplication, QColorDialog, QDialog, QEvent, QFileDialog, QFontDialog, QGuiApplication,
                        QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox, QObject, QProgressDialog,
                        QSizePolicy, Qt, QToolButton, QWidget, pyqtSignal,
                        QAbstractSpinBox, QComboBox, QKeyEvent, QLineEdit, QPlainTextEdit, QPushButton, QTextEdit, QTimer,
                        QVBoxLayout)

    app = QApplication.instance()
    if app is None:
        return
    skip = (QMessageBox, QProgressDialog, QInputDialog, QFileDialog, QColorDialog, QFontDialog)
    window_types = (Qt.WindowType.Window, Qt.WindowType.Dialog)
    no_border = Qt.WindowType.FramelessWindowHint | Qt.WindowType.X11BypassWindowManagerHint

    hidden = []

    background = {"held": os.environ.get("ARMADA_YOMITAN_ANKI_BACKGROUND") == "1", "windows": []}
    dont_show = Qt.WidgetAttribute.WA_DontShowOnScreen

    def hold(w):
        # Called before a window is mapped (its Polish event comes first): the widget works and paints as usual, only not on screen.
        if background["held"] and isinstance(w, QWidget) and w.isWindow() and not w.testAttribute(dont_show):
            w.setAttribute(dont_show, True)
            background["windows"].append(w)

    def release_held():
        if not background["held"]:
            return
        background["held"] = False
        for w in background["windows"]:
            try:
                w.setAttribute(dont_show, False)
                if not w.isVisible():
                    continue
                if w.isModal():                      # a dialog waiting inside exec(): hide() would dismiss it, so re-create its window
                    w.setWindowFlags(w.windowFlags())
                    w.show()
                elif w not in hidden:
                    w.hide()
                    hidden.append(w)
            except RuntimeError:
                pass
        background["windows"].clear()
        main = getattr(aqt, "mw", None)
        hidden.sort(key=lambda w: w is not main)

    def has(flags, flag):
        return (flags & flag) == flag

    def visible_windows():
        wins = []
        for w in QApplication.topLevelWidgets():
            try:
                if w.isVisible() and isinstance(w, (QMainWindow, QDialog)) and not isinstance(w, skip):
                    wins.append(w)
            except RuntimeError:
                pass
        main = getattr(aqt, "mw", None)
        wins.sort(key=lambda w: w is not main)
        return wins

    def hide_all(*_args):
        detach_keyboard()
        wins = visible_windows()
        if wins:
            hidden[:] = wins
        for w in wins:
            w.hide()

    def show_all(*_args):
        release_held()
        wins = []
        for w in hidden:
            try:
                w.isVisible()
                wins.append(w)
            except RuntimeError:
                pass
        hidden.clear()
        wins = wins or visible_windows() or [aqt.mw]
        for w in wins:
            w.show()
        wins[-1].raise_()
        wins[-1].activateWindow()

    def quit_anki(*_args):
        aqt.mw.close()

    commands = {"show": show_all, "hide": hide_all, "quit": quit_anki}

    def fit(w):
        # No window manager places windows, so make the big ones fill the screen and centre the small ones.
        screen = w.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        if isinstance(w, QMainWindow) or w.width() > area.width() * 0.6 or w.height() > area.height() * 0.6:
            w.setGeometry(area)
        else:
            w.move(area.center() - w.rect().center())

    def adopt(w):
        if getattr(w, "_armada_yomitan_seen", False):
            return
        w._armada_yomitan_seen = True
        if not isinstance(w, (QMainWindow, QDialog)) or isinstance(w, skip):
            return
        flags = w.windowFlags()
        if w.windowType() not in window_types or (flags & no_border):
            return
        if has(flags, Qt.WindowType.CustomizeWindowHint) and not has(flags, Qt.WindowType.WindowCloseButtonHint):
            return                                   # a window that deliberately has no close button (progress boxes)
        is_main = w is getattr(aqt, "mw", None)
        fit(w)
        bar = QWidget(w)
        bar.setObjectName("armadaYomitanBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setStyleSheet(BAR_CSS)
        row = QHBoxLayout(bar)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(8)
        title = QLabel(w.windowTitle() or (TEXT["ADDON_MAIN_TITLE"] if is_main else ""), bar)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        button = QToolButton(bar)
        button.setText(TEXT["ADDON_BACK_TO_OCR"] if is_main else TEXT["ADDON_CLOSE"])
        button.setMinimumHeight(BAR - 8)
        button.clicked.connect(hide_all if is_main else w.close)
        row.addWidget(title, 1)
        row.addWidget(button, 0)
        margins = w.contentsMargins()
        w._armada_yomitan_base_bottom = margins.bottom()
        w.setContentsMargins(margins.left(), margins.top() + BAR, margins.right(), margins.bottom())
        w._armada_yomitan_bar = bar
        w._armada_yomitan_title = title
        bar.setGeometry(0, 0, w.width(), BAR)
        bar.show()
        bar.raise_()

    # ---- the on-screen keyboard: a child widget of the window being typed into (a separate window would make the
    # compositor switch to it), which takes room from the window's contents instead of covering them
    kbd = {"widget": None, "host": None, "web": False, "web_window": None, "field": None, "tapped": None,
           "tap": 0.0, "gen": 0}
    Key = Qt.Key
    keycodes = {"backspace": (Key.Key_Backspace, "\b"), "enter": (Key.Key_Return, "\r"), "space": (Key.Key_Space, " ")}
    debug = os.environ.get("ARMADA_YOMITAN_ANKI_KEYBOARD_DEBUG") == "1"

    def dbg(text):
        if debug:
            _log(text)

    def describe(w):
        try:
            return "%s%s in %r" % (type(w).__name__, ("#" + w.objectName()) if w.objectName() else "", w.window().windowTitle())
        except (RuntimeError, AttributeError):
            return repr(w)

    def is_text_widget(w):
        try:
            if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit)):
                return not w.isReadOnly()
            return isinstance(w, QAbstractSpinBox)
        except RuntimeError:
            return False

    def text_target(obj):
        try:
            if is_text_widget(obj):
                return obj
            if isinstance(obj, QComboBox) and obj.isEditable() and is_text_widget(obj.lineEdit()):
                return obj.lineEdit()
        except RuntimeError:
            pass
        return None

    def field_widget():
        field = kbd["field"]
        if field is None:
            return None
        try:
            return field if field.isVisible() else None
        except RuntimeError:
            kbd["field"] = None
            return None

    def keyboard_visible():
        try:
            return kbd["widget"] is not None and kbd["widget"].isVisible()
        except RuntimeError:
            return False

    def web_alive():
        if not kbd["web"]:
            return False
        try:
            if kbd["web_window"] is not None and kbd["web_window"].isVisible():
                return True
        except RuntimeError:
            pass
        kbd["web"] = False
        kbd["web_window"] = None
        return False

    def native_wanted():
        field = field_widget()
        if field is None or not is_text_widget(field):
            return False
        try:
            focused = QApplication.focusWidget()
            # Qt's idea of the focus is only trusted when it's about this field's own window: with no window manager
            # a window can be in use without Qt ever having been told it is the active one
            return (focused is None or focused is field or is_text_widget(focused)
                    or focused.window() is not field.window())
        except RuntimeError:
            return False

    def want_keyboard():
        return web_alive() or native_wanted()

    def recent_tap():
        return time.monotonic() - kbd["tap"] < 1.0

    def over_keyboard(event):
        # Is this touch within the keyboard's area? Judged by where it is, because an event nobody handles is passed
        # on to the window behind, and that window would take it for a touch elsewhere.
        k = kbd["widget"]
        if k is None:
            return False
        try:
            if hasattr(event, "globalPosition"):
                point = event.globalPosition().toPoint()
            else:
                point = event.points()[0].globalPosition().toPoint()
            return bool(k.isVisible() and k.rect().contains(k.mapFromGlobal(point)))
        except Exception:
            return False

    def in_keyboard(w):
        try:
            while w is not None:
                if getattr(w, "_armada_yomitan_is_kbd", False):
                    return True
                w = w.parent()
        except (RuntimeError, AttributeError, TypeError):
            pass
        return False

    def send_key(code, text="", mods=Qt.KeyboardModifier.NoModifier):
        field, focused = field_widget(), QApplication.focusWidget()
        if field is not None and is_text_widget(field):
            target = field
        elif focused is not None and (field is None or focused.window() is field.window()):
            target = focused
        else:
            target = field or focused
        if target is None:
            return
        code = int(getattr(code, "value", code))
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(target, QKeyEvent(kind, code, mods, text))

    class Keyboard(QWidget):
        def __init__(self, host):
            QWidget.__init__(self, host)
            self._armada_yomitan_is_kbd = True
            self.setObjectName("armadaYomitanKbd")
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.setStyleSheet(KBD_CSS)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.layer, self.shift = "abc", False
            self.keys = []
            self.held, self.repeated, self.hold = None, False, 0
            self.column = QVBoxLayout(self)
            self.column.setContentsMargins(4, 4, 4, 4)
            self.column.setSpacing(4)
            self.render()

        def nearest_key(self, pos):
            # A touch that isn't on a key (in the gaps between keys and between rows, beside the ends of the shorter rows,
            # around the edge) counts as a touch on the nearest key, so there are no dead spots on the keyboard.
            best, best_d = None, None
            px, py = pos.x(), pos.y()
            for b in self.keys:
                try:
                    corner, w, h = b.mapTo(self, b.rect().topLeft()), b.width(), b.height()
                except RuntimeError:
                    continue
                dx = max(corner.x() - px, 0, px - (corner.x() + w))
                dy = max(corner.y() - py, 0, py - (corner.y() + h))
                d = dx * dx + dy * dy
                if best_d is None or d < best_d:
                    best, best_d = b, d
            return best

        def mousePressEvent(self, event):
            event.accept()
            self.hold += 1
            key = self.held = self.nearest_key(event.position())
            self.repeated = False
            if key is None:
                return
            key.setDown(True)
            if key.autoRepeat():
                self.repeated = True
                key.click()
                key.setDown(True)
                gen = self.hold
                QTimer.singleShot(400, lambda: self.repeat(gen))

        def repeat(self, gen):
            key = self.held
            if key is None or gen != self.hold:
                return
            try:
                key.click()
                key.setDown(True)
            except RuntimeError:
                self.held = None
                return
            QTimer.singleShot(60, lambda: self.repeat(gen))

        def mouseReleaseEvent(self, event):
            event.accept()
            key, self.held = self.held, None
            self.hold += 1
            if key is None:
                return
            try:
                key.setDown(False)
                if not self.repeated and self.nearest_key(event.position()) is key:
                    key.click()
            except RuntimeError:
                pass

        def mouseMoveEvent(self, event):
            event.accept()

        def mouseDoubleClickEvent(self, event):
            self.mousePressEvent(event)

        def render(self):
            self.keys = []
            self.held = None
            while self.column.count():
                item = self.column.takeAt(0)
                old = item.widget()
                if old is not None:
                    old.hide()
                    old.deleteLater()
            for spec in keyboard_rows(self.layer, self.shift):
                row = QWidget(self)
                row.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                line = QHBoxLayout(row)
                line.setContentsMargins(0, 0, 0, 0)
                line.setSpacing(4)
                for label, action, width in spec:
                    if action is None:
                        if width:
                            line.addStretch(width)
                        continue
                    button = QPushButton(label, row)
                    self.keys.append(button)
                    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                    if action[0] != "text":
                        button.setProperty("special", "true")
                    if action == ("shift",) and self.shift:
                        button.setProperty("on", "true")
                    if action == ("key", "backspace"):
                        button.setAutoRepeat(True)
                        button.setAutoRepeatDelay(400)
                        button.setAutoRepeatInterval(60)
                    button.clicked.connect(lambda _checked=False, a=action: self.press(a))
                    line.addWidget(button, width)
                self.column.addWidget(row, 1)

        def press(self, action):
            kind = action[0]
            if kind == "text":
                ch = action[1]
                if ch.isalpha():
                    send_key(ord(ch.upper()), ch, Qt.KeyboardModifier.ShiftModifier if ch.isupper() else Qt.KeyboardModifier.NoModifier)
                else:
                    send_key(ord(ch), ch)
                if self.shift:
                    self.shift = False
                    self.render()
            elif kind == "key":
                code, text = keycodes[action[1]]
                send_key(code, text)
            elif kind == "shift":
                self.shift = not self.shift
                self.render()
            elif kind == "layer":
                self.layer = action[1]
                self.render()
            elif kind == "hide":
                detach_keyboard()

    def keyboard_of(w):
        k = getattr(w, "_armada_yomitan_kbd", None)
        if k is None:
            return None
        try:
            k.isVisible()
            return k
        except RuntimeError:
            w._armada_yomitan_kbd = None
            w._armada_yomitan_kbd_h = 0
            return None

    def apply_margins(w):
        base = getattr(w, "_armada_yomitan_base_bottom", None)
        if base is None:
            return False
        want = base + (getattr(w, "_armada_yomitan_kbd_h", 0) if keyboard_of(w) is not None else 0)
        m = w.contentsMargins()
        if m.bottom() == want:
            return False
        w.setContentsMargins(m.left(), m.top(), m.right(), want)
        return True

    def sweep():
        for w in QApplication.topLevelWidgets():
            try:
                if w is not kbd["host"] and apply_margins(w):
                    _log("gave back leftover keyboard space on " + (w.windowTitle() or type(w).__name__))
            except RuntimeError:
                pass

    def place_keyboard(host):
        k = keyboard_of(host)
        if k is None:
            return
        area = (host.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        height = host._armada_yomitan_kbd_h
        bottom = min(host.height(), area.height() - host.y())
        k.setGeometry(0, bottom - height, host.width(), height)
        k.raise_()

    def detach_keyboard():
        k, host = kbd["widget"], kbd["host"]
        kbd["widget"] = kbd["host"] = None
        if k is not None:
            try:
                k.hide()
                k.deleteLater()
            except RuntimeError:
                pass
        if host is not None:
            try:
                host._armada_yomitan_kbd = None
                host._armada_yomitan_kbd_h = 0
                apply_margins(host)
                geo = getattr(host, "_armada_yomitan_kbd_geo", None)
                if geo is not None:
                    host._armada_yomitan_kbd_geo = None
                    host.setGeometry(geo)
            except RuntimeError:
                pass
        sweep()

    def show_keyboard():
        kbd["gen"] += 1
        target = field_widget() or QApplication.focusWidget()
        host = target.window() if target is not None else QApplication.activeWindow()
        if host is None or not isinstance(host, (QMainWindow, QDialog)):
            dbg("no window to put the keyboard in (%s)" % (describe(target) if target is not None else "no target"))
            return
        if keyboard_visible() and kbd["host"] is host:
            return
        detach_keyboard()
        area = (host.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        height = int(max(150, min(260, area.height() * 0.4)))
        widget = Keyboard(host)
        if getattr(host, "_armada_yomitan_base_bottom", None) is None:
            host._armada_yomitan_base_bottom = host.contentsMargins().bottom()
        if host.width() < area.width() * 0.95 or host.height() < area.height() * 0.95:
            host._armada_yomitan_kbd_geo = host.geometry()
            host.setGeometry(area)
        host._armada_yomitan_kbd_h = height
        host._armada_yomitan_kbd = widget
        kbd["widget"], kbd["host"] = widget, host
        apply_margins(host)
        widget.show()
        place_keyboard(host)
        dbg("keyboard up in %r for %s" % (host.windowTitle(), describe(target)))

    def hide_keyboard_later():
        kbd["gen"] += 1
        gen = kbd["gen"]

        def later():
            if gen == kbd["gen"] and not want_keyboard():
                dbg("keyboard hidden: nothing is being typed into")
                detach_keyboard()
        QTimer.singleShot(300, later)

    def on_focus_changed(_old, new):
        if is_text_widget(new):
            kbd["field"] = new
            if recent_tap() or keyboard_visible():
                show_keyboard()
        else:
            try:
                if new is not None and kbd["web_window"] is not None and new.window() is not kbd["web_window"]:
                    kbd["web"] = False
            except RuntimeError:
                kbd["web"] = False
            hide_keyboard_later()

    def web_editable(on):
        kbd["web"] = on
        widget = None
        if on:
            widget = kbd["tapped"] if recent_tap() else None
            widget = widget or QApplication.focusWidget()
        try:
            kbd["web_window"] = widget.window() if widget is not None else None
        except RuntimeError:
            kbd["web_window"] = None
        dbg("page says a field %s (%s)" % ("has focus" if on else "lost focus", describe(widget) if widget is not None else "?"))
        if on:
            kbd["field"] = widget
            if recent_tap() or keyboard_visible():
                show_keyboard()
        else:
            hide_keyboard_later()

    def field_tapped(field):
        try:
            if kbd["field"] is field and is_text_widget(field) and field.isVisible():
                show_keyboard()
        except RuntimeError:
            pass

    def on_tap(obj, kind):
        if not isinstance(obj, QWidget) or in_keyboard(obj):
            return
        kbd["tap"] = time.monotonic()
        kbd["tapped"] = obj
        sweep()
        field = text_target(obj)
        dbg("tap on %s -> %s" % (describe(obj), "text field" if field is not None else "not a text field"))
        if field is not None:
            kbd["field"] = field
            QTimer.singleShot(200, lambda: field_tapped(field))
        elif kind == QEvent.Type.MouseButtonPress and not web_alive():
            kbd["field"] = None
            hide_keyboard_later()

    class Touch(QObject):
        def eventFilter(self, obj, event):
            try:
                kind = event.type()
                if kind == QEvent.Type.Polish:
                    hold(obj)
                elif kind == QEvent.Type.Show:
                    if isinstance(obj, QWidget) and obj.isWindow():
                        adopt(obj)
                        if keyboard_enabled:
                            sweep()
                elif kind == QEvent.Type.Resize:
                    bar = getattr(obj, "_armada_yomitan_bar", None)
                    if bar is not None:
                        bar.setGeometry(0, 0, obj.width(), BAR)
                        bar.raise_()
                    if getattr(obj, "_armada_yomitan_kbd", None) is not None:
                        place_keyboard(obj)
                elif kind in (QEvent.Type.MouseButtonPress, QEvent.Type.TouchBegin):
                    if keyboard_enabled and not over_keyboard(event):
                        on_tap(obj, kind)
                elif kind == QEvent.Type.WindowTitleChange:
                    title = getattr(obj, "_armada_yomitan_title", None)
                    if title is not None:
                        title.setText(obj.windowTitle())
            except Exception:
                _log(traceback.format_exc(limit=2))
            return False

    keyboard_enabled = os.environ.get("ARMADA_YOMITAN_ANKI_KEYBOARD") != "0"
    touch = Touch(app)
    _KEEP.append(touch)
    app.installEventFilter(touch)
    for _w in QApplication.topLevelWidgets():
        try:
            if not _w.isVisible():
                hold(_w)
        except RuntimeError:
            pass

    class Bridge(QObject):
        command = pyqtSignal(str)                    # emitted from the socket thread, handled on Qt's main thread

    def run_command(word):
        try:
            commands[word]()
        except Exception:
            _log(traceback.format_exc(limit=3))

    def serve(path):
        try:
            try:
                os.unlink(path)
            except OSError:
                pass
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(path)
            os.chmod(path, 0o600)
            srv.listen(4)
            atexit.register(lambda: os.path.exists(path) and os.unlink(path))
        except OSError as e:
            _log("can't listen on %s: %s" % (path, e))
            return
        while True:
            conn, _addr = srv.accept()
            try:
                conn.settimeout(2)
                word = conn.recv(32).decode("ascii", "ignore").strip()
                if word in commands:
                    bridge.command.emit(word)
                    conn.sendall(b"ok\n")
                elif word == "ping":
                    conn.sendall(b"ok\n")
                elif word == "visible":
                    conn.sendall(b"no\n" if hidden else b"yes\n")
                else:
                    conn.sendall(b"unknown\n")
            except Exception:
                pass
            finally:
                conn.close()

    sock_path = os.environ.get("ARMADA_YOMITAN_ANKI_SOCK")
    if sock_path:
        bridge = Bridge(app)
        bridge.command.connect(run_command)
        _KEEP.append(bridge)
        threading.Thread(target=serve, args=(sock_path,), daemon=True).start()

    def touch_style(*_args):
        try:
            if TOUCH_CSS not in app.styleSheet():    # Anki rewrites the app style when the theme changes
                app.setStyleSheet(app.styleSheet() + TOUCH_CSS)
        except Exception:
            _log(traceback.format_exc(limit=2))

    def sync_scale(*_args):
        # Anki reads its UI size only at start-up: keep the saved one in step with armada-yomitan's
        want = os.environ.get("ARMADA_YOMITAN_ANKI_SCALE_TARGET")
        if not want:
            return
        try:
            want = float(want)
            pm = aqt.mw.pm
            if abs(pm.uiScale() - want) > 0.01:
                pm.setUiScale(want)
                pm.save()
                _log("Anki's UI size is now %g; it takes effect the next time Anki starts." % want)
        except Exception:
            _log(traceback.format_exc(limit=2))

    if keyboard_enabled:
        app.focusChanged.connect(on_focus_changed)

        def add_keyboard_js(web_content, context):
            if type(context).__name__ in ("DeckBrowser", "Overview", "Toolbar", "BottomBar"):
                return
            try:
                web_content.body += KBD_JS
            except Exception:
                _log(traceback.format_exc(limit=2))

        def on_js_message(handled, message, _context):
            if isinstance(message, str) and message.startswith("armada_yomitan_kbd:"):
                web_editable(message.endswith(":1"))
                return (True, None)
            return handled

        gui_hooks.webview_will_set_content.append(add_keyboard_js)
        gui_hooks.webview_did_receive_js_message.append(on_js_message)

    gui_hooks.main_window_did_init.append(touch_style)
    gui_hooks.main_window_did_init.append(sync_scale)
    theme_changed = getattr(gui_hooks, "theme_did_change", None)
    if theme_changed is not None:
        theme_changed.append(touch_style)


try:
    _setup()
except Exception:
    _log("could not start:\n" + traceback.format_exc())
