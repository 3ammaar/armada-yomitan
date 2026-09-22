"""Error output to the console."""

import re
import sys
import time

from armada_yomitan import strings

_ERROR_TEXT = re.compile("^(" + "|".join(re.escape(start) for start in strings.ERROR_STARTS) + ")", re.I)


def looks_like_error(text):
    return bool(_ERROR_TEXT.match(text or ""))


def log_error(text, detail=None):
    print(f"[armada-yomitan {time.strftime('%H:%M:%S')}] {text}", file=sys.stderr, flush=True)
    for line in detail or []:
        print("    " + line, file=sys.stderr, flush=True)
