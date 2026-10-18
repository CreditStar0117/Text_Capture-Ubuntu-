import os
import stat
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QColor, QImage

from text_capture import ocr

REFERENCE = Path(__file__).parent / "data" / "ocr"


def reference_pairs():
    """(name, image path, expected text, display scale) for every reference image."""
    pairs = []
    for png in sorted(REFERENCE.glob("*.png")):
        txt = png.with_suffix(".txt")
        scale = 2.0 if png.stem.endswith("-2x") else 1.0
        pairs.append((png.stem, png, txt.read_text().rstrip("\n"), scale))
    return pairs


def run_job(job, timeout=20.0):
    result = {}
    job.finished.connect(lambda text: result.setdefault("finished", text))
    job.failed.connect(lambda kind, message: result.setdefault("failed", (kind, message)))
    job.start()
    deadline = time.monotonic() + timeout
    while not result and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.005)
    return result


def recognize(qapp, png_path, scale=1.0, language="eng", **kwargs):
    image = ocr.preprocess(QImage(str(png_path)), scale, **{k: v for k, v in kwargs.items() if k == "upscale_at_1x"})
    psm = kwargs.get("psm", ocr.PAGE_SEGMENTATION)
    return run_job(ocr.OcrJob(ocr.to_png(image), language, psm=psm))


# --- 6.1 reference set ---------------------------------------------------------------


def test_reference_set_is_complete(qapp):
    pairs = reference_pairs()
    assert len(pairs) >= 20
    assert sum(name.startswith("real-") for name, *_ in pairs) >= 5
    for name, png, text, _ in pairs:
        assert not QImage(str(png)).isNull(), name
        assert text.strip(), name


# --- 6.2 languages ---------------------------------------------------------------------

LIST_LANGS = """List of available languages in "/usr/share/tesseract-ocr/5/tessdata/" (4):
eng
osd
deu
chi_sim
"""


def test_parse_languages():
    assert ocr.parse_languages(LIST_LANGS) == ["chi_sim", "eng", "deu"]  # sorted by display name
    assert [ocr.display_name(c) for c in ocr.parse_languages(LIST_LANGS)] == ["Chinese (Simplified)", "English", "German"]
    assert ocr.display_name("xyz") == "xyz"


def test_available_languages_on_this_machine():
    assert "eng" in ocr.available_languages()
    assert "osd" not in ocr.available_languages()


def test_missing_selected_language_falls_back_to_english():
    assert ocr.resolve_language("deu", ["deu", "eng"]) == ("deu", False)
    assert ocr.resolve_language("fra", ["deu", "eng"]) == ("eng", True)


# --- 6.3 preprocessing ------------------------------------------------------------------


def solid(width, height, color):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    return image


def test_preprocess_upscales_by_display_scale_and_pads(qapp):
    p = ocr.PADDING
    out = ocr.preprocess(solid(100, 20, "white"), scale=1.0, upscale_at_1x=3.0)
    assert (out.width(), out.height()) == (300 + 2 * p, 60 + 2 * p)
    assert out.format() == QImage.Format.Format_Grayscale8
    out = ocr.preprocess(solid(100, 20, "white"), scale=2.0, upscale_at_1x=3.0)
    assert (out.width(), out.height()) == (150 + 2 * p, 30 + 2 * p)
    out = ocr.preprocess(solid(100, 20, "white"), scale=4.0, upscale_at_1x=3.0)
    assert (out.width(), out.height()) == (100 + 2 * p, 20 + 2 * p)  # never downscaled


def test_preprocess_inverts_dark_images(qapp):
    out = ocr.preprocess(solid(50, 20, "#202020"), scale=1.0)
    assert QColor(out.pixel(out.width() // 2, out.height() // 2)).lightness() > 200
    assert QColor(out.pixel(0, 0)).lightness() > 200  # padding matches the new background


def test_preprocess_keeps_light_images(qapp):
    out = ocr.preprocess(solid(50, 20, "#f0f0f0"), scale=1.0)
    assert QColor(out.pixel(out.width() // 2, out.height() // 2)).lightness() > 200


# --- 6.4 runner -----------------------------------------------------------------------------


def test_real_run_returns_text(qapp):
    name, png, expected, scale = next(p for p in reference_pairs() if p[0] == "ubuntu-15-light")
    result = recognize(qapp, png, scale)
    assert "quick brown fox" in result["finished"]


def test_cancel_kills_the_process(qapp):
    png = ocr.to_png(ocr.preprocess(QImage(str(REFERENCE / "noto-15-light-block.png"))))
    job = ocr.OcrJob(png, "eng")
    events = []
    job.finished.connect(lambda text: events.append("finished"))
    job.failed.connect(lambda kind, message: events.append("failed"))
    job.start()
    assert job.running
    job.cancel()
    assert not job.running
    for _ in range(50):
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert events == []


@pytest.fixture
def fake_tesseract(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "tesseract"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return script


def test_timeout(qapp, fake_tesseract):
    fake_tesseract.write_text("#!/bin/sh\nexec sleep 30\n")
    fake_tesseract.chmod(fake_tesseract.stat().st_mode | stat.S_IEXEC)
    job = ocr.OcrJob(b"png", "eng", timeout_ms=300)
    started = time.monotonic()
    result = run_job(job)
    assert result["failed"][0] == ocr.TIMEOUT
    assert time.monotonic() - started < 5
    assert not job.running


def test_missing_engine(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    result = run_job(ocr.OcrJob(b"png", "eng"))
    kind, message = result["failed"]
    assert kind == ocr.MISSING_ENGINE
    assert "tesseract-ocr" in message
    assert ocr.available_languages() == []


def test_missing_language(qapp):
    png = ocr.to_png(ocr.preprocess(QImage(str(REFERENCE / "ubuntu-15-light.png"))))
    result = run_job(ocr.OcrJob(png, "zzz"))
    assert result["failed"][0] == ocr.MISSING_LANGUAGE


# --- 6.5 normalization ----------------------------------------------------------------------


def test_keep_line_breaks_on():
    assert ocr.normalize("Hello\nworld\n\f", keep_line_breaks=True) == "Hello\nworld"


def test_keep_line_breaks_off():
    assert ocr.normalize("Hello\nworld\n\f", keep_line_breaks=False) == "Hello world"


def test_paragraphs_and_blank_lines():
    raw = "  First line\nsecond line  \n\n\n\nNext paragraph\n\n"
    assert ocr.normalize(raw, keep_line_breaks=True) == "First line\nsecond line\n\nNext paragraph"
    assert ocr.normalize(raw, keep_line_breaks=False) == "First line second line\nNext paragraph"


@pytest.mark.parametrize("raw", ["", "   ", "\n\n\f", " \t\n "])
def test_whitespace_only_is_empty(raw):
    assert ocr.normalize(raw) == ""
    assert ocr.normalize(raw, keep_line_breaks=False) == ""


# --- 6.6 accuracy and speed ------------------------------------------------------------------


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def flat(text: str) -> str:
    return " ".join(text.split())


def test_reference_accuracy(qapp):
    errors = characters = 0
    misses = []
    for name, png, expected, scale in reference_pairs():
        got = flat(ocr.normalize(recognize(qapp, png, scale)["finished"]))
        distance = edit_distance(flat(expected), got)
        errors += distance
        characters += len(flat(expected))
        if distance:
            misses.append(f"{name}: {got!r}")
    accuracy = 1 - errors / characters
    assert accuracy >= 0.98, f"{accuracy:.2%}\n" + "\n".join(misses)


def test_large_region_is_fast(qapp):
    from PyQt6.QtCore import QRect, Qt
    from PyQt6.QtGui import QFont, QPainter

    image = solid(1000, 300, "white")
    painter = QPainter(image)
    font = QFont("Noto Sans")
    font.setPixelSize(15)
    painter.setFont(font)
    painter.setPen(QColor("#1e1e1e"))
    line = "Recognition of a large region must finish quickly so the overlay never lingers on screen."
    painter.drawText(QRect(8, 8, 984, 284), Qt.AlignmentFlag.AlignLeft, "\n".join([line] * 14))
    painter.end()

    started = time.perf_counter()
    result = run_job(ocr.OcrJob(ocr.to_png(ocr.preprocess(image, 1.0)), "eng"))
    seconds = time.perf_counter() - started
    assert "overlay never lingers" in result["finished"]
    assert seconds < 2.0, seconds
