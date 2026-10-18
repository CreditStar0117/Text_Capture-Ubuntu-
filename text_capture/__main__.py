"""Command-line entry point.

The client path (forwarding a request to a running instance) must stay
stdlib-only so that `text-capture --capture` starts fast (design D3).
"""

import argparse
import sys
import time

from . import APP_NAME, __version__, ipc, scope


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


def send_when_ready(command: str, wait: float = 5.0) -> int:
    """Another launch holds the lock but is not listening yet: retry until it is."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        time.sleep(0.1)
        if (reply := ipc.send(command)) is not None:
            return report(reply)
    print("text-capture: another instance is starting but does not answer", file=sys.stderr)
    return 1


def report(reply: str) -> int:
    if reply == "ok":
        return 0
    print(f"text-capture: {reply}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.uninstall:
        from .app import uninstall  # imports Qt; start-up speed does not matter here

        return uninstall()

    command = "capture" if args.capture else "quit" if args.quit else "start"
    if (reply := ipc.send(command)) is not None:
        return report(reply)

    lock = ipc.acquire_lock()
    if lock is None:
        return send_when_ready(command)
    if command == "quit":
        print(f"{APP_NAME} is not running.")
        return 0

    scope.ensure_own_scope(sys.argv[1:] if argv is None else argv)  # may re-execute this process

    from .app import run  # only the instance that becomes the server loads Qt

    return run(lock, capture=command == "capture")


if __name__ == "__main__":
    sys.exit(main())
