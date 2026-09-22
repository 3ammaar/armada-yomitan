"""Every user-facing text of the program."""


def by_count(count, one, many):
    """Picks the singular or plural template."""
    return one if count == 1 else many


# ==== Shared ==============================================================================================================
APP_NAME = "Armada OCR Yomitan"
QUIT = "Quit"
NEEDS_ROOT = "Run armada-yomitan as sudo or install system dependencies in the decky plugin"
MISSING_HEADING = "Missing:"
MISSING_PACKAGE = "{label} (package {packages})"
MISSING_OCR = "OCR engine (RapidOCR and its models)"
MISSING_CHROMIUM = "Chromium browser"
MISSING_YOMITAN = "Yomitan"
YES = "Yes"
NO = "No"


# ==== Shared status lines ================================================================================================
READY = "Ready."
ERROR = "Error: {error}"
LOADING_OCR_MODEL = "Loading OCR model…"
OCR_MODEL_FAILED = "OCR model failed to load: {error}"
CAPTURING_TOP_SCREEN = "Capturing the top screen…"
WAITING_FOR_TAP = "Waiting for a tap on the top screen…"
CANCELLED_OR_TIMED_OUT = "Cancelled or timed out."
BACK_TO_GAME = "The top touchscreen has been released."


# ==== Scanning the top screen (the sessions) =============================================================================
TOUCH_GRAB_FAILED_TAPS = "Couldn't grab the top touchscreen."
TOUCH_GRAB_FAILED_TAP = "Couldn't grab the top touchscreen."
TOUCH_GRAB_FAILED_DRAWING = "Couldn't grab the top touchscreen."
STILL_READING_SCREEN = "Still reading the screen…"
STILL_READING_TEXT = "Still reading the text…"
STILL_READING_TAP_QUEUED = "Still reading the text… your tap is queued."
READING_TEXT = "Reading the text…"
READING_TEXT_TAPS_QUEUED = "Reading the text… (taps are queued until it's done)"
SCAN_TIMING_GRAB = "grab {seconds:.1f}"
SCAN_TIMING_ENGINE = ", detect {detect:.1f}, read {read:.1f}"
SCAN_READY = "Ready: {lines} lines in {seconds:.1f}s ({detail})"
SCAN_FAILED = "Scan failed: {error}"
TAP_READY = "Ready. Press the button, then tap another word."
NO_TEXT_NEAR_SPOT = "No text near that spot."
FINISH_DRAWING_FIRST = "Finish drawing first."
PREVIEW_NOT_ENCODED = "Couldn't encode the preview."


# ==== OCR areas (Manual scanning) ========================================================================================
NO_OCR_AREAS = "No OCR areas yet."
NO_OCR_AREAS_HINT = "No OCR areas yet. Open Settings and tap Draw OCR areas."
CHOOSE_MANUAL_FIRST = "Choose Manual under Scanning first."
AREAS_SAVED_ONE = "{count} OCR area saved."
AREAS_SAVED_MANY = "{count} OCR areas saved."
DRAW_ALL_DELETED = "All areas deleted. Drag on the top screen to mark one."
DRAW_START = "Drag on the top screen to mark an area. Tap an area to delete it."
DRAW_CAPTURE_FAILED = "Couldn't capture the top screen: {error}"
DRAW_TOO_SMALL = "That's too small. Drag a bigger area."
DRAW_MAXIMUM = "That's the most areas ({maximum}). Tap one to delete it first."
DRAW_COUNT_ONE = "{count} area. Drag for another, or tap one to delete it."
DRAW_COUNT_MANY = "{count} areas. Drag for another, or tap one to delete it."
DRAW_DELETED = "Deleted an area."
DRAW_HINT = "Drag to mark an area. Tap inside one to delete it."


# ==== Choosing the top screen's source ===================================================================================
SOURCE_NODE_FROM_OPTION = "Node {node} (from --node)"
SOURCE_AUTOMATIC = "Automatic"
SCREEN_SIZE = "{width}×{height}"
SCREEN_WITH_SIZE = "{label} · {width}×{height}"
SCREEN_TOP = "Top screen"
SCREEN_BOTTOM = "Bottom screen"
SCREEN_OTHER = "Screen"
CAPTURING_SCREEN = "Capturing the {label} ({width}×{height})."
NODES_LOOKING = "Looking for screens…"
NODES_TAP_TO_CAPTURE = "Tap the screen to capture."
NODES_NONE_FOUND = "No other screen found."
NODES_NONE_FOUND_WHY = "No other screen found. ({error})"
NODE_NOT_DIGITS = "The node number must be a number."
NODE_TRYING = "Trying node {node}…"
NODE_NO_FRAME = "Node {node} didn't deliver a frame: {reason}"
NODE_NOT_A_PICTURE = "Node {node} delivered something that isn't a picture."
KEYBOARD_DID_NOT_START = "The keyboard didn't start in Yomitan's settings."


# ==== System packages (the view in Settings, and the checks behind it) ===================================================
SYSDEPS_CHECKING = "Checking the system packages…"
SYSDEPS_WAITING_FOR_RESTART = "The packages are installed and waiting for a restart."
SYSDEPS_ALL_PRESENT = "Every system package the program needs is installed."
SYSDEPS_SOME_MISSING = "Some system packages are missing. Installing them takes a few minutes and a restart."
SYSDEPS_ONLY_OPTIONAL_MISSING = "Only optional system packages are missing."
SYSDEPS_INSTALLING = "Installing… this can take several minutes. Keep the screen on."
SYSDEPS_ALREADY_INSTALLED = "Every system package is already installed."
SYSDEPS_INSTALLED_RESTART = "Installed. Restart the device to finish."

CHECK_GST_LAUNCH = "gst-launch-1.0"
CHECK_GST_VIDEOCONVERT = "GStreamer videoconvert"
CHECK_GST_PNGENC = "GStreamer pngenc"
CHECK_GST_PIPEWIRESRC = "GStreamer pipewiresrc"
CHECK_TESSERACT = "tesseract"
CHECK_TESSERACT_JPN = "tesseract language: jpn"
CHECK_TESSERACT_JPN_VERT = "tesseract language: jpn_vert (vertical text)"
CHECK_GTK = "Python GTK3 + GdkPixbuf"
CHECK_MINIZIP = "libminizip.so.1 (Anki's web view)"
CHECK_XCB_CURSOR = "libxcb-cursor.so.0 (Anki's Qt window plugin)"
CHECK_RUN_BOTTOM = "armada-run-bottom (needed to run on the bottom screen)"

PKG_NO_SUDO = "sudo isn't available, so the system packages can't be installed from here."
PKG_NO_RPM_OSTREE = ("rpm-ostree isn't installed, so this isn't an rpm-ostree Armada image. Install these with your package "
                     "manager instead: pipewire-gstreamer tesseract tesseract-langpack-jpn tesseract-langpack-jpn_vert "
                     "minizip-ng-compat xcb-util-cursor")
PKG_LAYERING = "Layering with rpm-ostree: {packages}"
PKG_RETRY_WITHOUT_OPTIONAL = "Install failed; retrying without the optional extras ({packages})..."
PKG_INSTALL_FAILED = "Install failed (rpm-ostree exited with an error). Its output is in the log."
PKG_REBOOT_FAILED = "Couldn't restart the device. Restart it from the power menu instead."


# ==== Capturing the top screen (errors that reach the screen) ============================================================
CAPTURE_SCREEN_NOT_FOUND = "Couldn't find the {size} screen you chose. Pick it again in Settings."
CAPTURE_NO_NODE = ("Couldn't find a gamescope PipeWire node (no pw-dump/pw-cli/wpctl, or none "
                   "listed). Choose the top screen in Settings, or pass --node ID.")
CAPTURE_MANY_NODES = "Found {count} candidate nodes {nodes}."
CAPTURE_BAD_COMMAND = ("Capture command uses {reason}, but it must write a PNG to stdout "
                       "and only use {{node}}.")
CAPTURE_TOOL_MISSING = "Capture tool not found: {tool}."
CAPTURE_TIMED_OUT = "Capture timed out (try moving something on the top screen)."
CAPTURE_NO_PIPEWIRE_PLUGIN = "GStreamer's PipeWire plugin (pipewiresrc) isn't installed."
CAPTURE_FAILED = "Capture failed: {output}"
CAPTURE_NOT_A_PNG = "Capture command didn't output a PNG on stdout."


# ==== The touchscreen and the OCR engines (errors that reach the screen) =================================================
TOUCH_NO_COORDINATES = "{path} has no touch coordinates"
TOUCH_NOT_CHOSEN = "No touchscreen chosen."
TOUCH_NO_DEVICE = "No input device name contains '{name}'."
TOUCH_SEVERAL_DEVICES = "Several devices match: {devices}"
TOUCH_NO_PERMISSION = "No permission to read {path}."

OCR_RAPIDOCR_MISSING = "rapidocr isn't installed."
OCR_OPENCV_MISSING = "opencv/numpy are missing."
OCR_CROP_NOT_DECODED = "Couldn't decode the crop for RapidOCR."
OCR_TESSERACT_MISSING = "tesseract not found"
OCR_TESSERACT_FAILED = "tesseract failed: {output}"
OCR_IMAGE_BLANK = "The region sent to OCR is a single flat colour (blank or black frame?)."
OCR_IMAGE_NOT_ENCODED = "Couldn't encode the image for OCR."
OCR_SCREEN_NOT_ENCODED = "Couldn't encode the picture of the top screen."


# ==== Anki (the button, the setup view, installing it here) ==============================================================
ANKI_IN_FRONT = "Anki is in front. Tap Back to OCR to return here."
ANKI_NOT_ANSWERING = "Anki is running but isn't answering. Try again or restart your device."
ANKI_PICK_OR_INSTALL = "Pick the Anki you already have, browse to it, or install it here."
ANKI_NOT_FOUND = "Anki wasn't found on this device. Browse to it, or install it here."
ANKI_NOT_ANKI = "That doesn't look like Anki. Pick the anki program itself, or the folder it is in."
ANKI_SET_UP = "Anki is set up: {label}"
ANKI_SET_UP_TAP = "Anki is set up ({label}). Tap the Anki button to open it."
ANKI_STARTING_INSTALL = "Starting…"
ANKI_REINSTALLING = "Reinstalling Anki…"
ANKI_REINSTALLED = "Anki reinstalled."
ANKI_INSTALL_CANCELLED = "Install cancelled."
ANKI_INSTALL_FAILED = "Install failed: {error}"
ANKI_INSTALLED_NEEDS_LIBS = "Anki is installed, but it needs {libraries}. Details are in the console."
ANKI_STARTING = "Starting Anki… it can take a little while."
ANKI_START_FAILED = "Couldn't start Anki: {error}"
ANKI_CLOSED = "Anki closed."
ANKI_CANT_START = "Anki can't start: it needs {libraries}. The console has the command to fix it."
ANKI_CLOSED_WITH_ERROR = "Anki closed with an error."
ANKI_CLOSED_WITH_ERROR_DETAIL = "Anki closed with an error: {detail}"

# Where an Anki was found. The two "short" forms are how the choice is shown once it is picked.
ANKI_INSTALLED_BY_APP = "Installed by this app"
ANKI_FOUND_ON_SYSTEM = "Anki on this system"
ANKI_FOUND_FLATPAK = "Anki (Flatpak)"
ANKI_FOUND_IN_PREFIX = "Anki in "
ANKI_FOUND_IN = ANKI_FOUND_IN_PREFIX + "{path}"
ANKI_SHORT_SYSTEM = "System Anki"

# The install's steps (shown while it runs) and its errors.
ANKI_NOT_ENOUGH_SPACE = "Not enough free space: about 3 GB is needed and {free:.1f} GB is free."
ANKI_STEP_PYTHON = "Setting up Python"
ANKI_STEP_DOWNLOAD = "Downloading Anki and Qt"
ANKI_STEP_RUNNING = "{title}…"
ANKI_STEP_OUTPUT = "{title}: {line}"
ANKI_STEP_FAILED = "{title} failed ({reason})"
ANKI_STEP_EXIT_CODE = "exit {code}"

# The system library a missing Anki dependency stands for (used in ANKI_INSTALLED_NEEDS_LIBS and ANKI_CANT_START).
LIBS_SHORT = "the system library {libraries}"
LIBS_SHORT_FEDORA = " (Fedora package: {packages})"


# ==== Installing the program's own parts (first run, --setup) ============================================================
SETUP_FAILED = "Install failed: {error}"
SETUP_DOWNLOADING_OCR_MODELS = "Downloading the OCR models (one time) ..."
SETUP_DOWNLOADING_CHROMIUM = "Downloading Chromium (one time, roughly 150 MB) ..."
SETUP_CHROMIUM_NOT_FOUND = "Chromium was downloaded but its program wasn't found under {folder}."
SETUP_CHROMIUM_LIBS_MISSING = ("\nWARNING: Chromium needs system libraries this image doesn't have: {libraries}"
                               "\nIt won't start until they're installed (e.g. with rpm-ostree).\n")
SETUP_STEP_FAILED = "Setup step failed (exit {code}): {command} ..."
SETUP_CURL_MISSING = "curl not found"
SETUP_EXIT_CODE = "exit {code}"
SETUP_DOWNLOAD_FAILED = "Couldn't download {url} (curl: {curl}; urllib: {urllib}). Setup needs internet access."
SETUP_DOWNLOADING_UV = "Downloading the uv installer from {url} ..."
SETUP_UV_NOT_FOUND = "uv installed but wasn't found at {path}."
SETUP_DOWNLOADING_YOMITAN = "Downloading Yomitan ..."
SETUP_OCR_PRESENT = "The OCR engine is already installed."
SETUP_CHROMIUM_PRESENT = "Chromium is already installed."
SETUP_YOMITAN_PRESENT = "Yomitan is already installed."
SETUP_YOMITAN_READY = "Yomitan {version} is ready in {folder}"
SETUP_YOMITAN_NO_CHROME_BUILD = "Couldn't find a Chrome build among the latest Yomitan release's files."
SETUP_YOMITAN_NO_MANIFEST = "The Yomitan download contains no manifest.json."


# ==== The first-run window (installing the program's parts) ==============================================================
SETUP_WINDOW_TITLE = "armada-yomitan needs to download its parts"
SETUP_WINDOW_INFO = "It takes a few minutes; keep this screen on."
SETUP_INSTALL = "Install"
SETUP_CONFIRM_INSTALL = "Install now?"
SETUP_CONFIRM_QUIT = "Quit?"
SETUP_CONFIRM_QUIT_RUNNING = "Quit? The installation will be stopped."
SETUP_TRY_AGAIN = "Try again"
SETUP_REBOOT_NEEDED = "Installed. Restart the device to finish installing the system packages."
SETUP_RESTART_DEVICE = "Restart the device"
SETUP_CONFIRM_RESTART = "Restart the device now?"
SETUP_STARTING = "Starting…"


# ==== The simple window (used when the web interface isn't installed) ====================================================
SIMPLE_BTN_IDLE = "🔍  Tap, then touch a word on the top screen"
SIMPLE_BTN_BUSY = "Cancel  (waiting for a tap on the top screen…)"
SIMPLE_BTN_SCAN = "🔍  Scan the top screen"
SIMPLE_BTN_RESCAN = "🔍  Scan again"
SIMPLE_BTN_DONE = "Done – give the top touchscreen back"
SIMPLE_CONFIDENCE = "{engine}: confidence {confidence:.0f}"
SIMPLE_CONFIDENCE_ESTIMATED = "{engine}: confidence {confidence:.0f} (character positions estimated)"
SIMPLE_NO_TEXT_NEAR_TAP = "No text found near the tap."
SIMPLE_NO_TEXT_IN_REGION = "No text detected."
SIMPLE_RUNNING_OCR = "Running OCR…"


# ==== The page on the bottom screen (data/page.html) =====================================================================
# Used by the page as @@NAME@@ in its HTML or S.NAME in its script (assets.render_texts); templates in the script go through fmt().

# -- the main screen
PAGE_STARTING = "Starting…"
PAGE_SCAN_SCREEN = "🔍 Scan screen"
PAGE_SCAN_AGAIN = "🔍 Scan again"
PAGE_SCAN_AREAS = "🔍 Scan areas"
PAGE_TAP_A_WORD = "🔍 Tap a word"
PAGE_READING = "Reading…"
PAGE_CANCEL = "Cancel"
PAGE_DONE = "Done"
PAGE_ANKI = "Anki"
PAGE_LOST_CONTACT = "Lost contact with the OCR helper."

# -- Settings
PAGE_BACK_TO_LOOKUP = "← Back to lookup"
PAGE_YOMITAN_TEXT_SIZE = "Yomitan text size"
PAGE_SCANNING = "Scanning"
PAGE_WHOLE_SCREEN = "Whole screen"
PAGE_SINGLE_TAP = "Single tap"
PAGE_MANUAL = "Manual"
PAGE_OCR_AREAS = "OCR areas"
PAGE_AREAS_NONE = "none yet"
PAGE_AREAS_ONE = "{count} area"
PAGE_AREAS_MANY = "{count} areas"
PAGE_DRAW_AREAS = "Draw OCR areas"
PAGE_FINISH_DRAWING = "Finish drawing"
PAGE_SCAN_DETAIL = "Scan detail"
PAGE_SCAN_DETAIL_HINT = "Fast reads at lower resolution"
PAGE_DETAIL_FAST = "Fast"
PAGE_DETAIL_BALANCED = "Balanced"
PAGE_DETAIL_FULL = "Full"
PAGE_SHOW_PREVIEW = "Show touch preview"
PAGE_ON = "On"
PAGE_OFF = "Off"
PAGE_TOP_SCREEN_SOURCE = "Top screen source"
PAGE_AUTOMATIC = SOURCE_AUTOMATIC
PAGE_CHOOSE = "Choose…"
PAGE_ANKI_BUTTON = "Anki button"
PAGE_ANKI_BUTTON_HINT = "Adds it to the main screen"
PAGE_ANKI_LOCATION = "Anki location"
PAGE_NOT_SET_UP = "Not set up"
PAGE_CHANGE = "Change…"
PAGE_ANKI_REINSTALL = "Reinstall Anki"
PAGE_ANKI_REINSTALL_CONFIRM_LATEST = "Are you sure? Your Anki is up to date."
PAGE_ANKI_REINSTALL_CONFIRM_UPDATE = "Are you sure? This will also update Anki to the latest version."
PAGE_ANKI_SIZE = "Anki size"
PAGE_ANKI_SIZE_HINT = "Applies the next time Anki opens"
PAGE_SYSTEM_PACKAGES = "System packages"
PAGE_NOT_CHECKED_YET = "Not checked yet"
PAGE_CHECK = "Check…"
PAGE_OPEN_YOMITAN_SETTINGS = "Open Yomitan settings"
PAGE_REINSTALL = "Re-install dependencies"
PAGE_REINSTALL_CONFIRM = "Re-install the dependencies? The app restarts and installs everything again."
PAGE_YES = YES
PAGE_NO = NO
PAGE_QUIT = QUIT

# -- drawing the OCR areas
PAGE_CLEAR = "Clear"
PAGE_DRAW_HELP = "On the top screen: drag to mark an area, tap an area to delete it."

# -- the system-packages view
PAGE_BACK = "← Back"
PAGE_SYSDEPS_CHECKING = SYSDEPS_CHECKING
PAGE_INSTALL_THEM = "Install them"
PAGE_RESTART_NOW = "Restart the device now"
PAGE_PACKAGE_NEEDED = "needed"
PAGE_PACKAGE_OPTIONAL = "optional"
PAGE_PACKAGE_NAMES = " · {packages}"
PAGE_PACKAGES_ALL_PRESENT = "All present"
PAGE_PACKAGES_NEEDED = "{needed} needed, {optional} optional missing"
PAGE_PACKAGES_OPTIONAL_ONLY = "{optional} optional missing"

# -- setting up Anki, and browsing for it
PAGE_ANKI_LOOKING = "Looking for Anki…"
PAGE_ANKI_INSTALL = "Install Anki automatically"
PAGE_ANKI_BROWSE = "Browse for Anki…"
PAGE_ANKI_CANCEL_INSTALL = "Cancel the install"
PAGE_USE_THIS_FOLDER = "Use this folder"
PAGE_UP_ONE_FOLDER = "↑  Up one folder"
PAGE_FOLDER = "📁 {name}"
PAGE_PROGRAM_HINT = "program: tap to use it"
PAGE_USE_THIS_ONE = "tap to use this one"

# -- choosing the top screen's source
PAGE_REFRESH = "↻ Refresh"
PAGE_NODE_NUMBER = "Node number"
PAGE_NODE_NUMBER_HINT = "Manually set the node number below"
PAGE_USE = "Use"
PAGE_NODE_NOT_DIGITS = NODE_NOT_DIGITS
PAGE_SOURCE_CURRENT = "✓ {label}"
PAGE_SOURCE_DETAIL = "{size} · node {id}"
PAGE_BACK_TO_SETTINGS = "← Back to settings"


# ==== Labels the app adds to Anki's windows (the add-on written into Anki) ===============================================
# The add-on runs inside Anki, so it gets these as a table filled in when the program writes it out (assets.render_addon).
ADDON_MAIN_TITLE = "Anki"
ADDON_BACK_TO_OCR = "Back to OCR"
ADDON_CLOSE = "×  Close"


# ==== The Decky plugin (its panel and the messages of its backend) =======================================================
# The plugin ships a copy of this file for its backend and gets the panel's texts (DECKY_ constants used by the panel) as a generated
# module: see tools/build_all.py.
DECKY_NAME = "Armada OCR Yomitan"                # the plugin's name in Decky's panel: its title, its list entry and its notifications
DECKY_LAUNCH = "Launch"
DECKY_STOP = "Stop"
DECKY_WENT_WRONG = "Something went wrong: {error}"
DECKY_ALREADY_RUNNING = "armada-yomitan is already running"
DECKY_NOT_BUNDLED = "armada-yomitan isn't in the plugin (bin/armada-yomitan is missing)"
DECKY_STOPPED_AT_ONCE = ("armada-yomitan stopped at once (status {code}); see {output} and "
                         "~/.local/share/armada-yomitan/armada-yomitan.log")
DECKY_STARTING = "armada-yomitan is starting on the bottom screen"
DECKY_NOT_RUNNING = "armada-yomitan is not running"
DECKY_COULD_NOT_STOP_ALL = "couldn't stop everything (still running: {pids})"
DECKY_STOPPED = "armada-yomitan stopped"
DECKY_LAUNCH_FAILED = "couldn't launch: {error}"
DECKY_STOP_FAILED = "couldn't stop: {error}"

# -- the panel's Install System Dependencies button
DECKY_INSTALL_DEPENDENCIES = "Install System Dependencies"
DECKY_INSTALL_CONFIRM_TITLE = "Install/reinstall system dependencies?"
DECKY_PART_UV = "uv (Python package installer)"
DECKY_PART_OCR = "RapidOCR and ONNX Runtime (Python packages in a private environment) with the OCR models"
DECKY_PART_CHROMIUM = "Chromium (private build for the app's page, about 150 MB, via Playwright)"
DECKY_PART_YOMITAN = "Yomitan (latest release from GitHub, patched for the app)"
DECKY_INSTALL_CONFIRM_OK = "Install"
DECKY_INSTALL_CONFIRM_CANCEL = "Cancel"
DECKY_TAG_INSTALLED = "installed"
DECKY_TAG_OPTIONAL = "optional"
DECKY_INSTALLING = "Installing: {line}"
DECKY_INSTALL_STARTED = "Installing dependencies. This takes a few minutes."
DECKY_INSTALL_DONE = "Dependencies installed. You can launch armada-yomitan."
DECKY_INSTALL_DONE_REBOOT = "Dependencies installed. Restart the device to finish the system packages, then launch armada-yomitan."
DECKY_INSTALL_FAILED = "Install failed: {error}"
DECKY_INSTALL_BUSY = "Dependencies are already being installed"
DECKY_INSTALL_STOP_FIRST = "Stop armada-yomitan before installing"
DECKY_LAUNCH_INSTALLING = "Dependencies are being installed; launch when that is done"
DECKY_DEPENDENCIES_UNREADABLE = "Couldn't read the dependency list: {error}"

# -- the panel's Advanced Settings: what is passed to the program when it is launched
DECKY_ADVANCED = "Advanced Settings"
DECKY_BACK = "Back"
DECKY_DEFAULT = "Default"
DECKY_APPLIES_NEXT_LAUNCH = "Applies the next time you launch."
DECKY_NOT_SET = "Not set"
DECKY_DEGREES = "{degrees}°"
DECKY_OPT_ROTATION = "Screen Rotation"
DECKY_OPT_TOUCH = "Touch Input Name"
DECKY_OPT_NODE = "Top Screen Node"
DECKY_OPT_MODE = "Scan Mode"
DECKY_OPT_ENGINE = "OCR Engine"
DECKY_OPT_SCAN_LENGTH = "Lookup Length"
DECKY_OPT_UI_SCALE = "Page Scale"
DECKY_OPT_NO_GRAB = "Share Touch With Game"
DECKY_MODE_SCREEN = PAGE_WHOLE_SCREEN
DECKY_MODE_TAP = PAGE_SINGLE_TAP
DECKY_MODE_MANUAL = PAGE_MANUAL
DECKY_ENGINE_AUTO = SOURCE_AUTOMATIC
DECKY_ENGINE_RAPIDOCR = "RapidOCR"
DECKY_ENGINE_TESSERACT = "Tesseract"


# ==== What counts as an error ============================================================================================
# A status-line message that starts with one of these (any capitalisation) is an error: it is also printed on the console in full.
ERROR_STARTS = ("Error", "Scan failed", "Couldn't", "Could not", "Can't", "Anki can't", "Install failed", "OCR model failed",
                "Anki closed with an error", "That doesn't look like", "Not enough", "No OCR areas yet")
