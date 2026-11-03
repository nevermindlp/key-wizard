from __future__ import annotations

import json
from pathlib import Path

from key_wizard.keys import normalize_hotkey
from key_wizard.models import AppConfig, ClickConfig, Hotkeys, MouseEvent


class ConfigError(ValueError):
    pass


def default_config() -> AppConfig:
    return AppConfig(
        click=ClickConfig("fixed", 200, 100, 300, 20),
        repeat=1,
        hotkeys=Hotkeys("f6", "f8", "f9", "f10", "esc"),
    )


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_click_fields(
    interval_mode: object,
    interval_ms: object,
    interval_min_ms: object,
    interval_max_ms: object,
    count: object,
) -> ClickConfig:
    if interval_mode not in ("fixed", "random"):
        raise ConfigError("间隔方式无效")
    for value in (interval_ms, interval_min_ms, interval_max_ms):
        if not _is_int(value) or not 10 <= int(value) <= 60000:
            raise ConfigError("间隔必须是 10 到 60000 的整数")
    if interval_mode == "random" and int(interval_min_ms) > int(interval_max_ms):
        raise ConfigError("随机间隔的最小值不能大于最大值")
    if not _is_int(count) or not 0 <= int(count) <= 100000:
        raise ConfigError("点击次数必须是 0 到 100000 的整数，0 表示无限")
    return ClickConfig(
        str(interval_mode),
        int(interval_ms),
        int(interval_min_ms),
        int(interval_max_ms),
        int(count),
    )


def validate_repeat(repeat: object) -> int:
    if not _is_int(repeat) or not 0 <= int(repeat) <= 10000:
        raise ConfigError("重复次数必须是 0 到 10000 的整数，0 表示无限")
    return int(repeat)


def validate_hotkeys(hotkeys: Hotkeys) -> Hotkeys:
    values = []
    for name in hotkeys.as_dict().values():
        normal = normalize_hotkey(name)
        if normal is None:
            raise ConfigError("不支持的快捷键")
        values.append(normal)
    if len(set(values)) != 5:
        raise ConfigError("快捷键不能重复")
    return Hotkeys(*values)


def config_from_dict(data: object) -> AppConfig:
    if not isinstance(data, dict):
        raise ConfigError("配置损坏")
    click = data.get("click")
    replay = data.get("replay")
    hotkeys = data.get("hotkeys")
    if not isinstance(click, dict) or not isinstance(replay, dict) or not isinstance(hotkeys, dict):
        raise ConfigError("配置损坏")
    click_config = validate_click_fields(
        click.get("interval_mode"),
        click.get("interval_ms"),
        click.get("interval_min_ms"),
        click.get("interval_max_ms"),
        click.get("count"),
    )
    repeat = validate_repeat(replay.get("repeat"))
    key_config = validate_hotkeys(
        Hotkeys(
            str(hotkeys.get("toggle_click", "")),
            str(hotkeys.get("start_record", "")),
            str(hotkeys.get("stop_record", "")),
            str(hotkeys.get("toggle_replay", "")),
            str(hotkeys.get("emergency_stop", "")),
        )
    )
    return AppConfig(click_config, repeat, key_config)


def config_to_dict(config: AppConfig) -> dict:
    return {
        "click": {
            "interval_mode": config.click.interval_mode,
            "interval_ms": config.click.interval_ms,
            "interval_min_ms": config.click.interval_min_ms,
            "interval_max_ms": config.click.interval_max_ms,
            "count": config.click.count,
        },
        "replay": {"repeat": config.repeat},
        "hotkeys": config.hotkeys.as_dict(),
    }


def save_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config_to_dict(config), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config(path: Path) -> tuple[AppConfig, str | None]:
    if not path.exists():
        return default_config(), None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return config_from_dict(data), None
    except (OSError, json.JSONDecodeError, ConfigError):
        return default_config(), "已恢复默认"


def _event_to_dict(event: MouseEvent) -> dict:
    data: dict = {"type": event.type, "x": event.x, "y": event.y, "dt_ms": event.dt_ms}
    if event.type == "click":
        data["button"] = event.button
        data["pressed"] = event.pressed
    return data


def _event_from_dict(data: object) -> MouseEvent:
    if not isinstance(data, dict):
        raise ConfigError("录像损坏")
    kind = data.get("type")
    x = data.get("x")
    y = data.get("y")
    dt = data.get("dt_ms")
    if kind not in ("move", "click") or not _is_int(x) or not _is_int(y) or not _is_int(dt) or int(dt) < 0:
        raise ConfigError("录像损坏")
    if kind == "move":
        return MouseEvent("move", int(x), int(y), int(dt))
    button = data.get("button")
    pressed = data.get("pressed")
    if button not in ("left", "right") or not isinstance(pressed, bool):
        raise ConfigError("录像损坏")
    return MouseEvent("click", int(x), int(y), int(dt), button, pressed)


def save_recording(path: Path, events: list[MouseEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"events": [_event_to_dict(event) for event in events]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_recording(path: Path) -> tuple[list[MouseEvent], str | None]:
    if not path.exists():
        return [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            raise ConfigError("录像损坏")
        return [_event_from_dict(item) for item in data["events"]], None
    except (OSError, json.JSONDecodeError, ConfigError):
        return [], None


def recording_duration_ms(events: list[MouseEvent]) -> int:
    return sum(event.dt_ms for event in events)
