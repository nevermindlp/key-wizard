from key_wizard.backend import HeldKeys, dispatch_key


def test_dispatch_known_key():
    seen = []
    dispatch_key(type("Key", (), {"name": "f6"})(), lambda name: seen.append(name))
    assert seen == ["f6"]


def test_dispatch_ignores_space_and_numpad():
    seen = []
    dispatch_key(type("Key", (), {"name": "space"})(), lambda name: seen.append(name))
    dispatch_key(type("Pad", (), {"vk": 0x61, "char": "1"})(), lambda name: seen.append(name))
    assert seen == []


def test_held_key_emits_once_until_release():
    seen = []
    held = HeldKeys()
    f6 = type("Key", (), {"name": "f6"})()
    held.press(f6, seen.append)
    held.press(f6, seen.append)
    assert seen == ["f6"]
    held.release(f6)
    held.press(f6, seen.append)
    assert seen == ["f6", "f6"]
    held.press(type("Key", (), {"name": "space"})(), seen.append)
    held.press(type("Pad", (), {"vk": 0x61, "char": "1"})(), seen.append)
    assert seen == ["f6", "f6"]
