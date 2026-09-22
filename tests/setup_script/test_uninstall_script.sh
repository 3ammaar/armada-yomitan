#!/usr/bin/env bash
# Tests uninstall_armada_yomitan.sh in a scratch HOME with fake rpm-ostree, sudo and systemctl.
# Run: bash tests/setup_script/test_uninstall_script.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../uninstall_armada_yomitan.sh"
W="$(mktemp -d)"
FAILED=0
check() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; FAILED=$((FAILED+1)); fi; }

mkdir -p "$W/bin"
mk() { printf '#!/bin/bash\n%s\n' "$2" > "$W/bin/$1"; chmod +x "$W/bin/$1"; }
mk sudo '"$@"'
mk systemctl 'echo "systemctl $*" >> "$W_CALLS"'
mk rpm-ostree 'if [ "$1" = status ]; then if grep -qs uninstall "$W_CALLS"; then echo "{\"deployments\":[{\"requested-packages\":[\"htop\"]}]}"; else echo "{\"deployments\":[{\"requested-packages\":[\"tesseract\",\"minizip-ng-compat\",\"htop\"],\"packages\":[\"tesseract\"]}]}"; fi; else echo "rpm-ostree $*" >> "$W_CALLS"; fi'
export PATH="$W/bin:$PATH" W_CALLS="$W/calls"

populate() {
    export HOME="$W/home"
    rm -rf "$HOME" "$W/calls"
    D="$HOME/.local/share"
    mkdir -p "$D/armada-yomitan/venv" "$D/armada-yomitan/browsers" "$D/armada-yomitan/anki/venv" "$D/armada-yomitan/bin"
    printf '#!/bin/sh\n' > "$D/armada-yomitan/bin/uv"; chmod +x "$D/armada-yomitan/bin/uv"
    echo '{"anki_cmd": ["/x/anki", "--base", "'"$HOME"'/custom-anki"]}' > "$D/armada-yomitan/ui.json"
    mkdir -p "$D/uv/python/cpython-3.13.1-linux" "$D/uv/python/cpython-3.12.0-linux" "$HOME/.cache/uv" "$D/other"
    for base in "$D/Anki2" "$HOME/custom-anki"; do
        mkdir -p "$base/addons21/armada_yomitan_touch" "$base/addons21/AnkiConnect" "$base/User 1"
        echo deck > "$base/User 1/collection.anki2"
        python3 - "$base" <<'PY'
import pickle, sqlite3, sys
for name, scale in (("prefs21.db", 3.0), ("prefs21.db.armada-yomitan.bak", 1.0)):
    con = sqlite3.connect(sys.argv[1] + "/" + name)
    con.execute("create table profiles (name text primary key, data blob)")
    con.execute("insert into profiles values ('_global', ?)", (pickle.dumps({"uiScale": scale, "lang": "en"}, protocol=4),))
    con.commit(); con.close()
PY
    done
}
scale() { python3 - "$1" <<'PY'
import pickle, sqlite3, sys
row = sqlite3.connect(sys.argv[1]).execute("select cast(data as blob) from profiles where name = '_global'").fetchone()
d = pickle.loads(row[0]); print(d["uiScale"], d["lang"])
PY
}

populate
OUT="$(bash "$SCRIPT" --dry-run 2>&1)"
check "--dry-run lists everything and removes nothing" '[[ "$OUT" == *armada-yomitan* && "$OUT" == *custom-anki* && -d "$D/armada-yomitan" && ! -e "$W/calls" ]]'
check "only layered packages of ours are listed (not htop)" '[[ "$OUT" == *"tesseract minizip-ng-compat"* && "$OUT" != *htop* ]]'

OUT="$(printf 'n\n' | bash "$SCRIPT" 2>&1)"
check "answering no cancels" '[[ "$OUT" == *Cancelled* && -d "$D/armada-yomitan" ]]'

bash -c 'exec -a "$0/venv/bin/python" sleep 120' "$D/armada-yomitan" &
SLEEPER=$!
sleep 0.3
OUT="$(bash "$SCRIPT" -y 2>&1)"
check "a process running from the program's folder is stopped" '! kill -0 $SLEEPER 2>/dev/null'
check "the program's folder is gone" '[[ ! -e "$D/armada-yomitan" ]]'
check "the add-on is removed from every Anki folder, Anki's other add-ons and data stay" \
      '[[ ! -e "$D/Anki2/addons21/armada_yomitan_touch" && ! -e "$HOME/custom-anki/addons21/armada_yomitan_touch" && -d "$D/Anki2/addons21/AnkiConnect" && -f "$D/Anki2/User 1/collection.anki2" && -f "$HOME/custom-anki/User 1/collection.anki2" ]]'
check "Anki's UI size is restored, its other preferences are kept, the backup is gone" \
      '[[ "$(scale "$D/Anki2/prefs21.db")" == "1.0 en" && "$(scale "$HOME/custom-anki/prefs21.db")" == "1.0 en" && ! -e "$D/Anki2/prefs21.db.armada-yomitan.bak" ]]'
check "uv's own Python 3.13 and cache go (our uv was the only one), other Pythons stay" \
      '[[ ! -e "$D/uv/python/cpython-3.13.1-linux" && ! -e "$HOME/.cache/uv" && -d "$D/uv/python/cpython-3.12.0-linux" && -d "$D/other" ]]'
check "the layered packages are uninstalled, and only those" '[[ "$(cat "$W/calls")" == "rpm-ostree uninstall tesseract minizip-ng-compat" ]]'
check "it says a reboot is needed and does not reboot by itself" '[[ "$OUT" == *"Reboot to finish"* && "$(cat "$W/calls")" != *systemctl* ]]'

OUT="$(bash "$SCRIPT" -y 2>&1)"; RC=$?
check "running again finds nothing to do" '[[ "$OUT" == *"Nothing to remove"* && $RC -eq 0 ]]'

populate
bash "$SCRIPT" -y --keep-packages >/dev/null 2>&1
check "--keep-packages leaves the system packages alone" '[[ ! -e "$W/calls" && ! -e "$D/armada-yomitan" ]]'

populate
mk uv 'exit 0'
bash "$SCRIPT" -y --keep-packages >/dev/null 2>&1
check "with another uv on the system, uv's Python and cache are kept" '[[ -d "$D/uv/python/cpython-3.13.1-linux" && -d "$HOME/.cache/uv" && ! -e "$D/armada-yomitan" ]]'
rm -f "$W/bin/uv"

populate
bash "$SCRIPT" -y --reboot >/dev/null 2>&1
check "--reboot reboots after the packages are uninstalled" '[[ "$(tail -1 "$W/calls")" == "systemctl reboot" ]]'

populate
ARMADA_YOMITAN_HOME="$HOME" bash "$SCRIPT" -y >/dev/null 2>&1; RC=$?
check "it refuses to remove the home folder" '[[ $RC -eq 2 && -d "$D/armada-yomitan" ]]'

rm -rf "$W"
echo; echo "$FAILED failed"; exit $((FAILED > 0))
