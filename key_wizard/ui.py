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
