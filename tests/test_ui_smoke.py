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
