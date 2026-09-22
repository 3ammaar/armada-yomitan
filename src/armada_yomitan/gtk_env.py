"""The display backend GTK windows use."""

import os


def prefer_x11():
    if os.environ.get("DISPLAY"):
        os.environ.setdefault("GDK_BACKEND", "x11")
