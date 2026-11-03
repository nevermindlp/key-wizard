import pytest

from key_wizard.config_store import (
    ConfigError,
    config_to_dict,
    default_config,
    load_config,
    load_recording,
    recording_duration_ms,
    save_config,
    save_recording,
    validate_click_fields,
    validate_hotkeys,
    validate_repeat,
)
from key_wizard.models import Hotkeys, MouseEvent


def test_default_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    original = default_config()
    save_config(path, original)
    loaded, warning = load_config(path)
    assert warning is None
    assert loaded == original
    assert config_to_dict(loaded)["hotkeys"]["toggle_click"] == "f6"
    assert config_to_dict(loaded)["click"]["interval_ms"] == 200
    assert config_to_dict(loaded)["replay"]["repeat"] == 1


def test_missing_config_is_default(tmp_path):
    loaded, warning = load_config(tmp_path / "missing.json")
    assert loaded == default_config()
    assert warning is None


def test_corrupt_config_restores_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{", encoding="utf-8")
    loaded, warning = load_config(path)
    assert loaded == default_config()
    assert warning == "已恢复默认"


def test_rejects_interval_bounds():
    with pytest.raises(ConfigError, match="间隔"):
        validate_click_fields("fixed", 9, 100, 300, 20)
    with pytest.raises(ConfigError, match="间隔"):
        validate_click_fields("fixed", 60001, 100, 300, 20)


def test_rejects_random_min_above_max():
    with pytest.raises(ConfigError, match="最小值"):
        validate_click_fields("random", 200, 300, 100, 20)


def test_rejects_count_and_repeat():
    with pytest.raises(ConfigError, match="点击次数"):
        validate_click_fields("fixed", 200, 100, 300, -1)
    with pytest.raises(ConfigError, match="点击次数"):
        validate_click_fields("fixed", 200, 100, 300, 100001)
    with pytest.raises(ConfigError, match="重复次数"):
        validate_repeat(10001)
    with pytest.raises(ConfigError, match="重复次数"):
        validate_repeat(-1)


def test_zero_count_and_repeat_mean_unlimited():
    click = validate_click_fields("fixed", 200, 100, 300, 0)
    assert click.count == 0
    assert validate_repeat(0) == 0


def test_rejects_duplicate_and_unknown_hotkeys():
    with pytest.raises(ConfigError, match="重复"):
        validate_hotkeys(Hotkeys("f6", "f6", "f9", "f10", "esc"))
    with pytest.raises(ConfigError, match="不支持"):
        validate_hotkeys(Hotkeys("ctrl+a", "f8", "f9", "f10", "esc"))


def test_recording_roundtrip_and_duration(tmp_path):
    events = [
        MouseEvent("move", 1, 2, 0),
        MouseEvent("click", 3, 4, 16, "left", True),
        MouseEvent("click", 3, 4, 40, "left", False),
    ]
    path = tmp_path / "recording.json"
    save_recording(path, events)
    loaded, warning = load_recording(path)
    assert warning is None
    assert loaded == events
    assert recording_duration_ms(events) == 56


def test_corrupt_recording_is_empty(tmp_path):
    path = tmp_path / "recording.json"
    path.write_text("nope", encoding="utf-8")
    loaded, warning = load_recording(path)
    assert loaded == []
    assert warning is None


def test_empty_recording_file(tmp_path):
    path = tmp_path / "recording.json"
    save_recording(path, [])
    loaded, warning = load_recording(path)
    assert loaded == []
    assert warning is None
