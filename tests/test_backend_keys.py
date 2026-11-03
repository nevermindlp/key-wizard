from key_wizard.backend import dispatch_key


def test_dispatch_known_key():
    seen = []
    dispatch_key(type("Key", (), {"name": "f6"})(), lambda name: seen.append(name))
    assert seen == ["f6"]


def test_dispatch_ignores_space_and_numpad():
    seen = []
    dispatch_key(type("Key", (), {"name": "space"})(), lambda name: seen.append(name))
    dispatch_key(type("Pad", (), {"vk": 0x61, "char": "1"})(), lambda name: seen.append(name))
    assert seen == []
