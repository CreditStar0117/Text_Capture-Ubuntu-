"""App and tray icons, drawn with QPainter (Ubuntu's Qt has no SVG image plugin by default).

    python3 -m text_capture.icons DIR   # write hicolor PNGs for the installer
"""

import sys
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen

from . import APP_DESKTOP_ID

APP_SIZES = (16, 24, 32, 48, 64, 128, 256)
TRAY_SIZES = (16, 22, 24, 32, 48)


def draw(size: int, tray: bool) -> QImage:
    """A dashed selection frame around a "T". Tray: light glyph for Ubuntu's dark top bar."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 64.0
    if tray:
        ink = QColor("#f6f5f4")
    else:
        background = QPainterPath()
        background.addRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s), 12 * s, 12 * s)
        p.fillPath(background, QColor("#3584e4"))
        ink = QColor("white")

    pen = QPen(ink, max(1.0, 4 * s))
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    inset, length = 10 * s, 12 * s
    frame = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    for (x, y), (dx, dy) in (
        ((frame.left(), frame.top()), (1, 1)),
        ((frame.right(), frame.top()), (-1, 1)),
        ((frame.left(), frame.bottom()), (1, -1)),
        ((frame.right(), frame.bottom()), (-1, -1)),
    ):
        p.drawLine(int(x), int(y), int(x + dx * length), int(y))
        p.drawLine(int(x), int(y), int(x), int(y + dy * length))

    font = QFont("Ubuntu")
    font.setBold(True)
    font.setPixelSize(max(6, round(30 * s)))
    p.setFont(font)
    p.setPen(ink)
    p.drawText(frame, Qt.AlignmentFlag.AlignCenter, "T")
    p.end()
    return image


def tray_icon() -> QIcon:
    from PyQt6.QtGui import QPixmap

    icon = QIcon()
    for size in TRAY_SIZES:
        icon.addPixmap(QPixmap.fromImage(draw(size, tray=True)))
    return icon


def app_icon() -> QIcon:
    from PyQt6.QtGui import QPixmap

    icon = QIcon()
    for size in APP_SIZES:
        icon.addPixmap(QPixmap.fromImage(draw(size, tray=False)))
    return icon


def write_hicolor(root: Path) -> list[Path]:
    written = []
    for size in APP_SIZES:
        path = root / f"{size}x{size}" / "apps" / f"{APP_DESKTOP_ID}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        draw(size, tray=False).save(str(path))
        written.append(path)
    return written


if __name__ == "__main__":
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtGui import QGuiApplication

    app = QGuiApplication(sys.argv[:1])
    for path in write_hicolor(Path(sys.argv[1])):
        print(path)
