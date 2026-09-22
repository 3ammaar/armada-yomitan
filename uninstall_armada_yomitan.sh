#!/usr/bin/env bash
# uninstall_armada_yomitan.sh - remove everything armada-yomitan installed (not the Decky plugin)
#
# Usage:
#   ./uninstall_armada_yomitan.sh                  remove everything (asks first)
#   ./uninstall_armada_yomitan.sh -y --reboot      no questions, reboot when done
#   ./uninstall_armada_yomitan.sh --keep-packages  leave the system packages installed
#   ./uninstall_armada_yomitan.sh --dry-run        only list what would be removed

set -u

ASSUME_YES=0
DO_REBOOT=0
KEEP_PACKAGES=0
DRY_RUN=0

while [ $# -gt 0 ]; do
    case "$1" in
        -y|--yes)         ASSUME_YES=1 ;;
        --reboot)         DO_REBOOT=1 ;;
        --keep-packages)  KEEP_PACKAGES=1 ;;
        --dry-run)        DRY_RUN=1 ;;
        -h|--help)        sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)                echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
    esac
    shift
done

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
APP_DIR="${ARMADA_YOMITAN_HOME:-$HOME/.local/share/armada-yomitan}"
APP_DIR="${APP_DIR/#\~/$HOME}"
ADDON_IDS="armada_yomitan_touch"
PACKAGES="gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good pipewire-gstreamer tesseract tesseract-langpack-jpn
tesseract-langpack-jpn_vert python3-gobject gtk3 minizip-ng-compat xcb-util-cursor"

have_cmd() { command -v "$1" >/dev/null 2>&1; }

safe_dir() {
    case "$1" in
        /*) ;;
        *) return 1 ;;
    esac
    [ "$1" != "/" ] && [ "$1" != "$HOME" ] && [ "$(printf '%s' "$1" | tr -cd / | wc -c)" -ge 2 ]
}

if ! safe_dir "$APP_DIR"; then
    echo "Refusing to remove '$APP_DIR' (set ARMADA_YOMITAN_HOME to the program's own folder)." >&2
    exit 2
fi

REMOVE=()
add_path() { [ -e "$1" ] || [ -L "$1" ] && REMOVE+=("$1"); }

add_path "$APP_DIR"
add_path "/tmp/armada-yomitan-$(id -u)-anki.sock"

ANKI_BASES=("$DATA_HOME/Anki2" "$HOME/.var/app/net.ankiweb.Anki/data/Anki2")
if have_cmd python3 && [ -f "$APP_DIR/ui.json" ]; then
    while IFS= read -r base; do
        [ -n "$base" ] && ANKI_BASES+=("$base")
    done < <(python3 - "$APP_DIR/ui.json" <<'PY' 2>/dev/null
import json, os, sys
cmd = json.load(open(sys.argv[1])).get("anki_cmd") or []
for i, part in enumerate(cmd):
    if part in ("-b", "--base") and i + 1 < len(cmd):
        print(os.path.expanduser(cmd[i + 1]))
    elif part.startswith("--base="):
        print(os.path.expanduser(part[7:]))
PY
)
fi

RESTORE=()
for base in "${ANKI_BASES[@]}"; do
    for id in $ADDON_IDS; do
        add_path "$base/addons21/$id"
    done
    [ -f "$base/prefs21.db.armada-yomitan.bak" ] && RESTORE+=("$base")
done

UV_OURS=0
if [ -x "$APP_DIR/bin/uv" ]; then
    other="$(command -v uv 2>/dev/null || true)"
    if [ -z "$other" ] || [ "$other" = "$APP_DIR/bin/uv" ]; then
        UV_OURS=1
        for dir in "$DATA_HOME"/uv/python/cpython-3.13*; do add_path "$dir"; done
        add_path "$CACHE_HOME/uv"
    fi
fi

PACKAGES_TO_REMOVE=()
if [ "$KEEP_PACKAGES" = 0 ] && have_cmd rpm-ostree && have_cmd python3; then
    layered="$(rpm-ostree status --json 2>/dev/null | python3 -c '
import json, sys
try:
    deployment = json.load(sys.stdin)["deployments"][0]
except (ValueError, KeyError, IndexError):
    sys.exit()
print(" ".join(sorted(set(deployment.get("requested-packages", [])) | set(deployment.get("packages", [])))))
' 2>/dev/null)"
    for pkg in $PACKAGES; do
        for have in $layered; do
            [ "$have" = "$pkg" ] && PACKAGES_TO_REMOVE+=("$pkg")
        done
    done
fi

pids() {
    { pgrep -f "from armada_yomitan.entry import main"; pgrep -f "$APP_DIR/"; } 2>/dev/null | sort -un | grep -vx -e "$$" -e "$PPID"
}
RUNNING="$(pids || true)"

echo "armada-yomitan uninstall"
echo
if [ -n "$RUNNING" ]; then
    echo "Running, will be stopped:"
    for pid in $RUNNING; do printf '  %s  %s\n' "$pid" "$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | cut -c1-100)"; done
fi
if [ "${#REMOVE[@]}" -gt 0 ]; then
    echo "Will be removed:"
    for path in "${REMOVE[@]}"; do echo "  $path"; done
fi
for base in "${RESTORE[@]}"; do echo "Anki's UI size restored in: $base/prefs21.db"; done
if [ "${#PACKAGES_TO_REMOVE[@]}" -gt 0 ]; then
    echo "System packages to uninstall (rpm-ostree, needs a reboot):"
    echo "  ${PACKAGES_TO_REMOVE[*]}"
fi
if [ -z "$RUNNING" ] && [ "${#REMOVE[@]}" = 0 ] && [ "${#RESTORE[@]}" = 0 ] && [ "${#PACKAGES_TO_REMOVE[@]}" = 0 ]; then
    echo "Nothing to remove."
    exit 0
fi
echo
echo "Anki's own data (decks, profiles) and the Decky plugin are not touched."

[ "$DRY_RUN" = 1 ] && exit 0
if [ "$ASSUME_YES" = 0 ]; then
    printf 'Continue? [y/N] '
    read -r answer
    case "$answer" in y|Y|yes|YES) ;; *) echo "Cancelled."; exit 1 ;; esac
fi

if [ -n "$RUNNING" ]; then
    echo "Stopping..."
    # shellcheck disable=SC2086
    kill -TERM $RUNNING 2>/dev/null
    for _ in $(seq 1 30); do
        [ -z "$(pids || true)" ] && break
        sleep 1
    done
    left="$(pids || true)"
    # shellcheck disable=SC2086
    [ -n "$left" ] && kill -KILL $left 2>/dev/null
fi

FAIL=0
for base in "${RESTORE[@]}"; do
    python3 - "$base" <<'PY' || { echo "Could not restore Anki's UI size in $base (is Anki running?)" >&2; FAIL=1; }
import os, pickle, sqlite3, sys
db = os.path.join(sys.argv[1], "prefs21.db")
backup = db + ".armada-yomitan.bak"

def read(path):
    con = sqlite3.connect(path, timeout=5)
    try:
        row = con.execute("select cast(data as blob) from profiles where name = '_global'").fetchone()
        return pickle.loads(row[0]) if row else None
    finally:
        con.close()

old, current = read(backup), read(db)
if isinstance(old, dict) and isinstance(current, dict):
    if "uiScale" in old:
        current["uiScale"] = old["uiScale"]
    else:
        current.pop("uiScale", None)
    con = sqlite3.connect(db, timeout=5)
    try:
        con.execute("update profiles set data = ? where name = '_global'", (pickle.dumps(current, protocol=4),))
        con.commit()
    finally:
        con.close()
os.remove(backup)
PY
done

for path in "${REMOVE[@]}"; do
    rm -rf -- "$path" && echo "removed $path" || { echo "could not remove $path" >&2; FAIL=1; }
done

if [ "${#PACKAGES_TO_REMOVE[@]}" -gt 0 ]; then
    SUDO=""
    [ "$(id -u)" != 0 ] && SUDO="sudo"
    echo "Uninstalling system packages..."
    if $SUDO rpm-ostree uninstall "${PACKAGES_TO_REMOVE[@]}"; then
        echo "Reboot to finish removing the system packages."
        if [ "$DO_REBOOT" = 1 ]; then
            $SUDO systemctl reboot
        fi
    else
        echo "rpm-ostree could not uninstall the packages." >&2
        FAIL=1
    fi
fi

echo
[ "$FAIL" = 0 ] && echo "Done." || echo "Done, with errors."
exit "$FAIL"
