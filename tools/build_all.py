#!/usr/bin/env python3
"""Builds dist/armada-yomitan and dist/armada-yomitan-decky.zip."""

import argparse
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import zipapp
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PLUGIN = ROOT / "decky-plugin"
CACHE = pathlib.Path.home() / ".cache" / "armada-yomitan-decky"
STRINGS_PY = ROOT / "src" / "armada_yomitan" / "strings.py"
NAME = "armada-yomitan"


class BuildError(Exception):
    pass


def build_executable(target):
    target = pathlib.Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    def include(path):
        return "__pycache__" not in path.parts and path.suffix != ".pyc"

    zipapp.create_archive(ROOT / "src", target, interpreter="/usr/bin/env python3", main="armada_yomitan.entry:main",
                          filter=include, compressed=True)
    os.chmod(target, 0o755)
    return target


def find_npm():
    local = CACHE / "node" / "bin"
    path = os.environ["PATH"] + (os.pathsep + str(local) if local.is_dir() else "")
    npm = shutil.which("npm", path=path)
    if not npm:
        raise BuildError("The Decky plugin's panel needs Node.js (npm), which wasn't found. Install Node 18 or newer, or unpack it into "
                         "~/.cache/armada-yomitan-decky/node. (The single file was built; build only that with --only executable.)")
    return npm, dict(os.environ, PATH=str(pathlib.Path(npm).parent) + os.pathsep + os.environ["PATH"])


def load_strings():
    spec = importlib.util.spec_from_file_location("armada_yomitan_strings", STRINGS_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plugin_manifest():
    manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    manifest["name"] = load_strings().DECKY_NAME
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def panel_strings():
    module = load_strings()
    lines = ["// Generated from src/armada_yomitan/strings.py by tools/build_all.py; edit the texts there."]
    lines += [f"export const {name} = {json.dumps(value, ensure_ascii=False)};"
              for name, value in vars(module).items() if name.startswith("DECKY_") and isinstance(value, str)]
    return "\n".join(lines) + "\n"


def build_panel():
    npm, env = find_npm()
    work = CACHE / "build"
    work.mkdir(parents=True, exist_ok=True)
    for item in ("package.json", "package-lock.json", "rollup.config.js", "tsconfig.json"):
        if (PLUGIN / item).exists():
            shutil.copy2(PLUGIN / item, work / item)
    # the panel must be built with the manifest that goes into the zip
    (work / "plugin.json").write_text(plugin_manifest(), encoding="utf-8")
    shutil.rmtree(work / "src", ignore_errors=True)
    shutil.copytree(PLUGIN / "src", work / "src")
    (work / "src" / "strings.ts").write_text(panel_strings(), encoding="utf-8")
    shutil.rmtree(work / "dist", ignore_errors=True)
    steps = ([npm, "ci" if (PLUGIN / "package-lock.json").exists() else "install", "--no-audit", "--no-fund"], [npm, "run", "build"])
    for step in steps:
        if subprocess.run(step, cwd=work, env=env).returncode != 0:
            raise BuildError(f"The panel's build failed ({' '.join(step[1:])}); its output is above.")
    if not (PLUGIN / "package-lock.json").exists() and (work / "package-lock.json").exists():
        shutil.copy2(work / "package-lock.json", PLUGIN / "package-lock.json")
    built = work / "dist" / "index.js"
    if not built.exists():
        raise BuildError("The panel didn't build: dist/index.js is missing.")
    return built


def assemble_plugin(stage, panel, executable):
    shutil.rmtree(stage, ignore_errors=True)
    (stage / "dist").mkdir(parents=True)
    (stage / "bin").mkdir()
    for item in ("main.py", "package.json"):
        shutil.copy2(PLUGIN / item, stage / item)
    (stage / "plugin.json").write_text(plugin_manifest(), encoding="utf-8")
    shutil.copy2(STRINGS_PY, stage / "strings.py")
    shutil.copy2(panel, stage / "dist" / "index.js")
    shutil.copy2(executable, stage / "bin" / NAME)
    return stage


def make_zip(folder, target):
    target = pathlib.Path(target)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo.from_file(path, f"{NAME}/{path.relative_to(folder).as_posix()}")
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o755 if path.name == NAME else 0o644) << 16
                z.writestr(info, path.read_bytes())
    return target


def build(only=None):
    DIST.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(DIST / "decky", ignore_errors=True)
    built = []
    executable = None
    if only in (None, "executable"):
        executable = build_executable(DIST / NAME)
        built.append(executable)
    if only in (None, "plugin"):
        stage = CACHE / "stage" / NAME
        try:
            panel = build_panel()
        except BuildError as e:
            e.built = built
            raise
        if executable is None:
            executable = build_executable(CACHE / "stage" / f"{NAME}.pyz")
        built.append(make_zip(assemble_plugin(stage, panel, executable), DIST / f"{NAME}-decky.zip"))
    return built


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the single-file app and the Decky plugin zip into dist/.")
    parser.add_argument("--only", choices=("executable", "plugin"), help="build just one of them")
    args = parser.parse_args(argv)
    try:
        built = build(args.only)
    except BuildError as e:
        for path in getattr(e, "built", []):
            print(f"built {path} ({path.stat().st_size / 1024:.0f} KiB)")
        print(f"\n{e}", file=sys.stderr)
        return 1
    for path in built:
        print(f"built {path} ({path.stat().st_size / 1024:.0f} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
