from __future__ import annotations

import locale
import subprocess
import sys


def shutdown_command(delay_seconds: int) -> list[str]:
    return ["shutdown", "/s", "/t", str(delay_seconds), "/c", "按键精灵定时关机"]


def cancel_shutdown_command() -> list[str]:
    return ["shutdown", "/a"]


class WindowsShutdown:
    """交给 Windows 自己计时。窗口关掉以后，到点仍然会关机。"""

    def schedule(self, delay_seconds: int) -> None:
        if delay_seconds < 1:
            raise OSError("关机时间太近")
        _run(cancel_shutdown_command())
        completed = _run(shutdown_command(delay_seconds))
        if completed.returncode != 0:
            raise OSError(_failure_text(completed, "定时关机失败"))

    def cancel(self) -> None:
        completed = _run(cancel_shutdown_command())
        if completed.returncode != 0:
            raise OSError(_failure_text(completed, "当前没有等待中的关机"))


class UnsupportedShutdown:
    def schedule(self, delay_seconds: int) -> None:
        raise OSError("定时关机只在 Windows 上可用")

    def cancel(self) -> None:
        return


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    kwargs: dict = {
        "args": args,
        "capture_output": True,
        "text": True,
        "encoding": locale.getpreferredencoding(False),
        "errors": "replace",
        "check": False,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(**kwargs)


def _failure_text(completed: subprocess.CompletedProcess[str], fallback: str) -> str:
    detail = (completed.stderr or completed.stdout or "").strip()
    return detail or fallback
