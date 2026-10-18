"""Image preprocessing, Tesseract runner, language list and text normalization (design D6).

Tesseract runs as a separate, niced process fed through stdin, so a slow or crashing
recognition can be killed without touching the app, and no image is written to disk.
"""

import re
import shutil
import subprocess

from PyQt6.QtCore import QBuffer, QIODevice, QObject, QProcess, QProcessEnvironment, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter

DEFAULT_LANGUAGE = "eng"
ENGINE_PACKAGE = "tesseract-ocr"
TIMEOUT_MS = 15_000

# Tuned against tests/data/ocr (task 6.6).
UPSCALE_AT_1X = 2.0  # effective upscale for text captured at 100% display scale
PAGE_SEGMENTATION = 6  # "assume a single uniform block of text"
PADDING = 10
MAX_SIDE = 8000

# Failure kinds reported through `OcrJob.failed(kind, message)`.
MISSING_ENGINE = "missing-engine"
MISSING_LANGUAGE = "missing-language"
TIMEOUT = "timeout"
ERROR = "error"

LANGUAGE_NAMES = {
    "afr": "Afrikaans", "ara": "Arabic", "bul": "Bulgarian", "cat": "Catalan", "ces": "Czech",
    "chi_sim": "Chinese (Simplified)", "chi_tra": "Chinese (Traditional)", "dan": "Danish",
    "deu": "German", "ell": "Greek", "eng": "English", "est": "Estonian", "fin": "Finnish",
    "fra": "French", "heb": "Hebrew", "hin": "Hindi", "hrv": "Croatian", "hun": "Hungarian",
    "ind": "Indonesian", "ita": "Italian", "jpn": "Japanese", "kor": "Korean", "lav": "Latvian",
    "lit": "Lithuanian", "nld": "Dutch", "nor": "Norwegian", "pol": "Polish", "por": "Portuguese",
    "ron": "Romanian", "rus": "Russian", "slk": "Slovak", "slv": "Slovenian", "spa": "Spanish",
    "srp": "Serbian", "swe": "Swedish", "tha": "Thai", "tur": "Turkish", "ukr": "Ukrainian",
    "vie": "Vietnamese",
}


# --- languages --------------------------------------------------------------------


def engine_installed() -> bool:
    return shutil.which("tesseract") is not None


def _list_langs_output() -> str:
    proc = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10)
    return proc.stdout + proc.stderr


def parse_languages(output: str) -> list[str]:
    """Language codes from `tesseract --list-langs` output, without the `osd` pseudo-language."""
    codes = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of available languages") or " " in line:
            continue
        if line != "osd":
            codes.append(line)
    return sorted(codes, key=lambda c: display_name(c).lower())


def available_languages(run=_list_langs_output) -> list[str]:
    if not engine_installed():
        return []
    try:
        return parse_languages(run())
    except (OSError, subprocess.SubprocessError):
        return []


def display_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def resolve_language(selected: str, available: list[str]) -> tuple[str, bool]:
    """The language to use and whether we had to fall back from the selected one."""
    if selected in available:
        return selected, False
    return DEFAULT_LANGUAGE, True


# --- preprocessing ------------------------------------------------------------------


def mean_lightness(gray: QImage) -> float:
    small = gray.scaled(64, 64, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    small = small.convertToFormat(QImage.Format.Format_Grayscale8)
    bits = small.constBits()
    bits.setsize(small.sizeInBytes())
    data = bytes(bits)
    stride = small.bytesPerLine()
    values = [data[y * stride + x] for y in range(small.height()) for x in range(small.width())]
    return sum(values) / len(values)


def border_lightness(gray: QImage) -> int:
    w, h = gray.width(), gray.height()
    points = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    points += [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    return round(sum(QColor(gray.pixel(x, y)).lightness() for x, y in points) / len(points))


def preprocess(image: QImage, scale: float = 1.0, upscale_at_1x: float = UPSCALE_AT_1X) -> QImage:
    """Grayscale, dark text on a light background, upscaled to what Tesseract reads best, padded.

    `scale` is the capture's physical pixels per logical pixel (2.0 on a 200% display),
    so text that is already rendered large is upscaled less.
    """
    gray = image.convertToFormat(QImage.Format.Format_Grayscale8)
    if mean_lightness(gray) < 128:
        gray.invertPixels()
    factor = max(1.0, upscale_at_1x / max(scale, 0.1))
    factor = min(factor, MAX_SIDE / max(gray.width(), gray.height(), 1))
    if factor > 1.0:
        gray = gray.scaled(
            round(gray.width() * factor),
            round(gray.height() * factor),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    padded = QImage(gray.width() + 2 * PADDING, gray.height() + 2 * PADDING, QImage.Format.Format_Grayscale8)
    padded.fill(QColor.fromHsl(0, 0, border_lightness(gray)))
    painter = QPainter(padded)
    painter.drawImage(PADDING, PADDING, gray)
    painter.end()
    return padded


def to_png(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


# --- recognition ----------------------------------------------------------------------


class OcrJob(QObject):
    """One asynchronous Tesseract run. Emits `finished(text)` or `failed(kind, message)`, once."""

    finished = pyqtSignal(str)
    failed = pyqtSignal(str, str)

    def __init__(self, png: bytes, language: str, psm: int = PAGE_SEGMENTATION, timeout_ms: int = TIMEOUT_MS, parent=None):
        super().__init__(parent)
        self._png = png
        self._language = language
        self._psm = psm
        self._done = False
        self._process = QProcess(self)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)
        self._timer = QTimer(self, singleShot=True, interval=timeout_ms)
        self._timer.timeout.connect(self._on_timeout)

    def start(self):
        if not engine_installed():
            QTimer.singleShot(0, lambda: self._fail(MISSING_ENGINE, f"Install the {ENGINE_PACKAGE} package."))
            return
        env = QProcessEnvironment.systemEnvironment()
        env.insert("OMP_THREAD_LIMIT", "1")  # small images: threads only add CPU contention
        self._process.setProcessEnvironment(env)
        args = ["stdin", "stdout", "-l", self._language, "--psm", str(self._psm), "--dpi", "300"]
        if shutil.which("nice"):
            self._process.start("nice", ["-n", "10", "tesseract", *args])
        else:
            self._process.start("tesseract", args)
        self._process.write(self._png)
        self._process.closeWriteChannel()
        self._timer.start()

    def cancel(self):
        """Stop without emitting anything."""
        self._done = True
        self._kill()

    @property
    def running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    def _kill(self):
        self._timer.stop()
        if self.running:
            self._process.kill()
            self._process.waitForFinished(1000)

    def _on_timeout(self):
        # Report first: killing emits QProcess.finished synchronously, which must not win.
        self._fail(TIMEOUT, "Recognition took too long and was stopped.")
        self._kill()

    def _on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._fail(MISSING_ENGINE, f"Install the {ENGINE_PACKAGE} package.")

    def _on_finished(self, code: int, status):
        if self._done:
            return
        self._timer.stop()
        stderr = bytes(self._process.readAllStandardError()).decode(errors="replace")
        if status != QProcess.ExitStatus.NormalExit or code != 0:
            if re.search(r"Failed loading language|Error opening data file", stderr):
                self._fail(MISSING_LANGUAGE, f"The OCR language '{self._language}' is not installed.")
            elif code == 127:
                self._fail(MISSING_ENGINE, f"Install the {ENGINE_PACKAGE} package.")
            else:
                self._fail(ERROR, stderr.strip().splitlines()[-1] if stderr.strip() else f"tesseract exited with {code}")
            return
        self._done = True
        self.finished.emit(bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace"))

    def _fail(self, kind: str, message: str):
        if self._done:
            return
        self._done = True
        self.failed.emit(kind, message)


# --- text normalization ---------------------------------------------------------------


def normalize(text: str, keep_line_breaks: bool = True) -> str:
    """Trim, collapse blank lines, and keep or join the lines within each paragraph."""
    text = text.replace("\f", "").replace("\r", "")
    paragraphs, current = [], []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    if keep_line_breaks:
        return "\n\n".join("\n".join(lines) for lines in paragraphs)
    return "\n".join(" ".join(lines) for lines in paragraphs)
