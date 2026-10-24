"""应用配置与路径管理（跨平台，Windows 优先）。"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "MijiaDesktop"
APP_TITLE = "米家控制台"
APP_ID = "MijiaDesktop.MijiaConsole"


def config_root() -> Path:
    """返回配置根目录：Windows 用 %APPDATA%，macOS 用 Application Support。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / APP_NAME


CONFIG_ROOT = config_root()
CONFIG_FILE = CONFIG_ROOT / "settings.json"
ACCOUNTS_DIR = CONFIG_ROOT / "accounts"
LOG_FILE = CONFIG_ROOT / "logs" / "app.log"


@dataclass
class Config:
    """持久化设置。字段增删保持向后兼容：读不到就用默认值。"""

    version: int = 1
    theme: str = "light"                 # light / dark
    account: str = ""                    # 当前账号名
    favorites: list[str] = field(default_factory=list)   # 收藏设备 did
    window: dict[str, Any] = field(default_factory=dict)
    close_to_tray: bool = True
    start_minimized: bool = False
    autostart: bool = False
    log_level: str = "INFO"
    auto_refresh: int = 0                # 秒，0 表示关闭
    last_page: int = 0
    stats_device: str = ""
    stats_key: str = "7.1"
    speaker_device: str = ""

    # ---------- 读写 ----------

    @classmethod
    def load(cls) -> "Config":
        data: dict[str, Any] = {}
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                raw = {}
            if isinstance(raw, dict):
                data = raw
            else:
                logging.getLogger("mijia.desktop").warning(
                    "settings.json 顶层不是对象（%s），已回退默认值", type(raw).__name__
                )
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        """原子写入；失败只记日志，不让配置问题打断主流程。"""
        try:
            CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(asdict(self), ensure_ascii=False, indent=2)
            fd, tmp = tempfile.mkstemp(dir=str(CONFIG_ROOT), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                os.replace(tmp, CONFIG_FILE)
            finally:
                if os.path.exists(tmp):
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
        except OSError as exc:
            logging.getLogger("mijia.desktop").warning("保存设置失败: %s", exc)


def ensure_dirs() -> None:
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_ROOT / "logs").mkdir(parents=True, exist_ok=True)


def default_auth_path() -> Path:
    """mijiaAPI 的默认凭证位置（用于首次启动时导入）。"""
    return Path.home() / ".config" / "mijia-api" / "auth.json"
