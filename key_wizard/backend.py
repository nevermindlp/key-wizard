from __future__ import annotations

import time
from collections.abc import Callable

from key_wizard.keys import pynput_key_to_name


def dispatch_key(key: object, on_key: Callable[[str], None]) -> None:
    name = pynput_key_to_name(key)
    if name is not None:
        on_key(name)


class HeldKeys:
    """按住期间只交出一次按下，松开后才能再触发。"""

    def __init__(self) -> None:
        self._names: set[str] = set()

    def press(self, key: object, on_key: Callable[[str], None]) -> None:
        name = pynput_key_to_name(key)
        if name is None or name in self._names:
            return
        self._names.add(name)
        on_key(name)

    def release(self, key: object) -> None:
        name = pynput_key_to_name(key)
        if name is not None:
            self._names.discard(name)


class PynputBackend:
    """Windows 上使用 pynput。单元测试不要调用移动和点击。"""

    def __init__(self) -> None:
        self._mouse_controller = None
        self._mouse_listener = None
        self._key_listener = None

    def position(self) -> tuple[int, int]:
        point = self._mouse().position
        return int(point[0]), int(point[1])

    def move(self, x: int, y: int) -> None:
        self._mouse().position = (int(x), int(y))

    def press(self, button: str, x: int, y: int) -> None:
        controller = self._mouse()
        controller.position = (int(x), int(y))
        controller.press(self._button(button))

    def release(self, button: str, x: int, y: int) -> None:
        controller = self._mouse()
        controller.position = (int(x), int(y))
        controller.release(self._button(button))

    def now_ms(self) -> int:
        return int(time.monotonic() * 1000)

    def sleep_ms(self, ms: int, stop) -> bool:
        if ms <= 0:
            return not stop.is_set()
        return not stop.wait(ms / 1000)

    def start_mouse_listener(self, on_click: Callable[[int, int, str, bool], None]) -> None:
        from pynput import mouse

        def handle(x, y, button, pressed):
            if button == mouse.Button.left:
                name = "left"
            elif button == mouse.Button.right:
                name = "right"
            else:
                return
            on_click(int(x), int(y), name, bool(pressed))

        self.stop_mouse_listener()
        listener = mouse.Listener(on_click=handle)
        listener.start()
        self._mouse_listener = listener

    def stop_mouse_listener(self) -> None:
        listener = self._mouse_listener
        self._mouse_listener = None
        if listener is not None:
            listener.stop()

    def start_hotkey_listener(self, on_key: Callable[[str], None]) -> bool:
        try:
            from pynput import keyboard
        except Exception:
            return False
        self.stop_hotkey_listener()
        held = HeldKeys()

        def on_press(key):
            held.press(key, on_key)

        def on_release(key):
            held.release(key)

        try:
            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.start()
        except Exception:
            return False
        self._key_listener = listener
        return True

    def stop_hotkey_listener(self) -> None:
        listener = self._key_listener
        self._key_listener = None
        if listener is not None:
            listener.stop()

    def _mouse(self):
        if self._mouse_controller is None:
            from pynput.mouse import Controller

            self._mouse_controller = Controller()
        return self._mouse_controller

    def _button(self, name: str):
        from pynput.mouse import Button

        if name == "right":
            return Button.right
        return Button.left
