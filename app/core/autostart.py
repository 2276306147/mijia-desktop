"""Windows 开机自启（注册表 HKCU\\...\\Run）。其他平台为空实现。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger("mijia.desktop")

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "MijiaDesktop"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def launch_command() -> str:
    """返回带引号的启动命令，供注册表或快捷方式使用。"""
    if is_frozen():
        return f'"{Path(sys.executable)}" --autostart'
    entry = Path(__file__).resolve().parents[2] / "run.py"
    return f'"{Path(sys.executable)}" "{entry}" --autostart'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """设置自启；返回是否成功（非 Windows 恒为 False）。"""
    if sys.platform != "win32":
        logger.info("当前平台不支持注册表自启，已跳过")
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(key, _VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError as exc:
        logger.warning("写入开机自启失败: %s", exc)
        return False
