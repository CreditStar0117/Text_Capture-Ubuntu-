import pytest

from text_capture import output


class FakeClipboard:
    def __init__(self, owns=True):
        self.owns = owns
        self.text = None

    def setText(self, text, mode):
        self.text = text

    def ownsClipboard(self):
        return self.owns


class FakeNotifier(output.Notifier):
    def __init__(self, notify_results=True):
        self.sent = []
        super().__init__(notify_results=lambda: notify_results, send=self.sent.append)


# --- 7.1 clipboard -------------------------------------------------------------------------


def test_text_round_trips_through_qt_clipboard(qapp):
    from PyQt6.QtGui import QGuiApplication

    output.copy_text("naïve café\nline two", fallback=lambda text: True)
    assert QGuiApplication.clipboard().text() == "naïve café\nline two"


def test_owned_clipboard_needs_no_fallback():
    calls = []
    assert output.copy_text("hi", FakeClipboard(owns=True), fallback=calls.append) is True
    assert calls == []


def test_fallback_used_when_clipboard_not_owned():
    calls = []
    assert output.copy_text("hi", FakeClipboard(owns=False), fallback=lambda t: calls.append(t) or True) is True
    assert calls == ["hi"]


@pytest.mark.parametrize("fallback", [None, lambda text: False])
def test_copy_fails_without_working_fallback(fallback):
    assert output.copy_text("hi", FakeClipboard(owns=False), fallback=fallback) is False


def test_fallback_only_on_wayland(monkeypatch):
    monkeypatch.setattr(output.shutil, "which", lambda name: "/usr/bin/wl-copy")
    assert output.clipboard_fallback("wayland") is output.wl_copy
    assert output.clipboard_fallback("x11") is None
    monkeypatch.setattr(output.shutil, "which", lambda name: None)
    assert output.clipboard_fallback("wayland") is None


# --- 7.2 notifications ---------------------------------------------------------------------


def test_preview_truncates_to_100_characters():
    assert output.preview("short\ntext") == "short text"
    long = "word " * 40
    assert output.preview(long) == ("word " * 20).rstrip() + "…"
    assert len(output.preview("x" * 250)) == 101


def test_notify_args_types_and_escaping():
    args = output.notify_args("It's done", "From: Maria <maria@example.com> & co", output.URGENCY_LOW, 7)
    method = args.index("org.freedesktop.Notifications.Notify")
    app, replaces, icon, summary, body, actions, hints, timeout = args[method + 1 :]
    assert replaces == "uint32 7"
    assert summary == "'It\\'s done'"
    assert body == "'From: Maria &lt;maria@example.com&gt; &amp; co'"
    assert actions == "@as []"
    assert "'transient': <true>" in hints and "'urgency': <byte 0>" in hints
    assert timeout.startswith("int32 ")


def test_notify_args_parse_as_gvariant():
    GLib = pytest.importorskip("gi.repository.GLib")
    args = output.notify_args("It's \"done\"", "a\nb\tc \\ d", output.URGENCY_NORMAL, 3)
    values = args[args.index("org.freedesktop.Notifications.Notify") + 1 :]
    types = ["s", "u", "s", "s", "s", "as", "a{sv}", "i"]
    parsed = [GLib.Variant.parse(GLib.VariantType(t), v).unpack() for t, v in zip(types, values)]
    assert parsed[3] == "It's \"done\""
    assert parsed[4] == "a\nb\tc \\ d"
    assert parsed[6] == {"transient": True, "urgency": 1, "desktop-entry": "io.github.CreditStar0117.TextCapture"}


def test_result_notification_on():
    n = FakeNotifier(notify_results=True)
    n.copied("Invoice 2026-104")
    assert len(n.sent) == 1
    assert "'Invoice 2026-104'" in n.sent[0]
    assert "'urgency': <byte 0>" in n.sent[0][-2]


def test_result_notification_off():
    n = FakeNotifier(notify_results=False)
    n.copied("Invoice 2026-104")
    assert n.sent == []


def test_errors_shown_even_when_notifications_off():
    n = FakeNotifier(notify_results=False)
    n.message("Capture failed", "details")
    assert len(n.sent) == 1
    assert "'urgency': <byte 1>" in n.sent[0][-2]


def test_notifications_replace_the_previous_one():
    n = FakeNotifier()
    n.last_id = 41
    n.message("No text found")
    assert "uint32 41" in n.sent[0]


# --- 7.3 empty results ----------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\n\t\n"])
def test_empty_result_never_touches_clipboard(text):
    n = FakeNotifier()
    copies = []
    assert output.deliver(text, n, copy=lambda t: copies.append(t) or True) == output.EMPTY
    assert copies == []
    assert len(n.sent) == 1 and "'No text found'" in n.sent[0]


def test_successful_delivery():
    n = FakeNotifier()
    copies = []
    assert output.deliver("Hello", n, copy=lambda t: copies.append(t) or True) == output.COPIED
    assert copies == ["Hello"]
    assert "'Text copied'" in n.sent[0]


def test_failed_copy_is_reported_even_when_notifications_off():
    n = FakeNotifier(notify_results=False)
    assert output.deliver("Hello", n, copy=lambda t: False) == output.FAILED
    assert len(n.sent) == 1 and "'Could not copy the text'" in n.sent[0]
