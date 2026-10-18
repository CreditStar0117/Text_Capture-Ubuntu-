"""Per-monitor frozen-image overlay windows for region selection (design D5).

Wayland cannot position one window across monitors, so there is one full-screen
window per screen, each painting that screen's frozen image. A selection therefore
stays on the monitor where the drag started.
"""

from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QGuiApplication, QImage, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from .grab import Rect, ScreenShot, selection_to_crop

MIN_SELECTION = 4  # logical pixels; smaller drags are treated as accidental clicks
TIMEOUT_MS = 60_000
DIM = QColor(0, 0, 0, 110)
ACCENT = QColor("#3584e4")
LABEL_BG = QColor(0, 0, 0, 190)


class OverlayWindow(QWidget):
    selected = pyqtSignal(object)  # Rect in this screen's logical pixels
    cancelled = pyqtSignal()
    activity = pyqtSignal()

    def __init__(self, shot: ScreenShot):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.shot = shot
        self.setWindowTitle("Text Capture")
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._origin: QPointF | None = None
        self._current: QPointF | None = None
        self._final: QRectF | None = None
        self._busy = False

    def show_on_screen(self):
        geometry = self.shot.screen.geometry()
        self.setScreen(self.shot.screen)
        self.setGeometry(geometry)
        self.showFullScreen()

    def set_busy(self, busy: bool):
        self._busy = busy
        self.setCursor(Qt.CursorShape.BusyCursor if busy else Qt.CursorShape.CrossCursor)
        self.update()

    # --- selection ------------------------------------------------------------------

    def _clamp(self, pos: QPointF) -> QPointF:
        return QPointF(min(max(pos.x(), 0.0), self.width()), min(max(pos.y(), 0.0), self.height()))

    def selection(self) -> QRectF | None:
        if self._final is not None:
            return self._final
        if self._origin is None or self._current is None:
            return None
        return QRectF(self._origin, self._current).normalized()

    def crop_rect(self, sel: QRectF) -> Rect:
        image = self.shot.image
        return selection_to_crop(Rect(sel.x(), sel.y(), sel.width(), sel.height()), self.width(), self.height(), image.width(), image.height())

    def mousePressEvent(self, event):
        if self._busy:
            return
        self.activity.emit()
        if event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
        elif event.button() == Qt.MouseButton.LeftButton:
            self._final = None
            self._origin = self._current = self._clamp(event.position())
            self.update()

    def mouseMoveEvent(self, event):
        if self._busy or self._origin is None:
            return
        self.activity.emit()
        self._current = self._clamp(event.position())
        self.update()

    def mouseReleaseEvent(self, event):
        if self._busy or self._origin is None or event.button() != Qt.MouseButton.LeftButton:
            return
        self._current = self._clamp(event.position())
        sel = self.selection()
        self._origin = self._current = None
        if sel.width() < MIN_SELECTION or sel.height() < MIN_SELECTION:
            self.update()
            return
        self._final = sel
        self.update()
        self.selected.emit(Rect(sel.x(), sel.y(), sel.width(), sel.height()))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()

    # --- painting -----------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        image = self.shot.image
        painter.drawImage(QRectF(self.rect()), image)
        painter.fillRect(self.rect(), DIM)
        sel = self.selection()
        if sel is not None and sel.width() > 0 and sel.height() > 0:
            crop = self.crop_rect(sel)
            painter.drawImage(sel, image, QRectF(crop.x, crop.y, crop.w, crop.h))
            painter.setPen(QPen(ACCENT, 1))
            painter.drawRect(sel.adjusted(0, 0, -1, -1))
            label = "Recognizing…" if self._busy else f"{crop.w} × {crop.h}"
            self._draw_label(painter, label, sel)
        elif self._busy:
            self._draw_label(painter, "Recognizing…", QRectF(self.rect()))
        painter.end()

    def _draw_label(self, painter: QPainter, text: str, near: QRectF):
        font = QFont(self.font())
        font.setPointSizeF(max(font.pointSizeF(), 10))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        box = QRectF(0, 0, metrics.horizontalAdvance(text) + 16, metrics.height() + 8)
        box.moveBottomLeft(QPointF(near.left(), near.top() - 4))
        if box.top() < 0:  # no room above the selection: put the label inside it
            box.moveTopLeft(QPointF(near.left() + 4, near.top() + 4))
        box.moveLeft(min(max(box.left(), 0), self.width() - box.width()))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(LABEL_BG)
        painter.drawRoundedRect(box, 4, 4)
        painter.setPen(QColor("white"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)


class OverlaySession(QObject):
    """All overlay windows of one capture; emits one `selected` or one `cancelled`."""

    selected = pyqtSignal(int, object)  # index of the screen shot, Rect in its logical pixels
    cancelled = pyqtSignal()

    def __init__(self, shots: list[ScreenShot], timeout_ms: int = TIMEOUT_MS, parent=None):
        super().__init__(parent)
        self.windows = [OverlayWindow(shot) for shot in shots]
        self._closed = False
        self._timer = QTimer(self, singleShot=True, interval=timeout_ms)
        self._timer.timeout.connect(self.cancel)
        for index, window in enumerate(self.windows):
            window.selected.connect(lambda rect, index=index: self._on_selected(index, rect))
            window.cancelled.connect(self.cancel)
            window.activity.connect(self._timer.start)

    def show(self):
        for window in self.windows:
            window.show_on_screen()
        under_cursor = QGuiApplication.screenAt(QCursor.pos())
        focus = next((w for w in self.windows if w.shot.screen is under_cursor), self.windows[0])
        focus.raise_()
        focus.activateWindow()
        self._timer.start()

    def crop(self, index: int, rect: Rect) -> QImage:
        window = self.windows[index]
        c = window.crop_rect(QRectF(rect.x, rect.y, rect.w, rect.h))
        return window.shot.image.copy(int(c.x), int(c.y), int(c.w), int(c.h))

    def set_busy(self, busy: bool = True):
        self._timer.stop()
        for window in self.windows:
            window.set_busy(busy)

    def _on_selected(self, index: int, rect: Rect):
        if not self._closed:
            self._timer.stop()
            self.selected.emit(index, rect)

    def cancel(self):
        if self._closed:
            return
        self.close()
        self.cancelled.emit()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        for window in self.windows:
            window.close()
            window.deleteLater()

    @property
    def closed(self) -> bool:
        return self._closed
