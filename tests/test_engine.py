from dataclasses import replace

from key_wizard.config_store import default_config
from key_wizard.engine import Engine, next_interval_ms
from key_wizard.models import RunState
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
    assert [item for item in backend.actions if item[0] == "press"] == [
        ("press", "left", 1, 1),
        ("press", "left", 2, 2),
        ("press", "left", 3, 3),
    ]
    assert [item for item in backend.actions if item[0] == "sleep"] == [("sleep", 200), ("sleep", 200)]
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
    engine = Engine(backend, rng=lambda a, b: 123)
    engine.start_click(_click_config(count=2, mode="random", low=100, high=300))
    engine.join()
    assert ("sleep", 123) in backend.actions
