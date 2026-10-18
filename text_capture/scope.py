"""Run the app instance under its stable app ID (design D4).

xdg-desktop-portal identifies an unsandboxed app by the systemd scope it runs in. GNOME
starts the app grid and autostart entries in `app-gnome-<desktop id>-<pid>.scope`, but a
start from a terminal or a shortcut command lands in some other scope. In that case the
instance re-executes itself once inside `app-<APP_DESKTOP_ID>-<pid>.scope`.
"""

import os
import re
import shutil
import sys

from . import APP_DESKTOP_ID

GUARD = "TEXT_CAPTURE_SCOPED"
_OWN_SCOPE = re.compile(rf"^app-(?:[^-]+-)?{re.escape(APP_DESKTOP_ID)}[-@.]")


def current_unit(cgroup_text: str | None = None) -> str:
    """The leaf systemd unit of this process, e.g. `app-gnome-code-1234.scope`."""
    if cgroup_text is None:
        try:
            with open("/proc/self/cgroup") as f:
                cgroup_text = f.read()
        except OSError:
            return ""
    for line in cgroup_text.splitlines():
        if line.startswith("0::"):
            return line.rsplit("/", 1)[-1]
    return ""


def in_own_scope(unit: str) -> bool:
    return bool(_OWN_SCOPE.match(unit))


def reexec_command(argv: list[str], env=None, unit: str | None = None, which=shutil.which) -> list[str] | None:
    """The command that restarts us in our own scope, or None if no restart is needed or possible."""
    env = os.environ if env is None else env
    if env.get(GUARD) or not which("systemd-run"):
        return None
    if in_own_scope(current_unit() if unit is None else unit):
        return None
    return [
        "systemd-run", "--user", "--scope", "--quiet", "--collect",
        f"--unit=app-{APP_DESKTOP_ID}-{os.getpid()}.scope",
        sys.executable, "-m", "text_capture", *argv,
    ]


def ensure_own_scope(argv: list[str]) -> None:
    """Replace this process with one running in our scope, if needed. Returns only if not."""
    command = reexec_command(argv)
    if command is None:
        return
    os.environ[GUARD] = "1"
    try:
        os.execvp(command[0], command)
    except OSError:
        pass  # keep running where we are; only portal permissions are affected
