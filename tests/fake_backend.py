from __future__ import annotations


class FakeBackend:
    def __init__(self) -> None:
        self.time_ms = 0
        self.pos = (0, 0)
        self.positions: list[tuple[int, int]] = []
        self.actions: list[tuple] = []
        self.stop_on_sleep = False
        self.block = False
        self.sleep_limit: int | None = None
        self.click_on_sleep: tuple[int, tuple] | None = None
        self._sleeps = 0
        self._on_click = None

    def position(self) -> tuple[int, int]:
        if self.positions:
            return self.positions.pop(0)
        return self.pos

    def move(self, x: int, y: int) -> None:
        self.pos = (int(x), int(y))
        self.actions.append(("move", int(x), int(y)))

    def press(self, button: str, x: int, y: int) -> None:
        self.pos = (int(x), int(y))
        self.actions.append(("press", button, int(x), int(y)))

    def release(self, button: str, x: int, y: int) -> None:
        self.actions.append(("release", button, int(x), int(y)))

    def now_ms(self) -> int:
        return self.time_ms

    def sleep_ms(self, ms: int, stop) -> bool:
        if stop.is_set():
            return False
        if self.block:
            stop.wait(timeout=2)
            return False
        if self.stop_on_sleep:
            stop.set()
            return False
        self._sleeps += 1
        if self.sleep_limit is not None and self._sleeps > self.sleep_limit:
            stop.set()
            return False
        self.time_ms += ms
        self.actions.append(("sleep", ms))
        if self.click_on_sleep and self._sleeps == self.click_on_sleep[0] and self._on_click:
            x, y, button, pressed = self.click_on_sleep[1]
            self._on_click(x, y, button, pressed)
        return not stop.is_set()

    def start_mouse_listener(self, on_click) -> None:
        self._on_click = on_click

    def stop_mouse_listener(self) -> None:
        self._on_click = None

    def start_hotkey_listener(self, on_key) -> bool:
        self.on_key = on_key
        return True

    def stop_hotkey_listener(self) -> None:
        self.on_key = None
