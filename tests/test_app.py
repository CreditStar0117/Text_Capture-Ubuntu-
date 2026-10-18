import time

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QImage
from PyQt6.QtWidgets import QApplication

from text_capture import app, gnome_hotkey, grab, ocr, settings
from text_capture.grab import Rect, ScreenShot
from text_capture.overlay import OverlaySession
from text_capture.settings import Settings

from test_gnome_hotkey import FakeGSettings
from test_output import FakeNotifier


def pump(ms=50):
    deadline = time.monotonic() + ms / 1000
    while time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.002)


class FakeGrabber(QObject):
    grabbed = pyqtSignal(list)
    failed = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.calls = 0

    def grab(self):
        self.calls += 1


class FakeJob(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str, str)
    instances = []

    def __init__(self, png, language, parent=None):
        super().__init__(parent)
        self.png, self.language = png, language
        self.started = self.cancelled = False
        FakeJob.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


class TrackingSession(OverlaySession):
    instances = []

    def __init__(self, shots, **kwargs):
        super().__init__(shots, **kwargs)
        TrackingSession.instances.append(self)


class FakePermission(QObject):
    granted = pyqtSignal()
    denied = pyqtSignal()
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)
    instances = []

    def __init__(self, denied_before, parent=None):
        super().__init__(parent)
        self.denied_before = denied_before
        self.started = self.closed = False
        FakePermission.instances.append(self)

    def start(self):
        self.started = True

    def close(self):
        self.closed = True


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return Settings()


@pytest.fixture
def shot(qapp):
    screen = QGuiApplication.primaryScreen()
    image = QImage(screen.geometry().width(), screen.geometry().height(), QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    return ScreenShot(screen, image)


@pytest.fixture
def rig(qapp, store):
    FakeJob.instances.clear()
    TrackingSession.instances.clear()
    FakePermission.instances.clear()
    clipboard = []
    order = []

    def copy(text):
        session = TrackingSession.instances[-1]
        order.append(("copy", session.closed))
        clipboard.append(text)
        return True

    notifier = FakeNotifier()
    grabber = FakeGrabber()
    controller = app.CaptureController(
        store, notifier, grabber,
        overlay_factory=TrackingSession, ocr_factory=FakeJob,
        languages=lambda: ["eng", "deu"], engine_installed=lambda: True,
        copy=copy, permission_factory=FakePermission,
    )
    yield controller, grabber, notifier, clipboard, order
    controller.finish()


def start_capture(controller, grabber, shot):
    controller.trigger()
    pump()
    assert grabber.calls >= 1
    grabber.grabbed.emit([shot])
    pump()
    return TrackingSession.instances[-1]


def summaries(notifier):
    return [args[args.index("org.freedesktop.Notifications.Notify") + 4] for args in notifier.sent]


# --- 8.1 capture controller ----------------------------------------------------------------


def test_full_capture_copies_before_overlay_closes(rig, shot):
    controller, grabber, notifier, clipboard, order = rig
    session = start_capture(controller, grabber, shot)
    assert controller.state == controller.SELECTING and session.windows[0].isVisible()

    session.windows[0].selected.emit(Rect(10, 10, 200, 50))
    job = FakeJob.instances[-1]
    assert job.started and job.language == "eng" and job.png.startswith(b"\x89PNG")
    assert controller.state == controller.RECOGNIZING

    job.finished.emit("  Hello\nworld\n\f")
    assert clipboard == ["Hello\nworld"]
    assert order == [("copy", False)]  # clipboard set while the overlay still had focus
    assert session.closed and controller.state == controller.IDLE
    assert summaries(notifier) == ["'Text copied'"]


def test_second_trigger_during_capture_is_ignored(rig, shot):
    controller, grabber, *_ = rig
    start_capture(controller, grabber, shot)
    controller.trigger()
    pump()
    assert grabber.calls == 1
    assert len(TrackingSession.instances) == 1


def test_exception_mid_capture_closes_overlays_and_next_trigger_works(rig, shot, monkeypatch):
    controller, grabber, notifier, clipboard, _ = rig
    session = start_capture(controller, grabber, shot)
    monkeypatch.setattr(app.ocr, "preprocess", lambda *a: 1 / 0)

    session.windows[0].selected.emit(Rect(10, 10, 200, 50))

    assert session.closed and all(not w.isVisible() for w in session.windows)
    assert controller.state == controller.IDLE
    assert summaries(notifier) == ["'Capture failed'"]
    assert clipboard == []

    monkeypatch.undo()
    start_capture(controller, grabber, shot)
    assert grabber.calls == 2 and controller.state == controller.SELECTING


def test_exception_while_showing_overlay(rig, shot, monkeypatch):
    controller, grabber, notifier, *_ = rig
    monkeypatch.setattr(TrackingSession, "show", lambda self: 1 / 0)
    controller.trigger()
    pump()
    grabber.grabbed.emit([shot])
    session = TrackingSession.instances[-1]
    assert session.closed and controller.state == controller.IDLE
    assert summaries(notifier) == ["'Capture failed'"]


def test_cancel_during_recognition(rig, shot):
    controller, grabber, notifier, clipboard, _ = rig
    session = start_capture(controller, grabber, shot)
    session.windows[0].selected.emit(Rect(10, 10, 200, 50))
    job = FakeJob.instances[-1]
    session.cancel()
    assert job.cancelled and clipboard == [] and controller.state == controller.IDLE
    job.finished.emit("late result")  # a late result is ignored
    assert clipboard == []


def test_ocr_failure_is_reported(rig, shot):
    controller, grabber, notifier, clipboard, _ = rig
    session = start_capture(controller, grabber, shot)
    session.windows[0].selected.emit(Rect(10, 10, 200, 50))
    FakeJob.instances[-1].failed.emit(ocr.TIMEOUT, "Recognition took too long and was stopped.")
    assert session.closed and clipboard == []
    assert summaries(notifier) == ["'Recognition timed out'"]


def test_missing_engine_reported_without_grabbing(rig):
    controller, grabber, notifier, *_ = rig
    controller.engine_installed = lambda: False
    controller.trigger()
    pump()
    assert grabber.calls == 0 and controller.state == controller.IDLE
    assert summaries(notifier) == ["'OCR engine not installed'"]
    assert "tesseract-ocr" in notifier.sent[0][-4]


def test_language_fallback_warned_once(rig, shot, store):
    controller, grabber, notifier, *_ = rig
    store.set(settings.LANGUAGE, "fra")
    for _ in range(2):
        session = start_capture(controller, grabber, shot)
        session.windows[0].selected.emit(Rect(10, 10, 200, 50))
        assert FakeJob.instances[-1].language == "eng"
        controller.finish()
    assert summaries(notifier) == ["'OCR language not available'"]


def test_grab_error_is_reported(rig):
    controller, grabber, notifier, *_ = rig
    controller.trigger()
    pump()
    grabber.failed.emit(grab.ERROR, "Ubuntu did not provide a screenshot.")
    assert controller.state == controller.IDLE
    assert summaries(notifier) == ["'Capture failed'"]


# --- 4.7 permission flow decisions -------------------------------------------------------


def test_permission_needed_then_granted_starts_capture(rig):
    controller, grabber, notifier, *_ = rig
    controller.trigger()
    pump()
    grabber.failed.emit(grab.PERMISSION_NEEDED, "")
    flow = FakePermission.instances[-1]
    assert flow.started and not flow.denied_before and controller.state == controller.PERMISSION

    flow.granted.emit()
    pump(app.PERMISSION_CAPTURE_DELAY_MS + 100)
    assert grabber.calls == 2 and controller.state == controller.GRABBING
    assert notifier.sent == []


def test_permission_denied_is_reported(rig):
    controller, grabber, notifier, *_ = rig
    controller.trigger()
    pump()
    grabber.failed.emit(grab.PERMISSION_DENIED, "")
    flow = FakePermission.instances[-1]
    assert flow.denied_before
    flow.denied.emit()
    assert controller.state == controller.IDLE
    assert summaries(notifier) == ["'Screen capture not allowed'"]


def test_permission_cancel_does_nothing(rig):
    controller, grabber, notifier, clipboard, _ = rig
    controller.trigger()
    pump()
    grabber.failed.emit(grab.PERMISSION_NEEDED, "")
    FakePermission.instances[-1].cancelled.emit()
    assert controller.state == controller.IDLE and notifier.sent == [] and clipboard == []


class FakePortal(QObject):
    done = pyqtSignal(int, QImage)

    def __init__(self, timeout_ms, parent=None):
        super().__init__(parent)

    def start(self):
        pass


@pytest.mark.parametrize(
    "response, stored, denied_before, outcome, forgot",
    [
        (0, "yes", False, "granted", False),
        (2, "no", False, "denied", False),
        (2, None, False, "failed", False),  # GNOME refused to show its dialog
        (0, "yes", True, "granted", True),  # Continue after an earlier Deny forgets that answer first
    ],
)
def test_permission_flow_outcomes(qapp, response, stored, denied_before, outcome, forgot):
    forgotten = []
    flow = app.PermissionFlow(denied_before, portal_factory=FakePortal, lookup=lambda: stored, forget=lambda: forgotten.append(1))
    events = []
    flow.granted.connect(lambda: events.append("granted"))
    flow.denied.connect(lambda: events.append("denied"))
    flow.failed.connect(lambda msg: events.append("failed"))
    flow.start()
    assert flow.window.isVisible()
    flow.window.continue_button.click()
    flow._request.done.emit(response, QImage())
    assert events == [outcome]
    assert bool(forgotten) == forgot
    assert flow.window is None


def test_permission_window_cancel(qapp):
    flow = app.PermissionFlow(False, portal_factory=FakePortal)
    events = []
    flow.cancelled.connect(lambda: events.append("cancelled"))
    flow.start()
    flow.window.cancel_button.click()
    assert events == ["cancelled"]


# --- 8.2 tray menu -------------------------------------------------------------------------


class FakeController:
    def __init__(self):
        self.triggers = []

    def trigger(self, delay_ms=0):
        self.triggers.append(delay_ms)


def test_tray_menu_structure(qapp, store):
    tray = app.Tray(store, FakeController(), quit_app=lambda: None, languages=lambda: ["eng", "deu"])
    texts = [a.text() for a in tray.menu.actions()]
    assert texts == ["Capture", "OCR Language", "", "Keep line breaks", "Show notifications", "Start at login", "", "Quit"]
    assert all(a.isChecked() for a in (tray.keep_action, tray.notify_action, tray.autostart_action))
    languages = tray.language_menu.actions()
    assert [a.text() for a in languages] == ["English", "German"]
    assert [a.isChecked() for a in languages] == [True, False]


def test_tray_actions_change_settings(qapp, store):
    controller = FakeController()
    quits = []
    tray = app.Tray(store, controller, quit_app=lambda: quits.append(1), languages=lambda: ["eng", "deu"])

    tray.capture_action.trigger()
    assert controller.triggers == [app.TRAY_CAPTURE_DELAY_MS]

    tray.keep_action.trigger()
    tray.notify_action.trigger()
    assert store.get(settings.KEEP_LINE_BREAKS) is False and store.get(settings.NOTIFY) is False

    tray.language_menu.actions()[1].trigger()
    assert store.get(settings.LANGUAGE) == "deu"
    tray.refresh_languages()
    assert [a.isChecked() for a in tray.language_menu.actions()] == [False, True]

    tray.autostart_action.trigger()
    assert store.get(settings.AUTOSTART) is False and not settings.autostart_path().exists()
    tray.autostart_action.trigger()
    assert settings.autostart_path().exists()

    tray.quit_action.trigger()
    assert quits == [1]


def test_tray_without_languages(qapp, store):
    tray = app.Tray(store, FakeController(), quit_app=lambda: None, languages=lambda: [])
    (only,) = tray.language_menu.actions()
    assert not only.isEnabled()


# --- 8.4 first run and uninstall --------------------------------------------------------------


GNOME_ENV = {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}


def test_pretty_accel():
    assert app.pretty_accel("<Control>q") == "Ctrl+Q"
    assert app.pretty_accel("<Shift><Super>q") == "Shift+Super+Q"
    assert app.pretty_accel("<Alt>F7") == "Alt+F7"


def test_first_run_creates_shortcut_and_autostart(store, monkeypatch):
    monkeypatch.setenv(settings.LAUNCHER_ENV, "/home/u/.local/bin/text-capture")
    monkeypatch.setattr(app.shutil, "which", lambda name: "/usr/bin/" + name)
    gs = FakeGSettings().free_default()
    notifier = FakeNotifier()

    app.first_run_setup(store, notifier, gs, env=GNOME_ENV)

    assert gnome_hotkey.get_custom(gnome_hotkey.OUR_PATH, "command", gs) == "/home/u/.local/bin/text-capture --capture"
    assert gnome_hotkey.get_custom(gnome_hotkey.OUR_PATH, "binding", gs) == "<Control>q"
    assert settings.autostart_path().exists()
    assert store.get(settings.HOTKEY_REGISTERED) is True
    assert summaries(notifier) == ["'Text Capture is ready'"]


def test_first_run_with_conflict_notifies(store, monkeypatch):
    monkeypatch.setattr(app.shutil, "which", lambda name: "/usr/bin/" + name)
    gs = FakeGSettings()  # NormCap holds Ctrl+Q, as on the dev machine
    notifier = FakeNotifier()
    app.first_run_setup(store, notifier, gs, env=GNOME_ENV)
    assert gnome_hotkey.get_custom(gnome_hotkey.OUR_PATH, "binding", gs) == ""
    assert summaries(notifier) == ["'Capture shortcut not set'"]


def test_deleted_shortcut_is_not_recreated(store, monkeypatch):
    monkeypatch.setattr(app.shutil, "which", lambda name: "/usr/bin/" + name)
    gs = FakeGSettings().free_default()
    app.first_run_setup(store, FakeNotifier(), gs, env=GNOME_ENV)
    gnome_hotkey.unregister(gs)  # the user removed it in Settings
    app.first_run_setup(store, FakeNotifier(), gs, env=GNOME_ENV)
    assert gnome_hotkey.OUR_PATH not in gnome_hotkey.custom_paths(gs)


def test_autostart_off_is_respected(store):
    store.set(settings.AUTOSTART, False)
    app.first_run_setup(store, FakeNotifier(), FakeGSettings(), env={})
    assert not settings.autostart_path().exists()


def test_uninstall_removes_only_ours(store, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(app.shutil, "which", lambda name: "/usr/bin/" + name)
    gs = FakeGSettings().free_default()
    before = gs.snapshot()
    app.first_run_setup(store, FakeNotifier(), gs, env=GNOME_ENV)
    other_autostart = settings.autostart_path().parent / "other-app.desktop"
    other_autostart.write_text("[Desktop Entry]\n")

    assert app.uninstall(gs) == 0

    assert gnome_hotkey.OUR_PATH not in gnome_hotkey.custom_paths(gs)
    assert gs.snapshot() == before
    assert not settings.autostart_path().exists()
    assert other_autostart.exists()
    assert Settings().get(settings.HOTKEY_REGISTERED) is False
    out = capsys.readouterr().out
    assert "Removed the capture shortcut." in out and "Removed the autostart entry." in out


def test_logging_goes_to_state_dir(store):
    app.setup_logging()
    app.log.info("hello from the test")
    for handler in app.log.handlers:
        handler.flush()
    log_file = settings.state_dir() / "text-capture.log"
    assert "hello from the test" in log_file.read_text()
    for handler in list(app.log.handlers):
        app.log.removeHandler(handler)
        handler.close()
