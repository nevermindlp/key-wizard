from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from collections.abc import Callable

from key_wizard.keys import pynput_key_to_name

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2。钩子坐标本来就是物理像素。
_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
_dpi_state = threading.local()
_user32 = None


def enable_physical_mouse_coordinates() -> None:
    """让本线程的光标坐标与低级鼠标钩子使用同一套物理像素。

    进程默认不感知 DPI 时，GetCursorPos 和 SetCursorPos 会被缩小，
    而 WH_MOUSE_LL 仍返回物理像素。录制把两套数写进同一条录像后，回放会跳。
    """
    if sys.platform != "win32" or getattr(_dpi_state, "done", False):
        return
    try:
        previous = _win_user32().SetThreadDpiAwarenessContext(_PER_MONITOR_AWARE_V2)
    except (AttributeError, OSError):
        _dpi_state.done = True
        return
    if previous:
        _dpi_state.done = True


def _win_user32():
    global _user32
    if _user32 is None:
        _user32 = ctypes.WinDLL("user32", use_last_error=True)
        _user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        _user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    return _user32


def to_logical_cursor(
    x: int,
    y: int,
    logical: tuple[int, int] | None = None,
    physical: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """把物理像素换成当前进程 SetCursorPos 使用的坐标。

    录制读到的是物理像素。若在回放线程里改成 DPI 感知再调用 SetCursorPos，
    接口会返回新坐标，但屏幕上的光标不会重画。
    """
    if logical is None or physical is None:
        logical_w, logical_h, physical_w, physical_h = _SCREEN_SCALE
    else:
        logical_w, logical_h = logical
        physical_w, physical_h = physical
    if physical_w <= 0 or physical_h <= 0:
        return int(x), int(y)
    return (
        int(round(x * logical_w / physical_w)),
        int(round(y * logical_h / physical_h)),
    )


def _physical_display_size(user32) -> tuple[int, int]:
    class _DevMode(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName", wintypes.WCHAR * 32),
            ("dmSpecVersion", wintypes.WORD),
            ("dmDriverVersion", wintypes.WORD),
            ("dmSize", wintypes.WORD),
            ("dmDriverExtra", wintypes.WORD),
            ("dmFields", wintypes.DWORD),
            ("dmOrientation", wintypes.SHORT),
            ("dmPaperSize", wintypes.SHORT),
            ("dmPaperLength", wintypes.SHORT),
            ("dmPaperWidth", wintypes.SHORT),
            ("dmScale", wintypes.SHORT),
            ("dmCopies", wintypes.SHORT),
            ("dmDefaultSource", wintypes.SHORT),
            ("dmPrintQuality", wintypes.SHORT),
            ("dmColor", wintypes.SHORT),
            ("dmDuplex", wintypes.SHORT),
            ("dmYResolution", wintypes.SHORT),
            ("dmTTOption", wintypes.SHORT),
            ("dmCollate", wintypes.SHORT),
            ("dmFormName", wintypes.WCHAR * 32),
            ("dmLogPixels", wintypes.WORD),
            ("dmBitsPerPel", wintypes.DWORD),
            ("dmPelsWidth", wintypes.DWORD),
            ("dmPelsHeight", wintypes.DWORD),
            ("dmDisplayFlags", wintypes.DWORD),
            ("dmDisplayFrequency", wintypes.DWORD),
            ("dmICMMethod", wintypes.DWORD),
            ("dmICMIntent", wintypes.DWORD),
            ("dmMediaType", wintypes.DWORD),
            ("dmDitherType", wintypes.DWORD),
            ("dmReserved1", wintypes.DWORD),
            ("dmReserved2", wintypes.DWORD),
            ("dmPanningWidth", wintypes.DWORD),
            ("dmPanningHeight", wintypes.DWORD),
        ]

    mode = _DevMode()
    mode.dmSize = ctypes.sizeof(_DevMode)
    if not user32.EnumDisplaySettingsW(None, -1, ctypes.byref(mode)):
        return 0, 0
    return int(mode.dmPelsWidth), int(mode.dmPelsHeight)


def _capture_screen_scale() -> tuple[int, int, int, int]:
    if sys.platform != "win32":
        return (1, 1, 1, 1)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    logical_w = int(user32.GetSystemMetrics(0))
    logical_h = int(user32.GetSystemMetrics(1))
    physical_w, physical_h = _physical_display_size(user32)
    if physical_w <= 0 or physical_h <= 0:
        return logical_w, logical_h, logical_w, logical_h
    return logical_w, logical_h, physical_w, physical_h


def _enable_process_dpi() -> None:
    """必须在进程第一次使用 user32 之前调用，屏幕指针才会跟着 SetCursorPos 走。

    只改线程 DPI 时，GetCursorPos 会返回新坐标，但前台是高 DPI 程序时指针不会重画。
    """
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext(_PER_MONITOR_AWARE_V2)
    except (AttributeError, OSError):
        return


_enable_process_dpi()
_SCREEN_SCALE = _capture_screen_scale()


_INPUT_MOUSE = 0
_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_ABSOLUTE = 0x8000
_MOUSEEVENTF_VIRTUALDESK = 0x4000


def _cursor_pos() -> tuple[int, int]:
    point = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def _win32_input_types():
    """与 auto-arena 相同：64 位下 dwExtraInfo 必须是指针宽度。"""
    ulong_ptr = ctypes.c_void_p if ctypes.sizeof(ctypes.c_void_p) >= 8 else ctypes.c_ulong

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = (
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ulong_ptr),
        )

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", ctypes.c_ulong),
            ("wScan", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ulong_ptr),
        )

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = (("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ulong), ("wParamH", ctypes.c_ulong))

    class INPUTUNION(ctypes.Union):
        _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))

    class INPUT(ctypes.Structure):
        _fields_ = (("type", ctypes.c_ulong), ("ii", INPUTUNION))

    return INPUT, MOUSEINPUT


def _send_mouse(flags: int, dx: int = 0, dy: int = 0) -> None:
    input_type, mouse_input = _win32_input_types()
    send_input = ctypes.windll.user32.SendInput
    old_argtypes = getattr(send_input, "argtypes", None)
    old_restype = getattr(send_input, "restype", None)
    event = input_type()
    event.type = _INPUT_MOUSE
    event.ii.mi = mouse_input(int(dx), int(dy), 0, int(flags), 0, None)
    try:
        send_input.argtypes = (ctypes.c_uint, ctypes.POINTER(input_type), ctypes.c_int)
        send_input.restype = ctypes.c_uint
        sent = send_input(1, ctypes.byref(event), ctypes.c_int(ctypes.sizeof(event)))
    finally:
        send_input.argtypes = old_argtypes
        send_input.restype = old_restype
    if sent != 1:
        raise OSError(f"SendInput failed (flags=0x{flags:x}, sent={sent})")


def _absolute_point(x: int, y: int) -> tuple[int, int]:
    user32 = ctypes.windll.user32
    origin_x = int(user32.GetSystemMetrics(76))
    origin_y = int(user32.GetSystemMetrics(77))
    width = int(user32.GetSystemMetrics(78))
    height = int(user32.GetSystemMetrics(79))
    if width <= 1 or height <= 1:
        width = int(user32.GetSystemMetrics(0))
        height = int(user32.GetSystemMetrics(1))
        origin_x, origin_y = 0, 0
    return (
        int(round((x - origin_x) * 65535 / max(width - 1, 1))),
        int(round((y - origin_y) * 65535 / max(height - 1, 1))),
    )


def _move_cursor(x: int, y: int) -> None:
    """和 auto-arena 一样：SetCursorPos，再用带 VIRTUALDESK 的绝对移动补一次。

    只看 GetCursorPos 会误以为已经到位，前台窗口下屏幕指针却不动，所以两次都做。
    """
    x, y = int(x), int(y)
    ctypes.windll.user32.SetCursorPos(x, y)
    absolute_x, absolute_y = _absolute_point(x, y)
    _send_mouse(
        _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK,
        absolute_x,
        absolute_y,
    )


def _mouse_button(button: str, down: bool) -> None:
    if button == "right":
        flag = _MOUSEEVENTF_RIGHTDOWN if down else _MOUSEEVENTF_RIGHTUP
    else:
        flag = _MOUSEEVENTF_LEFTDOWN if down else _MOUSEEVENTF_LEFTUP
    _send_mouse(flag)


def dispatch_key(key: object, on_key: Callable[[str], None]) -> None:
    name = pynput_key_to_name(key)
    if name is not None:
        on_key(name)


class HeldKeys:
    """按住期间只交出一次按下，松开后才能再触发。"""

    def __init__(self) -> None:
        self._names: set[str] = set()

    def press(self, key: object, on_key: Callable[[str], None]) -> None:
        name = pynput_key_to_name(key)
        if name is None or name in self._names:
            return
        self._names.add(name)
        on_key(name)

    def release(self, key: object) -> None:
        name = pynput_key_to_name(key)
        if name is not None:
            self._names.discard(name)


class PynputBackend:
    """监听仍用 pynput。移动和点击走 user32，与 auto-arena 相同。"""

    def __init__(self) -> None:
        self._mouse_listener = None
        self._key_listener = None

    def position(self) -> tuple[int, int]:
        return _cursor_pos()

    def move(self, x: int, y: int) -> None:
        _move_cursor(x, y)

    def press(self, button: str, x: int, y: int) -> None:
        _move_cursor(x, y)
        _mouse_button(button, True)

    def release(self, button: str, x: int, y: int) -> None:
        _move_cursor(x, y)
        _mouse_button(button, False)

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
        held = HeldKeys()

        def on_press(key):
            held.press(key, on_key)

        def on_release(key):
            held.release(key)

        try:
            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
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
