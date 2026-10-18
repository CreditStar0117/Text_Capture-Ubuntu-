import time

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication

from text_capture.grab import Rect, ScreenShot
from text_capture.overlay import OverlaySession


@pytest.fixture
def shot(qapp):
    screen = QGuiApplication.primaryScreen()
    g = screen.geometry()
    image = QImage(g.width(), g.height(), QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    return ScreenShot(screen, image)


@pytest.fixture
def session(shot):
    s = OverlaySession([shot])
    s.show()
    QApplication.processEvents()
    yield s
    s.close()


def mouse(widget, kind, x, y, button=Qt.MouseButton.LeftButton):
    types = {"press": QEvent.Type.MouseButtonPress, "move": QEvent.Type.MouseMove, "release": QEvent.Type.MouseButtonRelease}
    pos = QPointF(x, y)
    event = QMouseEvent(
        types[kind],
        pos,
        widget.mapToGlobal(pos),
        Qt.MouseButton.NoButton if kind == "move" else button,
        Qt.MouseButton.NoButton if kind == "release" else button,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, event)


def drag(widget, x0, y0, x1, y1):
    mouse(widget, "press", x0, y0)
    mouse(widget, "move", (x0 + x1) / 2, (y0 + y1) / 2)
    mouse(widget, "move", x1, y1)
    mouse(widget, "release", x1, y1)


def press_escape(widget):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))


def record(session):
    events = []
    session.selected.connect(lambda index, rect: events.append(("selected", index, rect)))
    session.cancelled.connect(lambda: events.append(("cancelled",)))
    return events


# --- 5.1 windows and painting ------------------------------------------------------------


def test_one_window_per_screen_shot(shot):
    s = OverlaySession([shot, shot])
    s.show()
    try:
        assert len(s.windows) == 2
        assert all(w.isVisible() and w.isFullScreen() for w in s.windows)
        assert all(w.screen() is shot.screen for w in s.windows)
    finally:
        s.close()


def test_frozen_image_is_dimmed(session, shot):
    window = session.windows[0]
    painted = window.grab().toImage()
    center = painted.pixelColor(window.width() // 2, window.height() // 2)
    assert center.lightness() < 200  # white source, dimmed
    assert window.cursor().shape() == Qt.CursorShape.CrossCursor


# --- 5.2 selection ----------------------------------------------------------------------------


def test_drag_selects_rectangle_and_shows_it_undimmed(session):
    events = record(session)
    window = session.windows[0]
    drag(window, 300, 200, 100, 100)  # dragging up-left works too

    assert events == [("selected", 0, Rect(100, 100, 200, 100))]
    painted = window.grab().toImage()
    assert painted.pixelColor(200, 150) == QColor("white")  # inside: undimmed
    assert painted.pixelColor(50, 50).lightness() < 200  # outside: dimmed
    crop = session.crop(0, Rect(100, 100, 200, 100))
    assert (crop.width(), crop.height()) == (200, 100)


@pytest.mark.parametrize("dx, dy", [(0, 0), (3, 40), (40, 3)])
def test_click_or_tiny_drag_is_ignored(session, dx, dy):
    events = record(session)
    window = session.windows[0]
    drag(window, 100, 100, 100 + dx, 100 + dy)
    assert events == []
    assert window.isVisible()
    drag(window, 100, 100, 160, 140)  # the user can try again
    assert events == [("selected", 0, Rect(100, 100, 60, 40))]


def test_drag_past_the_edge_is_clamped(session):
    events = record(session)
    window = session.windows[0]
    w, h = window.width(), window.height()
    drag(window, w - 50, h - 40, w + 300, h + 300)
    assert events == [("selected", 0, Rect(w - 50, h - 40, 50, 40))]


# --- 5.3 cancellation and busy state ---------------------------------------------------------


def test_escape_cancels(session):
    events = record(session)
    press_escape(session.windows[0])
    assert events == [("cancelled",)]
    assert session.closed


def test_right_click_cancels(session):
    events = record(session)
    mouse(session.windows[0], "press", 50, 50, Qt.MouseButton.RightButton)
    assert events == [("cancelled",)]


def test_inactivity_timeout_cancels(shot):
    s = OverlaySession([shot], timeout_ms=100)
    events = record(s)
    s.show()
    deadline = time.monotonic() + 3
    while not events and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert events == [("cancelled",)]
    assert s.closed


def test_activity_restarts_the_timeout(shot):
    s = OverlaySession([shot], timeout_ms=300)
    events = record(s)
    s.show()
    try:
        for _ in range(6):  # 600 ms of mouse activity in total
            mouse(s.windows[0], "move", 10, 10)
            mouse(s.windows[0], "press", 10, 10)
            mouse(s.windows[0], "release", 11, 11)
            t = time.monotonic()
            while time.monotonic() - t < 0.1:
                QApplication.processEvents()
        assert events == []
    finally:
        s.close()


def test_recognizing_state_keeps_overlay_and_escape_still_cancels(session):
    events = record(session)
    window = session.windows[0]
    drag(window, 100, 100, 300, 200)
    session.set_busy()
    drag(window, 10, 10, 90, 90)  # input is ignored while recognizing
    assert events == [("selected", 0, Rect(100, 100, 200, 100))]
    assert window.isVisible()
    assert window.cursor().shape() == Qt.CursorShape.BusyCursor

    press_escape(window)
    assert events[-1] == ("cancelled",)
    assert session.closed
