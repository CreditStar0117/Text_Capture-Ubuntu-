import pytest

from text_capture import settings
from text_capture.settings import Settings


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def test_defaults(config_home):
    s = Settings()
    assert s.get(settings.LANGUAGE) == "eng"
    assert s.get(settings.KEEP_LINE_BREAKS) is True
    assert s.get(settings.NOTIFY) is True
    assert s.get(settings.AUTOSTART) is True
    assert s.get(settings.HOTKEY_REGISTERED) is False


def test_file_location(config_home):
    s = Settings()
    s.set(settings.LANGUAGE, "fra")
    assert s.path == config_home / "text-capture" / "text-capture.conf"
    assert s.path.is_file()


def test_values_survive_reload(config_home):
    s = Settings()
    s.set(settings.LANGUAGE, "fra")
    s.set(settings.NOTIFY, False)
    s.set(settings.KEEP_LINE_BREAKS, False)
    s.set(settings.HOTKEY_REGISTERED, True)
    del s

    reloaded = Settings()
    assert reloaded.get(settings.LANGUAGE) == "fra"
    assert reloaded.get(settings.NOTIFY) is False
    assert reloaded.get(settings.KEEP_LINE_BREAKS) is False
    assert reloaded.get(settings.HOTKEY_REGISTERED) is True
    assert reloaded.get(settings.AUTOSTART) is True


# --- 8.3 autostart --------------------------------------------------------------------------


def test_autostart_toggle_writes_and_removes_entry(config_home, monkeypatch):
    monkeypatch.setenv(settings.LAUNCHER_ENV, "/home/u/.local/bin/text-capture")
    path = settings.autostart_path()
    assert path == config_home / "autostart" / "io.github.CreditStar0117.TextCapture.desktop"

    settings.set_autostart(True)
    entry = path.read_text()
    assert "Exec=/home/u/.local/bin/text-capture --background\n" in entry
    assert "X-GNOME-Autostart-enabled=true" in entry

    settings.set_autostart(False)
    assert not path.exists()
    settings.set_autostart(False)  # already off: no error


def test_exec_uses_absolute_source_path_without_launcher(config_home, monkeypatch):
    monkeypatch.delenv(settings.LAUNCHER_ENV, raising=False)
    argv = settings.launcher_argv()
    assert argv[0] == "env" and argv[1].startswith("PYTHONPATH=/")
    assert argv[2].startswith("/") and argv[-2:] == ["-m", "text_capture"]


def test_shortcut_command_quotes_for_the_shell(monkeypatch):
    import shlex

    monkeypatch.setenv(settings.LAUNCHER_ENV, "/home/u/My Apps/text-capture")
    assert shlex.split(settings.shortcut_command()) == ["/home/u/My Apps/text-capture", "--capture"]


def test_desktop_exec_quoting():
    assert settings.desktop_exec(["/usr/bin/x", "--background"]) == "/usr/bin/x --background"
    assert settings.desktop_exec(["/home/u/My Apps/x"]) == '"/home/u/My Apps/x"'
    assert settings.desktop_exec(["/opt/$weird/x"]) == '"/opt/\\\\$weird/x"'
    assert settings.desktop_exec(["50%"]) == "50%%"
    assert settings.desktop_exec(["env", "PYTHONPATH=/a/b"]) == "env PYTHONPATH=/a/b"


def test_autostart_entry_passes_desktop_file_validate(config_home, monkeypatch):
    import shutil
    import subprocess

    if not shutil.which("desktop-file-validate"):
        pytest.skip("desktop-file-validate not installed")
    monkeypatch.setenv(settings.LAUNCHER_ENV, "/home/u/My Apps/text-capture")
    settings.set_autostart(True)
    proc = subprocess.run(["desktop-file-validate", str(settings.autostart_path())], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
