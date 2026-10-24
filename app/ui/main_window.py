"""主窗口：侧边导航 + 页面栈 + 托盘 + 日志抽屉。"""

from __future__ import annotations

import html
import logging
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Config
from app.core.logbus import bridge
from app.core.service import DeviceInfo, MijiaService
from app.core.tasks import run_async
from app.paths import icon_path
from app.ui.login_dialog import LoginDialog
from app.ui.pages.consumables import ConsumablesPage
from app.ui.pages.devices import DevicesPage
from app.ui.pages.mcp import McpPage
from app.ui.pages.scenes import ScenesPage
from app.ui.pages.settings import SettingsPage
from app.ui.pages.speaker import SpeakerPage
from app.ui.pages.stats import StatsPage
from app.ui.theme import apply_theme
from app.ui.widgets import badge, label
from app.version import __version__

logger = logging.getLogger("mijia.desktop")

NAV = [
    ("设备", "查看状态、调整属性、执行动作"),
    ("场景", "一键运行米家手动场景"),
    ("统计", "用电量与使用时长趋势"),
    ("耗材", "滤芯、刷头等剩余量"),
    ("音箱", "让小爱执行指令或朗读"),
    ("MCP", "把设备能力开放给 AI 客户端"),
    ("设置", "账号、外观与偏好"),
]


class MainWindow(QMainWindow):
    def __init__(self, service: MijiaService, config: Config) -> None:
        super().__init__()
        self.service = service
        self.config = config
        self._quitting = False
        self._tray_hint_shown = False

        self.setWindowTitle("米家控制台")
        self.setWindowIcon(QIcon(str(icon_path())))
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)
        self._restore_geometry()

        self._build_ui()
        self._build_tray()
        self._wire_log()

        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._auto_refresh)
        self.apply_behavior()

        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self.refresh_current)

        import os

        if os.environ.get("MIJIA_DESKTOP_SKIP_BOOTSTRAP") != "1":
            QTimer.singleShot(120, self.bootstrap)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_topbar())
        content_layout.addWidget(self._build_stack(), 1)
        content_layout.addWidget(self._build_log_panel())
        layout.addWidget(content, 1)

        status = self.statusBar()
        status.setSizeGripEnabled(False)
        status.showMessage("就绪")

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(196)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(4)

        brand = QHBoxLayout()
        brand.setSpacing(9)
        mark = QLabel("米")
        mark.setObjectName("BrandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(26, 26)
        brand.addWidget(mark)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(label("米家控制台", ""))
        texts.addWidget(label(f"v{__version__}", "faint"))
        brand.addLayout(texts)
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for index, (title, _sub) in enumerate(NAV):
            button = QPushButton(title)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _c=False, i=index: self.goto(i))
            self.nav_group.addButton(button, index)
            layout.addWidget(button)
        layout.addStretch(1)

        self.account_label = label("未登录", "faint")
        self.account_label.setWordWrap(True)
        layout.addWidget(self.account_label)
        self.account_hint = label("", "faint")
        self.account_hint.setWordWrap(True)
        layout.addWidget(self.account_hint)
        return sidebar

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(64)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.page_title = label("设备", "")
        self.page_title.setObjectName("PageTitle")
        self.page_sub = label(NAV[0][1], "")
        self.page_sub.setObjectName("PageSub")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_sub)
        layout.addLayout(titles)
        layout.addStretch(1)

        self.status_badge = badge("检查中")
        layout.addWidget(self.status_badge)

        self.login_btn = QPushButton("扫码登录")
        self.login_btn.setProperty("kind", "primary")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.clicked.connect(lambda: self.open_login())
        layout.addWidget(self.login_btn)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_current)
        layout.addWidget(self.refresh_btn)

        self.log_btn = QPushButton("日志")
        self.log_btn.setProperty("kind", "ghost")
        self.log_btn.setCheckable(True)
        self.log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.log_btn.toggled.connect(self._toggle_log)
        layout.addWidget(self.log_btn)
        return bar

    def _build_stack(self) -> QWidget:
        self.stack = QStackedWidget()
        self.devices_page = DevicesPage(self.service, self.config)
        self.scenes_page = ScenesPage(self.service)
        self.stats_page = StatsPage(self.service, self.config)
        self.consumables_page = ConsumablesPage(self.service)
        self.speaker_page = SpeakerPage(self.service, self.config)
        self.mcp_page = McpPage(self.service, self.config)
        self.settings_page = SettingsPage(self.service, self.config)
        self._pages = [
            self.devices_page,
            self.scenes_page,
            self.stats_page,
            self.consumables_page,
            self.speaker_page,
            self.mcp_page,
            self.settings_page,
        ]
        for page in self._pages:
            self.stack.addWidget(page)
            if hasattr(page, "status"):
                page.status.connect(self._show_status)

        self.devices_page.favorite_changed.connect(self._rebuild_tray_menu)
        self.settings_page.theme_changed.connect(self._change_theme)
        self.settings_page.account_switched.connect(self.switch_account)
        self.settings_page.login_requested.connect(self.open_login)
        self.settings_page.behavior_changed.connect(self.apply_behavior)

        self.nav_group.button(0).setChecked(True)
        return self.stack

    def _build_log_panel(self) -> QWidget:
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("LogView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(600)
        self.log_view.setFixedHeight(150)
        self.log_view.hide()
        return self.log_view

    # ---------------------------------------------------------------- 托盘

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(QIcon(str(icon_path())), self)
        self.tray.setToolTip("米家控制台")
        self.tray_menu = QMenu()
        self.tray_menu.aboutToShow.connect(self._rebuild_tray_menu)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _rebuild_tray_menu(self) -> None:
        self.tray_menu.clear()
        show = QAction("显示主窗口", self)
        show.triggered.connect(self._restore)
        self.tray_menu.addAction(show)

        favorites = [d for d in self.service.snapshot.devices if d.did in self.config.favorites]
        if favorites:
            self.tray_menu.addSeparator()
            quick = self.tray_menu.addMenu("收藏设备")
            for device in favorites[:12]:
                quick.addMenu(self._device_menu(device))

        self.tray_menu.addSeparator()
        refresh = QAction("刷新设备列表", self)
        refresh.triggered.connect(self.devices_page.refresh)
        self.tray_menu.addAction(refresh)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit)
        self.tray_menu.addAction(quit_action)

    def _device_menu(self, device: DeviceInfo) -> QMenu:
        menu = QMenu(device.name, self)
        spec = self.service.cached_spec(device)
        quick_prop = None
        if spec:
            for prop in spec.get("properties", []):
                if prop.get("type") == "bool" and "w" in prop.get("rw", "") and prop["name"].split("-")[0] == "on":
                    quick_prop = prop
                    break
        if quick_prop is not None:
            for text, value in (("打开", True), ("关闭", False)):
                action = QAction(text, menu)
                action.triggered.connect(
                    lambda _c=False, p=quick_prop, v=value: self._quick_write(device, p, v)
                )
                menu.addAction(action)
        else:
            action = QAction("在窗口中查看", menu)
            action.triggered.connect(lambda: self._open_device(device))
            menu.addAction(action)
        return menu

    def _quick_write(self, device: DeviceInfo, prop: dict, value: bool) -> None:
        label_text = "打开" if value else "关闭"
        self._show_status(f"{label_text} {device.name} …")

        def done(message: str) -> None:
            self._show_status(f"{device.name}：{message}")

        def failed(message: str, _trace: str = "") -> None:
            self._show_status(f"{device.name} 操作失败：{message}")
            if QSystemTrayIcon.supportsMessages():
                self.tray.showMessage("操作失败", message, QSystemTrayIcon.MessageIcon.Warning, 4000)

        run_async(lambda: self.service.write_prop(device, prop, value), done, failed)

    def _open_device(self, device: DeviceInfo) -> None:
        self.goto(0)
        self.restore()
        self.devices_page.select(device.did)

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore()

    def restore(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---------------------------------------------------------------- 启动

    def bootstrap(self) -> None:
        account = self.service.ensure_account()
        if account is None:
            name = "我的账号"
            try:
                self.service.accounts.create(name)
                self.service.use_account(name)
                account = name
            except Exception as exc:  # noqa: BLE001
                logger.warning("创建默认账号失败: %s", exc)
        self.refresh_account_label()
        self.check_session(auto_login=not (self.service.auth_path and self.service.auth_path.exists()))

    def check_session(self, auto_login: bool = False) -> None:
        self._set_badge("检查中")
        self.login_btn.setVisible(False)

        def done(result: tuple[bool, str]) -> None:
            ok, message = result
            if ok:
                self._set_badge("已连接", "badgeOk")
                self.login_btn.setVisible(False)
                self._show_status(message)
                self.devices_page.refresh()
                self.mcp_page.refresh_config()
            else:
                self._set_badge("未登录" if "登录" in message else "离线", "badgeWarn")
                self.login_btn.setVisible(True)
                self._show_status(message)
                if auto_login:
                    QTimer.singleShot(300, lambda: self.open_login())

        def failed(message: str, _trace: str = "") -> None:
            self._set_badge("离线", "badgeWarn")
            self.login_btn.setVisible(True)
            self._show_status(f"连接失败：{message}")

        run_async(self.service.check_session, done, failed)

    # ---------------------------------------------------------------- 交互

    def goto(self, index: int) -> None:
        index = max(0, min(index, len(NAV) - 1))
        self.stack.setCurrentIndex(index)
        self.page_title.setText(NAV[index][0])
        self.page_sub.setText(NAV[index][1])
        button = self.nav_group.button(index)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self.config.last_page = index
        self.config.save()

        page = self._pages[index]
        if index == 0 and not self.service.snapshot.devices:
            page.refresh()
        elif hasattr(page, "ensure_data"):
            page.ensure_data()

    def refresh_current(self) -> None:
        page = self._pages[self.stack.currentIndex()]
        if hasattr(page, "refresh"):
            page.refresh()

    def open_login(self, account: str | None = None) -> None:
        name = account or self.config.account
        if not name:
            QMessageBox.information(self, "提示", "请先在设置里新建一个账号")
            return
        if name != self.config.account:
            self.switch_account(name, reload=False)
        dialog = LoginDialog(self.service, name, self)
        dialog.logged_in.connect(lambda: self._show_status("登录成功"))
        if dialog.exec() == LoginDialog.DialogCode.Accepted:
            self.refresh_account_label()
            self._reset_pages()
            self.check_session()
            self.mcp_page.refresh_config()

    def switch_account(self, name: str, reload: bool = True) -> None:
        if not name:
            return
        try:
            if name != self.config.account:
                self.service.use_account(name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "切换失败", str(exc))
            return
        self.refresh_account_label()
        if reload:
            self._reset_pages()
            self.check_session()

    def _reset_pages(self) -> None:
        for page in self._pages:
            reset = getattr(page, "reset", None)
            if callable(reset):
                reset()
        self.mcp_page.refresh_config()

    def _change_theme(self, theme: str) -> None:
        apply_theme(QApplication.instance(), theme)
        self._show_status("主题已切换为" + ("深色" if theme == "dark" else "浅色"))

    def apply_behavior(self) -> None:
        if self.config.auto_refresh > 0:
            self._auto_timer.start(max(5, self.config.auto_refresh) * 1000)
        else:
            self._auto_timer.stop()
        if self.config.autostart:
            from app.core import autostart

            autostart.set_enabled(True)

    def _auto_refresh(self) -> None:
        if self.stack.currentIndex() == 0:
            self.devices_page.refresh()

    def refresh_account_label(self) -> None:
        name = self.config.account or "未登录"
        self.account_label.setText(f"账号：{name}")
        count = len(self.service.accounts.list())
        self.account_hint.setText(f"共 {count} 个账号 · 可在设置中切换")

    def _show_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 6000)

    def _set_badge(self, text: str, kind: str = "badge") -> None:
        self.status_badge.setText(text)
        self.status_badge.setProperty("kind", kind)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

    # ---------------------------------------------------------------- 日志

    def _wire_log(self) -> None:
        bridge.message.connect(self._append_log)

    def _append_log(self, level: str, name: str, text: str) -> None:
        if not self.log_view.isVisible() and level in ("DEBUG", "INFO"):
            return
        color = {
            "DEBUG": "#94a3b8",
            "INFO": "#64748b",
            "WARNING": "#d97706",
            "ERROR": "#dc2626",
            "CRITICAL": "#dc2626",
        }.get(level, "#64748b")
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendHtml(
            f'<span style="color:#94a3b8">{stamp}</span> '
            f'<span style="color:{color}">{level[:4]:<4}</span> '
            f'<span style="color:{color}">{html.escape(text)}</span>'
        )

    def _toggle_log(self, visible: bool) -> None:
        self.log_view.setVisible(visible)
        if visible:
            self.log_view.ensureCursorVisible()

    # ---------------------------------------------------------------- 窗口

    def _restore_geometry(self) -> None:
        geom = self.config.window or {}
        if geom.get("maximized"):
            self.showMaximized()
        elif all(k in geom for k in ("w", "h")):
            self.resize(int(geom["w"]), int(geom["h"]))
            if "x" in geom and "y" in geom:
                self.move(int(geom["x"]), int(geom["y"]))

    def _save_geometry(self) -> None:
        self.config.window = {
            "w": self.width(),
            "h": self.height(),
            "x": self.x(),
            "y": self.y(),
            "maximized": self.isMaximized(),
        }
        self.config.save()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_geometry()
        if self._quitting or not self.config.close_to_tray or not self.tray.isVisible():
            event.accept()
            QApplication.quit()
            return
        event.ignore()
        self.hide()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            if QSystemTrayIcon.supportsMessages():
                self.tray.showMessage(
                    "米家控制台",
                    "已最小化到托盘，双击图标可恢复窗口",
                    QSystemTrayIcon.MessageIcon.Information,
                    3500,
                )

    def quit(self) -> None:
        self._quitting = True
        self._save_geometry()
        self.tray.hide()
        QApplication.quit()
