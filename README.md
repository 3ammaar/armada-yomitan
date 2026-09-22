# armada-yomitan

Bottom-screen OCR + Yomitan + Anki for the AYN Thor (on Armada OS). Play a game on the top screen, tap text, get the
dictionary entry (and Anki mining) on the bottom screen. It is currently only tested with Japanese dictionaries.

> **⚠️ Disclaimer:** This project was written with very heavy use of AI. It's just a tool I wanted for personal use, and I haven't reviewed much of the code, but I've tested it on a fresh install of Armada and released it here in case anyone else can make use of it.

## Install and run

1. Download `armada-yomitan-decky.zip` onto your device.
2. Enter Decky settings on your device, enable developer mode from **General -> Other**, then **Install Plugin from ZIP File** under the developer settings. Navigate to and select `armada-yomitan-decky.zip` to install it.
3. Open Decky's menu, select **Armada OCR Yomitan**, then tap **Install System Dependencies** and confirm to install packages related to OCR and Chromium, as well as the latest release of Yomitan.
4. Restart the device. On a first install this is mandatory.
5. Tap **Launch** within the **Armada OCR Yomitan**  Decky plugin menu.
6. Enter settings and choose a **Top screen source** to select the screen that the OCR will target.
7. Enter settings and **Open Yomitan settings** to install dictionaries. See https://yomitan.wiki/getting-started/ for more.
8. On the main program's lookup page, tap **Scan screen**, then tap a word on the top screen to look it up within the installed dictionaries.
9. Press **Done** to give touch input back to the top screen.

## Using Anki
1. After launching, enter settings and enable the Anki button.
2. Back on the main page, tap **Anki**. This will prompt you to either automatically install Anki or navigate to an existing installation.
3. After launching Anki for the first time, the UI will likely be very small. Set the language within Anki and any other setup required, until you arrive at the main Anki page.
4. Tap the **Back to OCR** button to return to the main program, enter settings again and adjust **Anki size**. You may need to return to Anki, exit it via **File -> Exit** and relaunch via the Anki button for the UI scale to adjust.
5. Optionally, within Anki, go to **Tools -> Add-ons** and install the AnkiConnect add-on (https://ankiweb.net/shared/info/2055492159). Tap **Back to OCR**, return to the main program, and navigate to **Open Yomitan settings** before following https://yomitan.wiki/anki/.

## Uninstall

The Decky plugin can be uninstalled from Decky's plugin settings, but it will leave behind its dependencies (which shouldn't be an issue other than taking 1-1.5 GB). If you want to uninstall these, use `uninstall_armada_yomitan.sh`.

```
./uninstall_armada_yomitan.sh                  # removes everything below, after asking
./uninstall_armada_yomitan.sh --dry-run        # only lists what it would remove
./uninstall_armada_yomitan.sh -y --reboot      # no questions, reboot when done
./uninstall_armada_yomitan.sh --keep-packages  # leave the system packages installed
```

It removes `~/.local/share/armada-yomitan` (or `ARMADA_YOMITAN_HOME`), reverts its changes to Anki, removes uv's Python and cache when uv came from this program, and removes the system packages it layered with rpm-ostree (a reboot finishes that).

## Build

`python3 tools/build_all.py` builds the Decky plugin `dist/armada-yomitan-decky.zip` and also a basic executable `dist/armada-yomitan` that can be used instead.
