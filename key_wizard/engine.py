from __future__ import annotations

import random
import threading
from collections.abc import Callable

from key_wizard.models import AppConfig, ClickConfig, Progress, RunState


def next_interval_ms(click: ClickConfig, rng: Callable[[int, int], int]) -> int:
    if click.interval_mode == "fixed":
        return click.interval_ms
    return rng(click.interval_min_ms, click.interval_max_ms)


class Engine:
    def __init__(self, backend, rng: Callable[[int, int], int] | None = None) -> None:
        self.backend = backend
        self.rng = rng or random.randint
        self.state = RunState.IDLE
        self.recording: list = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._listeners: list[Callable[[Progress], None]] = []

    def add_progress_listener(self, callback: Callable[[Progress], None]) -> None:
        self._listeners.append(callback)

    def start_click(self, snapshot: AppConfig) -> bool:
        return self._start(RunState.CLICKING, self._run_click, snapshot)

    def start_record(self) -> bool:
        return self._start(RunState.RECORDING, self._run_record)

    def start_replay(self, snapshot: AppConfig) -> bool:
        with self._lock:
            if self.state != RunState.IDLE:
                return False
            if not self.recording:
                self._emit(Progress(state=RunState.IDLE, message="没有录像"))
                return False
            events = list(self.recording)
        return self._start(RunState.PLAYING, self._run_replay, snapshot, events)

    def stop_record(self) -> list | None:
        with self._lock:
            recording = self.state == RunState.RECORDING
            thread = self._thread
            if recording:
                self._stop.set()
        if not recording:
            return None
        if thread is not None and thread is not threading.current_thread():
            thread.join(2.0)
        return list(self.recording)

    def stop(self) -> None:
        with self._lock:
            self._stop.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(2.0)

    def join(self, timeout: float = 2.0) -> None:
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def _start(self, state: RunState, target, *args) -> bool:
        with self._lock:
            if self.state != RunState.IDLE:
                return False
            self.state = state
            self._stop.clear()
            self._thread = threading.Thread(target=self._guard, args=(target, args), daemon=True)
            self._thread.start()
            return True

    def _guard(self, target, args) -> None:
        try:
            target(*args)
        finally:
            with self._lock:
                self.state = RunState.IDLE
            self._emit(Progress(state=RunState.IDLE, message="空闲"))

    def _emit(self, progress: Progress) -> None:
        for callback in list(self._listeners):
            callback(progress)

    def _run_click(self, snapshot: AppConfig) -> None:
        done = 0
        total = snapshot.click.count
        while done < total and not self._stop.is_set():
            x, y = self.backend.position()
            self.backend.press("left", int(x), int(y))
            self.backend.release("left", int(x), int(y))
            done += 1
            self._emit(Progress(state=RunState.CLICKING, clicks_done=done, click_count=total))
            if done >= total or self._stop.is_set():
                break
            wait = next_interval_ms(snapshot.click, self.rng)
            if not self.backend.sleep_ms(wait, self._stop):
                break

    def _run_record(self) -> None:
        while not self._stop.is_set():
            if not self.backend.sleep_ms(16, self._stop):
                break

    def _run_replay(self, snapshot: AppConfig, events: list) -> None:
        while not self._stop.is_set():
            if not self.backend.sleep_ms(16, self._stop):
                break
