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
