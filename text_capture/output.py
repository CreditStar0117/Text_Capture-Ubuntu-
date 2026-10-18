"""Clipboard delivery and desktop notifications (design D7, D8).

Notifications go through `gdbus call` in a QProcess: PyQt6's QtDBus cannot marshal the
uint32 and string-array arguments that org.freedesktop.Notifications.Notify requires.
"""

import html
import logging
import re
import shutil
import subprocess

from PyQt6.QtCore import QObject, QProcess
from PyQt6.QtGui import QClipboard, QGuiApplication

from . import APP_DESKTOP_ID, APP_NAME

log = logging.getLogger(__name__)

PREVIEW_CHARS = 100
URGENCY_LOW = 0
URGENCY_NORMAL = 1


# --- clipboard ------------------------------------------------------------------------


def wl_copy(text: str) -> bool:
    try:
        proc = subprocess.run(["wl-copy", "--type", "text/plain;charset=utf-8"], input=text.encode(), timeout=3)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def clipboard_fallback(session: str):
    """The fallback copier for this session, if one is available."""
    return wl_copy if session == "wayland" and shutil.which("wl-copy") else None


def copy_text(text: str, clipboard: QClipboard | None = None, fallback=None) -> bool:
    """Put `text` on the regular clipboard. Call while the overlay still has focus (D7)."""
    clipboard = clipboard or QGuiApplication.clipboard()
    clipboard.setText(text, QClipboard.Mode.Clipboard)
    if clipboard.ownsClipboard():
        return True
    if fallback is not None and fallback(text):
        return True
    log.warning("Could not take ownership of the clipboard")
    return False


# --- notifications ----------------------------------------------------------------------


def preview(text: str, limit: int = PREVIEW_CHARS) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit].rstrip() + "…"


def gvariant_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\t", "\\t")
    return f"'{escaped}'"


def notify_args(summary: str, body: str, urgency: int, replaces_id: int = 0) -> list[str]:
    """`gdbus` arguments for one Notify call; the body is escaped because GNOME reads markup."""
    hints = f"{{'transient': <true>, 'urgency': <byte {urgency}>, 'desktop-entry': <{gvariant_string(APP_DESKTOP_ID)}>}}"
    return [
        "call", "--session",
        "--dest", "org.freedesktop.Notifications",
        "--object-path", "/org/freedesktop/Notifications",
        "--method", "org.freedesktop.Notifications.Notify",
        gvariant_string(APP_NAME),
        f"uint32 {replaces_id}",
        gvariant_string(APP_DESKTOP_ID),
        gvariant_string(summary),
        gvariant_string(html.escape(body, quote=False)),
        "@as []",
        hints,
        "int32 4000",
    ]


class Notifier(QObject):
    """Non-blocking desktop notifications; each one replaces the previous one."""

    def __init__(self, notify_results=lambda: True, send=None, parent=None):
        super().__init__(parent)
        self._notify_results = notify_results
        self._send = send or self._send_gdbus
        self.last_id = 0

    def copied(self, text: str):
        if self._notify_results():
            self._send(notify_args("Text copied", preview(text), URGENCY_LOW, self.last_id))

    def message(self, summary: str, body: str = ""):
        """Errors and "no text found": shown whatever the notification setting is."""
        self._send(notify_args(summary, body, URGENCY_NORMAL, self.last_id))

    def _send_gdbus(self, args: list[str]):
        process = QProcess(self)
        process.finished.connect(lambda *_: self._on_sent(process))
        process.errorOccurred.connect(lambda error: log.warning("gdbus failed to start: %s", error))
        process.start("gdbus", args)

    def _on_sent(self, process: QProcess):
        out = bytes(process.readAllStandardOutput()).decode(errors="replace")
        if match := re.search(r"uint32 (\d+)", out):
            self.last_id = int(match.group(1))
        else:
            log.warning("Notification failed: %s", bytes(process.readAllStandardError()).decode(errors="replace").strip())
        process.deleteLater()


# --- delivering a result ----------------------------------------------------------------

COPIED = "copied"
EMPTY = "empty"
FAILED = "failed"


def deliver(text: str, notifier: Notifier, copy=copy_text) -> str:
    """Copy recognized text and tell the user; an empty result never touches the clipboard."""
    if not text.strip():
        notifier.message("No text found", "Nothing was recognized in the selected area. Your clipboard was not changed.")
        return EMPTY
    if not copy(text):
        notifier.message("Could not copy the text", "The recognized text could not be placed on the clipboard.")
        return FAILED
    notifier.copied(text)
    return COPIED
