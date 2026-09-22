"""The log file."""

import os
import sys
import time

from armada_yomitan.paths import HOME_DIR, LOG_PATH

LOG_LIMIT = 512 * 1024


def open_append():
    try:
        os.makedirs(HOME_DIR, exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_LIMIT:
            os.remove(LOG_PATH)
        return os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    except OSError:
        return None


def note(text):
    line = f"[armada-yomitan {time.strftime('%H:%M:%S')} pid {os.getpid()}] {text}"
    fd = open_append()
    if fd is not None:
        try:
            os.write(fd, (line + "\n").encode(errors="replace"))
        except OSError:
            pass
        finally:
            os.close(fd)
    try:
        if os.isatty(2):
            print(line, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass
