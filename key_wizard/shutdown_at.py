from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

MAX_SHUTDOWN_MINUTES = 7 * 24 * 60


@dataclass(frozen=True)
class ShutdownMoment:
    at: datetime
    delay_seconds: int
    when_text: str


def parse_shutdown_text(text: str, now: datetime) -> ShutdownMoment:
    """把用户输入解释成一次关机时刻。

    含有冒号时按当天钟点理解，这个钟点已过则安排到明天。
    纯数字按分钟倒计时理解。
    """
    raw = text.strip().replace("：", ":")
    if not raw:
        raise ValueError("请输入钟点或分钟数")
    if ":" in raw:
        return _parse_clock(raw, now)
    if raw.isdigit():
        return _parse_minutes(int(raw), now)
    raise ValueError("请输入 23:30 这样的钟点，或输入分钟数")


def _parse_clock(raw: str, now: datetime) -> ShutdownMoment:
    hour_text, separator, minute_text = raw.partition(":")
    if separator != ":" or not hour_text.isdigit() or not minute_text.isdigit() or len(minute_text) != 2:
        raise ValueError("请把钟点输完整，例如 23:30")
    hour = int(hour_text)
    minute = int(minute_text)
    if hour > 23 or minute > 59:
        raise ValueError("钟点必须在 00:00 到 23:59 之间")
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return _moment(target, now)


def _parse_minutes(minutes: int, now: datetime) -> ShutdownMoment:
    if minutes < 1:
        raise ValueError("分钟数至少为 1")
    if minutes > MAX_SHUTDOWN_MINUTES:
        raise ValueError("分钟数不能超过 10080，也就是 7 天")
    target = now + timedelta(minutes=minutes)
    return ShutdownMoment(target, minutes * 60, _when_text(target, now))


def _moment(target: datetime, now: datetime) -> ShutdownMoment:
    delay = math.ceil((target - now).total_seconds())
    if delay < 1:
        raise ValueError("关机时间太近")
    return ShutdownMoment(target, delay, _when_text(target, now))


def _when_text(target: datetime, now: datetime) -> str:
    if target.date() == now.date():
        day = "今天"
    elif target.date() == (now + timedelta(days=1)).date():
        day = "明天"
    else:
        day = f"{target.month}月{target.day}日"
    return f"{day} {target:%H:%M}"
