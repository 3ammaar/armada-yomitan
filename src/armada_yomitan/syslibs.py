"""Missing system libraries."""

import re
import subprocess

from armada_yomitan import strings


def missing_libs(program):
    try:
        out = subprocess.run(["ldd", program], capture_output=True, text=True, timeout=30).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return sorted({line.split()[0] for line in out.splitlines() if "not found" in line})


FEDORA_PACKAGES = {
    "libminizip.so.1": "minizip-ng-compat", "libxcb-cursor.so.0": "xcb-util-cursor", "libxkbfile.so.1": "libxkbfile",
    "libxcb-icccm.so.4": "xcb-util-wm", "libxcb-image.so.0": "xcb-util-image", "libxcb-keysyms.so.1": "xcb-util-keysyms",
    "libxcb-render-util.so.0": "xcb-util-renderutil", "libxkbcommon-x11.so.0": "libxkbcommon-x11",
    "libxkbcommon.so.0": "libxkbcommon", "libnss3.so": "nss", "libnssutil3.so": "nss", "libsmime3.so": "nss",
    "libnspr4.so": "nspr", "libasound.so.2": "alsa-lib", "libXcomposite.so.1": "libXcomposite",
    "libXdamage.so.1": "libXdamage", "libXrandr.so.2": "libXrandr", "libXtst.so.6": "libXtst",
    "libXfixes.so.3": "libXfixes", "libxshmfence.so.1": "libxshmfence", "libcups.so.2": "cups-libs",
    "libdbus-1.so.3": "dbus-libs", "libgbm.so.1": "mesa-libgbm", "libdrm.so.2": "libdrm",
    "libEGL.so.1": "libglvnd-egl", "libGL.so.1": "libglvnd-glx", "libpulse.so.0": "pulseaudio-libs",
}


def parse_missing_libs(text):
    return sorted(set(re.findall(r"(lib[\w.+-]*\.so(?:\.\d+)*)[^\n]*cannot open shared object file", text or "")))


def lib_fix(libs):
    pkgs = sorted({FEDORA_PACKAGES[lib] for lib in libs if lib in FEDORA_PACKAGES})
    unknown = sorted(lib for lib in libs if lib not in FEDORA_PACKAGES)
    short = strings.LIBS_SHORT.format(libraries=", ".join(libs[:2])) + (strings.LIBS_SHORT_FEDORA.format(packages=" ".join(pkgs)) if pkgs else "")
    lines = ["Missing system libraries: " + ", ".join(libs)]
    if pkgs:
        lines += ["On a Fedora-based system like this one, install them with:",
                  "    sudo rpm-ostree install " + " ".join(pkgs),
                  "then reboot. (If a package isn't found, look for it with: rpm-ostree search <name>)"]
    if unknown:
        lines.append("No package suggestion for: " + ", ".join(unknown))
    return short, lines
