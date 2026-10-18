"""QApplication, tray icon and menu, and the capture controller."""

import functools
import logging
import logging.handlers
import os
import shutil
import subprocess
import sys
import time

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QActionGroup, QFont
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMenu, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget

from . import APP_DESKTOP_ID, APP_ID, APP_NAME, gnome_hotkey, grab, icons, ipc, ocr, output, settings
from .overlay import OverlaySession
from .settings import Settings

log = logging.getLogger("text_capture")

TRAY_CAPTURE_DELAY_MS = 250  # let the tray menu close so it is not in the frozen image
PERMISSION_CAPTURE_DELAY_MS = 300  # let the permission window close before grabbing
PERMISSION_TIMEOUT_MS = 120_000  # the user is reading Ubuntu's Allow/Deny dialog


def guarded(method):
    """Run a capture step; any exception closes every overlay and is reported (tray-service spec)."""

    @functools.wraps(method)
    def wrapper(self, *args):
        try:
            return method(self, *args)
        except Exception:
            log.exception("Capture step %s failed", method.__name__)
            self.abort()

    return wrapper


def pretty_accel(accel: str) -> str:
    """`<Control>q` -> `Ctrl+Q`."""
    names = {"control": "Ctrl", "primary": "Ctrl", "ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "super": "Super"}
    parts, rest = [], accel
    while rest.startswith("<") and ">" in rest:
        name, rest = rest[1:].split(">", 1)
        parts.append(names.get(name.lower(), name))
    return "+".join(parts + [rest.upper() if len(rest) == 1 else rest])


# --- screenshot permission (Wayland, design D4) -----------------------------------------


class PermissionWindow(QWidget):
    def __init__(self, denied_before: bool):
        super().__init__(None, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        title = QLabel("Allow screen capture")
        font = QFont(title.font())
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.2)
        title.setFont(font)
        intro = "Text Capture was not allowed to take screenshots last time.\n\n" if denied_before else ""
        body = QLabel(
            intro + "To read text from your screen, Ubuntu must allow Text Capture to take screenshots. "
            "Click Continue, then choose Allow in Ubuntu's dialog. Ubuntu remembers your choice."
        )
        body.setWordWrap(True)
        self.status = QLabel("Waiting for your answer in Ubuntu's dialog…")
        self.status.hide()
        self.cancel_button = QPushButton("Cancel")
        self.continue_button = QPushButton("Continue")
        self.continue_button.setDefault(True)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.continue_button)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        self.setFixedWidth(420)
        self.closed_by_user = None  # set by the flow

    def set_waiting(self):
        self.status.show()
        self.continue_button.setEnabled(False)

    def closeEvent(self, event):
        if self.closed_by_user:
            self.closed_by_user()
        super().closeEvent(event)


class PermissionFlow(QObject):
    """Shows the permission window; its Continue click lets GNOME show its Allow/Deny dialog."""

    granted = pyqtSignal()
    denied = pyqtSignal()
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, denied_before: bool, parent=None, portal_factory=grab.PortalScreenshot,
                 lookup=grab.screenshot_permission, forget=grab.forget_screenshot_permission):
        super().__init__(parent)
        self.denied_before = denied_before
        self._portal_factory, self._lookup, self._forget = portal_factory, lookup, forget
        self.window = None
        self._done = False

    def start(self):
        self.window = PermissionWindow(self.denied_before)
        self.window.continue_button.clicked.connect(self._continue)
        self.window.cancel_button.clicked.connect(self._cancel)
        self.window.closed_by_user = self._cancel
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _continue(self):
        if self.denied_before:
            self._forget()  # the user explicitly asked to choose again
        self.window.set_waiting()
        # The window must keep focus during this request: GNOME only shows its
        # dialog for the focused app. The image it returns shows our window: discard it.
        self._request = self._portal_factory(timeout_ms=PERMISSION_TIMEOUT_MS, parent=self)
        self._request.done.connect(self._on_done)
        self._request.start()

    def _on_done(self, response: int, image):
        if response == grab.RESPONSE_OK:
            self._finish(self.granted)
        elif self._lookup() == "no":
            self._finish(self.denied)
        else:
            self._finish(self.failed, "Ubuntu did not show its permission dialog. "
                         "Install Text Capture with scripts/install.sh, then try again.")

    def _cancel(self):
        self._finish(self.cancelled)

    def _finish(self, signal, *args):
        if self._done:
            return
        self._done = True
        self.close()
        signal.emit(*args)

    def close(self):
        if self.window is not None:
            window, self.window = self.window, None
            window.closed_by_user = None
            window.close()
            window.deleteLater()


# --- capture controller -------------------------------------------------------------


class CaptureController(QObject):
    """grab -> overlay -> OCR -> clipboard -> close, one capture at a time (design D5-D7)."""

    IDLE, GRABBING, PERMISSION, SELECTING, RECOGNIZING = "idle", "grabbing", "permission", "selecting", "recognizing"
    state_changed = pyqtSignal(str)

    def __init__(self, store: Settings, notifier, grabber=None, *, overlay_factory=OverlaySession, ocr_factory=ocr.OcrJob,
                 languages=ocr.available_languages, engine_installed=ocr.engine_installed, copy=None,
                 permission_factory=PermissionFlow, parent=None):
        super().__init__(parent)
        self.store = store
        self.notifier = notifier
        self.grabber = grabber or grab.create_grabber(parent=self)
        self.grabber.grabbed.connect(self._on_grabbed)
        self.grabber.failed.connect(self._on_grab_failed)
        self.overlay_factory = overlay_factory
        self.ocr_factory = ocr_factory
        self.languages = languages
        self.engine_installed = engine_installed
        self.copy = copy or functools.partial(output.copy_text, fallback=output.clipboard_fallback(grab.session_type()))
        self.permission_factory = permission_factory
        self.state = self.IDLE
        self.session = None
        self.job = None
        self.permission = None
        self._language_warned = False

    @property
    def busy(self) -> bool:
        return self.state != self.IDLE

    def _set(self, state: str):
        self.state = state
        self.state_changed.emit(state)

    def trigger(self, delay_ms: int = 0):
        if self.busy:
            log.info("Capture already in progress (%s); trigger ignored", self.state)
            return
        self._set(self.GRABBING)
        QTimer.singleShot(delay_ms, self._start)

    @guarded
    def _start(self):
        if self.state != self.GRABBING:
            return
        if not self.engine_installed():
            self.finish()
            self.notifier.message("OCR engine not installed",
                                  f"Install it with: sudo apt install {ocr.ENGINE_PACKAGE} tesseract-ocr-eng")
            return
        self.grabber.grab()

    @guarded
    def _on_grabbed(self, shots):
        if self.state != self.GRABBING:
            return
        self.session = self.overlay_factory(shots)
        self.session.selected.connect(self._on_selected)
        self.session.cancelled.connect(self.finish)
        self._set(self.SELECTING)
        self.session.show()

    @guarded
    def _on_grab_failed(self, kind: str, message: str):
        if self.state != self.GRABBING:
            return
        if kind in (grab.PERMISSION_NEEDED, grab.PERMISSION_DENIED):
            self._set(self.PERMISSION)
            self.permission = self.permission_factory(denied_before=kind == grab.PERMISSION_DENIED, parent=self)
            self.permission.granted.connect(self._on_permission_granted)
            self.permission.denied.connect(self._on_permission_denied)
            self.permission.cancelled.connect(self.finish)
            self.permission.failed.connect(lambda msg: self._fail("Screen capture not available", msg))
            self.permission.start()
            return
        self._fail("Capture failed", message or "The screen could not be captured.")

    def _on_permission_granted(self):
        self.finish()
        self.trigger(PERMISSION_CAPTURE_DELAY_MS)

    def _on_permission_denied(self):
        self._fail("Screen capture not allowed",
                   "Text Capture needs permission to take screenshots. Trigger a capture again to be asked again.")

    @guarded
    def _on_selected(self, index: int, rect):
        if self.state != self.SELECTING:
            return
        window = self.session.windows[index]
        image = self.session.crop(index, rect)
        scale = window.shot.image.width() / max(window.width(), 1)
        selected = self.store.get(settings.LANGUAGE)
        language, fell_back = ocr.resolve_language(selected, self.languages())
        if fell_back and not self._language_warned:
            self._language_warned = True
            self.notifier.message("OCR language not available",
                                  f"{ocr.display_name(selected)} is not installed, so English is used.")
        self.session.set_busy()
        self._set(self.RECOGNIZING)
        self.job = self.ocr_factory(ocr.to_png(ocr.preprocess(image, scale)), language, parent=self)
        self.job.finished.connect(self._on_recognized)
        self.job.failed.connect(self._on_ocr_failed)
        self.job.start()

    @guarded
    def _on_recognized(self, raw: str):
        if self.state != self.RECOGNIZING:
            return
        text = ocr.normalize(raw, self.store.get(settings.KEEP_LINE_BREAKS))
        output.deliver(text, self.notifier, self.copy)  # while the overlay still has focus (D7)
        self.finish()

    @guarded
    def _on_ocr_failed(self, kind: str, message: str):
        if self.state != self.RECOGNIZING:
            return
        titles = {
            ocr.MISSING_ENGINE: "OCR engine not installed",
            ocr.MISSING_LANGUAGE: "OCR language not installed",
            ocr.TIMEOUT: "Recognition timed out",
        }
        self._fail(titles.get(kind, "Recognition failed"), message)

    def _fail(self, summary: str, body: str):
        self.finish()
        self.notifier.message(summary, body)

    def finish(self):
        """Close everything this capture opened and return to idle. Safe to call twice."""
        job, self.job = self.job, None
        session, self.session = self.session, None
        permission, self.permission = self.permission, None
        try:
            if job is not None:
                job.cancel()
                job.deleteLater()
        finally:
            try:
                if session is not None:
                    session.close()
                    session.deleteLater()
            finally:
                if permission is not None:
                    permission.close()
                    permission.deleteLater()
                self._set(self.IDLE)

    def abort(self):
        try:
            self.finish()
        finally:
            self.notifier.message("Capture failed", "Something went wrong. Details are in the log file.")


# --- tray ---------------------------------------------------------------------------------


class Tray(QObject):
    def __init__(self, store: Settings, controller, quit_app, languages=ocr.available_languages, parent=None):
        super().__init__(parent)
        self.store = store
        self.controller = controller
        self.languages = languages
        self.menu = QMenu()
        self.capture_action = self.menu.addAction("Capture")
        self.capture_action.triggered.connect(lambda: controller.trigger(TRAY_CAPTURE_DELAY_MS))
        self.language_menu = self.menu.addMenu("OCR Language")
        self.language_group = QActionGroup(self)
        self.language_group.setExclusive(True)
        self.menu.addSeparator()
        self.keep_action = self._toggle("Keep line breaks", settings.KEEP_LINE_BREAKS)
        self.notify_action = self._toggle("Show notifications", settings.NOTIFY)
        self.autostart_action = self._toggle("Start at login", settings.AUTOSTART, settings.set_autostart)
        self.menu.addSeparator()
        self.quit_action = self.menu.addAction("Quit")
        self.quit_action.triggered.connect(quit_app)
        self.menu.aboutToShow.connect(self.refresh_languages)
        self.refresh_languages()
        self.icon = QSystemTrayIcon(icons.tray_icon(), self)
        self.icon.setToolTip(APP_NAME)
        self.icon.setContextMenu(self.menu)

    def show(self) -> bool:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        self.icon.show()
        return True

    def _toggle(self, text: str, key: str, on_change=None):
        action = self.menu.addAction(text)
        action.setCheckable(True)
        action.setChecked(self.store.get(key))

        def changed(checked):
            self.store.set(key, checked)
            if on_change is not None:
                on_change(checked)

        action.toggled.connect(changed)
        return action

    def refresh_languages(self):
        current = self.store.get(settings.LANGUAGE)
        for action in self.language_group.actions():
            self.language_group.removeAction(action)
        self.language_menu.clear()
        codes = self.languages()
        if not codes:
            self.language_menu.addAction("No OCR languages installed").setEnabled(False)
            return
        for code in codes:
            action = self.language_menu.addAction(ocr.display_name(code))
            action.setCheckable(True)
            action.setData(code)
            action.setChecked(code == current or (current not in codes and code == ocr.DEFAULT_LANGUAGE))
            action.triggered.connect(lambda checked, code=code: self.store.set(settings.LANGUAGE, code))
            self.language_group.addAction(action)


# --- start-up, first run, uninstall -----------------------------------------------------


def setup_logging() -> None:
    directory = settings.state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(directory / f"{APP_ID}.log", maxBytes=1_000_000, backupCount=1)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def gnome_available(env=None) -> bool:
    env = os.environ if env is None else env
    return "GNOME" in env.get("XDG_CURRENT_DESKTOP", "").upper() and shutil.which("gsettings") is not None


def setup_hotkey(store: Settings, notifier, run=gnome_hotkey.run_gsettings, command=None) -> None:
    """First run: add our shortcut. Later runs: keep its command current, never re-create it."""
    command = command or settings.shortcut_command()
    try:
        if store.get(settings.HOTKEY_REGISTERED):
            if gnome_hotkey.OUR_PATH in gnome_hotkey.custom_paths(run):
                gnome_hotkey.register(command, run)  # updates the command only
            return
        result = gnome_hotkey.register(command, run)
    except (gnome_hotkey.GSettingsError, OSError, subprocess.SubprocessError) as exc:
        log.warning("Could not register the capture shortcut: %s", exc)
        return
    store.set(settings.HOTKEY_REGISTERED, True)
    key = pretty_accel(gnome_hotkey.DEFAULT_BINDING)
    if result.conflict:
        notifier.message("Capture shortcut not set",
                         f"{key} is already used by another shortcut. Choose a key for “{APP_NAME}” "
                         "in Settings › Keyboard › Keyboard Shortcuts › Custom Shortcuts.")
    else:
        notifier.message(f"{APP_NAME} is ready", f"Press {pretty_accel(result.binding)} to capture text from the screen.")


def first_run_setup(store: Settings, notifier, run=gnome_hotkey.run_gsettings, env=None) -> None:
    if gnome_available(env):
        setup_hotkey(store, notifier, run)
    else:
        log.info("Not a GNOME session: no shortcut registered; bind `text-capture --capture` by hand")
    if store.get(settings.AUTOSTART):
        settings.set_autostart(True)  # also refreshes the launcher path


def install_excepthook(controller: CaptureController) -> None:
    def hook(exc_type, exc, tb):
        log.error("Unhandled exception", exc_info=(exc_type, exc, tb))
        if controller.busy:
            controller.abort()

    sys.excepthook = hook


def run(lock_fd: int, capture: bool = False) -> int:
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(APP_DESKTOP_ID)
    app.setWindowIcon(icons.app_icon())
    app.setQuitOnLastWindowClosed(False)
    setup_logging()

    store = Settings()
    notifier = output.Notifier(notify_results=lambda: store.get(settings.NOTIFY))
    controller = CaptureController(store, notifier)
    install_excepthook(controller)
    app.aboutToQuit.connect(controller.finish)
    first_run_setup(store, notifier)

    tray = Tray(store, controller, app.quit)
    if not tray.show() and not store.get(settings.NO_TRAY_NOTICE_SHOWN):
        store.set(settings.NO_TRAY_NOTICE_SHOWN, True)
        notifier.message("Tray icon not available",
                         f"{APP_NAME} is running. Use the capture shortcut to capture text; "
                         "run `text-capture --quit` to stop it.")

    def on_command(command: str):
        if command == "capture":
            controller.trigger()
        elif command == "quit":
            app.quit()

    server = ipc.start_server(on_command)
    if capture:
        QTimer.singleShot(0, controller.trigger)
    log.info("%s started (session %s, pid %d)", APP_NAME, grab.session_type(), os.getpid())
    code = app.exec()
    server.close()
    ipc.socket_path().unlink(missing_ok=True)
    os.close(lock_fd)
    log.info("%s stopped", APP_NAME)
    return code


def uninstall(run_gsettings=gnome_hotkey.run_gsettings, wait: float = 5.0) -> int:
    """Stop the app and remove the shortcut and autostart entry it created."""
    if ipc.send("quit") is not None:
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:  # the lock is free once the instance has exited
            if (fd := ipc.acquire_lock()) is not None:
                os.close(fd)
                break
            time.sleep(0.1)
        print(f"Stopped {APP_NAME}.")
    try:
        if gnome_hotkey.unregister(run_gsettings):
            print("Removed the capture shortcut.")
    except (gnome_hotkey.GSettingsError, OSError, subprocess.SubprocessError) as exc:
        print(f"Could not remove the capture shortcut: {exc}", file=sys.stderr)
    if settings.autostart_path().exists():
        settings.set_autostart(False)
        print("Removed the autostart entry.")
    Settings().set(settings.HOTKEY_REGISTERED, False)
    return 0
