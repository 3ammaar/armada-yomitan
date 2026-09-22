"""The embedded data files and their rendering."""

import html
import json
import re
from importlib import resources

from armada_yomitan import strings


def _read(name):
    return (resources.files("armada_yomitan") / "data" / name).read_bytes().decode("utf-8")


_TEXT_MARK = re.compile(r"@@([A-Z0-9_]+)@@")
_SCRIPT_USE = re.compile(r"\bS\.(PAGE_[A-Z0-9_]+)")


def render_texts(page):
    """Fills the @@NAME@@ placeholders from strings.py."""
    used = sorted(set(_SCRIPT_USE.findall(page)))
    script_texts = json.dumps({name: getattr(strings, name) for name in used}, ensure_ascii=False).replace("<", "\\u003c")

    def fill(match):
        name = match.group(1)
        return script_texts if name == "PAGE_SCRIPT_TEXTS" else html.escape(getattr(strings, name), quote=False)

    return _TEXT_MARK.sub(fill, page)


_ADDON_USE = re.compile(r'TEXT\["(ADDON_[A-Z0-9_]+)"\]')


def render_addon(source):
    """Fills in __ADDON_TEXTS__."""
    used = sorted(set(_ADDON_USE.findall(source)))
    return source.replace("__ADDON_TEXTS__", json.dumps({name: getattr(strings, name) for name in used}))


ANKI_TOUCH_ADDON = render_addon(_read("anki_touch_addon.py"))
KBD_JS = _read("kbd.js")
PAGE_HTML = _read("page.html")
YOMI_CSS = _read("yomitan_search.css")
YOMI_JS = _read("yomitan_search.js")
