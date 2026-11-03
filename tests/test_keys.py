import pytest

from key_wizard.keys import display_key, normalize_hotkey, pynput_key_to_name


def test_normalize_accepts_spec_keys():
    assert normalize_hotkey("F6") == "f6"
    assert normalize_hotkey("Esc") == "esc"
    assert normalize_hotkey("a") == "a"
    assert normalize_hotkey("5") == "5"


def test_normalize_rejects_combo_empty_and_numpad_name():
    assert normalize_hotkey("ctrl+a") is None
    assert normalize_hotkey("") is None
    assert normalize_hotkey("num1") is None
    assert normalize_hotkey(None) is None


def test_display_key():
    assert display_key("f6") == "F6"
    assert display_key("esc") == "Esc"
    assert display_key("a") == "A"


def test_pynput_function_escape_and_letter():
    pynput = pytest.importorskip("pynput")
    key = pynput.keyboard.Key
    code = pynput.keyboard.KeyCode
    assert pynput_key_to_name(key.f6) == "f6"
    assert pynput_key_to_name(key.esc) == "esc"
    assert pynput_key_to_name(code.from_char("A")) == "a"
    assert pynput_key_to_name(code.from_char("5")) == "5"
    assert pynput_key_to_name(key.space) is None


def test_pynput_rejects_numpad_virtual_key():
    pynput = pytest.importorskip("pynput")
    code = pynput.keyboard.KeyCode
    numpad_one = code.from_vk(0x61)
    assert pynput_key_to_name(numpad_one) is None
