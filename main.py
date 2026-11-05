from __future__ import annotations

import sys


def _enable_per_monitor_dpi() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        # 必须先于 tkinter。否则回放只能改到坐标，屏幕上的指针不动。
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        return


def _report_startup_failure(exc: BaseException) -> None:
    message = f"按键精灵启动失败：\n{exc}"
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "按键精灵", 0x10)
    else:
        print(message, file=sys.stderr)


_enable_per_monitor_dpi()


def main() -> None:
    import queue

    import tkinter as tk

    from key_wizard.backend import PynputBackend
    from key_wizard.config_store import load_config, load_recording, save_config, save_recording
    from key_wizard.controller import Controller
    from key_wizard.engine import Engine
    from key_wizard.paths import data_dir
    from key_wizard.ui import App

    data = data_dir()
    data.mkdir(parents=True, exist_ok=True)
    config_path = data / "config.json"
    recording_path = data / "recording.json"
    config, warning = load_config(config_path)
    if not config_path.exists():
        save_config(config_path, config)
    recording, _recording_warning = load_recording(recording_path)
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
        lambda item: save_config(config_path, item),
        lambda items: save_recording(recording_path, items),
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
    try:
        main()
    except Exception as exc:
        _report_startup_failure(exc)
        raise
