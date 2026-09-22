"""Which install steps have completed."""

import json
import os

from armada_yomitan.paths import INSTALL_STATE_PATH

STEPS = ("ocr", "chromium", "yomitan")


def load():
    """The completed steps, or None when nothing has been recorded."""
    try:
        with open(INSTALL_STATE_PATH, encoding="utf-8") as f:
            return {step for step in json.load(f) if step in STEPS}
    except (OSError, ValueError, TypeError):
        return None


def _save(done):
    os.makedirs(os.path.dirname(INSTALL_STATE_PATH), exist_ok=True)
    tmp = INSTALL_STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(done), f)
    os.replace(tmp, INSTALL_STATE_PATH)


def is_done(step):
    return step in (load() or set())


def mark(*steps):
    _save((load() or set()) | set(steps))


def unmark(*steps):
    _save((load() or set()) - set(steps))


def reset():
    _save(set())


def complete():
    return set(STEPS) <= (load() or set())
