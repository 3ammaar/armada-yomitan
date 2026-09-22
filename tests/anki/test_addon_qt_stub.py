"""Tests for the Anki add-on against a stand-in Qt."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract
import sys, types, io, contextlib

# ---------- a small stand-in for the bits of Qt/aqt the add-on uses (checks the add-on's logic, not real Qt)
class Pt:
    def __init__(s, x, y): s._x, s._y = x, y
    def x(s): return s._x
    def y(s): return s._y
    def toPoint(s): return s
    def __sub__(s, o): return Pt(s._x - o._x, s._y - o._y)
class Rect:
    def __init__(s, x, y, w, h): s.x, s.y, s.w, s.h = x, y, w, h
    def width(s): return s.w
    def height(s): return s.h
    def center(s): return Pt(s.x + s.w // 2, s.y + s.h // 2)
    def topLeft(s): return Pt(s.x, s.y)
    def contains(s, p): return s.x <= p.x() < s.x + s.w and s.y <= p.y() < s.y + s.h
class Margins:
    def __init__(s, l=0, t=0, r=0, b=0): s.v = (l, t, r, b)
    def left(s): return s.v[0]
    def top(s): return s.v[1]
    def right(s): return s.v[2]
    def bottom(s): return s.v[3]
class Qt:
    class Key: Key_Backspace, Key_Return, Key_Space = 0x01000003, 0x01000004, 0x20
    class KeyboardModifier: NoModifier, ShiftModifier = 0, 0x02000000
    class FocusPolicy: NoFocus = 0
    class WindowType: Window, Dialog, Popup, FramelessWindowHint, X11BypassWindowManagerHint, CustomizeWindowHint, WindowCloseButtonHint = 1, 2, 4, 8, 16, 32, 64
    class WidgetAttribute: WA_StyledBackground, WA_DontShowOnScreen = 1, 2
class QEvent:
    class Type: Show, Resize, WindowTitleChange, MouseButtonPress, TouchBegin, KeyPress, KeyRelease, Polish = "show", "resize", "title", "press", "touch", "keydown", "keyup", "polish"
class Ev:
    def __init__(s, t, local=None, glob=None):
        s._t, s.accepted = t, False
        s._local = Pt(*local) if local else None; s._glob = Pt(*glob) if glob else None
    def type(s): return s._t
    def accept(s): s.accepted = True
    def position(s): return s._local
    def globalPosition(s):
        if s._glob is None: raise AttributeError("no position")
        return s._glob
class _Sig2:
    def __init__(s): s.slots = []
    def connect(s, f): s.slots.append(f)
    def emit(s, *a): [f(*a) for f in s.slots]
class pyqtSignal:
    def __init__(s, *t): pass
    def __set_name__(s, owner, name): s.name = name
    def __get__(s, obj, owner=None): return s if obj is None else obj.__dict__.setdefault("_sig_" + s.name, _Sig2())
ALL = []
class QObject:
    def __init__(s, parent=None):
        s._parent = parent; s.kids = []
        if parent is not None: parent.kids.append(s)
        elif isinstance(s, QWidget): ALL.append(s)
class Screen:
    def availableGeometry(s): return Rect(0, 0, 620, 540)
class QGuiApplication:
    @staticmethod
    def primaryScreen(): return Screen()
class Sig:
    def __init__(s): s.slots = []
    def connect(s, f): s.slots.append(f)
    def fire(s): [f() for f in s.slots]
class QWidget(QObject):
    wtype = Qt.WindowType.Window
    def __init__(s, parent=None):
        super().__init__(parent); s._margins = Margins(); s._geo = Rect(0, 0, 100, 100); s._title = ""; s._flags = 0; s.closed = 0; s.shown = False
    def parent(s): return s._parent
    def objectName(s): return getattr(s, 'name', '')
    def isWindow(s): return s._parent is None
    def windowFlags(s): return s._flags
    def windowType(s): return s.wtype
    def contentsMargins(s): return s._margins
    def setContentsMargins(s, l, t, r, b): s._margins = Margins(l, t, r, b)
    def width(s): return s._geo.w
    def height(s): return s._geo.h
    def rect(s): return Rect(0, 0, s._geo.w, s._geo.h)
    def screen(s): return Screen()
    def setGeometry(s, *a): s._geo = a[0] if len(a) == 1 else Rect(*a)
    def move(s, p): s.pos = (p.x(), p.y())
    def windowTitle(s): return s._title
    def setObjectName(s, n): s.name = n
    def setAttribute(s, attr, on=True): s.__dict__.setdefault("attrs", {})[attr] = on
    def testAttribute(s, attr): return s.__dict__.get("attrs", {}).get(attr, False)
    def isModal(s): return getattr(s, "modal", False)
    def setWindowFlags(s, flags): s._flags = flags; s.shown = False; s.on_screen = False; s._explicit = False   # Qt hides the widget when its flags change
    def setStyleSheet(s, css): s.css = css
    def show(s):
        s.shown = True; s._explicit = True
        s.on_screen = not s.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)     # a widget with that attribute is "shown" but never mapped
        s.ever_on_screen = getattr(s, "ever_on_screen", False) or s.on_screen
    def hide(s): s.shown = False; s._explicit = False; s.on_screen = False
    def isVisible(s):
        if getattr(s, "deleted", False): raise RuntimeError("wrapped C/C++ object has been deleted")
        if s._parent is None or getattr(s, "_explicit", None) is not None: return s.shown
        return s._parent.isVisible()
    def activateWindow(s): s.active = True
    def raise_(s): s.raised = getattr(s, "raised", 0) + 1
    def close(s): s.closed += 1
    def setSizePolicy(s, *a): pass
    def _origin(s):
        x, y = s._geo.x, s._geo.y
        if s._parent is not None: px, py = s._parent._origin(); x, y = x + px, y + py
        return x, y
    def mapFromGlobal(s, p): ox, oy = s._origin(); return Pt(p.x() - ox, p.y() - oy)
    def mapTo(s, anc, p):
        x, y, w = p.x(), p.y(), s
        while w is not anc: x, y, w = x + w._geo.x, y + w._geo.y, w._parent
        return Pt(x, y)
    def setFocusPolicy(s, p): s.focuspolicy = p
    def setProperty(s, k, v): s.__dict__.setdefault("props", {})[k] = v
    def deleteLater(s): s.gone = True; s.shown = False; s._explicit = False
    def geometry(s): return s._geo
    def y(s): return 0
    def window(s):
        w = s
        while w._parent is not None: w = w._parent
        return w
    def setParent(s, p): s._parent = p
    def setMinimumHeight(s, h): s.minh = h
class QMainWindow(QWidget): pass
class QDialog(QWidget): wtype = Qt.WindowType.Dialog
class QMessageBox(QDialog): pass
class QProgressDialog(QDialog): pass
class QInputDialog(QDialog): pass
class QFileDialog(QDialog): pass
class QColorDialog(QDialog): pass
class QFontDialog(QDialog): pass
class QLineEdit(QWidget):
    ro = False
    def isReadOnly(s): return s.ro
class QTextEdit(QLineEdit): pass
class QPlainTextEdit(QLineEdit): pass
class QAbstractSpinBox(QWidget): pass
class QComboBox(QWidget):
    editable = True
    def isEditable(s): return s.editable
    def lineEdit(s):
        if not hasattr(s, "_le"): s._le = QLineEdit(s)
        return s._le
class QPushButton(QWidget):
    def __init__(s, text="", parent=None): super().__init__(parent); s.text = text; s.clicked = Sig(); s.repeat = False
    def setAutoRepeat(s, on): s.repeat = on
    def autoRepeat(s): return s.repeat
    def setDown(s, on): s.down = on
    def click(s): s.down = False; s.clicked.fire()
    def setAutoRepeatDelay(s, n): pass
    def setAutoRepeatInterval(s, n): pass
class QKeyEvent:
    def __init__(s, kind, code, mods, text=""): s.kind, s.code, s.mods, s.text = kind, code, mods, text
TIMERS = []
class QTimer:
    @staticmethod
    def singleShot(ms, fn): TIMERS.append(fn)
class QLabel(QWidget):
    def __init__(s, text="", parent=None): super().__init__(parent); s.text = text
    def setText(s, t): s.text = t
class QToolButton(QWidget):
    def __init__(s, parent=None): super().__init__(parent); s.clicked = Sig()
    def setText(s, t): s.text = t
class _Item:
    def __init__(s, w): s.w = w
    def widget(s): return s.w
class QHBoxLayout:
    def __init__(s, w): s.w = w; s.items = []
    def setContentsMargins(s, *a): pass
    def setSpacing(s, n): pass
    def addWidget(s, w, stretch=0): s.items.append(w)
    def addStretch(s, n): pass
    def count(s): return len(s.items)
    def takeAt(s, i): return _Item(s.items.pop(i))
QVBoxLayout = QHBoxLayout
class QSizePolicy:
    class Policy: Ignored = Preferred = Expanding = 0
class App:
    def __init__(s): s.css = "base{}"; s.filters = []; s.kids = []; s.focusChanged = _Sig2(); s.focus = None; s.sent = []
    def installEventFilter(s, f): s.filters.append(f)
    def styleSheet(s): return s.css
    def setStyleSheet(s, c): s.css = c
app = App()
class QApplication:
    @staticmethod
    def instance(): return app
    @staticmethod
    def topLevelWidgets(): return [w for w in ALL if not getattr(w, "gone", False)]
    @staticmethod
    def focusWidget(): return app.focus
    @staticmethod
    def activeWindow(): return None
    @staticmethod
    def sendEvent(target, ev): app.sent.append((target, ev)); return True
class PM:
    def __init__(s, v): s.v = v; s.saved = 0
    def uiScale(s): return s.v
    def setUiScale(s, v): s.v = v
    def save(s): s.saved += 1
aqt = types.ModuleType("aqt"); aqtqt = types.ModuleType("aqt.qt")
for k, v in dict(QApplication=QApplication, QColorDialog=QColorDialog, QDialog=QDialog, QEvent=QEvent, QFileDialog=QFileDialog, QFontDialog=QFontDialog,
                 QGuiApplication=QGuiApplication, QHBoxLayout=QHBoxLayout, QInputDialog=QInputDialog, QLabel=QLabel, QMainWindow=QMainWindow,
                 QMessageBox=QMessageBox, QObject=QObject, pyqtSignal=pyqtSignal, QAbstractSpinBox=QAbstractSpinBox, QComboBox=QComboBox, QKeyEvent=QKeyEvent, QLineEdit=QLineEdit, QPlainTextEdit=QPlainTextEdit, QPushButton=QPushButton, QTextEdit=QTextEdit, QTimer=QTimer, QVBoxLayout=QVBoxLayout, QProgressDialog=QProgressDialog, QSizePolicy=QSizePolicy, Qt=Qt, QToolButton=QToolButton, QWidget=QWidget).items():
    setattr(aqtqt, k, v)
hooks = types.SimpleNamespace(main_window_did_init=[], theme_did_change=[], webview_will_set_content=[], webview_did_receive_js_message=[])
aqt.gui_hooks = hooks; aqt.qt = aqtqt; aqt.mw = QMainWindow(); aqt.mw.pm = PM(1.0)
sys.modules.update({"aqt": aqt, "aqt.qt": aqtqt})

import os
os.environ["ARMADA_YOMITAN_ANKI_SCALE_TARGET"] = "2.5"; os.environ["ARMADA_YOMITAN_ANKI_SOCK"] = "/tmp/fake-anki-test.sock"
ns = {"__name__": "armada_yomitan_touch"}
err = io.StringIO()
with contextlib.redirect_stderr(err):
    exec(compile(_extract.anki_addon(), "addon", "exec"), ns)
print("start-up messages:", repr(err.getvalue()))
flt = ns["_KEEP"][0]; print("event filter installed on the app:", app.filters == [flt], "| hooks registered:", len(hooks.main_window_did_init), len(hooks.theme_did_change))
show = lambda w: flt.eventFilter(w, Ev(QEvent.Type.Show))
def bar_of(w): return getattr(w, "_armada_yomitan_bar", None)

print("\n--- main window")
mw = aqt.mw; mw._title = "Anki - User 1"; mw._geo = Rect(0, 0, 300, 200); show(mw)
b = bar_of(mw)
print("filled the screen:", (mw.width(), mw.height()), "| top margin:", mw.contentsMargins().top(), "| bar:", b.name, (b.width(), b.height()) if False else (b._geo.w, b._geo.h), "shown:", b.shown)
mine = [t for t in b.kids if isinstance(t, QToolButton)]; print("button says:", mine[0].text); mine[0].clicked.fire(); print("clicking it hides the main window, doesn't close it:", (mw.closed, mw.shown) == (0, False))
print("title label:", [l.text for l in b.kids if isinstance(l, QLabel)])

print("\n--- card browser (a second main-style window)")
br = QMainWindow(); br._title = "Browse"; show(br); bb = bar_of(br); print("bar:", bool(bb), "| filled:", (br.width(), br.height()))
bt = [t for t in bb.kids if isinstance(t, QToolButton)][0]; print("button says:", repr(bt.text)); bt.clicked.fire(); print("close called on the browser:", br.closed == 1)

print("\n--- dialogs")
big = QDialog(); big._geo = Rect(0, 0, 500, 400); show(big); print("big dialog fills the screen:", (big.width(), big.height()), "| bar:", bool(bar_of(big)))
small = QDialog(); small._geo = Rect(0, 0, 200, 100); show(small); print("small dialog keeps its size, centred at", small.pos, "| size", (small.width(), small.height()), "| bar:", bool(bar_of(small)))
for cls in (QMessageBox, QProgressDialog, QInputDialog, QFileDialog): w = cls(); show(w); print(f"  {cls.__name__}: no bar ->", bar_of(w) is None)
prog = QDialog(); prog._flags = Qt.WindowType.CustomizeWindowHint; show(prog); print("  window that removed its own close button: no bar ->", bar_of(prog) is None)
prog2 = QDialog(); prog2._flags = Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowCloseButtonHint; show(prog2); print("  ...but one that kept it gets a bar ->", bar_of(prog2) is not None)
menu = QWidget(); menu.wtype = Qt.WindowType.Popup; show(menu); print("  popup menu: no bar ->", bar_of(menu) is None)
splash = QDialog(); splash._flags = Qt.WindowType.FramelessWindowHint; show(splash); print("  frameless: no bar ->", bar_of(splash) is None)
child = QDialog(parent=br); show(child); print("  a child widget (not a window): no bar ->", bar_of(child) is None)

print("\n--- events")
n = len([1 for _ in [0]]); show(br); print("showing again doesn't add a second bar:", bar_of(br) is bb)
br._geo = Rect(0, 0, 400, 300); flt.eventFilter(br, Ev(QEvent.Type.Resize)); print("resize keeps the bar full width:", bb._geo.w == 400 and bb._geo.h == 44)
br._title = "Browse (3 cards)"; flt.eventFilter(br, Ev(QEvent.Type.WindowTitleChange))
print("title change updates the label:", [l.text for l in bb.kids if isinstance(l, QLabel)])
print("any other event is ignored and passed on:", flt.eventFilter(br, Ev("mouse")) is False)
class Boom(QDialog):
    def windowFlags(s): raise RuntimeError("boom")
e2 = io.StringIO()
with contextlib.redirect_stderr(e2): r = show(Boom())
print("an error inside is logged, not raised; event passes on:", r is False, "|", e2.getvalue().splitlines()[0][:40])

print("\n--- after Anki's window is set up")
for f in hooks.main_window_did_init: f()
print("touch style appended once:", app.css.count("QMenu::item {") == 1, "| base kept:", app.css.startswith("base{}"))
app.css = "theme-reset{}"; [f() for f in hooks.theme_did_change]; print("re-added after a theme change:", "QMenu::item" in app.css)
[f() for f in hooks.theme_did_change]; print("not doubled:", app.css.count("QMenuBar::item {") == 1)
print("UI size 1.0 -> pref updated to", aqt.mw.pm.v, "and saved", aqt.mw.pm.saved, "time(s)")
[f() for f in hooks.main_window_did_init]; print("already right -> saved still", aqt.mw.pm.saved)


print("\n=== Back to OCR keeps Anki running; the socket brings it back ===")
import socket, time
def send(word):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); c.settimeout(3); c.connect("/tmp/fake-anki-test.sock"); c.sendall(word.encode() + b"\n"); r = c.recv(64).decode().strip(); c.close(); return r
time.sleep(0.3)
print("socket mode:", oct(os.stat("/tmp/fake-anki-test.sock").st_mode & 0o777), "| ping:", send("ping"))
for w in list(ALL): w.shown = False
mw, br, dlg, mb = aqt.mw, QMainWindow(), QDialog(), QMessageBox()
for w in (br, dlg, mw, mb): show(w); w.shown = True
btn = [t for t in bar_of(mw).kids if isinstance(t, QToolButton)][0]
btn.clicked.fire()
print("after Back to OCR: main/browser/dialog hidden:", not mw.shown, not br.shown, not dlg.shown, "| message box left alone:", mb.shown, "| nothing closed:", mw.closed + br.closed + dlg.closed == 0 or (mw.closed, br.closed, dlg.closed))
print("...and a visible query now says no:", send("visible") == "no")
print("send show ->", send("show"))
print("all three back:", mw.shown, br.shown, dlg.shown, "| a child window ends on top:", getattr(dlg, "active", False) or getattr(br, "active", False), "| main not the top one:", not getattr(mw, "active", False))
print("...and a visible query now says yes:", send("visible") == "yes")
print("show again while visible is harmless:", send("show"), mw.shown)
btn.clicked.fire(); br.gone = True; br.deleted = True
print("send show ->", send("show"), "| survives a deleted window:", mw.shown and dlg.shown)
mw.shown = False
print("hide command:", send("hide"), "| ", send("bogus"), "| visible query says no:", send("visible") == "no")
closed0 = aqt.mw.closed; print("quit ->", send("quit"), "| main window asked to close:", aqt.mw.closed == closed0 + 1)

# =========================================================== the on-screen keyboard
print("\n\n================ KEYBOARD ================")
for w in list(ALL): w.shown = False
TIMERS.clear(); app.sent.clear()
def fire():
    global TIMERS
    pending, TIMERS = TIMERS[:], []
    TIMERS.clear(); [f() for f in pending]
def tap(obj): flt.eventFilter(obj, Ev(QEvent.Type.MouseButtonPress))
def focus(new):
    old, app.focus = app.focus, new; app.focusChanged.emit(old, new)
def keys(node, out=None):
    out = [] if out is None else out
    for k in node.kids:
        if getattr(k, "gone", False): continue
        if isinstance(k, QPushButton): out.append(k)
        keys(k, out)
    return out
def kbd_of(host): return getattr(host, "_armada_yomitan_kbd", None)
def key(kb, text): return [b for b in keys(kb) if b.text == text][0]
def press(kb, text): key(kb, text).clicked.fire()
def sent_since(n): return [(type(t).__name__, e.kind[3:] if e.kind.startswith("key") else e.kind, e.code, e.text, e.mods) for t, e in app.sent[n:]]

host = QMainWindow(); host._title = "Browse"; host._geo = Rect(0, 0, 620, 540); show(host); host.shown = True
search = QLineEdit(host); other = QLineEdit(host); btn_ok = QPushButton("Add", host); ro = QLineEdit(host); ro.ro = True
print("hooks: focusChanged connected:", len(app.focusChanged.slots) == 1, "| js hooks:", len(hooks.webview_will_set_content), len(hooks.webview_did_receive_js_message))

print("\n--- a field that focuses itself (no tap): no keyboard")
focus(search); print("keyboard shown:", kbd_of(host) is not None)
print("\n--- tapping a field")
tap(search); focus(None); focus(search)
kb = kbd_of(host); print("keyboard up:", kb is not None and kb.shown, "| window bottom margin reserved:", host.contentsMargins().bottom(), "| placed at the bottom:", (kb._geo.x, kb._geo.y, kb._geo.w, kb._geo.h), "| window untouched size:", (host.width(), host.height()))
labels = [b.text for b in keys(kb)]; print("keys:", " ".join(labels))
print("no key can take focus:", all(b.focuspolicy == Qt.FocusPolicy.NoFocus for b in keys(kb)) and kb.focuspolicy == Qt.FocusPolicy.NoFocus)

print("\n--- typing goes to the focused field")
n = len(app.sent); press(kb, "q"); print("q ->", sent_since(n))
n = len(app.sent); press(kb, "Shift"); print("Shift: labels now upper-case:", "Q" in [b.text for b in keys(kb)], "| Shift lit:", key(kb, "Shift").props.get("on"))
kb = kbd_of(host); n = len(app.sent); press(kb, "A"); print("A ->", sent_since(n)[0], "| Shift used up:", "a" in [b.text for b in keys(kbd_of(host))] and "on" not in key(kbd_of(host), "Shift").__dict__.get("props", {}))
kb = kbd_of(host); press(kb, "Shift"); press(kbd_of(host), "Shift"); print("Shift twice = off again:", "q" in [b.text for b in keys(kbd_of(host))])
kb = kbd_of(host); n = len(app.sent); press(kb, "Space"); press(kb, "Enter"); press(kb, "Del"); print("Space/Enter/Del ->", [(c, t) for _, k, c, t, _ in sent_since(n) if k == "down"], "| Del auto-repeats:", key(kb, "Del").repeat)
press(kb, "123"); kb = kbd_of(host); print("symbols:", " ".join(b.text for b in keys(kb)))
n = len(app.sent); press(kb, "7"); press(kb, ":"); press(kb, '"'); print("7 : \" ->", [(c, t) for _, k, c, t, _ in sent_since(n) if k == "down"])
press(kb, "abc"); print("back to letters:", "q" in [b.text for b in keys(kbd_of(host))])
n = len(app.sent); press(kbd_of(host), ","); press(kbd_of(host), "."); print(", . ->", [t for _, k, c, t, _ in sent_since(n) if k == "down"])

print("\n--- Hide, then tap the same field again")
press(kbd_of(host), "Hide"); print("hidden, margin given back:", kbd_of(host) is None, host.contentsMargins().bottom() == 0)
tap(search); fire(); print("tapping the focused field brings it back:", kbd_of(host) is not None)

print("\n--- moving between fields keeps it; moving to a button hides it")
tap(other); focus(search); focus(None); tap(other); focus(other); fire(); print("field to field: still up:", kbd_of(host) is not None)
tap(btn_ok); focus(btn_ok); print("just after tapping a button (not yet):", kbd_of(host) is not None); fire(); print("300 ms later: hidden:", kbd_of(host) is None, "| margin restored:", host.contentsMargins().bottom() == 0)
tap(ro); focus(ro); fire(); print("read-only field: no keyboard:", kbd_of(host) is None)

print("\n--- a small dialog takes the screen while the keyboard is up")
dlg = QDialog(); dlg._geo = Rect(100, 100, 200, 120); show(dlg); dlg.shown = True; field = QLineEdit(dlg)
tap(field); focus(field); print("during:", (dlg.width(), dlg.height()), "keyboard:", kbd_of(dlg) is not None)
press(kbd_of(dlg), "Hide"); print("after:", (dlg.width(), dlg.height()), (dlg._geo.x, dlg._geo.y))

print("\n--- fields inside a web page (the card editor)")
web = QWidget(host)
body = type("WC", (), {"body": "<div id=editor></div>"})(); hooks.webview_will_set_content[0](body, None); print("script added to the page:", "focusin" in body.body and "armada_yomitan_kbd:" in body.body, "| page content kept:", body.body.startswith("<div"))
js = hooks.webview_did_receive_js_message[0]
print("other messages pass through untouched:", js((False, None), "something:else", None) == (False, None), js((True, 5), "x", None) == (True, 5))
app.focus = web; tap(web); print("field focused in the page ->", js((False, None), "armada_yomitan_kbd:1", None), "| keyboard up:", kbd_of(host) is not None)
n = len(app.sent); press(kbd_of(host), "e"); print("typing goes to the page's widget:", sent_since(n)[0][0], sent_since(n)[0][3])
js((False, None), "armada_yomitan_kbd:0", None); print("field blurred: still up until the delay ends:", kbd_of(host) is not None); fire(); print("then hidden:", kbd_of(host) is None)
js((False, None), "armada_yomitan_kbd:0", None); js((False, None), "armada_yomitan_kbd:1", None); fire(); print("blur then focus the next field quickly: not hidden by the old timer:", kbd_of(host) is not None or "no tap: correct")
press(kbd_of(host), "Hide") if kbd_of(host) else None; js((False, None), "armada_yomitan_kbd:0", None); fire()
tap(web); fire(); js((False, None), "armada_yomitan_kbd:1", None); fire(); print("page field focused, keyboard hidden, tap the page field again ->", kbd_of(host) is not None)

print("\n--- Back to OCR hides the keyboard too")
mwin = aqt.mw; mwin.shown = True; ex = QLineEdit(mwin); tap(ex); focus(ex); print("keyboard on the main window:", kbd_of(mwin) is not None)
[b for b in bar_of(mwin).kids if isinstance(b, QToolButton)][0].clicked.fire(); print("after Back to OCR: keyboard gone:", kbd_of(mwin) is None, "| margin restored:", mwin.contentsMargins().bottom() == 0, "| main hidden:", not mwin.shown)

print("\n--- a window deleted while the keyboard was up")
gone_host = QMainWindow(); gone_host._geo = Rect(0, 0, 620, 540); show(gone_host); gone_host.shown = True; f2 = QLineEdit(gone_host); tap(f2); focus(f2)
gone_host.deleted = True
def boom(*a): raise RuntimeError("wrapped C/C++ object has been deleted")
gone_host.contentsMargins = boom
focus(None); fire(); print("no crash:", True)

# =========================================================== the "main page stays squished" fixes
print("\n\n================ LEFTOVER SPACE ================")
TIMERS.clear()
mwin = aqt.mw; mwin.shown = True
print("main window's own bottom margin recorded when adopted:", mwin._armada_yomitan_base_bottom, "| now:", mwin.contentsMargins().bottom())

print("\n--- a window with its own non-zero bottom margin gets exactly that back")
odd = QMainWindow(); odd._geo = Rect(0, 0, 620, 540); odd.setContentsMargins(0, 0, 0, 7); show(odd); odd.shown = True
print("recorded:", odd._armada_yomitan_base_bottom, "(top margin is now", odd.contentsMargins().top(), "with the strip)")
fld = QLineEdit(odd); tap(fld); focus(fld); print("with keyboard:", odd.contentsMargins().bottom())
press(kbd_of(odd), "Hide"); print("after Hide:", odd.contentsMargins().bottom())
tap(fld); fire(); print("keyboard again:", odd.contentsMargins().bottom()); focus(None); fire(); print("after it hides itself:", odd.contentsMargins().bottom())

print("\n--- a leak the old code could have left: space reserved, nothing attached, bookkeeping lost")
m = mwin.contentsMargins(); mwin.setContentsMargins(m.left(), m.top(), m.right(), m.bottom() + 216)
mwin._armada_yomitan_kbd = None; mwin._armada_yomitan_kbd_h = 0
print("main window squashed by", mwin.contentsMargins().bottom())
import io, contextlib
err = io.StringIO()
with contextlib.redirect_stderr(err): tap(QWidget(mwin))
print("after one tap:", mwin.contentsMargins().bottom(), "| logged:", err.getvalue().strip())
print("and a second leak, healed by simply showing a window:", end=" ")
mwin.setContentsMargins(0, mwin.contentsMargins().top(), 0, 90); err = io.StringIO()
with contextlib.redirect_stderr(err): show(QDialog())
print(mwin.contentsMargins().bottom(), "|", err.getvalue().strip()[:60])
print("a window's real top strip is untouched by all this:", mwin.contentsMargins().top() == 44)

print("\n--- the keyboard's widget vanished (deleted with something else) before detach")
h2 = QMainWindow(); h2._geo = Rect(0, 0, 620, 540); show(h2); h2.shown = True; f3 = QLineEdit(h2); tap(f3); focus(f3)
k3 = kbd_of(h2); print("attached:", h2.contentsMargins().bottom())
def gone_hide(*a): raise RuntimeError("wrapped C/C++ object has been deleted")
k3.hide = gone_hide; k3.deleted = True
press_free = None
focus(None); fire(); print("keyboard object dead, yet the window's margin is back to", h2.contentsMargins().bottom())

print("\n--- a stale 'field focused in a page' after that window closes")
ed = QMainWindow(); ed._geo = Rect(0, 0, 620, 540); show(ed); ed.shown = True; edweb = QWidget(ed)
app.focus = edweb; tap(edweb); js((False, None), "armada_yomitan_kbd:1", None); print("editor field focused -> keyboard:", kbd_of(ed) is not None)
ed.gone = True; ed.deleted = True; ed.shown = False
mainweb = QWidget(mwin); app.focus = mainweb; focus_before = app.focus
app.focusChanged.emit(edweb, mainweb); tap(mainweb); fire(); fire()
print("keyboard on the main window after tapping a deck:", kbd_of(mwin) is not None, "| main window margin:", mwin.contentsMargins().bottom())

print("\n--- the main window's own pages are left alone")
def ctx(name): return type(name, (), {})()
for name in ("DeckBrowser", "Overview", "Toolbar", "BottomBar", "Editor", "Reviewer", "AddCards"):
    body = type("WC", (), {"body": "<p>x</p>"})(); hooks.webview_will_set_content[0](body, ctx(name)); print(f"  {name:12} script added: {'focusin' in body.body}")

# =========================================================== the card browser search bar
print("\n\n================ CARD BROWSER SEARCH BAR ================")
TIMERS.clear(); app.sent.clear()
for w in list(ALL): w.shown = False
mwin = aqt.mw; mwin.shown = True; mwin_widget = QWidget(mwin)
br2 = QMainWindow(); br2._title = "Browse"; br2._geo = Rect(0, 0, 620, 540); show(br2); br2.shown = True
combo = QComboBox(br2); le = combo.lineEdit(); go = QPushButton("Go", br2)
app.focus = None

print("--- tap the (already focused, so no focus change) search bar; Qt reports no focus at all")
tap(le); print("right away (finger still down):", kbd_of(br2) is not None); fire(); print("after the tap:", kbd_of(br2) is not None, "| bottom margin:", br2.contentsMargins().bottom())
n = len(app.sent); press(kbd_of(br2), "q"); print("q goes to the search bar's line edit:", [(type(t).__name__, t is le, e.text) for t, e in app.sent[n:n + 1]])
fire(); print("stays up (300 ms later, nothing else happened):", kbd_of(br2) is not None)
print("\n--- tapping the keys themselves doesn't count as tapping elsewhere")
kb = kbd_of(br2); flt.eventFilter(key(kb, "w"), Ev(QEvent.Type.MouseButtonPress)); flt.eventFilter(kb, Ev(QEvent.Type.MouseButtonPress)); fire(); print("still up:", kbd_of(br2) is not None)
n = len(app.sent); press(kb, "w"); print("and typing still reaches the field:", app.sent[n][0] is le)
print("\n--- Qt's focus is on a widget in a different window (the main one): ignored")
app.focus = mwin_widget; app.focusChanged.emit(None, mwin_widget); fire(); print("keyboard stays:", kbd_of(br2) is not None)
app.focus = None
print("\n--- tapping the combo box itself (not its line edit)")
press(kbd_of(br2), "Hide"); tap(combo); fire(); print("keyboard up:", kbd_of(br2) is not None, "| typing goes to:", end=" ")
n = len(app.sent); press(kbd_of(br2), "e"); print("the line edit" if app.sent[n][0] is le else type(app.sent[n][0]).__name__)
print("\n--- tapping the Go button (not a text field) hides it")
tap(go); print("just after:", kbd_of(br2) is not None); fire(); print("300 ms later, hidden:", kbd_of(br2) is None, "| margin back:", br2.contentsMargins().bottom() == 0)
print("\n--- an uneditable combo box, and a read-only field: no keyboard")
ro_combo = QComboBox(br2); ro_combo.editable = False; tap(ro_combo); fire(); print("uneditable combo:", kbd_of(br2) is None)
ro_le = QLineEdit(br2); ro_le.ro = True; tap(ro_le); fire(); print("read-only line edit:", kbd_of(br2) is None)

print("\n--- a field in a page (editor) when Qt reports no focus either")
web2 = QWidget(br2); other = QWidget(br2)
tap(web2); print("page field focused ->", js((False, None), "armada_yomitan_kbd:1", None), "| keyboard up:", kbd_of(br2) is not None)
n = len(app.sent); press(kbd_of(br2), "z"); print("typing goes to the page's widget:", app.sent[n][0] is web2)
tap(other); fire(); print("tapping other parts of the page doesn't hide it (the page reports blur itself):", kbd_of(br2) is not None)
js((False, None), "armada_yomitan_kbd:0", None); fire(); print("page says field lost focus: hidden:", kbd_of(br2) is None)
print("tap a page (not a field) with no field focused -> nothing:", (tap(other), fire(), kbd_of(br2) is None)[2])

# =========================================================== touching the keyboard's background
print("\n\n================ KEYBOARD BACKGROUND ================")
TIMERS.clear(); app.sent.clear()
for w in list(ALL): w.shown = False
bh = QMainWindow(); bh._title = "Browse"; bh._geo = Rect(0, 0, 620, 540); show(bh); bh.shown = True
field = QLineEdit(bh); other_btn = QPushButton("Go", bh); app.focus = None
tap(field); fire()
kb = kbd_of(bh); print("keyboard up:", kb is not None, "| geometry:", (kb._geo.x, kb._geo.y, kb._geo.w, kb._geo.h))

def lay_out(kb, margin=4, spacing=4):
    spec = ns["keyboard_rows"](kb.layer, kb.shift)
    rows = [k for k in kb.kids if not getattr(k, "gone", False)]
    H, W = kb._geo.h, kb._geo.w
    rh = (H - 2 * margin - spacing * (len(spec) - 1)) / len(spec)
    for i, (row, items) in enumerate(zip(rows, spec)):
        entries = [it for it in items if it[1] is not None or it[2]]
        avail = W - 2 * margin - spacing * (len(entries) - 1); unit = avail / sum(it[2] for it in entries)
        row._geo = Rect(margin, margin + i * (rh + spacing), W - 2 * margin, rh)
        x = 0.0; buttons = [b for b in row.kids if isinstance(b, QPushButton)]; bi = 0
        for label, action, width in entries:
            w = width * unit
            if action is not None: buttons[bi]._geo = Rect(x, 0, w, rh); bi += 1
            x += w + spacing
def rects(kb): return {b.text: (b.mapTo(kb, Pt(0, 0)).x(), b.mapTo(kb, Pt(0, 0)).y(), b.width(), b.height()) for b in kb.keys}
lay_out(kb); keyrect = rects(kb)
def cx(t): x, y, w, h = keyrect[t]; return x + w / 2
def cy(t): x, y, w, h = keyrect[t]; return y + h / 2
def edges(t): x, y, w, h = keyrect[t]; return x, y, x + w, y + h
KBD_Y = kb._geo.y
def evt(kind, x, y): return Ev(kind, local=(x, y), glob=(x, y + KBD_Y))

clicks = []
saved = {}
def record_only(kb):
    for b in kb.keys: saved[id(b)] = list(b.clicked.slots); b.clicked.slots = [lambda t=b.text: clicks.append(t)]
def restore(kb):
    for b in kb.keys: b.clicked.slots = saved[id(b)]
def probe(x, y, release=None):
    del clicks[:]; kb.mousePressEvent(evt(QEvent.Type.MouseButtonPress, x, y)); rx, ry = release or (x, y); kb.mouseReleaseEvent(evt("release", rx, ry)); return list(clicks)
record_only(kb)

print("\n--- every spot on the keyboard belongs to some key")
gx = (edges("q")[2] + edges("w")[0]) / 2; gy = (edges("q")[3] + edges("a")[1]) / 2
print("in the gap between q and w, nearer w:", probe(gx + 1.5, cy("q")), "| nearer q:", probe(gx - 1.5, cy("q")))
print("in the gap between the q row and the a row, above a:", probe(cx("a"), gy + 1.5), "| above q:", probe(cx("q"), gy - 1.5))
print("left of the short second row, next to a:", probe(edges("a")[0] - 6, cy("a")), "| right of it, next to l:", probe(edges("l")[2] + 6, cy("l")))
print("outer edge: above q:", probe(cx("q"), 1), "| left of q:", probe(1, cy("q")), "| right of p:", probe(kb._geo.w - 1, cy("p")), "| below Space:", probe(cx("Space"), kb._geo.h - 1))
print("corners:", probe(0, 0), probe(kb._geo.w - 1, 0), probe(0, kb._geo.h - 1), probe(kb._geo.w - 1, kb._geo.h - 1))
allpts = [(x, y) for x in range(0, kb._geo.w, 2) for y in range(0, kb._geo.h, 2)]
bad = [p for p in allpts if len(probe(*p)) != 1]
print("swept %d points over the whole keyboard: every one hit exactly one key: %s" % (len(allpts), not bad), bad[:3])
def inside(x, y, t): x0, y0, x1, y1 = edges(t); return x0 <= x < x1 and y0 <= y < y1
wrong = [(x, y) for x, y in allpts if any(inside(x, y, t) for t in keyrect) and probe(x, y) != [[t for t in keyrect if inside(x, y, t)][0]]]
print("and a spot that IS on a key still goes to that key:", not wrong)
ev = evt(QEvent.Type.MouseButtonPress, gx, cy("q")); kb.mousePressEvent(ev); kb.mouseReleaseEvent(evt("release", gx, cy("q"))); print("a touch on the background is accepted (doesn't travel on to the window behind):", ev.accepted)

print("\n--- the window behind never sees it, so the keyboard stays")
def deliver(x, y):
    ev = evt(QEvent.Type.MouseButtonPress, x, y); rows = [k for k in kb.kids if not getattr(k, "gone", False)]
    for obj in (rows[1], kb, bh):
        flt.eventFilter(obj, ev)
        if obj is kb: kb.mousePressEvent(ev)
        if ev.accepted: break
    kb.mouseReleaseEvent(evt("release", x, y)); return ev
deliver(gx, cy("q")); fire(); fire(); print("tap in a gap: keyboard still there:", kbd_of(bh) is not None)
deliver(1, 1); fire(); fire(); print("tap in the corner: keyboard still there:", kbd_of(bh) is not None)
ev = evt(QEvent.Type.MouseButtonPress, gx, cy("q")); flt.eventFilter(bh, ev); fire(); fire()
print("even if the press did reach the window (its position is over the keyboard): still there:", kbd_of(bh) is not None)
class TouchEv(Ev):
    def points(s): return [type("P", (), {"globalPosition": lambda self: s._glob})()]
    def globalPosition(s): raise AttributeError
flt.eventFilter(bh, TouchEv(QEvent.Type.TouchBegin, glob=(gx, cy("q") + KBD_Y))); fire(); fire(); print("a finger (touch event) over the keyboard is ignored the same way:", kbd_of(bh) is not None)
flt.eventFilter(other_btn, Ev(QEvent.Type.MouseButtonPress, local=(5, 5), glob=(5, 100))); fire(); fire()
print("but a tap on a button ABOVE the keyboard still hides it:", kbd_of(bh) is None)

print("\n--- typing through the gaps, for real")
tap(field); fire(); kb = kbd_of(bh); lay_out(kb); keyrect = rects(kb); KBD_Y = kb._geo.y
def typed(x, y, release=None):
    n = len(app.sent); kb.mousePressEvent(evt(QEvent.Type.MouseButtonPress, x, y)); rx, ry = release or (x, y); kb.mouseReleaseEvent(evt("release", rx, ry)); return [e.text for t, e in app.sent[n:] if e.kind == "keydown"]
gx = (edges("q")[2] + edges("w")[0]) / 2
print("gap between q and w (nearer w) types:", typed(gx + 1.5, cy("q")), "| the a row's left indent types:", typed(edges("a")[0] - 6, cy("a")))
print("pressed look while held:", end=" "); b_w = [b for b in kb.keys if b.text == "w"][0]; kb.mousePressEvent(evt("press", gx + 1.5, cy("q"))); print(b_w.down, "| released after:", end=" "); kb.mouseReleaseEvent(evt("release", gx + 1.5, cy("q"))); print(not b_w.down)
print("press in a gap, slide onto another key, let go -> nothing typed:", typed(gx + 1.5, cy("q"), release=(cx("p"), cy("p"))))

print("\n--- holding Del (or just beside it)")
dx0 = edges("Del")[0]; n = len(app.sent); TIMERS.clear()
kb.mousePressEvent(evt("press", dx0 - 1, cy("Del")))
def backspaces(): return sum(1 for t, e in app.sent[n:] if e.kind == "keydown" and e.text == "\b")
print("deletes at once:", backspaces() == 1, "| Del looks pressed:", [b for b in kb.keys if b.text == "Del"][0].down)
fire(); fire(); fire(); held = backspaces(); print("keeps deleting while held (count > 1):", held > 1, held)
kb.mouseReleaseEvent(evt("release", dx0 - 1, cy("Del"))); after = backspaces(); fire(); fire(); print("the release adds none and it stops at once:", after == held and backspaces() == held)

print("\n--- the symbols page")
kb = kbd_of(bh); press(kb, "123"); kb = kbd_of(bh); lay_out(kb); keyrect = rects(kb); record_only(kb)
pts = [(x, y) for x in range(0, kb._geo.w, 2) for y in range(0, kb._geo.h, 2)]
print("swept %d points: every one hit exactly one key: %s" % (len(pts), all(len(probe(*p)) == 1 for p in pts)))

print("\n=== started in the background: nothing reaches the screen until the first show ===")
os.environ["ARMADA_YOMITAN_ANKI_BACKGROUND"] = "1"
app.filters.clear(); n_before = len(ALL)
early = QDialog()
ns2 = {"__name__": "armada_yomitan_touch"}
err = io.StringIO()
with contextlib.redirect_stderr(err):
    exec(compile(_extract.anki_addon(), "addon", "exec"), ns2)
flt2 = app.filters[0]
print("start-up messages:", repr(err.getvalue()))
print("a window that already existed is held:", early.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen))
mw2, br2, box2 = QMainWindow(), QMainWindow(), QMessageBox()
box2.modal = True
for w in (mw2, br2, box2):
    flt2.eventFilter(w, Ev(QEvent.Type.Polish))
    w.show(); flt2.eventFilter(w, Ev(QEvent.Type.Show))
child = QWidget(mw2); flt2.eventFilter(child, Ev(QEvent.Type.Polish))
print("every top-level window is held, so none was ever on the screen:", all(w.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen) and not w.ever_on_screen for w in (mw2, br2, box2)))
print("a child widget isn't touched (it isn't a window):", not child.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen))
print("the strip was still added to the held main window (it is set up as usual):", bar_of(mw2) is not None)
aqt.mw = mw2
time.sleep(0.3)
print("ping works while held:", send("ping"))
print("send show ->", send("show"))
time.sleep(0.2)
print("main and browser are on the screen now:", mw2.on_screen and br2.on_screen, "| the hold is released:", not mw2.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen))
print("a modal box wasn't hidden (that would dismiss it), it was re-created and shown:", box2.on_screen and box2.shown, "| its flags were reset:", box2._flags == 0)
later = QMainWindow(); flt2.eventFilter(later, Ev(QEvent.Type.Polish)); later.show()
print("windows made after the release are shown normally:", later.on_screen and not later.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen))
print("hide, then show again, still work:", send("hide"), not mw2.shown, send("show"), mw2.on_screen)
os.environ.pop("ARMADA_YOMITAN_ANKI_BACKGROUND")
