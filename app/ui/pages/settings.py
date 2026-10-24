"""设置页：账号、外观、行为、日志、关于。"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core import autostart
from app.core.config import LOG_FILE, Config
from app.core.logbus import set_level
from app.core.service import MijiaService
from app.ui.widgets import HLine, badge, label, section_card
from app.version import __version__


class SettingsPage(QWidget):
    status = Signal(str)
    theme_changed = Signal(str)
    account_switched = Signal(str)
    login_requested = Signal(str)
    behavior_changed = Signal()

    def __init__(self, service: MijiaService, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.config = config

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 8, 16)
        outer.setSpacing(14)
        scroll.setWidget(container)
        root.addWidget(scroll)

        # ---------- 账号 ----------
        account_card, account_body = section_card("账号", "每个账号一份独立凭证，互不影响")
        self.account_list = QListWidget()
        self.account_list.setFixedHeight(132)
        self.account_list.itemDoubleClicked.connect(lambda _item: self._switch())
        account_body.addWidget(self.account_list)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for text, slot, kind in (
            ("切换", self._switch, "primary"),
            ("扫码登录", self._login, ""),
            ("新建账号", self._create, ""),
            ("删除", self._delete, "danger"),
        ):
            button = QPushButton(text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if kind:
                button.setProperty("kind", kind)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        account_body.addLayout(buttons)
        outer.addWidget(account_card)

        # ---------- 外观 ----------
        look_card, look_body = section_card("外观")
        look_row = QHBoxLayout()
        look_row.addWidget(label("主题", "muted"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        index = self.theme_combo.findData(self.config.theme)
        self.theme_combo.setCurrentIndex(max(0, index))
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        look_row.addWidget(self.theme_combo)
        look_row.addStretch(1)
        look_body.addLayout(look_row)
        outer.addWidget(look_card)

        # ---------- 行为 ----------
        behavior_card, behavior_body = section_card("行为")
        self.close_to_tray = QCheckBox("关闭窗口时最小化到托盘（不退出）")
        self.close_to_tray.setChecked(self.config.close_to_tray)
        self.close_to_tray.toggled.connect(lambda v: self._save("close_to_tray", v))
        behavior_body.addWidget(self.close_to_tray)

        self.start_minimized = QCheckBox("开机启动时最小化到托盘")
        self.start_minimized.setChecked(self.config.start_minimized)
        self.start_minimized.toggled.connect(lambda v: self._save("start_minimized", v))
        behavior_body.addWidget(self.start_minimized)

        self.autostart_box = QCheckBox("开机自动启动（写入当前用户注册表）")
        self.autostart_box.setChecked(autostart.is_enabled())
        if not autostart.is_enabled() and self.config.autostart:
            self.autostart_box.setChecked(True)
        self.autostart_box.toggled.connect(self._toggle_autostart)
        if sys.platform != "win32":
            self.autostart_box.setEnabled(False)
            self.autostart_box.setToolTip("仅 Windows 支持")
        behavior_body.addWidget(self.autostart_box)

        refresh_row = QHBoxLayout()
        refresh_row.addWidget(label("自动刷新设备列表", "muted"))
        self.refresh_combo = QComboBox()
        for text, seconds in (("关闭", 0), ("30 秒", 30), ("1 分钟", 60), ("5 分钟", 300), ("15 分钟", 900)):
            self.refresh_combo.addItem(text, seconds)
        index = self.refresh_combo.findData(self.config.auto_refresh)
        self.refresh_combo.setCurrentIndex(max(0, index))
        self.refresh_combo.currentIndexChanged.connect(
            lambda: self._refresh_interval(int(self.refresh_combo.currentData()))
        )
        refresh_row.addWidget(self.refresh_combo)
        refresh_row.addStretch(1)
        behavior_body.addLayout(refresh_row)
        outer.addWidget(behavior_card)

        # ---------- 日志 ----------
        log_card, log_body = section_card("日志", "滚动记录，保留 3 个历史文件")
        log_card.setToolTip(str(LOG_FILE))
        log_row = QHBoxLayout()
        log_row.addWidget(label("级别", "muted"))
        self.log_combo = QComboBox()
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            self.log_combo.addItem(level, level)
        index = self.log_combo.findData(self.config.log_level)
        self.log_combo.setCurrentIndex(max(0, index))
        self.log_combo.currentIndexChanged.connect(self._log_level)
        log_row.addWidget(self.log_combo)
        open_btn = QPushButton("打开日志目录")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_logs)
        log_row.addWidget(open_btn)
        log_row.addStretch(1)
        log_body.addLayout(log_row)
        outer.addWidget(log_card)

        # ---------- 关于 ----------
        about_card, about_body = section_card("关于")
        about_row = QHBoxLayout()
        about_row.setSpacing(8)
        about_row.addWidget(label(f"米家控制台 {__version__}", "h2"))
        about_row.addWidget(badge("GPL-3.0"))
        about_row.addStretch(1)
        about_body.addLayout(about_row)
        desc = label(
            "基于 mijiaAPI（github.com/Do1e/mijia-api）构建的非官方桌面客户端，"
            "与小米公司无关联。接口为逆向实现，可能随官方变更失效。"
            "本项目以 GPL-3.0 发布，分发时请遵守同一许可证。",
            "faint",
        )
        desc.setWordWrap(True)
        about_body.addWidget(desc)
        about_body.addWidget(HLine())
        link_row = QHBoxLayout()
        for text, url in (
            ("mijiaAPI 文档", "https://mijia-api.do1e.com"),
            ("项目仓库", "https://github.com/Do1e/mijia-api"),
            ("PyPI", "https://pypi.org/project/mijiaAPI/"),
        ):
            button = QPushButton(text)
            button.setProperty("kind", "ghost")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _c=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            link_row.addWidget(button)
        link_row.addStretch(1)
        about_body.addLayout(link_row)
        outer.addWidget(about_card)
        outer.addStretch(1)

        self.reload_accounts()

    # ------------------------------------------------------------------

    def reload_accounts(self) -> None:
        self.account_list.clear()
        for name in self.service.accounts.list():
            suffix = "　（当前）" if name == self.config.account else ""
            self.account_list.addItem(f"{name}{suffix}")

    def _selected(self) -> str:
        item = self.account_list.currentItem()
        if item is None:
            return ""
        return item.text().replace("　（当前）", "").strip()

    def _switch(self) -> None:
        name = self._selected()
        if not name:
            QMessageBox.information(self, "提示", "先选中一个账号")
            return
        self.account_switched.emit(name)

    def _login(self) -> None:
        name = self._selected() or self.config.account
        if not name:
            QMessageBox.information(self, "提示", "先新建一个账号")
            return
        self.login_requested.emit(name)

    def _create(self) -> None:
        name, ok = QInputDialog.getText(self, "新建账号", "账号名称（仅本机显示）：")
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            self.service.accounts.create(name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "创建失败", str(exc))
            return
        self.reload_accounts()
        self.status.emit(f"账号“{name}”已创建，请点“扫码登录”完成授权")

    def _delete(self) -> None:
        name = self._selected()
        if not name:
            return
        confirm = QMessageBox.question(
            self,
            "删除账号",
            f"确定删除“{name}”及其本地凭证吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.service.delete_account(name)
        self.reload_accounts()
        self.status.emit(f"账号“{name}”已删除")
        self.account_switched.emit(self.config.account)

    # ---- 设置项 ----

    def _save(self, field: str, value) -> None:
        setattr(self.config, field, value)
        self.config.save()
        self.behavior_changed.emit()

    def _theme_changed(self) -> None:
        theme = self.theme_combo.currentData()
        self.config.theme = theme
        self.config.save()
        self.theme_changed.emit(theme)

    def _toggle_autostart(self, checked: bool) -> None:
        ok = autostart.set_enabled(checked)
        self.config.autostart = checked and ok
        self.config.save()
        if not ok:
            self.autostart_box.blockSignals(True)
            self.autostart_box.setChecked(False)
            self.autostart_box.blockSignals(False)
            self.status.emit("当前平台不支持开机自启")
        else:
            self.status.emit("开机自启已" + ("开启" if checked else "关闭"))

    def _refresh_interval(self, value: int) -> None:
        self.config.auto_refresh = value
        self.config.save()
        self.behavior_changed.emit()

    def _log_level(self) -> None:
        level = self.log_combo.currentData()
        self.config.log_level = level
        self.config.save()
        set_level(level)
        self.status.emit(f"日志级别已切换为 {level}")

    def _open_logs(self) -> None:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_FILE.parent)))
