"""Helpers shared by the test scripts."""

import importlib
import os
import pkgutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
DATA = os.path.join(SRC, "armada_yomitan", "data")
TMP = tempfile.gettempdir()


def _data(name):
    with open(os.path.join(DATA, name), encoding="utf-8", newline="") as f:
        return f.read()


def kbd_js():
    return _data("kbd.js")


def anki_addon():
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    from armada_yomitan import assets
    return assets.ANKI_TOUCH_ADDON


class Package:
    def __init__(self, modules):
        object.__setattr__(self, "_modules", modules)

    def __getattr__(self, name):
        for module in self._modules:
            if hasattr(module, name):
                return getattr(module, name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        owners = [module for module in self._modules if hasattr(module, name)]
        if not owners:
            raise AttributeError(f"no module of the package has {name!r} (a typo, or a name that moved?)")
        for module in owners:
            setattr(module, name, value)


def load_module(home):
    os.makedirs(home, exist_ok=True)
    os.environ["ARMADA_YOMITAN_HOME"] = home
    for name in [n for n in sys.modules if n == "armada_yomitan" or n.startswith("armada_yomitan.")]:
        del sys.modules[name]
    if sys.path[0] != SRC:
        sys.path.insert(0, SRC)                    # ahead of the working directory, which may hold something named armada_yomitan.py
    package = importlib.import_module("armada_yomitan")
    assert os.path.dirname(package.__file__) == os.path.join(SRC, "armada_yomitan"), package.__file__
    modules = [importlib.import_module(m.name) for m in pkgutil.walk_packages(package.__path__, "armada_yomitan.")]
    return Package(modules)
