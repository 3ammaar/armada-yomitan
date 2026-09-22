"""Tests for the touchscreen permission message."""

import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import _extract

FAILED = []


def check(label, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{extra}]" if extra and not ok else ""))
    if not ok:
        FAILED.append(label)


if os.geteuid() == 0:
    print("SKIP  running as root, which can read any file: a permission error can't be provoked")
    sys.exit(0)

work = tempfile.mkdtemp(prefix="ay-touchperm-")
m = _extract.load_module(f"{work}/home")
strings = m.strings
device = f"{work}/event6"
open(device, "w").close()
os.chmod(device, 0o000)
m.list_input_devices = lambda: [("Goodix top_touchscreen", device)]
cfg = m.Config()
cfg.touch_name = "top_touchscreen"

err = io.StringIO()
with contextlib.redirect_stderr(err):
    try:
        m.open_touch(cfg)
        message = None
    except RuntimeError as e:
        message = str(e)
console = err.getvalue()
check("the message on the screen is still the short one", message is not None and message.startswith(strings.TOUCH_NO_PERMISSION.format(path=device)), str(message))
check("the console says who owns the device (mode and group)", "Why the touchscreen can't be read" in console and "is mode 0000" in console and "group" in console, console)
check("...and who this process is, with its groups (the input group being absent is then visible)", f"uid {os.getuid()}" in console and "with groups" in console, console)
check("the details are printed once", console.count("Why the touchscreen can't be read") == 1, console)

print("\n%d failed" % len(FAILED))
sys.exit(1 if FAILED else 0)
