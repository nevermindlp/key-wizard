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


def test_idle_progress_keeps_hotkey_listener_failure():
    controller, engine, saved, _rebinds = _setup(rebind_ok=False)
    engine.state = RunState.CLICKING
    controller.on_progress(Progress(state=RunState.CLICKING, clicks_done=1, click_count=20))
    controller.begin_capture("emergency_stop")
    controller.handle_key("q")
    engine.state = RunState.IDLE
    controller.on_progress(Progress(state=RunState.IDLE, message="空闲"))
    assert saved["config"].hotkeys.emergency_stop == "q"
    assert controller.view().status == "热键监听失败"
