"""Re-running the program."""

import os
import shlex
import sys

from armada_yomitan.paths import VENV_DIR, VENV_PY

# drop the working directory from sys.path so it can't shadow the package
_BOOTSTRAP = ("import sys; sys.path[:] = [p for p in sys.path if p]; sys.path.append(sys.argv.pop(1)); "
              "from armada_yomitan.entry import main; main()")


def package_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def program_command(python=None):
    return [python or sys.executable, "-c", _BOOTSTRAP, package_root()]


def program_hint():
    root = package_root()
    if os.path.isfile(root):
        return f"python3 {root}"
    return f"env PYTHONPATH={shlex.quote(root)} python3 -m armada_yomitan"


def base_python():
    """The interpreter the running one was made from (this one when not in a virtual environment)."""
    if os.path.realpath(sys.prefix) != os.path.realpath(sys.base_prefix):
        candidate = os.path.join(sys.base_prefix, "bin", "python3")
        if os.path.exists(candidate):
            return candidate
    return sys.executable


def restart():
    python = VENV_PY if os.path.exists(VENV_PY) else sys.executable
    os.execv(python, program_command(python) + sys.argv[1:])


def maybe_reexec_into_venv():
    if os.environ.get("ARMADA_YOMITAN_NO_VENV") or "--setup" in sys.argv:
        return
    if os.path.isdir(VENV_DIR) and not os.path.exists(VENV_PY):
        print("(the OCR environment looks broken, e.g. after a system Python update; "
              "run: armada-yomitan --setup)", file=sys.stderr)
        return
    if os.path.exists(VENV_PY) and os.path.realpath(sys.prefix) != os.path.realpath(VENV_DIR):
        try:
            os.execv(VENV_PY, program_command(VENV_PY) + sys.argv[1:])
        except OSError as e:
            print(f"(couldn't start the OCR environment: {e})", file=sys.stderr)
