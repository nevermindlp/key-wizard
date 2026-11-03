from __future__ import annotations

_NUMPAD_VKS = set(range(0x60, 0x6A))
_ALLOWED = {"esc", *[f"f{i}" for i in range(1, 13)], *list("abcdefghijklmnopqrstuvwxyz0123456789")}


def normalize_hotkey(name: str | None) -> str | None:
    if not isinstance(name, str):
        return None
    text = name.strip().lower()
    if text in _ALLOWED:
        return text
    return None


def display_key(name: str) -> str:
    if name == "esc":
        return "Esc"
    return name.upper()


def pynput_key_to_name(key: object) -> str | None:
    vk = getattr(key, "vk", None)
    if isinstance(vk, int) and vk in _NUMPAD_VKS:
        return None
    enum_name = getattr(key, "name", None)
    if isinstance(enum_name, str):
        return normalize_hotkey(enum_name)
    char = getattr(key, "char", None)
    if isinstance(char, str):
        return normalize_hotkey(char)
    return None
