from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunState(str, Enum):
    IDLE = "idle"
    CLICKING = "clicking"
    RECORDING = "recording"
    PLAYING = "playing"


@dataclass(frozen=True)
class ClickConfig:
    interval_mode: str
    interval_ms: int
    interval_min_ms: int
    interval_max_ms: int
    count: int


@dataclass(frozen=True)
class Hotkeys:
    toggle_click: str
    start_record: str
    stop_record: str
    toggle_replay: str
    emergency_stop: str

    def as_dict(self) -> dict[str, str]:
        return {
            "toggle_click": self.toggle_click,
            "start_record": self.start_record,
            "stop_record": self.stop_record,
            "toggle_replay": self.toggle_replay,
            "emergency_stop": self.emergency_stop,
        }


@dataclass(frozen=True)
class AppConfig:
    click: ClickConfig
    repeat: int
    hotkeys: Hotkeys


@dataclass(frozen=True)
class MouseEvent:
    type: str
    x: int
    y: int
    dt_ms: int
    button: str | None = None
    pressed: bool | None = None


@dataclass(frozen=True)
class Progress:
    state: RunState
    message: str = ""
    clicks_done: int = 0
    click_count: int = 0
    event_count: int = 0
    elapsed_ms: int = 0
    repeat_index: int = 0
    repeat_total: int = 0
