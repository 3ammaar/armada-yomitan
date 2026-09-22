"""The program's entry point."""

import faulthandler
import os
import signal
import traceback

from armada_yomitan.logfile import note


def main():
    faulthandler.enable()
    for number in (signal.SIGTERM, signal.SIGHUP):
        faulthandler.register(number, chain=True)
    try:
        from armada_yomitan.cli import main as run
        from armada_yomitan.launcher import ON_BOTTOM
    except BaseException:
        note("the program failed to load:\n" + traceback.format_exc())
        raise
    launched = bool(os.environ.get(ON_BOTTOM))
    try:
        run()
    except SystemExit as e:
        if launched:
            note(f"the program exited with status {e.code!r}")
        raise
    except KeyboardInterrupt:
        raise
    except BaseException:
        note("the program crashed:\n" + traceback.format_exc())
        raise
    if launched:
        note("the program exited normally")
