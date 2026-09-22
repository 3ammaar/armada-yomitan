"""Tests for the GTK display backend choice."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract

FAILED = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{extra}]" if extra and not ok else ""))
    if not ok:
        FAILED.append(label)


def backend(**env):
    base = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "GDK_BACKEND", "WAYLAND_DISPLAY")}
    code = f"import sys; sys.path.insert(0, {_extract.SRC!r}); from armada_yomitan.gtk_env import prefer_x11; import os; prefer_x11(); print(os.environ.get('GDK_BACKEND', ''))"
    return subprocess.run([sys.executable, "-c", code], env={**base, **env}, capture_output=True, text=True).stdout.strip()


check("with an X display, GTK is told to use X11 (its Wayland backend crashes on touch under gamescope)", backend(DISPLAY=":2", WAYLAND_DISPLAY="gamescope-1") == "x11")
check("an explicit choice is kept", backend(DISPLAY=":2", GDK_BACKEND="broadway") == "broadway")
check("without an X display nothing is forced", backend() == "")
src = open(os.path.join(_extract.SRC, "armada_yomitan", "gtk_setup.py")).read() + open(os.path.join(_extract.SRC, "armada_yomitan", "gtk_ui.py")).read()
check("both GTK windows ask for it before importing gi", src.count("prefer_x11()\n    import gi") == 2)

print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
