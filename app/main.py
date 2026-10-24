"""应用入口。"""

from __future__ import annotations

import argparse
import ctypes
import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from app.core.config import Config, ensure_dirs
from app.core.logbus import setup_logging
from app.core.service import MijiaService
from app.demo import install_demo
from app.paths import icon_path
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme
from app.version import __version__

logger = logging.getLogger("mijia.desktop")

SERVER_NAME = "MijiaDesktop.SingleInstance"


def _acquire_single_instance(name: str) -> QLocalServer | None:
    """已有实例在跑就通知它显示窗口并返回 None。"""
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(250):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(250)
        probe.disconnectFromServer()
        return None
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)
    return server


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
            "MijiaDesktop.MijiaConsole.1"
        )
    except Exception:  # noqa: BLE001 - 仅影响任务栏图标分组
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="MijiaConsole", description="米家控制台")
    parser.add_argument("--autostart", action="store_true", help="开机自启（启动后最小化到托盘）")
    parser.add_argument("--demo", action="store_true", help="演示模式：用假数据预览界面，不连接云端")
    parser.add_argument("--version", action="version", version=f"米家控制台 {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args, qt_args = build_parser().parse_known_args(argv)

    _set_windows_app_id()
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("米家控制台")
    app.setApplicationDisplayName("米家控制台")
    app.setOrganizationName("MijiaDesktop")
    app.setWindowIcon(QIcon(str(icon_path())))
    app.setQuitOnLastWindowClosed(False)

    ensure_dirs()
    config = Config.load()
    setup_logging(config.log_level)
    apply_theme(app, config.theme)

    server = _acquire_single_instance(SERVER_NAME)
    if server is None:
        logger.info("已有实例在运行，已唤起原窗口")
        return 0

    service = MijiaService(config)
    if args.demo:
        install_demo(service)
    window = MainWindow(service, config)

    def show_from_other_instance() -> None:
        connection = server.nextPendingConnection()
        if connection is not None:
            connection.readyRead.connect(connection.readAll)
            connection.disconnected.connect(connection.deleteLater)
        window.restore()

    server.newConnection.connect(show_from_other_instance)

    if args.autostart or config.start_minimized:
        window.hide()
    else:
        window.show()

    logger.info("米家控制台 %s 启动", __version__)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
