import pytest

from text_capture import grab
from text_capture.grab import Rect, screen_source_rects, selection_to_crop

# --- 4.1 session detection ------------------------------------------------------


@pytest.mark.parametrize(
    "env, expected",
    [
        ({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}, "x11"),
        ({"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0"}, "wayland"),
        # Qt forced onto XWayland must still use the portal: X11 grabs show Wayland windows black.
        ({"XDG_SESSION_TYPE": "wayland", "QT_QPA_PLATFORM": "xcb", "DISPLAY": ":0"}, "wayland"),
        ({"WAYLAND_DISPLAY": "wayland-0"}, "wayland"),
        ({"XDG_SESSION_TYPE": "tty", "WAYLAND_DISPLAY": "wayland-0"}, "wayland"),
        ({"DISPLAY": ":0"}, "x11"),
        ({}, "x11"),
    ],
)
def test_session_type(env, expected):
    assert grab.session_type(env) == expected


def test_create_grabber(qapp):
    assert isinstance(grab.create_grabber({"XDG_SESSION_TYPE": "x11"}), grab.X11Grabber)
    assert isinstance(grab.create_grabber({"XDG_SESSION_TYPE": "wayland", "QT_QPA_PLATFORM": "xcb"}), grab.PortalGrabber)


# --- 4.5 geometry -----------------------------------------------------------------


def test_single_screen_100():
    assert screen_source_rects([(Rect(0, 0, 1920, 1080), 1.0)], 1920, 1080) == [Rect(0, 0, 1920, 1080)]
    assert selection_to_crop(Rect(100, 50, 200, 40), 1920, 1080, 1920, 1080) == Rect(100, 50, 200, 40)


def test_single_screen_200():
    assert screen_source_rects([(Rect(0, 0, 1920, 1080), 2.0)], 3840, 2160) == [Rect(0, 0, 3840, 2160)]
    # Spec scenario: a 100 x 50 logical selection at 200% is a 200 x 100 image.
    assert selection_to_crop(Rect(10, 10, 100, 50), 1920, 1080, 3840, 2160) == Rect(20, 20, 200, 100)


def test_single_screen_125_fractional():
    assert screen_source_rects([(Rect(0, 0, 1920, 1080), 1.25)], 2400, 1350) == [Rect(0, 0, 2400, 1350)]
    assert selection_to_crop(Rect(100, 100, 80, 40), 1920, 1080, 2400, 1350) == Rect(125, 125, 100, 50)
    # Non-integer edges round outwards so no selected pixel is lost.
    assert selection_to_crop(Rect(1, 1, 3, 3), 1920, 1080, 2400, 1350) == Rect(1, 1, 4, 4)


def test_two_screens_same_scale_100():
    screens = [(Rect(0, 0, 1920, 1080), 1.0), (Rect(1920, 0, 1920, 1080), 1.0)]
    assert screen_source_rects(screens, 3840, 1080) == [Rect(0, 0, 1920, 1080), Rect(1920, 0, 1920, 1080)]


def test_two_screens_same_scale_200_logical_layout():
    screens = [(Rect(0, 0, 1920, 1080), 2.0), (Rect(1920, 0, 1920, 1080), 2.0)]
    assert screen_source_rects(screens, 7680, 2160) == [Rect(0, 0, 3840, 2160), Rect(3840, 0, 3840, 2160)]


def test_two_screens_same_scale_200_physical_layout():
    # Qt keeps a screen's top-left in device pixels: the second screen starts at x=3840.
    screens = [(Rect(0, 0, 1920, 1080), 2.0), (Rect(3840, 0, 1920, 1080), 2.0)]
    assert screen_source_rects(screens, 7680, 2160) == [Rect(0, 0, 3840, 2160), Rect(3840, 0, 3840, 2160)]


def test_mixed_scales_physical_layout():
    screens = [(Rect(0, 0, 1920, 1080), 1.0), (Rect(1920, 0, 1920, 1080), 2.0)]
    assert screen_source_rects(screens, 5760, 2160) == [Rect(0, 0, 1920, 1080), Rect(1920, 0, 3840, 2160)]


def test_mixed_scales_logical_layout_falls_back_to_uniform_scale():
    # GNOME renders a logical-layout screenshot at the highest scale for every monitor.
    screens = [(Rect(0, 0, 1920, 1080), 1.0), (Rect(1920, 0, 1920, 1080), 2.0)]
    assert screen_source_rects(screens, 7680, 2160) == [Rect(0, 0, 3840, 2160), Rect(3840, 0, 3840, 2160)]
    # A selection on the 1x monitor then maps onto its upscaled pixels.
    assert selection_to_crop(Rect(10, 10, 100, 50), 1920, 1080, 3840, 2160) == Rect(20, 20, 200, 100)


def test_negative_offsets():
    left_of_primary = [(Rect(0, 0, 1920, 1080), 1.0), (Rect(-1920, 0, 1920, 1080), 1.0)]
    assert screen_source_rects(left_of_primary, 3840, 1080) == [Rect(1920, 0, 1920, 1080), Rect(0, 0, 1920, 1080)]

    raised = [(Rect(0, 0, 1920, 1080), 1.0), (Rect(1920, -300, 1280, 1024), 1.0)]
    assert screen_source_rects(raised, 3200, 1380) == [Rect(0, 300, 1920, 1080), Rect(1920, 0, 1280, 1024)]


def test_selection_is_clamped_to_the_image():
    assert selection_to_crop(Rect(1900, 1000, 100, 100), 1920, 1080, 1920, 1080) == Rect(1900, 1000, 20, 80)
    assert selection_to_crop(Rect(-5, -5, 10, 10), 1920, 1080, 1920, 1080) == Rect(0, 0, 5, 5)


class FakeScreen:
    def __init__(self, x, y, w, h, dpr=1.0):
        from PyQt6.QtCore import QRect

        self._geometry = QRect(x, y, w, h)
        self._dpr = dpr

    def geometry(self):
        return self._geometry

    def devicePixelRatio(self):
        return self._dpr


def test_split_desktop(qapp):
    from PyQt6.QtGui import QColor, QImage, QPainter

    desktop = QImage(300, 100, QImage.Format.Format_RGB32)
    painter = QPainter(desktop)
    painter.fillRect(0, 0, 100, 100, QColor("red"))
    painter.fillRect(100, 0, 200, 100, QColor("blue"))
    painter.end()

    left, right = grab.split_desktop(desktop, [FakeScreen(0, 0, 100, 100), FakeScreen(100, 0, 200, 100)])
    assert (left.image.width(), left.image.height()) == (100, 100)
    assert (right.image.width(), right.image.height()) == (200, 100)
    assert left.image.pixelColor(99, 50) == QColor("red")
    assert right.image.pixelColor(0, 50) == QColor("blue")


# --- 4.3 / 4.7 portal failure classification ------------------------------------------


@pytest.mark.parametrize(
    "response, stored, kind",
    [
        (2, None, grab.PERMISSION_NEEDED),  # GNOME refused to show its dialog: we are not focused
        (1, None, grab.PERMISSION_NEEDED),  # dialog dismissed without an answer
        (2, "no", grab.PERMISSION_DENIED),
        (2, "yes", grab.ERROR),  # allowed, so something else went wrong
        (-1, None, grab.ERROR),  # timeout or D-Bus error
    ],
)
def test_classify_failure(response, stored, kind):
    assert grab.classify_failure(response, stored) == kind
