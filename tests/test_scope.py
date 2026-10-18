import pytest

from text_capture import scope

CGROUP_VSCODE = "0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-gnome-code-12345.scope\n"


def test_current_unit():
    assert scope.current_unit(CGROUP_VSCODE) == "app-gnome-code-12345.scope"
    assert scope.current_unit("") == ""


@pytest.mark.parametrize(
    "unit, own",
    [
        ("app-gnome-io.github.CreditStar0117.TextCapture-4242.scope", True),  # app grid / autostart
        ("app-io.github.CreditStar0117.TextCapture-4242.scope", True),  # our own systemd-run
        ("app-io.github.CreditStar0117.TextCapture@autostart.service", True),  # systemd xdg-autostart
        ("app-gnome-code-12345.scope", False),  # started from a VS Code terminal
        ("app-gnome-text\\x2dcapture-99.scope", False),  # started by a shortcut command
        ("app-gnome-io.github.CreditStar0117.TextCaptureX-1.scope", False),
        ("", False),
    ],
)
def test_in_own_scope(unit, own):
    assert scope.in_own_scope(unit) is own


def test_reexec_when_in_a_foreign_scope():
    command = scope.reexec_command(["--capture"], env={}, unit="app-gnome-code-1.scope", which=lambda name: "/usr/bin/" + name)
    assert command[:5] == ["systemd-run", "--user", "--scope", "--quiet", "--collect"]
    assert command[5].startswith("--unit=app-io.github.CreditStar0117.TextCapture-")
    assert command[-3:] == ["-m", "text_capture", "--capture"]


def test_no_reexec_when_already_in_own_scope():
    unit = "app-gnome-io.github.CreditStar0117.TextCapture-7.scope"
    assert scope.reexec_command([], env={}, unit=unit, which=lambda name: "/usr/bin/" + name) is None


def test_guard_prevents_loops():
    assert scope.reexec_command([], env={scope.GUARD: "1"}, unit="app-gnome-code-1.scope", which=lambda n: "/x") is None


def test_no_reexec_without_systemd_run():
    assert scope.reexec_command([], env={}, unit="app-gnome-code-1.scope", which=lambda name: None) is None
