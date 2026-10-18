"""Persistent user settings and the autostart entry (design D9)."""

import os
import re
import shlex
import sys
from pathlib import Path

from PyQt6.QtCore import QSettings

from . import APP_DESKTOP_ID, APP_ID, APP_NAME

LANGUAGE = "ocr/language"
KEEP_LINE_BREAKS = "output/keep_line_breaks"
NOTIFY = "output/notify"
AUTOSTART = "app/autostart"
HOTKEY_REGISTERED = "hotkey/registered"
NO_TRAY_NOTICE_SHOWN = "app/no_tray_notice_shown"

DEFAULTS = {
    LANGUAGE: "eng",
    KEEP_LINE_BREAKS: True,
    NOTIFY: True,
    AUTOSTART: True,
    HOTKEY_REGISTERED: False,
    NO_TRAY_NOTICE_SHOWN: False,
}


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def state_dir() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / APP_ID


class Settings:
    """Typed access to `~/.config/text-capture/text-capture.conf`; every change is written at once."""

    def __init__(self, path: Path | None = None):
        self.path = path or config_dir() / APP_ID / f"{APP_ID}.conf"
        self._store = QSettings(str(self.path), QSettings.Format.IniFormat)

    def get(self, key: str):
        default = DEFAULTS[key]
        return self._store.value(key, default, type=type(default))

    def set(self, key: str, value) -> None:
        self._store.setValue(key, value)
        self._store.sync()


# --- launcher command and autostart entry ----------------------------------------------

LAUNCHER_ENV = "TEXT_CAPTURE_LAUNCHER"  # set by the installed launcher script to its own path


def launcher_argv() -> list[str]:
    """How GNOME should start this app: the installed launcher, or this source tree."""
    if launcher := os.environ.get(LAUNCHER_ENV):
        return [launcher]
    package_parent = str(Path(__file__).resolve().parent.parent)
    return ["env", f"PYTHONPATH={package_parent}", sys.executable, "-m", "text_capture"]


def shortcut_command() -> str:
    """Command line for the GNOME custom shortcut (parsed with shell quoting rules)."""
    return shlex.join(launcher_argv() + ["--capture"])


_EXEC_RESERVED = set(" \t\n\"'\\><~|&;$*?#()`")


def desktop_exec(argv: list[str]) -> str:
    """Quote arguments for a .desktop Exec key (Desktop Entry spec, "The Exec key").

    Arguments with reserved characters are double-quoted with `"`, `` ` ``, `$` and `\\`
    backslash-escaped; `%` becomes `%%`; then the whole value gets the key-file level
    escaping, where every backslash is doubled.
    """
    def quote(arg: str) -> str:
        arg = arg.replace("%", "%%")
        if arg and not set(arg) & _EXEC_RESERVED:
            return arg
        return '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'

    return " ".join(quote(a) for a in argv).replace("\\", "\\\\")


def autostart_path() -> Path:
    return config_dir() / "autostart" / f"{APP_DESKTOP_ID}.desktop"


def autostart_entry() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Copy text from anywhere on the screen\n"
        f"Exec={desktop_exec(launcher_argv() + ['--background'])}\n"
        f"Icon={APP_DESKTOP_ID}\n"
        "Terminal=false\n"
        "NoDisplay=true\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def set_autostart(enabled: bool) -> None:
    path = autostart_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(autostart_entry())
    else:
        path.unlink(missing_ok=True)
