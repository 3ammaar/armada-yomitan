#!/usr/bin/env bash
# Runs every suite.
# Python/bash suites must pass; browser suites run if Playwright + Chromium exist (read their output for unexpected False lines).
cd "$(dirname "$0")/.." || exit 1
FAIL=0
run() { echo; echo "=== $*"; "$@"; local rc=$?; [ $rc -ne 0 ] && { echo "!!! $* exited $rc"; FAIL=1; }; }
run python3 tests/python/test_yomitan_patch.py
run python3 tests/python/test_anki_launcher.py
run python3 tests/python/test_relaunch.py
run python3 tests/python/test_build.py
run python3 tests/python/test_strings.py
run python3 tests/python/test_launcher.py
run python3 tests/python/test_shutdown.py
run python3 tests/python/test_decky_backend.py
run python3 tests/python/test_touch_permission.py
run python3 tests/python/test_syspackages.py
run python3 tests/python/test_installer.py
run python3 tests/python/test_gtk_setup.py
run python3 tests/python/test_gtk_env.py
run python3 tests/python/test_first_run.py
run bash tests/setup_script/test_uninstall_script.sh
run python3 tests/anki/test_addon_qt_stub.py
if python3 -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
  for t in test_keyboard_host test_keyboard_scrollers test_keyboard_iframe test_ocr_page test_sysdeps_page test_reinstall_page test_yomitan_scanner_exclusion; do
    run python3 tests/web/$t.py
  done
else
  echo; echo "(Playwright isn't installed: skipping tests/web)"
fi
echo; [ $FAIL -eq 0 ] && echo "ALL SUITES RAN WITHOUT FAILURE (still read the browser output for unexpected False lines)" || echo "SOME SUITES FAILED"
exit $FAIL
