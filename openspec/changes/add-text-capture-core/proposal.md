# Proposal

## Why

Capture2Text is a popular Windows tool: press a hotkey, drag a box around any text on screen, and the recognized text is in the clipboard. Ubuntu has no equivalent that works the same way in both X11 and Wayland sessions. This repository exists to provide one. Today it holds only a README, so this change defines and builds the first usable version.

## What Changes

- Add a background app, **Text Capture**, that starts at login, shows a tray icon, and stays idle until the user triggers a capture.
- Add a global capture hotkey (default `Ctrl+Q`; Capture2Text's `Win+Q` equivalent, `Super+Q`, is already taken by Ubuntu Dock). It works in both X11 and Wayland sessions on GNOME 46, the desktop in Ubuntu 24.04.
- Add region capture. The hotkey opens a dimmed, see-through overlay over the live screen (nothing freezes), the user drags a rectangle (Esc cancels), and the pixels under it are captured when the button is released.
- Add OCR of the captured region using Tesseract, with a choice of language from the language packs installed on the system.
- Copy recognized text to the clipboard and show a short desktop notification. Never overwrite the clipboard when no text is found.
- Add a tray menu: Capture, OCR language, Keep line breaks, Show notifications, Start at login, Quit.
- Guarantee non-interference: the app never blocks or slows other apps, only takes focus while its own overlay is open, and hands focus back when the overlay closes.

Out of scope for this change: translation, text-to-speech, "capture line under cursor", re-capturing the last region, vertical (CJK) text orientation, selections that span monitors, and .deb/Snap/Flatpak packaging.

## Capabilities

### New Capabilities
- `capture-hotkey`: Registering, triggering and changing the system-wide shortcut that starts a capture, in both X11 and Wayland sessions.
- `region-capture`: A see-through selection overlay over the live screen, rectangle selection and cancellation, and turning the selection into an image across monitors and display scales.
- `text-recognition`: Turning a captured image into text: OCR engine, language selection, image preprocessing, and line-break handling.
- `capture-output`: What happens with recognized text: clipboard delivery, user feedback notifications, and empty-result handling.
- `tray-service`: The long-running background process: tray icon and menu, single instance, start at login, settings persistence, and non-interference with other apps.

### Modified Capabilities
- None (no existing specs).

## Impact

- **New code**: a Python 3.12 application (package `text_capture`, command `text-capture`) in a repo that currently has no source code.
- **System dependencies (apt, Ubuntu 24.04)**: `python3-pyqt6`, `qt6-wayland`, `tesseract-ocr`, `tesseract-ocr-eng`, plus any optional `tesseract-ocr-<lang>` packs. The existing `xdg-desktop-portal-gnome` (Screenshot portal) and the default-enabled Ubuntu AppIndicators extension (tray icon) are also used.
- **User environment changes**: adds one entry to GNOME custom keyboard shortcuts (existing entries are left untouched) and an autostart file at `~/.config/autostart/io.github.CreditStar0117.TextCapture.desktop`. Both can be removed with `text-capture --uninstall`.
- **Privacy**: screenshots and OCR stay on the machine. Nothing is sent over the network.
