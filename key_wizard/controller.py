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
            if self.engine.state == RunState.IDLE:
                self._flush_dirty()
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
        if self.engine.state == RunState.IDLE:
            self._flush_dirty()

    def toggle_replay(self) -> None:
        if self.engine.state == RunState.PLAYING:
            self.engine.stop()
            if self.engine.state == RunState.IDLE:
                self._flush_dirty()
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
            if self.engine.state == RunState.IDLE:
                self._flush_dirty()

    def on_progress(self, progress: Progress) -> None:
        if progress.state == RunState.IDLE and self.engine.state != RunState.IDLE:
            return
        self._last_progress = progress
        if progress.state == RunState.IDLE:
            self._flush_dirty()
            if progress.message and self.status != "热键监听失败":
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
