import copy
from pathlib import Path

import pytest

from text_capture import gnome_hotkey as hk

FIXTURES = Path(__file__).parent / "data" / "gsettings"
CUSTOM0 = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
CUSTOM1 = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom1/"


class FakeGSettings:
    """In-memory gsettings: values are kept as GVariant text, like the real CLI prints them.

    Schemas are the ones recorded from the dev machine (stock Ubuntu 24.04 + Ubuntu Dock).
    The two custom shortcuts mirror the dev machine too, except where a test changes them.
    """

    def __init__(self):
        self.schemas = {}
        for file in FIXTURES.glob("*.txt"):
            keys = {}
            for line in file.read_text().splitlines():
                schema, key, value = line.split(" ", 2)
                keys[key] = value
            self.schemas[file.stem] = keys
        self.custom = {
            CUSTOM0: {"name": "'Flameshot Capture'", "command": "'/usr/bin/flameshot gui'", "binding": "'<Control>1'"},
            CUSTOM1: {"name": "'NormCap OCR'", "command": "'flatpak run normcap'", "binding": "'<Control>q'"},
        }

    def free_default(self):
        """Move the second custom shortcut off the default key."""
        self.custom[CUSTOM1]["binding"] = "'<Control>2'"
        return self

    def __call__(self, args):
        if args == ["list-schemas"]:
            return "".join(f"{schema}\n" for schema in self.schemas)
        op, schema, *rest = args
        if ":" in schema:
            store = self.custom.setdefault(schema.split(":", 1)[1], {})
        elif schema in self.schemas:
            store = self.schemas[schema]
        else:
            raise hk.GSettingsError(f"No such schema “{schema}”")
        if op == "list-recursively":
            return "".join(f"{schema} {k} {v}\n" for k, v in store.items())
        if op == "get":
            return store.get(rest[0], "''") + "\n"
        if op == "set":
            store[rest[0]] = rest[1]
            return ""
        if op == "reset":
            store.pop(rest[0], None)
            return ""
        raise AssertionError(op)

    def snapshot(self):
        others = {p: v for p, v in self.custom.items() if p != hk.OUR_PATH}
        schemas = copy.deepcopy(self.schemas)
        schemas[hk.MEDIA_KEYS].pop(hk.CUSTOM_LIST_KEY)
        return copy.deepcopy(others), schemas


@pytest.fixture
def gs():
    return FakeGSettings()


# --- 3.2 conflict detection -------------------------------------------------


@pytest.mark.parametrize(
    "a, b",
    [
        ("<Super>q", "<super>Q"),
        ("<Shift><Super>q", "<Super><Shift>q"),
        ("<Primary>c", "<Control>c"),
        ("<Ctrl><Alt>t", "<Alt><Control>t"),
        ("<Mod4>q", "<Super>q"),
    ],
)
def test_normalize_equivalent(a, b):
    assert hk.normalize(a) == hk.normalize(b)


@pytest.mark.parametrize("value", ["", "disabled", "<Super>", "<Super"])
def test_normalize_ignores_non_bindings(value):
    assert hk.normalize(value) is None


def test_parse_value():
    assert hk.parse_value("@as []") == []
    assert hk.parse_value("['<Super>l']") == ["<Super>l"]
    assert hk.parse_value("'<Control>1'") == "<Control>1"
    assert hk.parse_value("uint32 6") is None
    assert hk.parse_value("true") is None


def test_default_binding_is_ctrl_q():
    assert hk.normalize(hk.DEFAULT_BINDING) == "<control>q"


def test_recorded_fixtures(gs):
    taken = hk.taken_bindings(gs)
    assert hk.normalize("<Super>l") in taken  # screensaver, media-keys schema
    assert hk.normalize("<Alt>F7") in taken  # begin-move, wm schema
    assert hk.normalize("<Super>q") in taken  # Ubuntu Dock, an extension schema
    assert hk.normalize("<Control>1") in taken  # existing custom shortcut
    assert hk.normalize("<Control>q") in taken  # NormCap on the dev machine
    assert hk.normalize(hk.DEFAULT_BINDING) not in hk.taken_bindings(gs.free_default())


def test_default_taken_by_gnome_shortcut(gs):
    gs.free_default()
    gs.schemas["org.gnome.desktop.wm.keybindings"]["close"] = "['<Alt>F4', '<Primary>Q']"
    assert hk.normalize(hk.DEFAULT_BINDING) in hk.taken_bindings(gs)


def test_default_taken_by_extension(gs):
    gs.free_default()
    gs.schemas["org.gnome.shell.extensions.dash-to-dock"]["shortcut"] = "['<Ctrl>q']"
    assert hk.normalize(hk.DEFAULT_BINDING) in hk.taken_bindings(gs)


def test_missing_schema_is_skipped(gs):
    del gs.schemas["org.gnome.mutter.wayland.keybindings"]
    assert hk.normalize("<Super>l") in hk.taken_bindings(gs)


# --- 3.3 registration ---------------------------------------------------------


def test_register_free_binding(gs):
    gs.free_default()
    before = gs.snapshot()
    paths_before = hk.custom_paths(gs)

    result = hk.register("/home/u/.local/bin/text-capture --capture", gs)

    assert result == hk.RegisterResult("<Control>q", created=True, conflict=False)
    assert hk.custom_paths(gs) == paths_before + [hk.OUR_PATH]
    assert hk.get_custom(hk.OUR_PATH, "name", gs) == "Text Capture"
    assert hk.get_custom(hk.OUR_PATH, "command", gs) == "/home/u/.local/bin/text-capture --capture"
    assert hk.get_custom(hk.OUR_PATH, "binding", gs) == "<Control>q"
    assert gs.snapshot() == before  # every other entry and schema is byte-identical


def test_register_with_conflict_creates_unbound_entry(gs):
    # The dev machine: NormCap already holds Ctrl+Q.
    before = gs.snapshot()
    result = hk.register("text-capture --capture", gs)
    assert result == hk.RegisterResult("", created=True, conflict=True)
    assert hk.OUR_PATH in hk.custom_paths(gs)
    assert hk.get_custom(hk.OUR_PATH, "binding", gs) == ""
    assert gs.snapshot() == before


def test_register_is_idempotent(gs):
    for _ in range(10):
        hk.register("text-capture --capture", gs)
    assert hk.custom_paths(gs).count(hk.OUR_PATH) == 1
    assert len(hk.custom_paths(gs)) == 3


def test_user_chosen_binding_is_preserved(gs):
    hk.register("text-capture --capture", gs)
    hk.set_custom(hk.OUR_PATH, "binding", "<Control><Alt>t", gs)

    result = hk.register("/new/path/text-capture --capture", gs)

    assert result == hk.RegisterResult("<Control><Alt>t", created=False, conflict=False)
    assert hk.get_custom(hk.OUR_PATH, "binding", gs) == "<Control><Alt>t"
    assert hk.get_custom(hk.OUR_PATH, "command", gs) == "/new/path/text-capture --capture"


def test_command_with_quotes_round_trips(gs):
    command = "env PYTHONPATH='/home/u/it'\\'s' python3 -m text_capture --capture"
    hk.register(command, gs)
    assert hk.get_custom(hk.OUR_PATH, "command", gs) == command


# --- 3.4 removal --------------------------------------------------------------


def test_unregister_removes_only_ours(gs):
    before = gs.snapshot()
    paths_before = hk.custom_paths(gs)
    hk.register("text-capture --capture", gs)

    assert hk.unregister(gs) is True

    assert hk.custom_paths(gs) == paths_before
    assert gs.custom.get(hk.OUR_PATH, {}) == {}
    assert gs.snapshot() == before


def test_unregister_when_not_registered(gs):
    before = gs.snapshot()
    assert hk.unregister(gs) is False
    assert gs.snapshot() == before


def test_unregister_last_entry_writes_empty_list(gs):
    gs.schemas[hk.MEDIA_KEYS][hk.CUSTOM_LIST_KEY] = "@as []"
    hk.register("text-capture --capture", gs)
    hk.unregister(gs)
    assert gs.schemas[hk.MEDIA_KEYS][hk.CUSTOM_LIST_KEY] == "@as []"
