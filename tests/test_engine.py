from dataclasses import replace

from key_wizard.config_store import default_config
from key_wizard.engine import Engine, next_interval_ms
from key_wizard.models import MouseEvent, RunState
from tests.fake_backend import FakeBackend


def _click_config(count=3, mode="fixed", interval=200, low=100, high=300):
    config = default_config()
    click = replace(
        config.click,
        interval_mode=mode,
        interval_ms=interval,
        interval_min_ms=low,
        interval_max_ms=high,
        count=count,
    )
    return replace(config, click=click)


def test_fixed_interval_ignores_rng():
    click = _click_config().click
    assert next_interval_ms(click, lambda _a, _b: 1) == 200


def test_random_interval_passes_inclusive_bounds():
    click = _click_config(mode="random", low=10, high=12).click
    calls = []

    def rng(low, high):
        calls.append((low, high))
        return low

    assert next_interval_ms(click, rng) == 10
    assert calls == [(10, 12)]
    assert next_interval_ms(click, lambda _low, high: high) == 12


def test_click_follows_cursor_and_stops_after_count():
    backend = FakeBackend()
    backend.positions = [(1, 1), (2, 2), (3, 3)]
    engine = Engine(backend)
    assert engine.start_click(_click_config(count=3, interval=200))
    engine.join()
    assert backend.actions == [
        ("press", "left", 1, 1),
        ("release", "left", 1, 1),
        ("sleep", 200),
        ("press", "left", 2, 2),
        ("release", "left", 2, 2),
        ("sleep", 200),
        ("press", "left", 3, 3),
        ("release", "left", 3, 3),
    ]
    assert engine.state == RunState.IDLE


def test_stop_during_wait_does_not_click_again():
    backend = FakeBackend()
    backend.stop_on_sleep = True
    backend.positions = [(5, 5), (9, 9)]
    engine = Engine(backend)
    engine.start_click(_click_config(count=10))
    engine.join()
    assert [item for item in backend.actions if item[0] == "press"] == [("press", "left", 5, 5)]
    assert engine.state == RunState.IDLE


def test_random_click_sleeps_rng_value():
    backend = FakeBackend()
    backend.positions = [(4, 4), (5, 5)]
    calls = []

    def rng(low, high):
        calls.append((low, high))
        return 123

    engine = Engine(backend, rng=rng)
    engine.start_click(_click_config(count=2, mode="random", low=100, high=300))
    engine.join()
    assert calls == [(100, 300)]
    assert backend.actions == [
        ("press", "left", 4, 4),
        ("release", "left", 4, 4),
        ("sleep", 123),
        ("press", "left", 5, 5),
        ("release", "left", 5, 5),
    ]
    assert engine.state == RunState.IDLE


def test_other_starts_are_ignored_while_clicking():
    backend = FakeBackend()
    backend.block = True
    engine = Engine(backend)
    assert engine.start_click(_click_config(count=5))
    assert engine.start_record() is False
    assert engine.start_replay(_click_config()) is False
    assert engine.stop_record() is None
    assert engine.state == RunState.CLICKING
    engine.stop()
    engine.join()
    assert engine.state == RunState.IDLE


def test_record_drops_duplicate_points_and_keeps_click_timing():
    backend = FakeBackend()
    backend.sleep_limit = 3
    backend.positions = [(0, 0), (0, 0), (1, 0)]
    backend.click_on_sleep = (2, (5, 5, "right", True))
    engine = Engine(backend)
    assert engine.start_record()
    engine.join()
    assert engine.recording == [
        MouseEvent("move", 0, 0, 0),
        MouseEvent("click", 5, 5, 16, "right", True),
        MouseEvent("move", 1, 0, 16),
    ]
    assert engine.state == RunState.IDLE


def test_replay_repeats_events_in_order():
    backend = FakeBackend()
    engine = Engine(backend)
    engine.recording = [
        MouseEvent("move", 10, 20, 0),
        MouseEvent("click", 10, 20, 30, "left", True),
        MouseEvent("click", 10, 20, 10, "left", False),
    ]
    assert engine.start_replay(replace(_click_config(), repeat=2))
    engine.join()
    assert backend.actions == [
        ("move", 10, 20),
        ("sleep", 30),
        ("press", "left", 10, 20),
        ("sleep", 10),
        ("release", "left", 10, 20),
        ("move", 10, 20),
        ("sleep", 30),
        ("press", "left", 10, 20),
        ("sleep", 10),
        ("release", "left", 10, 20),
    ]
    assert engine.state == RunState.IDLE


def test_replay_stop_releases_pressed_button():
    backend = FakeBackend()
    backend.stop_on_sleep = True
    engine = Engine(backend)
    engine.recording = [
        MouseEvent("click", 1, 2, 0, "left", True),
        MouseEvent("move", 9, 9, 500),
    ]
    engine.start_replay(replace(_click_config(), repeat=3))
    engine.join()
    assert ("press", "left", 1, 2) in backend.actions
    assert ("move", 9, 9) not in backend.actions
    assert ("release", "left", 1, 2) in backend.actions


def test_zero_count_clicks_until_stopped():
    backend = FakeBackend()
    backend.sleep_limit = 2
    backend.positions = [(1, 1), (2, 2), (3, 3), (4, 4)]
    engine = Engine(backend)
    assert engine.start_click(_click_config(count=0, interval=40))
    engine.join()
    presses = [item for item in backend.actions if item[0] == "press"]
    assert presses == [
        ("press", "left", 1, 1),
        ("press", "left", 2, 2),
        ("press", "left", 3, 3),
    ]
    assert engine.state == RunState.IDLE


def test_zero_repeat_replays_until_stopped():
    backend = FakeBackend()
    backend.sleep_limit = 2
    engine = Engine(backend)
    engine.recording = [MouseEvent("move", 7, 8, 15)]
    assert engine.start_replay(replace(_click_config(), repeat=0))
    engine.join()
    assert backend.actions == [
        ("sleep", 15),
        ("move", 7, 8),
        ("sleep", 15),
        ("move", 7, 8),
    ]
    assert engine.state == RunState.IDLE


def test_replay_without_recording_does_not_start():
    backend = FakeBackend()
    engine = Engine(backend)
    notes = []
    engine.add_progress_listener(lambda progress: notes.append(progress.message))
    assert engine.start_replay(_click_config()) is False
    assert engine.state == RunState.IDLE
    assert "没有录像" in notes
    assert backend.actions == []
