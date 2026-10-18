"""Command-line entry point.

The client path (forwarding a request to a running instance) must stay
stdlib-only so that `text-capture --capture` starts fast (design D3).
"""

import argparse
import sys

from . import APP_NAME, __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="text-capture",
        description=f"{APP_NAME}: select a screen region, recognize its text and copy it to the clipboard.",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--capture", action="store_true", help="start a capture (starts the app if it is not running)")
    actions.add_argument("--quit", action="store_true", help="stop the running app")
    actions.add_argument("--background", action="store_true", help="start in the background without capturing (used at login)")
    actions.add_argument("--uninstall", action="store_true", help="stop the app and remove its shortcut and autostart entry")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
