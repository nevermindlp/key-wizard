# 按键精灵 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做一个 Windows 上的按键精灵：窗口里修改点击间隔、次数、回放次数和五个快捷键，并立刻生效；按当前鼠标位置循环左键点击；录制鼠标轨迹和左右键，再按次数重放。

**Architecture:** `config_store` 负责 JSON 校验与读写，`engine` 在后台线程里做连点、录制和回放，并通过可替换的 `InputBackend` 碰鼠标。`controller` 决定配置何时写入、快捷键冲突和按钮可用状态。`ui` 只渲染 tkinter，并把热键与进度放进队列。全局监听把每一次按键投递给控制器，因此「设键」能收到任意新键。

**Tech Stack:** Python 3.11+、tkinter、pynput、pytest。配置在 `data/config.json`，录像在 `data/recording.json`。

**Spec:** `docs/superpowers/specs/2026-11-03-key-wizard-design.md`

---

## File structure

- `requirements.txt` — `pynput` 与 `pytest`
- `.gitignore` — 缓存、虚拟环境和运行时 `data/`
- `key_wizard/__init__.py` — 包标记
- `key_wizard/models.py` — 配置、事件、状态、进度
- `key_wizard/keys.py` — 快捷键规范化、显示名、pynput 键名转换
- `key_wizard/config_store.py` — 默认值、校验、配置与录像读写
- `key_wizard/backend.py` — `InputBackend` 协议与 `PynputBackend`
- `key_wizard/engine.py` — 状态机、连点、录制、回放
- `key_wizard/controller.py` — 编辑生效时机、设键、按钮与状态文案
- `key_wizard/ui.py` — tkinter 窗口
- `main.py` — 创建 `data/`、加载文件、启动界面
- `tests/fake_backend.py` — 不移动真实鼠标的后端
- `tests/test_keys.py`
- `tests/test_config_store.py`
- `tests/test_engine.py`
- `tests/test_controller.py`
- `tests/test_backend_keys.py`
- `tests/test_ui_smoke.py`

工作目录始终是仓库根目录。当前目录还不是 git 仓库，Task 1 会执行 `git init`。每个任务结束时提交。不要修改 git config。

---

### Task 1: 数据模型和快捷键名称

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `key_wizard/__init__.py`
- Create: `key_wizard/models.py`
- Create: `key_wizard/keys.py`
- Test: `tests/test_keys.py`

- [ ] **Step 1: 初始化仓库并安装测试依赖**

```bash
git init
python3 -m pip install -r requirements.txt
```

先写下这两个文件，再执行上面的命令。

`.gitignore`:

```gitignore
__pycache__/
.pytest_cache/
*.pyc
.venv/
data/
```

`requirements.txt`:

```text
pynput>=1.7.7
pytest>=8.0
```

`key_wizard/__init__.py`:

```python
"""按键精灵。"""
```

- [ ] **Step 2: 写会失败的快捷键测试**

`tests/test_keys.py`:

```python
import pytest

from key_wizard.keys import display_key, normalize_hotkey, pynput_key_to_name


def test_normalize_accepts_spec_keys():
    assert normalize_hotkey("F6") == "f6"
    assert normalize_hotkey("Esc") == "esc"
    assert normalize_hotkey("a") == "a"
    assert normalize_hotkey("5") == "5"


def test_normalize_rejects_combo_empty_and_numpad_name():
    assert normalize_hotkey("ctrl+a") is None
    assert normalize_hotkey("") is None
    assert normalize_hotkey("num1") is None
    assert normalize_hotkey(None) is None


def test_display_key():
    assert display_key("f6") == "F6"
    assert display_key("esc") == "Esc"
    assert display_key("a") == "A"


def test_pynput_function_escape_and_letter():
    pynput = pytest.importorskip("pynput")
    key = pynput.keyboard.Key
    code = pynput.keyboard.KeyCode
    assert pynput_key_to_name(key.f6) == "f6"
    assert pynput_key_to_name(key.esc) == "esc"
    assert pynput_key_to_name(code.from_char("A")) == "a"
    assert pynput_key_to_name(code.from_char("5")) == "5"
    assert pynput_key_to_name(key.space) is None


def test_pynput_rejects_numpad_virtual_key():
    pynput = pytest.importorskip("pynput")
    code = pynput.keyboard.KeyCode
    numpad_one = code.from_vk(0x61)
    assert pynput_key_to_name(numpad_one) is None
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_keys.py -v`

Expected: FAIL，`key_wizard.keys` 无法导入。

- [ ] **Step 4: 写模型和键名转换**

`key_wizard/models.py`:

```python
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
```

`key_wizard/keys.py`:

```python
from __future__ import annotations

_NUMPAD_VKS = set(range(0x60, 0x6A))
_ALLOWED = {"esc", *[f"f{i}" for i in range(1, 13)], *list("abcdefghijklmnopqrstuvwxyz0123456789")}


def normalize_hotkey(name: str | None) -> str | None:
    if not isinstance(name, str):
        return None
    text = name.strip().lower()
    if text in _ALLOWED:
        return text
    return None


def display_key(name: str) -> str:
    if name == "esc":
        return "Esc"
    return name.upper()


def pynput_key_to_name(key: object) -> str | None:
    vk = getattr(key, "vk", None)
    if isinstance(vk, int) and vk in _NUMPAD_VKS:
        return None
    enum_name = getattr(key, "name", None)
    if isinstance(enum_name, str):
        return normalize_hotkey(enum_name)
    char = getattr(key, "char", None)
    if isinstance(char, str):
        return normalize_hotkey(char)
    return None
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_keys.py -v`

Expected: PASS。若本机没有 pynput，前三个测试仍须通过，后两个为 SKIP。安装 `requirements.txt` 后，五个测试都要 PASS。

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements.txt key_wizard/__init__.py key_wizard/models.py key_wizard/keys.py tests/test_keys.py
git commit -m "feat: add config models and hotkey names"
```

---

### Task 2: 配置与录像读写

**Files:**
- Create: `key_wizard/config_store.py`
- Test: `tests/test_config_store.py`

- [ ] **Step 1: 写会失败的配置测试**

`tests/test_config_store.py`:

```python
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
        validate_click_fields("fixed", 200, 100, 300, 0)
    with pytest.raises(ConfigError, match="重复次数"):
        validate_repeat(10001)


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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_config_store.py -v`

Expected: FAIL，`key_wizard.config_store` 无法导入。

- [ ] **Step 3: 实现配置仓库**

`key_wizard/config_store.py`:

```python
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
    if not _is_int(count) or not 1 <= int(count) <= 100000:
        raise ConfigError("点击次数必须是 1 到 100000 的整数")
    return ClickConfig(
        str(interval_mode),
        int(interval_ms),
        int(interval_min_ms),
        int(interval_max_ms),
        int(count),
    )


def validate_repeat(repeat: object) -> int:
    if not _is_int(repeat) or not 1 <= int(repeat) <= 10000:
        raise ConfigError("重复次数必须是 1 到 10000 的整数")
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_config_store.py tests/test_keys.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add key_wizard/config_store.py tests/test_config_store.py
git commit -m "feat: validate and store click config and recordings"
```

---

### Task 3: 连点引擎

**Files:**
- Create: `tests/fake_backend.py`
- Create: `key_wizard/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: 写假后端和会失败的连点测试**

`tests/fake_backend.py`:

```python
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
```

`tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_engine.py -v`

Expected: FAIL，`key_wizard.engine` 无法导入。

- [ ] **Step 3: 实现连点**

`key_wizard/engine.py` 在本任务先只包含间隔与连点。后续任务会替换整个文件。

```python
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

    def stop(self) -> None:
        self._stop.set()
        self.join()

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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_engine.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/fake_backend.py tests/test_engine.py key_wizard/engine.py
git commit -m "feat: click at the live cursor position"
```

---

### Task 4: 状态机互斥

**Files:**
- Modify: `key_wizard/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: 追加失败测试**

把下面的测试加到 `tests/test_engine.py` 末尾。此时 `start_record`、`start_replay`、`stop_record` 还不存在，测试应失败。

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_engine.py::test_other_starts_are_ignored_while_clicking -v`

Expected: FAIL，`Engine` 没有 `start_record`。

- [ ] **Step 3: 补上拒绝非法开始的方法**

在 `Engine` 中增加下面三个方法。它们只负责互斥；真正的录制和回放在后面的任务里替换 `_run_record` 与 `_run_replay`。

```python
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
    if not recording:
        return None
    self._stop.set()
    self.join()
    return list(self.recording)

def _run_record(self) -> None:
    while not self._stop.is_set():
        if not self.backend.sleep_ms(16, self._stop):
            break

def _run_replay(self, snapshot: AppConfig, events: list) -> None:
    while not self._stop.is_set():
        if not self.backend.sleep_ms(16, self._stop):
            break
```

`start_click` 已经通过 `_start` 在非空闲时返回 `False`。不要在持有 `self._lock` 时调用 `join`。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_engine.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add key_wizard/engine.py tests/test_engine.py
git commit -m "feat: reject overlapping click record and replay"
```

---

### Task 5: 录制轨迹和点击

**Files:**
- Modify: `key_wizard/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: 追加失败测试**

```python
from key_wizard.models import MouseEvent


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
```

时间线：三次成功的 16 毫秒采样后，第四次睡眠因 `sleep_limit` 停止。第一次采样记下 `(0, 0)` 且 `dt_ms == 0`。第二次睡眠里立刻记右键，`dt_ms == 16`，随后坐标没变所以不记移动。第三次采样坐标变成 `(1, 0)`，`dt_ms == 16`。

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_engine.py::test_record_drops_duplicate_points_and_keeps_click_timing -v`

Expected: FAIL，录像为空列表或事件不匹配。

- [ ] **Step 3: 用真正的录制循环替换 `_run_record`**

```python
def _run_record(self) -> None:
    events: list[MouseEvent] = []
    last_move: tuple[int, int] | None = None
    last_ms: int | None = None

    def append(kind: str, x: int, y: int, button: str | None = None, pressed: bool | None = None) -> None:
        nonlocal last_ms
        with self._lock:
            now = int(self.backend.now_ms())
            dt = 0 if last_ms is None else max(0, now - last_ms)
            last_ms = now
            event = MouseEvent(kind, int(x), int(y), dt, button, pressed)
            events.append(event)
            self.recording = list(events)
            elapsed = sum(item.dt_ms for item in events)
            count = len(events)
        self._emit(Progress(state=RunState.RECORDING, event_count=count, elapsed_ms=elapsed))

    def on_click(x: int, y: int, button: str, pressed: bool) -> None:
        if self._stop.is_set():
            return
        if button not in ("left", "right"):
            return
        append("click", x, y, button, pressed)

    self.backend.start_mouse_listener(on_click)
    try:
        while not self._stop.is_set():
            if not self.backend.sleep_ms(self.SAMPLE_MS, self._stop):
                break
            x, y = self.backend.position()
            point = (int(x), int(y))
            if point == last_move:
                continue
            last_move = point
            append("move", point[0], point[1])
    finally:
        self.backend.stop_mouse_listener()
        with self._lock:
            self.recording = list(events)
```

在类体内增加 `SAMPLE_MS = 16`。从 `key_wizard.models` 导入 `MouseEvent`。`last_move` 只和上一个已写入的移动点比较，点击不改变它。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_engine.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add key_wizard/engine.py tests/test_engine.py
git commit -m "feat: record mouse moves and button presses"
```

---

### Task 6: 回放

**Files:**
- Modify: `key_wizard/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: 追加失败测试**

```python
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


def test_replay_without_recording_does_not_start():
    backend = FakeBackend()
    engine = Engine(backend)
    notes = []
    engine.add_progress_listener(lambda progress: notes.append(progress.message))
    assert engine.start_replay(_click_config()) is False
    assert engine.state == RunState.IDLE
    assert "没有录像" in notes
    assert backend.actions == []
```

`tests/test_engine.py` 顶部已有 `from dataclasses import replace`。本测试再从 `key_wizard.models` 导入 `MouseEvent`。若 Task 5 已经导入，保持这一行即可：`from key_wizard.models import MouseEvent, RunState`。

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_engine.py::test_replay_repeats_events_in_order tests/test_engine.py::test_replay_stop_releases_pressed_button tests/test_engine.py::test_replay_without_recording_does_not_start -v`

Expected: FAIL。现有 `_run_replay` 只睡眠，不会移动鼠标。

- [ ] **Step 3: 替换 `_run_replay` 并在停止时松开按键**

在 `__init__` 增加 `self._pressed: set[str] = set()`。`_start` 在启动线程前执行 `self._pressed.clear()`。

```python
def _run_replay(self, snapshot: AppConfig, events: list[MouseEvent]) -> None:
    try:
        for index in range(snapshot.repeat):
            if self._stop.is_set():
                break
            self._emit(
                Progress(
                    state=RunState.PLAYING,
                    repeat_index=index + 1,
                    repeat_total=snapshot.repeat,
                )
            )
            for event in events:
                if self._stop.is_set():
                    break
                if event.dt_ms > 0 and not self.backend.sleep_ms(event.dt_ms, self._stop):
                    break
                if self._stop.is_set():
                    break
                if event.type == "move":
                    self.backend.move(event.x, event.y)
                elif event.type == "click" and event.button in ("left", "right") and isinstance(event.pressed, bool):
                    if event.pressed:
                        self.backend.press(event.button, event.x, event.y)
                        self._pressed.add(event.button)
                    else:
                        self.backend.release(event.button, event.x, event.y)
                        self._pressed.discard(event.button)
    finally:
        self._release_stuck()


def _release_stuck(self) -> None:
    x, y = self.backend.position()
    for button in list(self._pressed):
        self.backend.release(button, int(x), int(y))
    self._pressed.clear()
```

`dt_ms == 0` 的事件不等待。中断发生在睡眠返回 `False` 之后，该事件不再执行。`press` 会把假后端的坐标改成按下位置，所以补发的松开落在该点。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_engine.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add key_wizard/engine.py tests/test_engine.py
git commit -m "feat: replay recorded mouse events"
```

---

### Task 7: 控制器

控制器持有「正在编辑的配置」和「当前动作开始时的配置」。空闲时失焦或设键成功就写入；执行中只把新值留在界面，回到空闲再写入。快捷键命令始终看开始时的那一份。

**Files:**
- Create: `key_wizard/controller.py`
- Test: `tests/test_controller.py`

- [ ] **Step 1: 写会失败的控制器测试**

`tests/test_controller.py`:

```python
from key_wizard.config_store import default_config
from key_wizard.controller import Controller
from key_wizard.models import MouseEvent, Progress, RunState


class FakeEngine:
    def __init__(self) -> None:
        self.state = RunState.IDLE
        self.recording: list[MouseEvent] = []
        self.calls: list[tuple] = []

    def start_click(self, snapshot) -> bool:
        if self.state != RunState.IDLE:
            return False
        self.state = RunState.CLICKING
        self.calls.append(("click", snapshot))
        return True

    def start_record(self) -> bool:
        if self.state != RunState.IDLE:
            return False
        self.state = RunState.RECORDING
        self.calls.append(("record",))
        return True

    def stop_record(self):
        if self.state != RunState.RECORDING:
            return None
        self.recording = [MouseEvent("move", 8, 9, 0), MouseEvent("move", 10, 9, 16)]
        self.state = RunState.IDLE
        self.calls.append(("stop_record",))
        return list(self.recording)

    def start_replay(self, snapshot) -> bool:
        if self.state != RunState.IDLE or not self.recording:
            return False
        self.state = RunState.PLAYING
        self.calls.append(("replay", snapshot))
        return True

    def stop(self) -> None:
        self.state = RunState.IDLE
        self.calls.append(("stop",))


def _setup(rebind_ok=True):
    saved = {}
    rebinds = []

    def save_config(config):
        saved["config"] = config

    def save_recording(events):
        saved["recording"] = events

    def rebind(hotkeys):
        rebinds.append(hotkeys)
        return rebind_ok

    engine = FakeEngine()
    controller = Controller(default_config(), engine, save_config, save_recording, rebind)
    return controller, engine, saved, rebinds


def test_idle_count_saves_without_rebinding_hotkeys():
    controller, _engine, saved, rebinds = _setup()
    controller.commit_count("15")
    assert saved["config"].click.count == 15
    assert rebinds == []
    assert controller.view().count == "15"


def test_invalid_count_restores_previous_text():
    controller, _engine, saved, _rebinds = _setup()
    controller.commit_count("0")
    assert "config" not in saved
    assert controller.view().count == "20"
    assert "点击次数" in controller.view().status


def test_running_edit_waits_until_idle():
    controller, engine, saved, _rebinds = _setup()
    engine.state = RunState.CLICKING
    controller.on_progress(Progress(state=RunState.CLICKING, clicks_done=1, click_count=20))
    controller.commit_interval_ms("500")
    assert "config" not in saved
    assert "本次结束后生效" in controller.view().status
    engine.state = RunState.IDLE
    controller.on_progress(Progress(state=RunState.IDLE, message="空闲"))
    assert saved["config"].click.interval_ms == 500


def test_capture_rejects_duplicate_and_accepts_new_key():
    controller, _engine, saved, rebinds = _setup()
    controller.begin_capture("toggle_click")
    controller.handle_key("f8")
    assert controller.applied.hotkeys.toggle_click == "f6"
    assert "重复" in controller.view().status
    controller.begin_capture("toggle_click")
    controller.handle_key("A")
    assert saved["config"].hotkeys.toggle_click == "a"
    assert rebinds[-1].toggle_click == "a"
    assert controller.view().status == "已改成 A"
    assert controller.view().hotkey_values["toggle_click"] == "a"


def test_capture_while_running_keeps_old_binding_until_idle():
    controller, engine, saved, rebinds = _setup()
    engine.state = RunState.CLICKING
    controller.on_progress(Progress(state=RunState.CLICKING, clicks_done=1, click_count=20))
    controller.begin_capture("emergency_stop")
    controller.handle_key("q")
    assert "config" not in saved
    assert rebinds == []
    assert controller.view().hotkey_values["emergency_stop"] == "q"
    controller.handle_key("esc")
    assert engine.calls[-1][0] == "stop"
    engine.state = RunState.IDLE
    controller.on_progress(Progress(state=RunState.IDLE, message="空闲"))
    assert saved["config"].hotkeys.emergency_stop == "q"


def test_buttons_follow_state():
    controller, engine, _saved, _rebinds = _setup()
    engine.state = RunState.RECORDING
    controller.on_progress(Progress(state=RunState.RECORDING, event_count=2, elapsed_ms=16))
    view = controller.view()
    assert view.start_record_enabled is False
    assert view.stop_record_enabled is True
    assert view.click_enabled is False
    assert view.replay_enabled is False
    assert "2 个事件" in view.status


def test_random_mode_toggles_fields():
    controller, _engine, _saved, _rebinds = _setup()
    controller.commit_mode("random")
    view = controller.view()
    assert view.fixed_enabled is False
    assert view.random_enabled is True
    controller.commit_mode("fixed")
    assert controller.view().fixed_enabled is True
    assert controller.view().random_enabled is False


def test_replay_without_events_sets_status():
    controller, engine, _saved, _rebinds = _setup()
    controller.toggle_replay()
    assert engine.calls == []
    assert controller.view().status == "没有录像"


def test_shutdown_saves_recording():
    controller, engine, saved, _rebinds = _setup()
    engine.state = RunState.RECORDING
    controller.shutdown()
    assert saved["recording"][0] == MouseEvent("move", 8, 9, 0)
    assert controller.view().summary == "2 个事件，16 毫秒"


def test_hotkey_listener_failure_sets_status():
    controller, _engine, saved, _rebinds = _setup(rebind_ok=False)
    controller.begin_capture("toggle_replay")
    controller.handle_key("b")
    assert saved["config"].hotkeys.toggle_replay == "b"
    assert controller.view().status == "热键监听失败"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_controller.py -v`

Expected: FAIL，`key_wizard.controller` 无法导入。

- [ ] **Step 3: 实现控制器**

`key_wizard/controller.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from key_wizard.config_store import ConfigError, recording_duration_ms, validate_click_fields, validate_repeat
from key_wizard.keys import display_key, normalize_hotkey
from key_wizard.models import AppConfig, Hotkeys, MouseEvent, Progress, RunState


@dataclass(frozen=True)
class ViewState:
    status: str
    interval_mode: str
    interval_ms: str
    interval_min_ms: str
    interval_max_ms: str
    count: str
    repeat: str
    hotkey_values: dict[str, str]
    hotkey_labels: dict[str, str]
    fixed_enabled: bool
    random_enabled: bool
    click_enabled: bool
    start_record_enabled: bool
    stop_record_enabled: bool
    replay_enabled: bool
    click_label: str
    replay_label: str
    summary: str
    capturing: str | None


class Controller:
    def __init__(
        self,
        config: AppConfig,
        engine,
        save_config: Callable[[AppConfig], None],
        save_recording: Callable[[list[MouseEvent]], None],
        rebind: Callable[[Hotkeys], bool],
        on_shutdown: Callable[[], None] | None = None,
    ) -> None:
        self.edited = config
        self.applied = config
        self.engine = engine
        self._save_config = save_config
        self._save_recording = save_recording
        self._rebind = rebind
        self._on_shutdown = on_shutdown
        self.status = "空闲"
        self.capturing: str | None = None
        self._dirty = False
        self._last_progress: Progress | None = None

    def view(self) -> ViewState:
        click = self.edited.click
        state = self.engine.state
        labels = {name: display_key(value) for name, value in self.edited.hotkeys.as_dict().items()}
        events = list(self.engine.recording)
        if events:
            summary = f"{len(events)} 个事件，{recording_duration_ms(events)} 毫秒"
        else:
            summary = "尚未录制"
        return ViewState(
            status=self._status_text(),
            interval_mode=click.interval_mode,
            interval_ms=str(click.interval_ms),
            interval_min_ms=str(click.interval_min_ms),
            interval_max_ms=str(click.interval_max_ms),
            count=str(click.count),
            repeat=str(self.edited.repeat),
            hotkey_values=self.edited.hotkeys.as_dict(),
            hotkey_labels=labels,
            fixed_enabled=click.interval_mode == "fixed",
            random_enabled=click.interval_mode == "random",
            click_enabled=state in (RunState.IDLE, RunState.CLICKING),
            start_record_enabled=state == RunState.IDLE,
            stop_record_enabled=state == RunState.RECORDING,
            replay_enabled=state in (RunState.IDLE, RunState.PLAYING),
            click_label="停止连点" if state == RunState.CLICKING else "开始连点",
            replay_label="停止回放" if state == RunState.PLAYING else "开始回放",
            summary=summary,
            capturing=self.capturing,
        )

    def commit_mode(self, mode: str) -> None:
        if mode not in ("fixed", "random"):
            self.status = "间隔方式无效"
            return
        self.edited = replace(self.edited, click=replace(self.edited.click, interval_mode=mode))
        self.status = "空闲"
        self._publish()

    def commit_interval_ms(self, text: str) -> None:
        self._commit_click(text, "interval_ms")

    def commit_interval_min_ms(self, text: str) -> None:
        self._commit_click(text, "interval_min_ms")

    def commit_interval_max_ms(self, text: str) -> None:
        self._commit_click(text, "interval_max_ms")

    def commit_count(self, text: str) -> None:
        self._commit_click(text, "count")

    def commit_repeat(self, text: str) -> None:
        try:
            repeat = validate_repeat(int(text))
        except (ValueError, ConfigError) as exc:
            self.status = str(exc) if isinstance(exc, ConfigError) else "重复次数必须是 1 到 10000 的整数"
            return
        self.edited = replace(self.edited, repeat=repeat)
        self.status = "空闲"
        self._publish()

    def begin_capture(self, field: str) -> None:
        self.capturing = field
        self.status = "请按下新的快捷键"

    def handle_key(self, raw: str) -> None:
        name = normalize_hotkey(raw)
        if self.capturing:
            self._finish_capture(name)
            return
        if name is None:
            return
        hotkeys = self.applied.hotkeys
        if name == hotkeys.emergency_stop:
            self.emergency_stop()
        elif name == hotkeys.toggle_click:
            self.toggle_click()
        elif name == hotkeys.start_record:
            self.start_record()
        elif name == hotkeys.stop_record:
            self.stop_record()
        elif name == hotkeys.toggle_replay:
            self.toggle_replay()

    def toggle_click(self) -> None:
        if self.engine.state == RunState.CLICKING:
            self.engine.stop()
            return
        if self.engine.state != RunState.IDLE:
            return
        self.engine.start_click(self.applied)

    def start_record(self) -> None:
        if self.engine.state != RunState.IDLE:
            return
        self.engine.start_record()

    def stop_record(self) -> None:
        if self.engine.state != RunState.RECORDING:
            return
        events = self.engine.stop_record() or []
        self._save_recording(events)
        self._flush_dirty()

    def toggle_replay(self) -> None:
        if self.engine.state == RunState.PLAYING:
            self.engine.stop()
            return
        if self.engine.state != RunState.IDLE:
            return
        if not self.engine.recording:
            self.status = "没有录像"
            return
        self.engine.start_replay(self.applied)

    def emergency_stop(self) -> None:
        if self.engine.state == RunState.RECORDING:
            self.stop_record()
        elif self.engine.state != RunState.IDLE:
            self.engine.stop()

    def on_progress(self, progress: Progress) -> None:
        self._last_progress = progress
        if progress.state == RunState.IDLE:
            self._flush_dirty()
            if progress.message:
                self.status = progress.message
        else:
            self.status = self._running_text(progress)

    def shutdown(self) -> None:
        if self.engine.state == RunState.RECORDING:
            self.stop_record()
        elif self.engine.state != RunState.IDLE:
            self.engine.stop()
        self._flush_dirty()
        if self._on_shutdown is not None:
            self._on_shutdown()

    def _commit_click(self, text: str, field: str) -> None:
        click = self.edited.click
        values = {
            "interval_ms": click.interval_ms,
            "interval_min_ms": click.interval_min_ms,
            "interval_max_ms": click.interval_max_ms,
            "count": click.count,
        }
        try:
            values[field] = int(text)
            updated = validate_click_fields(
                click.interval_mode,
                values["interval_ms"],
                values["interval_min_ms"],
                values["interval_max_ms"],
                values["count"],
            )
        except (ValueError, ConfigError) as exc:
            self.status = str(exc) if isinstance(exc, ConfigError) else "间隔必须是 10 到 60000 的整数"
            return
        self.edited = replace(self.edited, click=updated)
        self.status = "空闲"
        self._publish()

    def _finish_capture(self, name: str | None) -> None:
        field = self.capturing
        self.capturing = None
        if field is None or name is None:
            self.status = "不支持的快捷键"
            return
        mapping = self.edited.hotkeys.as_dict()
        for other, value in mapping.items():
            if other != field and value == name:
                self.status = "快捷键不能重复"
                return
        mapping[field] = name
        self.edited = replace(self.edited, hotkeys=Hotkeys(**mapping))
        self.status = f"已改成 {display_key(name)}"
        self._publish()

    def _publish(self) -> None:
        if self.engine.state != RunState.IDLE:
            self._dirty = True
            return
        self._write_applied()

    def _flush_dirty(self) -> None:
        if self._dirty or self.edited != self.applied:
            self._write_applied()

    def _write_applied(self) -> None:
        hotkeys_changed = self.edited.hotkeys != self.applied.hotkeys
        self.applied = self.edited
        self._dirty = False
        self._save_config(self.applied)
        if hotkeys_changed:
            if not self._rebind(self.applied.hotkeys):
                self.status = "热键监听失败"

    def _status_text(self) -> str:
        if self.engine.state != RunState.IDLE and self._last_progress is not None:
            return self._running_text(self._last_progress)
        return self.status

    def _running_text(self, progress: Progress) -> str:
        if progress.state == RunState.CLICKING:
            text = f"已点击 {progress.clicks_done}/{progress.click_count}"
        elif progress.state == RunState.RECORDING:
            text = f"已记录 {progress.event_count} 个事件，时长 {progress.elapsed_ms} 毫秒"
        elif progress.state == RunState.PLAYING:
            text = f"第 {progress.repeat_index}/{progress.repeat_total} 次"
        else:
            text = progress.message or "空闲"
        return f"{text}。修改会在本次结束后生效"
```

`test_running_edit_waits_until_idle` 在空闲进度到来后会把状态设成进度消息「空闲」。写入仍须发生。`test_capture_while_running_keeps_old_binding_until_idle` 在执行中按 `esc`：`applied` 仍是旧键，所以急停生效；回到空闲后再保存 `q`。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_controller.py tests/test_engine.py tests/test_config_store.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add key_wizard/controller.py tests/test_controller.py
git commit -m "feat: apply config and editable hotkeys from the controller"
```

---

### Task 8: pynput 后端

**Files:**
- Create: `key_wizard/backend.py`
- Test: `tests/test_backend_keys.py`

后端的真实移动和点击不在单元测试里调用。本任务只锁定两件事：键名转换已经在 Task 1 覆盖；监听器把识别出的键交给回调，识别不了的键不交。

- [ ] **Step 1: 写监听分发测试**

`tests/test_backend_keys.py`:

```python
from key_wizard.backend import dispatch_key


def test_dispatch_known_key():
    seen = []
    dispatch_key(type("Key", (), {"name": "f6"})(), lambda name: seen.append(name))
    assert seen == ["f6"]


def test_dispatch_ignores_space_and_numpad():
    seen = []
    dispatch_key(type("Key", (), {"name": "space"})(), lambda name: seen.append(name))
    dispatch_key(type("Pad", (), {"vk": 0x61, "char": "1"})(), lambda name: seen.append(name))
    assert seen == []
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_backend_keys.py -v`

Expected: FAIL，`key_wizard.backend` 无法导入。

- [ ] **Step 3: 实现后端**

`key_wizard/backend.py`:

```python
from __future__ import annotations

import time
from collections.abc import Callable

from key_wizard.keys import pynput_key_to_name


def dispatch_key(key: object, on_key: Callable[[str], None]) -> None:
    name = pynput_key_to_name(key)
    if name is not None:
        on_key(name)


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

        def on_press(key):
            dispatch_key(key, on_key)

        try:
            listener = keyboard.Listener(on_press=on_press)
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
```

`on_key` 收到每一个合法单键。界面把这个回调放进队列，不在 pynput 线程里改控件或睡眠。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_backend_keys.py tests/test_keys.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add key_wizard/backend.py tests/test_backend_keys.py
git commit -m "feat: dispatch global key presses through pynput"
```

---

### Task 9: 窗口和入口

**Files:**
- Create: `key_wizard/ui.py`
- Create: `main.py`
- Test: `tests/test_ui_smoke.py`

- [ ] **Step 1: 写窗口冒烟测试**

`tests/test_ui_smoke.py`:

```python
import queue

import pytest

from key_wizard.config_store import default_config
from key_wizard.controller import Controller
from key_wizard.models import RunState
from key_wizard.ui import App


class IdleEngine:
    def __init__(self) -> None:
        self.state = RunState.IDLE
        self.recording = []

    def start_click(self, _snapshot) -> bool:
        return True

    def start_record(self) -> bool:
        return True

    def stop_record(self):
        return []

    def start_replay(self, _snapshot) -> bool:
        return False

    def stop(self) -> None:
        return None


def test_window_shows_default_hotkeys_and_capture():
    tkinter = pytest.importorskip("tkinter")
    try:
        root = tkinter.Tk()
    except tkinter.TclError:
        pytest.skip("当前环境没有图形界面")
    root.withdraw()
    saved = {}
    controller = Controller(
        default_config(),
        IdleEngine(),
        lambda config: saved.setdefault("config", config),
        lambda events: saved.setdefault("recording", events),
        lambda _hotkeys: True,
    )
    events: queue.Queue = queue.Queue()
    app = App(root, controller, events)
    root.update_idletasks()
    assert root.title() == "按键精灵"
    assert app.click_button.cget("text") == "开始连点"
    assert app.hotkey_value_labels["toggle_click"].cget("text") == "F6"
    assert str(app.fixed_entry.cget("state")) == "normal"
    assert str(app.min_entry.cget("state")) == "disabled"
    app.capture_buttons["start_record"].invoke()
    root.update()
    assert app.status_label.cget("text") == "请按下新的快捷键"
    events.put(("key", "k"))
    app.poll()
    root.update()
    assert saved["config"].hotkeys.start_record == "k"
    assert app.hotkey_value_labels["start_record"].cget("text") == "K"
    app.close()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_ui_smoke.py -v`

Expected: FAIL，`key_wizard.ui` 无法导入。若没有图形界面，安装实现后此测试 SKIP，不算功能完成；有图形界面时必须 PASS。

- [ ] **Step 3: 实现界面**

`key_wizard/ui.py`:

```python
from __future__ import annotations

import queue
import tkinter as tk
from tkinter import ttk

from key_wizard.controller import Controller


HOTKEY_ROWS = (
    ("toggle_click", "循环点击"),
    ("start_record", "开始录制"),
    ("stop_record", "停止录制"),
    ("toggle_replay", "回放"),
    ("emergency_stop", "紧急停止"),
)


class App:
    def __init__(self, root: tk.Tk, controller: Controller, events: queue.Queue) -> None:
        self.root = root
        self.controller = controller
        self.events = events
        root.title("按键精灵")
        root.geometry("520x620")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.status_label = ttk.Label(root, text="")
        self.status_label.pack(fill="x", padx=12, pady=(12, 6))
        self._build_click(root)
        self._build_record(root)
        self._build_hotkeys(root)
        self._syncing = False
        self.render()
        self._after_id = root.after(50, self.poll)

    def close(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.controller.shutdown()
        self.root.destroy()

    def poll(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self.controller.on_progress(payload)
            elif kind == "key":
                self.controller.handle_key(payload)
        self.render()
        if self.root.winfo_exists():
            self._after_id = self.root.after(50, self.poll)

    def render(self) -> None:
        view = self.controller.view()
        self._syncing = True
        self.status_label.configure(text=view.status)
        self.mode_var.set(view.interval_mode)
        self._set_entry(self.fixed_entry, self.fixed_var, view.interval_ms, view.fixed_enabled)
        self._set_entry(self.min_entry, self.min_var, view.interval_min_ms, view.random_enabled)
        self._set_entry(self.max_entry, self.max_var, view.interval_max_ms, view.random_enabled)
        self._set_entry(self.count_entry, self.count_var, view.count, True)
        self._set_entry(self.repeat_entry, self.repeat_var, view.repeat, True)
        self.summary_label.configure(text=view.summary)
        self.click_button.configure(text=view.click_label, state=self._state(view.click_enabled))
        self.record_button.configure(state=self._state(view.start_record_enabled))
        self.stop_record_button.configure(state=self._state(view.stop_record_enabled))
        self.replay_button.configure(text=view.replay_label, state=self._state(view.replay_enabled))
        for field, _title in HOTKEY_ROWS:
            self.hotkey_value_labels[field].configure(text=view.hotkey_labels[field])
            capturing = view.capturing == field
            self.capture_buttons[field].configure(text="请按键" if capturing else "设键")
        self._syncing = False

    def _build_click(self, root: tk.Tk) -> None:
        frame = ttk.LabelFrame(root, text="循环点击")
        frame.pack(fill="x", padx=12, pady=6)
        self.mode_var = tk.StringVar(value="fixed")
        ttk.Radiobutton(frame, text="固定间隔", variable=self.mode_var, value="fixed", command=self._mode).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Radiobutton(frame, text="随机间隔", variable=self.mode_var, value="random", command=self._mode).grid(row=0, column=1, sticky="w", padx=8, pady=4)
        self.fixed_var = tk.StringVar()
        self.min_var = tk.StringVar()
        self.max_var = tk.StringVar()
        self.count_var = tk.StringVar()
        self.fixed_entry = self._labeled_entry(frame, 1, "固定间隔（毫秒）", self.fixed_var, self._commit_fixed)
        self.min_entry = self._labeled_entry(frame, 2, "随机最小（毫秒）", self.min_var, self._commit_min)
        self.max_entry = self._labeled_entry(frame, 3, "随机最大（毫秒）", self.max_var, self._commit_max)
        self.count_entry = self._labeled_entry(frame, 4, "点击次数", self.count_var, self._commit_count)
        self.click_button = ttk.Button(frame, text="开始连点", command=self.controller.toggle_click)
        self.click_button.grid(row=5, column=0, columnspan=2, sticky="ew", padx=8, pady=8)

    def _build_record(self, root: tk.Tk) -> None:
        frame = ttk.LabelFrame(root, text="录制回放")
        frame.pack(fill="x", padx=12, pady=6)
        self.repeat_var = tk.StringVar()
        self.repeat_entry = self._labeled_entry(frame, 0, "重复次数", self.repeat_var, self._commit_repeat)
        self.summary_label = ttk.Label(frame, text="尚未录制")
        self.summary_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        self.record_button = ttk.Button(frame, text="开始录制", command=self.controller.start_record)
        self.stop_record_button = ttk.Button(frame, text="停止录制", command=self.controller.stop_record)
        self.replay_button = ttk.Button(frame, text="开始回放", command=self.controller.toggle_replay)
        self.record_button.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        self.stop_record_button.grid(row=2, column=1, sticky="ew", padx=8, pady=8)
        self.replay_button.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))

    def _build_hotkeys(self, root: tk.Tk) -> None:
        frame = ttk.LabelFrame(root, text="快捷键")
        frame.pack(fill="x", padx=12, pady=6)
        self.hotkey_value_labels = {}
        self.capture_buttons = {}
        for row, (field, title) in enumerate(HOTKEY_ROWS):
            ttk.Label(frame, text=title).grid(row=row, column=0, sticky="w", padx=8, pady=4)
            label = ttk.Label(frame, text="", width=12)
            label.grid(row=row, column=1, sticky="w", padx=8, pady=4)
            button = ttk.Button(frame, text="设键", command=lambda item=field: self._begin_capture(item))
            button.grid(row=row, column=2, sticky="ew", padx=8, pady=4)
            self.hotkey_value_labels[field] = label
            self.capture_buttons[field] = button

    def _labeled_entry(self, frame, row: int, title: str, variable: tk.StringVar, commit) -> ttk.Entry:
        ttk.Label(frame, text=title).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        entry = ttk.Entry(frame, textvariable=variable, width=18)
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        entry.bind("<FocusOut>", lambda _event: commit())
        return entry

    def _set_entry(self, entry: ttk.Entry, variable: tk.StringVar, value: str, enabled: bool) -> None:
        entry.configure(state="normal")
        if entry.focus_get() is not entry and variable.get() != value:
            variable.set(value)
        entry.configure(state="normal" if enabled else "disabled")

    def _state(self, enabled: bool) -> str:
        return "normal" if enabled else "disabled"

    def _begin_capture(self, field: str) -> None:
        self.controller.begin_capture(field)
        self.render()

    def _mode(self) -> None:
        if self._syncing:
            return
        self.controller.commit_mode(self.mode_var.get())
        self.render()

    def _commit_fixed(self) -> None:
        self._commit(lambda: self.controller.commit_interval_ms(self.fixed_var.get()))

    def _commit_min(self) -> None:
        self._commit(lambda: self.controller.commit_interval_min_ms(self.min_var.get()))

    def _commit_max(self) -> None:
        self._commit(lambda: self.controller.commit_interval_max_ms(self.max_var.get()))

    def _commit_count(self) -> None:
        self._commit(lambda: self.controller.commit_count(self.count_var.get()))

    def _commit_repeat(self) -> None:
        self._commit(lambda: self.controller.commit_repeat(self.repeat_var.get()))

    def _commit(self, action) -> None:
        if self._syncing:
            return
        action()
        self.render()
```

`main.py`:

```python
from __future__ import annotations

import queue
from pathlib import Path

import tkinter as tk

from key_wizard.backend import PynputBackend
from key_wizard.config_store import load_config, load_recording, save_config, save_recording
from key_wizard.controller import Controller
from key_wizard.engine import Engine
from key_wizard.ui import App


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONFIG_PATH = DATA / "config.json"
RECORDING_PATH = DATA / "recording.json"


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    config, warning = load_config(CONFIG_PATH)
    if not CONFIG_PATH.exists():
        save_config(CONFIG_PATH, config)
    recording, _recording_warning = load_recording(RECORDING_PATH)
    backend = PynputBackend()
    engine = Engine(backend)
    engine.recording = recording
    events: queue.Queue = queue.Queue()

    def rebind(_hotkeys) -> bool:
        return backend.start_hotkey_listener(lambda name: events.put(("key", name)))

    def on_shutdown() -> None:
        backend.stop_hotkey_listener()
        backend.stop_mouse_listener()

    controller = Controller(
        config,
        engine,
        lambda item: save_config(CONFIG_PATH, item),
        lambda items: save_recording(RECORDING_PATH, items),
        rebind,
        on_shutdown,
    )
    if warning:
        controller.status = warning
    engine.add_progress_listener(lambda progress: events.put(("progress", progress)))
    if not rebind(config.hotkeys):
        controller.status = "热键监听失败"
    root = tk.Tk()
    App(root, controller, events)
    root.mainloop()


if __name__ == "__main__":
    main()
```

热键监听看的是全部合法按键，不是一份固定的五个键。控制器用 `applied` 决定哪个键触发动作，所以改键后要等 `rebind` 成功，新键才会从监听线程送进队列。监听线程只执行 `events.put`。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest -v`

Expected: 全部 PASS。没有图形界面时，`tests/test_ui_smoke.py` 为 SKIP，其余 PASS。

- [ ] **Step 5: Commit**

```bash
git add key_wizard/ui.py main.py tests/test_ui_smoke.py
git commit -m "feat: add the settings window and application entry"
```

---

### Task 10: Windows 手工确认

自动化测试不移动真实鼠标。在 Windows 上安装依赖后运行 `python main.py`，逐项确认：

- [ ] 第一次启动生成 `data/config.json`，窗口标题是「按键精灵」，五个键显示 F6、F8、F9、F10、Esc。
- [ ] 把点击次数改成 5，固定间隔改成 300，失焦后文件里的值变了。再开一次程序，数值还在。
- [ ] 按 F6，连点跟随鼠标当前位置，点满 5 次停止。连点时把鼠标挪开，下一次点在新位置。
- [ ] 连点过程中再按 F6，立即停止，并且不会多点一次。
- [ ] 改成随机间隔，最小值 100，最大值 200。连点的间隔不是恒定的。把最小值改成大于最大值，输入恢复原值，状态行说明原因。
- [ ] 按 F8，移动鼠标并分别点击左键和右键，再按 F9。摘要出现事件数和时长。按 F10，鼠标沿原路径移动并在原位置按下、松开，次数与「重复次数」一致。
- [ ] 没有录像时按 F10，状态行是「没有录像」，鼠标不动。
- [ ] 录制或回放时按 Esc，动作立刻停止。回放若停在按下之后，鼠标键会松开。
- [ ] 连点进行中修改间隔，本次间隔不变，状态行含有「修改会在本次结束后生效」。停止后再次连点，使用新间隔。
- [ ] 点「设键」把循环点击改成 `K`。空闲时 `K` 能开始和停止连点，F6 不再触发。五个键设成同一个时，状态行提示重复，原键保留。
- [ ] 连点进行中把急停改成 `Q`。这次仍按 Esc 停止。停止之后，Esc 不再急停，`Q` 可以急停。关闭程序再打开，`Q` 仍是急停键。
- [ ] 录制过程中关闭窗口，`data/recording.json` 里有刚才的事件。

---

## Spec coverage

- 跟随鼠标连点、固定/随机间隔、次数后停止、等待可打断：Task 3
- 同一时间只做一件事：Task 4
- 16 毫秒采样、坐标不变不记、点击立即记、`dt_ms`：Task 5
- 回放顺序、重复次数、空录像、中断补松开：Task 6
- 配置范围、损坏恢复、录像时长：Task 2
- 空闲立即生效、执行中延后生效、五个快捷键可改且不能重复：Task 7、Task 9
- 全局热键在其他软件前台可用：Task 8 的 `keyboard.Listener`，Task 9 把按键送进队列
- 窗口四块、按钮可用状态、关闭时保存录像：Task 9、Task 10
