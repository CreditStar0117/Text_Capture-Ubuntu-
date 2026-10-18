"""Register, check conflicts for and remove the GNOME custom shortcut (design D2).

GNOME's settings daemon owns the key in both X11 and Wayland sessions; we only add
one custom-keybinding entry that runs `text-capture --capture`. Every function takes
a `run` callable (gsettings arguments -> stdout) so tests can substitute a fake.
"""

import ast
import subprocess
from dataclasses import dataclass

from . import APP_NAME

MEDIA_KEYS = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = f"{MEDIA_KEYS}.custom-keybinding"
CUSTOM_LIST_KEY = "custom-keybindings"
OUR_PATH = f"/{MEDIA_KEYS.replace('.', '/')}/custom-keybindings/text-capture/"
DEFAULT_BINDING = "<Control>q"

SCANNED_SCHEMAS = (
    "org.gnome.desktop.wm.keybindings",
    "org.gnome.shell.keybindings",
    "org.gnome.mutter.keybindings",
    "org.gnome.mutter.wayland.keybindings",
    MEDIA_KEYS,
)
# Shell extensions grab keys too: Ubuntu Dock binds <Super>q on a stock Ubuntu 24.04.
EXTENSION_SCHEMA_PREFIX = "org.gnome.shell.extensions."

MODIFIER_ALIASES = {"ctrl": "control", "primary": "control", "mod1": "alt", "mod4": "super"}


class GSettingsError(Exception):
    pass


def run_gsettings(args: list[str]) -> str:
    proc = subprocess.run(["gsettings", *args], capture_output=True, text=True, timeout=5)
    if proc.returncode != 0:
        raise GSettingsError(proc.stderr.strip() or f"gsettings {' '.join(args)} failed")
    return proc.stdout


def parse_value(text: str) -> str | list[str] | None:
    """Parse the GVariant text of a string or string-array value; anything else gives None."""
    text = text.strip().removeprefix("@as ")
    if not text or text[0] not in "['\"":
        return None
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    if isinstance(value, str) or (isinstance(value, list) and all(isinstance(v, str) for v in value)):
        return value
    return None


def gvariant_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def gvariant_string_list(values: list[str]) -> str:
    return "[" + ", ".join(map(gvariant_string, values)) + "]" if values else "@as []"


def normalize(accel: str) -> str | None:
    """Canonical form of a GTK accelerator: aliases resolved, modifiers sorted, all lower case."""
    rest = accel.strip()
    if not rest or rest.lower() == "disabled":
        return None
    modifiers = set()
    while rest.startswith("<"):
        end = rest.find(">")
        if end < 0:
            return None
        name = rest[1:end].lower()
        modifiers.add(MODIFIER_ALIASES.get(name, name))
        rest = rest[end + 1 :]
    if not rest:
        return None
    return "".join(f"<{m}>" for m in sorted(modifiers)) + rest.lower()


def custom_paths(run=run_gsettings) -> list[str]:
    value = parse_value(run(["get", MEDIA_KEYS, CUSTOM_LIST_KEY]))
    return value if isinstance(value, list) else []


def get_custom(path: str, key: str, run=run_gsettings) -> str:
    value = parse_value(run(["get", f"{CUSTOM_SCHEMA}:{path}", key]))
    return value if isinstance(value, str) else ""


def set_custom(path: str, key: str, value: str, run=run_gsettings) -> None:
    run(["set", f"{CUSTOM_SCHEMA}:{path}", key, gvariant_string(value)])


def taken_bindings(run=run_gsettings, exclude_path: str = OUR_PATH) -> set[str]:
    """Normalized accelerators used by GNOME's own shortcuts and by other custom shortcuts."""
    taken = set()
    extensions = [s for s in run(["list-schemas"]).split() if s.startswith(EXTENSION_SCHEMA_PREFIX)]
    for schema in (*SCANNED_SCHEMAS, *sorted(extensions)):
        try:
            listing = run(["list-recursively", schema])
        except GSettingsError:
            continue  # schema not installed on this system
        for line in listing.splitlines():
            parts = line.split(" ", 2)
            if len(parts) < 3 or parts[1] == CUSTOM_LIST_KEY:
                continue
            value = parse_value(parts[2])
            values = [value] if isinstance(value, str) else value or []
            taken.update(filter(None, map(normalize, values)))
    for path in custom_paths(run):
        if path != exclude_path and (accel := normalize(get_custom(path, "binding", run))):
            taken.add(accel)
    return taken


@dataclass
class RegisterResult:
    binding: str  # "" when the entry exists but has no key bound
    created: bool
    conflict: bool


def register(command: str, run=run_gsettings, binding: str = DEFAULT_BINDING) -> RegisterResult:
    """Add our entry if it is missing; never touch other entries or a binding the user chose."""
    paths = custom_paths(run)
    if OUR_PATH in paths:
        set_custom(OUR_PATH, "command", command, run)
        return RegisterResult(get_custom(OUR_PATH, "binding", run), created=False, conflict=False)

    conflict = normalize(binding) in taken_bindings(run)
    bound = "" if conflict else binding
    set_custom(OUR_PATH, "name", APP_NAME, run)
    set_custom(OUR_PATH, "command", command, run)
    set_custom(OUR_PATH, "binding", bound, run)
    run(["set", MEDIA_KEYS, CUSTOM_LIST_KEY, gvariant_string_list(paths + [OUR_PATH])])
    return RegisterResult(bound, created=True, conflict=conflict)


def unregister(run=run_gsettings) -> bool:
    """Remove our entry and its keys; return whether it was listed."""
    paths = custom_paths(run)
    listed = OUR_PATH in paths
    if listed:
        run(["set", MEDIA_KEYS, CUSTOM_LIST_KEY, gvariant_string_list([p for p in paths if p != OUR_PATH])])
    for key in ("name", "command", "binding"):
        run(["reset", f"{CUSTOM_SCHEMA}:{OUR_PATH}", key])
    return listed
