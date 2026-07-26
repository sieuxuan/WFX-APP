import pytest

from wfx_panel import hotkey


def test_default_is_valid_and_normalized():
    assert hotkey.is_valid(hotkey.DEFAULT)
    assert hotkey.normalize(hotkey.DEFAULT) == "ctrl+shift+x"


def test_normalize_orders_modifiers_and_lowercases():
    assert hotkey.normalize("Shift + CTRL + X") == "ctrl+shift+x"
    assert hotkey.normalize("alt+ctrl+F5") == "ctrl+alt+f5"


def test_normalize_accepts_modifier_aliases():
    assert hotkey.normalize("control+shift+k") == "ctrl+shift+k"
    assert hotkey.normalize("win+shift+k") == "shift+windows+k"


@pytest.mark.parametrize(
    "unsafe",
    [
        "ctrl+backspace",
        "alt+delete",
        "ctrl+shift+enter",
        "ctrl+tab",
        "ctrl+space",
        "alt+escape",
    ],
)
def test_rejects_unsafe_base_keys(unsafe):
    assert hotkey.is_valid(unsafe) is False
    with pytest.raises(ValueError):
        hotkey.normalize(unsafe)


def test_rejects_bare_key_without_modifier():
    assert hotkey.is_valid("x") is False


def test_allows_function_keys_without_modifier():
    assert hotkey.normalize("F5") == "f5"
    assert hotkey.is_valid("f12") is True


def test_rejects_f1_and_modifier_only():
    assert hotkey.is_valid("f1") is False
    assert hotkey.is_valid("ctrl+shift") is False


def test_rejects_two_base_keys():
    assert hotkey.is_valid("ctrl+x+y") is False


def test_format_label():
    assert hotkey.format_label("ctrl+shift+x") == "Ctrl + Shift + X"
    assert hotkey.format_label("shift+windows+k") == "Shift + Win + K"
    assert hotkey.format_label("f9") == "F9"


def test_from_event_builds_spec():
    assert hotkey.from_event(
        {
            "ctrl": True,
            "alt": False,
            "shift": True,
            "meta": False,
            "key": "X",
            "code": "KeyX",
        }
    ) == "ctrl+shift+x"
    assert hotkey.from_event(
        {
            "ctrl": True,
            "alt": True,
            "shift": False,
            "meta": False,
            "key": "5",
            "code": "Digit5",
        }
    ) == "ctrl+alt+5"
    assert hotkey.from_event(
        {
            "ctrl": False,
            "alt": False,
            "shift": False,
            "meta": False,
            "key": "F7",
            "code": "F7",
        }
    ) == "f7"


def test_from_event_rejects_unsafe():
    with pytest.raises(ValueError):
        hotkey.from_event(
            {
                "ctrl": True,
                "alt": False,
                "shift": False,
                "meta": False,
                "key": "Backspace",
                "code": "Backspace",
            }
        )
