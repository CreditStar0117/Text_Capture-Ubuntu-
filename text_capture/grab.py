"""Screen grabbing: X11 grabber and xdg-desktop-portal grabber (design D4).

Both grabbers emit `grabbed(list[ScreenShot])` with one image per monitor in that
monitor's physical pixels, or `failed(kind, message)`. The whole desktop is grabbed
before any overlay exists, so the overlay never appears in its own image.
"""

import argparse
import itertools
import logging
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import QObject, QRect, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher
from PyQt6.QtGui import QGuiApplication, QImage, QPainter, QScreen

from . import APP_DESKTOP_ID

log = logging.getLogger(__name__)

# Failure kinds reported through `failed(kind, message)`.
ERROR = "error"
PERMISSION_NEEDED = "permission-needed"  # nothing stored yet: ask through the permission window
PERMISSION_DENIED = "permission-denied"  # the user chose Deny earlier


def session_type(env=None) -> str:
    """"wayland" or "x11", from the session itself rather than the Qt platform in use."""
    env = os.environ if env is None else env
    kind = env.get("XDG_SESSION_TYPE", "").lower()
    if kind in ("x11", "wayland"):
        return kind
    return "wayland" if env.get("WAYLAND_DISPLAY") else "x11"


def create_grabber(env=None, parent=None):
    return PortalGrabber(parent) if session_type(env) == "wayland" else X11Grabber(parent)


# --- geometry (pure; unit-tested) --------------------------------------------


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float


def _fits(rects: list[Rect], width: int, height: int, slack: float = 2) -> bool:
    right = max(r.x + r.w for r in rects)
    bottom = max(r.y + r.h for r in rects)
    return abs(right - width) <= slack and abs(bottom - height) <= slack


def screen_source_rects(screens: list[tuple[Rect, float]], image_w: int, image_h: int) -> list[Rect]:
    """Where each screen (logical geometry, device pixel ratio) sits in one full-desktop image.

    First try "physical layout": screens keep their top-left in device pixels and only
    their size is scaled (GNOME's default integer scaling). If that does not add up to
    the image size, fall back to one uniform scale over the logical layout (GNOME's
    logical layout mode, used with fractional or mixed scaling).
    """
    min_x = min(r.x for r, _ in screens)
    min_y = min(r.y for r, _ in screens)
    physical = [Rect(r.x - min_x, r.y - min_y, r.w * dpr, r.h * dpr) for r, dpr in screens]
    if _fits(physical, image_w, image_h):
        return physical
    layout_w = max(r.x + r.w for r, _ in screens) - min_x
    layout_h = max(r.y + r.h for r, _ in screens) - min_y
    kx, ky = image_w / layout_w, image_h / layout_h
    return [Rect((r.x - min_x) * kx, (r.y - min_y) * ky, r.w * kx, r.h * ky) for r, _ in screens]


def selection_to_crop(sel: Rect, logical_w: float, logical_h: float, image_w: int, image_h: int) -> Rect:
    """Map a selection in a screen's logical pixels to whole pixels of that screen's image."""
    sx, sy = image_w / logical_w, image_h / logical_h
    x0 = max(0, math.floor(sel.x * sx + 1e-6))
    y0 = max(0, math.floor(sel.y * sy + 1e-6))
    x1 = min(image_w, math.ceil((sel.x + sel.w) * sx - 1e-6))
    y1 = min(image_h, math.ceil((sel.y + sel.h) * sy - 1e-6))
    return Rect(x0, y0, max(0, x1 - x0), max(0, y1 - y0))


# --- grabbers -------------------------------------------------------------------


@dataclass
class ScreenShot:
    screen: QScreen
    image: QImage  # the screen's contents in physical pixels


def _logical(screen: QScreen) -> tuple[Rect, float]:
    g = screen.geometry()
    return Rect(g.x(), g.y(), g.width(), g.height()), screen.devicePixelRatio()


def split_desktop(image: QImage, screens: list[QScreen]) -> list[ScreenShot]:
    rects = screen_source_rects([_logical(s) for s in screens], image.width(), image.height())
    return [
        ScreenShot(screen, image.copy(QRect(round(r.x), round(r.y), round(r.w), round(r.h))))
        for screen, r in zip(screens, rects)
    ]


class X11Grabber(QObject):
    grabbed = pyqtSignal(list)
    failed = pyqtSignal(str, str)

    def grab(self):
        shots = []
        for screen in QGuiApplication.screens():
            pixmap = screen.grabWindow(0)
            if pixmap.isNull():
                self.failed.emit(ERROR, "Could not read the screen.")
                return
            shots.append(ScreenShot(screen, pixmap.toImage()))
        self.grabbed.emit(shots)


PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
PERMISSION_STORE = "org.freedesktop.impl.portal.PermissionStore"
PERMISSION_STORE_PATH = "/org/freedesktop/impl/portal/PermissionStore"
RESPONSE_OK = 0
_tokens = itertools.count(1)


class PortalScreenshot(QObject):
    """One non-interactive org.freedesktop.portal.Screenshot request.

    Emits `done(response, image)`; the image is null unless response is 0. The PNG the
    portal wrote is read into memory and deleted (some GNOME versions put it in
    ~/Pictures/Screenshots), but only that exact file, and only if it is newer than
    the request.
    """

    done = pyqtSignal(int, QImage)

    def __init__(self, timeout_ms: int = 15000, parent=None):
        super().__init__(parent)
        self._bus = QDBusConnection.sessionBus()
        self._timer = QTimer(self, singleShot=True, interval=timeout_ms)
        self._timer.timeout.connect(lambda: self._finish(-1, QImage()))
        self._handle = None
        self._started = 0.0
        self._finished = False

    def start(self, parent_window: str = ""):
        token = f"textcapture{os.getpid()}_{next(_tokens)}"
        sender = self._bus.baseService().lstrip(":").replace(".", "_")
        self._subscribe(f"{PORTAL_PATH}/request/{sender}/{token}")
        msg = QDBusMessage.createMethodCall(PORTAL_SERVICE, PORTAL_PATH, "org.freedesktop.portal.Screenshot", "Screenshot")
        msg.setArguments([parent_window, {"handle_token": token, "interactive": False}])
        self._started = time.time()
        self._watcher = QDBusPendingCallWatcher(self._bus.asyncCall(msg), self)
        self._watcher.finished.connect(self._on_call_finished)
        self._timer.start()

    def _subscribe(self, handle: str):
        self._handle = handle
        self._bus.connect(PORTAL_SERVICE, handle, "org.freedesktop.portal.Request", "Response", self._on_response)

    def _on_call_finished(self, watcher):
        reply = watcher.reply()
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            log.warning("Screenshot portal call failed: %s", reply.errorMessage())
            self._finish(-1, QImage())
            return
        handle = reply.arguments()[0]
        if handle != self._handle:  # portals older than 0.9 pick their own handle
            self._subscribe(handle)

    @pyqtSlot(QDBusMessage)
    def _on_response(self, message):
        response, results = message.arguments()
        if response != RESPONSE_OK:
            self._finish(response, QImage())
            return
        path = Path(unquote(urlparse(results.get("uri", "")).path))
        image = QImage(str(path))
        self._delete_portal_file(path)
        self._finish(RESPONSE_OK if not image.isNull() else -1, image)

    def _delete_portal_file(self, path: Path):
        try:
            if path.is_file() and path.stat().st_mtime >= self._started - 2:
                path.unlink()
        except OSError as exc:
            log.warning("Could not delete portal screenshot %s: %s", path, exc)

    def _finish(self, response: int, image: QImage):
        if self._finished:
            return
        self._finished = True
        self._timer.stop()
        self._bus.disconnect(PORTAL_SERVICE, self._handle, "org.freedesktop.portal.Request", "Response", self._on_response)
        self.done.emit(response, image)


def screenshot_permission(app_id: str = APP_DESKTOP_ID) -> str | None:
    """The stored portal screenshot permission for `app_id`: "yes", "no" or None."""
    msg = QDBusMessage.createMethodCall(PERMISSION_STORE, PERMISSION_STORE_PATH, PERMISSION_STORE, "Lookup")
    msg.setArguments(["screenshot", "screenshot"])
    reply = QDBusConnection.sessionBus().call(msg)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        return None  # NotFound: nothing stored for anyone yet
    permissions = reply.arguments()[0] or {}
    values = permissions.get(app_id) or []
    return values[0] if values else None


def forget_screenshot_permission(app_id: str = APP_DESKTOP_ID) -> None:
    """Delete a stored answer so the portal asks again (only on the user's explicit request)."""
    msg = QDBusMessage.createMethodCall(PERMISSION_STORE, PERMISSION_STORE_PATH, PERMISSION_STORE, "DeletePermission")
    msg.setArguments(["screenshot", "screenshot", app_id])
    QDBusConnection.sessionBus().call(msg)


def classify_failure(response: int, permission: str | None) -> str:
    """Failure kind for a non-OK portal response, given the stored permission."""
    if response < 0 or permission == "yes":
        return ERROR
    return PERMISSION_DENIED if permission == "no" else PERMISSION_NEEDED


class PortalGrabber(QObject):
    grabbed = pyqtSignal(list)
    failed = pyqtSignal(str, str)

    def grab(self):
        self._request = PortalScreenshot(parent=self)
        self._request.done.connect(self._on_done)
        self._request.start()

    def _on_done(self, response: int, image: QImage):
        self._request.deleteLater()
        if response == RESPONSE_OK:
            self.grabbed.emit(split_desktop(image, QGuiApplication.screens()))
            return
        kind = classify_failure(response, screenshot_permission())
        log.info("Screenshot portal response %s -> %s", response, kind)
        self.failed.emit(kind, "Ubuntu did not provide a screenshot." if kind == ERROR else "")


# --- debug command: python3 -m text_capture.grab --save desktop.png -------------


def compose(shots: list[ScreenShot]) -> QImage:
    """All screens side by side as on the desktop, at the largest pixel ratio."""
    scale = max(s.image.width() / s.screen.geometry().width() for s in shots)
    union = QRect()
    for s in shots:
        union = union.united(s.screen.geometry())
    canvas = QImage(round(union.width() * scale), round(union.height() * scale), QImage.Format.Format_RGB32)
    canvas.fill(0)
    painter = QPainter(canvas)
    for s in shots:
        g = s.screen.geometry().translated(-union.topLeft())
        target = QRect(round(g.x() * scale), round(g.y() * scale), round(g.width() * scale), round(g.height() * scale))
        painter.drawImage(target, s.image)
    painter.end()
    return canvas


def main(argv=None) -> int:
    from PyQt6.QtWidgets import QApplication

    parser = argparse.ArgumentParser(prog="python3 -m text_capture.grab", description="Grab the desktop once (debugging).")
    parser.add_argument("--save", metavar="PNG", help="write the full desktop image here")
    parser.add_argument("--portal", action="store_true", help="use the screenshot portal even on X11")
    parser.add_argument("--repeat", type=int, default=1, help="grab this many times and print timings")
    args = parser.parse_args(argv)

    app = QApplication(sys.argv[:1])
    app.setDesktopFileName(APP_DESKTOP_ID)
    grabber = PortalGrabber() if args.portal else create_grabber()
    state = {"left": args.repeat, "t0": 0.0, "rc": 0}

    def once():
        state["t0"] = time.perf_counter()
        grabber.grab()

    def on_grabbed(shots):
        ms = (time.perf_counter() - state["t0"]) * 1000
        sizes = ", ".join(f"{s.screen.name()} {s.image.width()}x{s.image.height()}" for s in shots)
        print(f"{type(grabber).__name__}: {ms:.0f} ms ({sizes})", flush=True)
        state["left"] -= 1
        if state["left"] == 0:
            if args.save:
                compose(shots).save(args.save)
                print(f"saved {args.save}")
            app.quit()
        else:
            QTimer.singleShot(300, once)

    def on_failed(kind, message):
        print(f"failed: {kind} {message}", file=sys.stderr)
        state["rc"] = 1
        app.quit()

    grabber.grabbed.connect(on_grabbed)
    grabber.failed.connect(on_failed)
    QTimer.singleShot(0, once)
    app.exec()
    return state["rc"]


if __name__ == "__main__":
    sys.exit(main())
