import ctypes
import sys
import threading
from ctypes import wintypes

import pytest

from key_wizard.backend import enable_physical_mouse_coordinates, to_logical_cursor


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


def test_physical_pixels_convert_to_logical_cursor_space():
    assert to_logical_cursor(1500, 900, (2560, 1440), (3840, 2160)) == (1000, 600)
    assert to_logical_cursor(10, 20, (100, 100), (100, 100)) == (10, 20)


def test_mouse_thread_sees_physical_screen_pixels():
    if sys.platform != "win32":
        pytest.skip("仅 Windows")
    found: dict = {}

    def run() -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        before = user32.GetSystemMetrics(0)
        enable_physical_mouse_coordinates()
        after = user32.GetSystemMetrics(0)
        mode = _DevMode()
        mode.dmSize = ctypes.sizeof(_DevMode)
        ok = user32.EnumDisplaySettingsW(None, -1, ctypes.byref(mode))
        found.update(before=before, after=after, ok=bool(ok), physical=mode.dmPelsWidth)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    assert found["ok"]
    assert found["after"] == found["physical"]
    assert found["after"] >= found["before"]
