from __future__ import annotations

import sys
from pathlib import Path


def install_dir() -> Path:
    """程序自己的目录。

    源码运行时是项目根目录。打包后是 exe 所在目录。
    PyInstaller 单文件会把代码解压到临时目录，配置不能写到那里。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    return install_dir() / "data"
