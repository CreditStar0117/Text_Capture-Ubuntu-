"""Generate the OCR reference set: PNG images of known text plus the expected `.txt`.

    python3 tests/data/ocr/generate.py           # rendered images (works offscreen)
    python3 tests/data/ocr/generate.py --real    # also real screenshots of Qt widgets (needs an X11 session)

Rendered images draw text the way a 96-dpi screen does, at 100% and 200% scale, in
light and dark themes. "Real" images show a window with standard widgets on the
screen for about a second and grab them from the display, so the system's own font
rendering is included.
"""

import argparse
import os
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent

LIGHT = ("#1e1e1e", "#ffffff")
DARK = ("#deddda", "#242424")
GRAY = ("#5e5c64", "#fafafa")

# name, font family, pixel size at 100%, weight, scale, (text colour, background), text
RENDERED = [
    ("ubuntu-15-light", "Ubuntu", 15, 400, 1, LIGHT, "The quick brown fox jumps over the lazy dog."),
    ("ubuntu-13-dark", "Ubuntu", 13, 400, 1, DARK, "File Edit View Selection Go Run Terminal Help"),
    ("dejavu-12-light", "DejaVu Sans", 12, 400, 1, LIGHT, "Settings saved. Restart the application to apply the new theme."),
    ("noto-16-light-para", "Noto Sans", 16, 400, 1, LIGHT,
     "Your package has been shipped and will arrive\nbetween Monday and Wednesday next week."),
    ("liberation-serif-16-light", "Liberation Serif", 16, 400, 1, LIGHT,
     "It was the best of times, it was the worst of times,\nit was the age of wisdom, it was the age of foolishness."),
    ("dejavu-mono-15-dark", "DejaVu Sans Mono", 15, 400, 1, DARK, "git commit -m \"Fix login timeout\""),
    ("ubuntu-15-light-2x", "Ubuntu", 15, 400, 2, LIGHT, "Network connected to Office WiFi"),
    ("noto-13-dark-2x", "Noto Sans", 13, 400, 2, DARK, "Battery 84% remaining, about 5 hours left"),
    ("ubuntu-12-light", "Ubuntu", 12, 400, 1, LIGHT, "Invoice 2026-104 is due on 12 November 2026"),
    ("liberation-sans-15-light", "Liberation Sans", 15, 400, 1, LIGHT, "From: Maria Lopez <maria@example.com>"),
    ("noto-15-link", "Noto Sans", 15, 400, 1, ("#1a5fb4", "#ffffff"), "Click here to download the latest release"),
    ("noto-15-button", "Noto Sans", 15, 700, 1, ("#ffffff", "#3584e4"), "Install Update"),
    ("ubuntu-13-secondary", "Ubuntu", 13, 400, 1, GRAY, "Last modified 3 hours ago by Daniel"),
    ("dejavu-15-dark-para", "DejaVu Sans", 15, 400, 1, DARK,
     "Meeting notes for Thursday:\nreview the budget, plan the release,\nand book the venue for the workshop."),
    ("noto-mono-14-light", "Noto Sans Mono", 14, 400, 1, LIGHT, "sudo apt install tesseract-ocr"),
    ("noto-serif-19-light", "Noto Serif", 19, 400, 1, LIGHT, "Annual Report 2026: Results and Outlook"),
    ("ubuntu-16-bold-dark", "Ubuntu", 16, 700, 1, DARK, "Warning: Low disk space on the home folder"),
    ("noto-13-dark-numbers", "Noto Sans", 13, 400, 1, DARK, "Total: 1,234.56 EUR Tax: 234.10 EUR"),
    ("dejavu-serif-15-dark-2x", "DejaVu Serif", 15, 400, 2, DARK, "Chapter 3: The Long Road Home"),
    ("liberation-mono-13-light", "Liberation Mono", 13, 400, 1, LIGHT, "ERROR 404: Page not found"),
    ("noto-15-light-block", "Noto Sans", 15, 400, 1, LIGHT,
     "Text Capture lets you select any part of the screen and copies the text\n"
     "inside it to the clipboard. It works in every application, including\n"
     "images, videos, games and remote desktops, because it reads pixels\n"
     "instead of asking the application for its text. Press the shortcut,\n"
     "drag a rectangle around the words you need, and paste them anywhere.\n"
     "Recognition happens on your computer and nothing is sent online."),
]

REAL = [
    ("real-label", "label", "Choose a folder to save your documents"),
    ("real-lineedit", "lineedit", "Quarterly sales summary"),
    ("real-button", "button", "Save Changes"),
    ("real-checkbox", "checkbox", "Remember my password"),
    ("real-textedit", "textedit", "Dear team,\nthe office will be closed on Friday\nfor maintenance work."),
]


def render(name, family, pixel_size, weight, scale, colors, text):
    from PyQt6.QtCore import QRect, Qt
    from PyQt6.QtGui import QColor, QFont, QImage, QPainter

    font = QFont(family)
    font.setPixelSize(pixel_size * scale)
    font.setWeight(QFont.Weight(weight))
    margin = 8 * scale
    # Draw on a generous canvas, then crop to where the text really landed: metrics
    # taken from the screen can be shorter than the layout used on an image.
    canvas = QImage(4000, 1000, QImage.Format.Format_RGB32)
    canvas.fill(QColor(colors[1]))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(font)
    painter.setPen(QColor(colors[0]))
    bounds = painter.drawText(QRect(margin, margin, 3000, 900), Qt.AlignmentFlag.AlignLeft, text)
    painter.end()
    image = canvas.copy(0, 0, bounds.right() + 1 + margin, bounds.bottom() + 1 + margin)
    image.save(str(OUT / f"{name}.png"))
    (OUT / f"{name}.txt").write_text(text + "\n")


def grab_real_widgets():
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication, QCheckBox, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

    window = QWidget()
    window.setWindowTitle("Text Capture reference")
    layout = QVBoxLayout(window)
    widgets = {}
    for name, kind, text in REAL:
        if kind == "label":
            w = QLabel(text)
        elif kind == "lineedit":
            w = QLineEdit(text)
            w.setMinimumWidth(320)
        elif kind == "button":
            w = QPushButton(text)
        elif kind == "checkbox":
            w = QCheckBox(text)
        else:
            w = QTextEdit()
            w.setPlainText(text)
            w.setFixedHeight(90)
        layout.addWidget(w)
        widgets[name] = (w, text)
    window.show()
    window.raise_()
    window.activateWindow()
    loop = QEventLoop()
    QTimer.singleShot(800, loop.quit)
    loop.exec()

    screen = window.screen()
    for name, (w, text) in widgets.items():
        top_left = w.mapToGlobal(w.rect().topLeft()) - screen.geometry().topLeft()
        image = screen.grabWindow(0, top_left.x(), top_left.y(), w.width(), w.height()).toImage()
        image.save(str(OUT / f"{name}.png"))
        (OUT / f"{name}.txt").write_text(text + "\n")
    window.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--real", action="store_true", help="also grab real widgets from the X11 screen")
    args = parser.parse_args()
    if not args.real:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    for case in RENDERED:
        render(*case)
    if args.real:
        grab_real_widgets()
    print(f"wrote {len(list(OUT.glob('*.png')))} images to {OUT}")
    del app


if __name__ == "__main__":
    main()
