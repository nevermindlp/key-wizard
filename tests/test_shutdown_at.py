from datetime import datetime

import pytest

from key_wizard.power import cancel_shutdown_command, shutdown_command
from key_wizard.shutdown_at import parse_shutdown_text


NOW = datetime(2026, 11, 16, 15, 22, 40)


def test_minutes_become_a_clock_time():
    moment = parse_shutdown_text("30", NOW)
    assert moment.at == datetime(2026, 11, 16, 15, 52, 40)
    assert moment.delay_seconds == 1800
    assert moment.when_text == "今天 15:52"


def test_clock_time_later_today():
    moment = parse_shutdown_text("23:30", NOW)
    assert moment.at == datetime(2026, 11, 16, 23, 30)
    assert moment.delay_seconds == 8 * 3600 + 7 * 60 + 20
    assert moment.when_text == "今天 23:30"


def test_clock_time_already_passed_moves_to_tomorrow():
    moment = parse_shutdown_text("08:05", NOW)
    assert moment.at == datetime(2026, 11, 17, 8, 5)
    assert moment.when_text == "明天 08:05"


def test_exact_current_minute_moves_to_tomorrow():
    now = datetime(2026, 11, 16, 23, 30)
    moment = parse_shutdown_text("23:30", now)
    assert moment.at == datetime(2026, 11, 17, 23, 30)
    assert moment.when_text == "明天 23:30"


def test_fullwidth_colon_is_a_clock_time():
    moment = parse_shutdown_text(" 23：30 ", NOW)
    assert moment.at == datetime(2026, 11, 16, 23, 30)


def test_countdown_can_cross_midnight_and_several_days():
    moment = parse_shutdown_text("120", datetime(2026, 11, 16, 23, 10))
    assert moment.at == datetime(2026, 11, 17, 1, 10)
    assert moment.when_text == "明天 01:10"
    later = parse_shutdown_text("1500", NOW)
    assert later.at == datetime(2026, 11, 17, 16, 22, 40)
    assert later.when_text == "明天 16:22"
    week = parse_shutdown_text("10080", NOW)
    assert week.when_text == "11月23日 15:22"


@pytest.mark.parametrize(
    "text",
    ["", "0", "10081", "23:60", "24:00", "23:", "23:3", "abc", "30分"],
)
def test_reject_unusable_shutdown_text(text: str):
    with pytest.raises(ValueError):
        parse_shutdown_text(text, NOW)


def test_windows_shutdown_commands():
    assert shutdown_command(1800) == ["shutdown", "/s", "/t", "1800", "/c", "按键精灵定时关机"]
    assert cancel_shutdown_command() == ["shutdown", "/a"]
