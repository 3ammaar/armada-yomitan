# Tests

```
bash tests/run_all.sh                          # everything that can run here
python3 tests/python/test_relaunch.py          # a single suite; Python/bash suites print PASS/FAIL and exit non-zero on failure
python3 tests/python/test_anki_launcher.py
python3 tests/python/test_yomitan_patch.py
python3 tests/anki/test_addon_qt_stub.py       # stand-in Qt; read the output for unexpected False/Traceback
python3 tests/web/test_keyboard_host.py        # browser suites: need Playwright + Chromium
```

Browser suites: `pip install playwright && playwright install chromium` (or point `CHROME_PATH` at a full Chromium for the
extension test). They emulate the Thor's viewport (472×411 CSS px, scale 2.625) with touch.

`_extract.py` is the helper the scripts share: `load_module(home)` imports a fresh copy of the `armada_yomitan` package with
`ARMADA_YOMITAN_HOME` pointing at a scratch folder and returns a facade over all of its modules. The tests read and monkeypatch names on
that one object (`m.capture_png = fake`); a read finds the name in whichever module has it, and a write goes to every module that
has it, which is the effect such a patch has to have. `kbd_js()` reads the keyboard script from `src/armada_yomitan/data/`, and
`anki_addon()` returns the Anki add-on as the program writes it (its texts filled in).
