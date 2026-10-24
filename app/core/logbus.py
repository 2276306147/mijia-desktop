"""日志：同时写入滚动文件、输出到控制台，并转发给界面。"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QObject, Signal

from .config import LOG_FILE


class LogBridge(QObject):
    """跨线程日志信号（Qt 会自动排队到主线程）。"""

    message = Signal(str, str, str)   # level, logger, text


bridge = LogBridge()


class _QtHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            bridge.message.emit(record.levelname, record.name, self.format(record))
        except Exception:  # noqa: BLE001 - 日志不能反过来炸应用
            pass


_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s"

# mijiaAPI 在 DEBUG 级别会打印整个 auth_data（含 serviceToken），必须脱敏
_SENSITIVE = ("认证数据", "serviceToken", "ssecurity", "passToken")


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        if any(word in message for word in _SENSITIVE):
            record.msg = "[认证数据已脱敏]"
            record.args = ()
        return True


def setup_logging(level: str = "INFO") -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(_FORMAT, datefmt="%H:%M:%S")

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=1_500_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(file_handler)
    except OSError:
        pass

    if sys.stderr is not None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        root.addHandler(stream)

    qt_handler = _QtHandler()
    qt_handler.setFormatter(formatter)
    root.addHandler(qt_handler)

    redact = _RedactFilter()
    for handler in root.handlers:
        handler.addFilter(redact)
    logging.getLogger("mijiaAPI").addFilter(redact)

    # 第三方库降噪
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("qrcode").setLevel(logging.WARNING)

    return logging.getLogger("mijia.desktop")


def set_level(level: str) -> None:
    value = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(value)
    # 即使选了 DEBUG，也不让 mijiaAPI 输出凭证；协议细节仍可用 INFO 观察
    logging.getLogger("mijiaAPI").setLevel(max(value, logging.INFO))
