# Text Capture

**Text Capture** is a [Capture2Text](https://capture2text.sourceforge.net/)-style screen OCR tool for Ubuntu. Press a hotkey, drag a box around any text on the screen, and the text is copied to your clipboard, ready to paste anywhere.

It runs quietly in the background and never pauses, freezes or steals focus from your other apps or the system.

> **Project status: version 0.1.** Tested on Ubuntu 24.04 in an Xorg session. Wayland support is built but has not been tested on a Wayland session yet. Remaining checks are tracked in [openspec/changes/add-text-capture-core/tasks.md](openspec/changes/add-text-capture-core/tasks.md).

## Features

- **Global hotkey:** `Ctrl+Q` by default. It works in any app, and you can change it in Settings.
- **Region capture:** the screen freezes and you drag a rectangle over the text you want. `Esc` or right-click cancels.
- **OCR** with [Tesseract](https://github.com/tesseract-ocr/tesseract), in any language you have installed.
- **Copy to clipboard:** paste the text anywhere with `Ctrl+V`. If no text is found, your clipboard is left as it was.
- **Tray icon** with a menu for language and settings.
- **Works in both Ubuntu on Xorg and Ubuntu on Wayland.**
- **Private:** screenshots and text stay on your computer. Nothing is sent over the network, and no screenshot files are kept.

## Requirements

- Ubuntu 24.04 LTS with the standard GNOME desktop (Xorg or Wayland session)
- These packages, all from Ubuntu's standard repositories:

  | Package | Why it's needed |
  |---|---|
  | `python3-pyqt6` | App window, tray icon and clipboard |
  | `qt6-wayland` | Native support for Wayland sessions |
  | `tesseract-ocr` | Text recognition engine |
  | `tesseract-ocr-eng` | English OCR language data |
  | `python3-pytest` | Running the tests (development only) |

## Install

### 1. Get the code

```bash
sudo apt install git
git clone https://github.com/CreditStar0117/Text_Capture-Ubuntu-.git
cd Text_Capture-Ubuntu-
```

### 2. Install the required packages

The install script checks which packages are missing and offers to install them. It asks before running `sudo apt install`.

```bash
scripts/install.sh --check-deps
```

You can also install them directly:

```bash
sudo apt install python3-pyqt6 qt6-wayland tesseract-ocr tesseract-ocr-eng python3-pytest
```

When everything is in place, the script prints `All required packages are installed`. (`python3-pytest` is only needed to run the tests; the app itself doesn't use it.)

### 3. Install the app

```bash
scripts/install.sh
```

This needs no `sudo`. It installs for your user only:
- The app in `~/.local/share/text-capture`.
- The `text-capture` command in `~/.local/bin`.
- **Text Capture** in your app grid, with its icon.

Run the same command again to update after pulling new code. It stops a running Text Capture first, so start it again afterwards.

### 4. First start

Open **Text Capture** from the app grid, or run `text-capture --background`. No window opens: the app lives in the top bar. On first start it:
- Adds a **Text Capture** shortcut (`Ctrl+Q`) to GNOME's custom keyboard shortcuts and shows "Text Capture is ready". Your existing shortcuts are never changed. If `Ctrl+Q` is already taken, you get "Capture shortcut not set" instead; see [Changing the capture shortcut](#changing-the-capture-shortcut).
- Turns on **Start at login**, so it is always ready.

## Usage

1. Press **`Ctrl+Q`**. The screen freezes and dims. Your apps keep running underneath.
2. **Drag** a rectangle around the text you want. Its size in pixels is shown while you drag.
3. Release the mouse button. "Recognizing…" appears for a moment. Then the text is copied to the clipboard, the screen returns to normal, and a short notification shows the start of the text.
4. **Paste** with `Ctrl+V` wherever you need it. The keyboard is back in the app you were using.

Press `Esc` or right-click to cancel, even while "Recognizing…" is shown. If nothing is selected within 60 seconds, the capture cancels itself. A plain click or a tiny drag is ignored, so you can just drag again.

**First capture in a Wayland session:** Ubuntu must allow Text Capture to take screenshots. A small Text Capture window explains this. Click **Continue**, then **Allow** in Ubuntu's dialog. Ubuntu remembers the answer, and the capture starts right away.

### Command line

```text
text-capture [--capture | --quit | --background | --uninstall] [--version]

  --capture     start a capture (starts the app if it is not running)
  --quit        stop the running app
  --background  start in the background without capturing (used at login)
  --uninstall   stop the app and remove its shortcut and autostart entry
  --version     show the version
```

`text-capture --capture` starts a capture exactly as the hotkey does, so you can call it from scripts or bind it to another key.

### Tray menu

Click the Text Capture icon in the top bar:

| Item | What it does |
|---|---|
| **Capture** | Starts a capture, same as the hotkey |
| **OCR Language** | Chooses the recognition language from the ones installed |
| **Keep line breaks** | On: each line stays on its own line. Off: each paragraph becomes one line |
| **Show notifications** | Shows or hides the notification after each capture (errors are always shown) |
| **Start at login** | Starts Text Capture automatically when you log in |
| **Quit** | Stops the app |

## Changing the capture shortcut

1. Open **Settings › Keyboard › View and Customize Shortcuts › Custom Shortcuts**.
2. Click **Text Capture** and set a new key combination, or remove it to disable the shortcut.

If `Ctrl+Q` is already used by another shortcut when Text Capture first starts (for example by another OCR tool), Text Capture leaves its own shortcut unbound and shows a notification. Your other shortcut keeps working. Set a free combination using the steps above, or free `Ctrl+Q` first if you want Text Capture to have it.

**Note:** many apps (Firefox, VS Code, LibreOffice, Text Editor) use `Ctrl+Q` to quit. While `Ctrl+Q` is the capture shortcut, GNOME catches it before those apps do, so quit them from their menu or with `Alt+F4` instead.

Capture2Text uses `Win+Q`. On Ubuntu that key (`Super+Q`) already belongs to Ubuntu Dock, so it isn't the default here.

## OCR languages

English is installed by default. To add a language, install its Tesseract pack, then restart Text Capture (choose **Quit** in the tray menu and open it again from the app grid):

```bash
# Examples: German, French, Spanish, Japanese, Simplified Chinese
sudo apt install tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa tesseract-ocr-jpn tesseract-ocr-chi-sim
```

To see every available language pack:

```bash
apt-cache search tesseract-ocr-
```

Then choose the language under **OCR Language** in the tray menu.

## Uninstall

```bash
scripts/install.sh --uninstall
```

This stops the app and removes:
- Its keyboard shortcut and its autostart entry (your other shortcuts and autostart apps are untouched).
- Its files in `~/.local`: the app, the `text-capture` command, the app-grid entry and the icons.

Your settings in `~/.config/text-capture/` and the log in `~/.local/state/text-capture/` are kept. Delete those folders to remove them too.

To remove only the shortcut and the autostart entry but keep the app installed, run `text-capture --uninstall`.

The apt packages are left installed. To remove them:

```bash
sudo apt remove python3-pyqt6 qt6-wayland tesseract-ocr tesseract-ocr-eng python3-pytest
```

## Troubleshooting

**No tray icon in the top bar.**
Ubuntu shows tray icons through the *Ubuntu AppIndicators* extension. Check that it is on:

```bash
gnome-extensions enable ubuntu-appindicators@ubuntu.com
```

Without a tray icon the hotkey still works, and `text-capture --quit` stops the app.

**On Wayland, a Text Capture window asks to allow screen capture.**
This happens once. Click **Continue**, then **Allow** in Ubuntu's dialog. If you chose **Deny**, captures don't work and a notification tells you so. To change your answer, trigger a capture again: the window comes back. Click **Continue**, and Ubuntu asks again.

If the window says Ubuntu did not show its dialog, install Text Capture with `scripts/install.sh` (Ubuntu only shows the dialog for installed apps) and try again.

**The shortcut does nothing.**
Open **Settings › Keyboard › View and Customize Shortcuts › Custom Shortcuts** and check that **Text Capture** has a key. To check that the app itself works, run `text-capture --capture` in a terminal.

**"OCR engine not installed" notification.**
Install Tesseract and its English data:

```bash
sudo apt install tesseract-ocr tesseract-ocr-eng
```

**Something else went wrong.**
Text Capture writes a log to `~/.local/state/text-capture/text-capture.log`.

**Find out which session you are running** (Xorg or Wayland):

```bash
echo $XDG_SESSION_TYPE
```

## Development

Run the tests from the source folder:

```bash
python3 -m pytest
```

`python3 -m text_capture` runs the app straight from the source folder. Use `scripts/install.sh` for everyday use, so the shortcut and autostart entry point at the installed copy.

`tests/data/ocr/generate.py` rebuilds the OCR reference images. `python3 -m text_capture.grab --save desktop.png` grabs the desktop once, to debug screen capture.

This project is planned with [OpenSpec](https://github.com/Fission-AI/OpenSpec). What the app must do is specified in [openspec/changes/add-text-capture-core/specs/](openspec/changes/add-text-capture-core/specs/), and how it is built is in [design.md](openspec/changes/add-text-capture-core/design.md).
