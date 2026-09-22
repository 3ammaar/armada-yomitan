# armada-yomitan: Decky Loader plugin

A panel with **Launch**, **Stop**, **Install System Dependencies** and **Advanced Settings**. Launch starts armada-yomitan on the bottom screen; Stop ends it and
everything it started. Because the app is started by the plugin and not by a Steam shortcut, Steam doesn't treat it as a running game.

## Build and install

```
python3 tools/build_all.py                   # -> dist/armada-yomitan-decky.zip (and dist/armada-yomitan, the app on its own)
python3 tools/build_all.py --only plugin     # just the zip
```

The panel's build needs Node 18+ (npm) and internet access; it is built in `~/.cache/armada-yomitan-decky`, so nothing lands in the
project. Install the zip with Decky's developer option "Install plugin from ZIP", or unzip it into `~/homebrew/plugins/` and restart
Decky Loader. The plugin carries the app (`bin/armada-yomitan`, run with `/usr/bin/python3`), so rebuild the plugin when the app
changes. The first Launch shows the app's install window.

All of the plugin's texts, including its name in Decky (`DECKY_NAME`), are in `src/armada_yomitan/strings.py`; edit them there and rebuild.

## Install System Dependencies

Asks for confirmation ("Install/reinstall system dependencies?"), listing the system packages (optional ones and ones already installed are marked) and
the app's own parts: uv, RapidOCR with ONNX Runtime and the OCR models, a private Chromium and Yomitan. Then it installs all of it: the system packages with
rpm-ostree as root (so no password) and the parts as your user under `~/.local/share/armada-yomitan`; anything already installed is kept. Progress shows under the button and the output is kept in `install-output.log` next to the plugin's log. A restart is needed afterwards
when system packages were added. It can't run while the app is running, and Launch is refused while it runs. The app started from here shows
"Run armada-yomitan as sudo or install system dependencies in the decky plugin" with only Quit if anything is still missing.

## Advanced Settings

Launch arguments, saved as you change them and used the next time you press Launch. An empty setting passes nothing, so the app's own
default applies. **Default** resets everything to nothing except Screen Rotation 270 and Touch Input Name `top_touchscreen`.

| Setting | Argument |
|---|---|
| Screen Rotation | `--rotation` |
| Touch Input Name | `--touch` |
| Top Screen Node | `--node` |
| Scan Mode | `--mode` |
| OCR Engine | `--engine` |
| Lookup Length | `--scan-length` |
| Page Scale | `--ui-scale` |
| Share Touch With Game | `--no-grab` |

## Logs

The app's own log is `~/.local/share/armada-yomitan/armada-yomitan.log`; the plugin's is under `~/homebrew/logs/`.
