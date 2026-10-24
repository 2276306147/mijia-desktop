"""资源路径（源码运行与 PyInstaller 打包后都可用）。"""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource(name: str) -> Path:
    return app_root() / "resources" / name


def icon_path() -> Path:
    for candidate in ("app.ico", "app.png"):
        path = resource(candidate)
        if path.exists():
            return path
    return resource("app.png")
