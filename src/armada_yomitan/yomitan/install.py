"""Installing Yomitan."""

import io
import json
import os
import shutil
import zipfile

from armada_yomitan import strings
from armada_yomitan.paths import EXT_DIR
from armada_yomitan.toolchain import download, report
from armada_yomitan.yomitan.patch import apply_ext_patches

YOMITAN_RELEASE_API = "https://api.github.com/repos/yomidevs/yomitan/releases/latest"


def yomitan_asset(release):
    assets = [(a.get("name", ""), a.get("browser_download_url", "")) for a in release.get("assets", [])]
    for name, url in assets:
        if name == "yomitan-chrome.zip":
            return url
    for name, url in assets:
        if "chrome" in name.lower() and name.endswith(".zip") and "dev" not in name.lower():
            return url
    raise RuntimeError(strings.SETUP_YOMITAN_NO_CHROME_BUILD)


def install_yomitan(say=None):
    report(say, strings.SETUP_DOWNLOADING_YOMITAN)
    release = json.loads(download(YOMITAN_RELEASE_API))
    zf = zipfile.ZipFile(io.BytesIO(download(yomitan_asset(release), timeout=300)))
    names = zf.namelist()
    manifests = sorted((n for n in names if n.endswith("manifest.json")), key=len)
    if not manifests:
        raise RuntimeError(strings.SETUP_YOMITAN_NO_MANIFEST)
    prefix = manifests[0][:-len("manifest.json")]
    shutil.rmtree(EXT_DIR, ignore_errors=True)
    os.makedirs(EXT_DIR)
    root = os.path.realpath(EXT_DIR)
    for name in names:
        if not name.startswith(prefix) or name.endswith("/"):
            continue
        dest = os.path.realpath(os.path.join(EXT_DIR, name[len(prefix):]))
        if not dest.startswith(root + os.sep):               # never write outside the folder
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with zf.open(name) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
    report(say, strings.SETUP_YOMITAN_READY.format(version=apply_ext_patches(), folder=EXT_DIR))
