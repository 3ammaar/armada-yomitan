"""Paths under ARMADA_YOMITAN_HOME."""

import os

HOME_DIR = os.path.expanduser(os.environ.get("ARMADA_YOMITAN_HOME", "~/.local/share/armada-yomitan"))
VENV_DIR = os.path.join(HOME_DIR, "venv")
VENV_PY = os.path.join(VENV_DIR, "bin", "python")
EXT_DIR = os.path.join(HOME_DIR, "yomitan")
PROFILE_DIR = os.path.join(HOME_DIR, "browser-profile")
BROWSERS_DIR = os.path.join(HOME_DIR, "browsers")
PREFS_PATH = os.path.join(HOME_DIR, "ui.json")
LOG_PATH = os.path.join(HOME_DIR, "armada-yomitan.log")
ANKI_DIR = os.path.join(HOME_DIR, "anki")
ANKI_VENV = os.path.join(ANKI_DIR, "venv")
INSTALL_STATE_PATH = os.path.join(HOME_DIR, "install-state.json")
