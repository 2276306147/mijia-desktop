"""设备页：家庭/房间树 + 属性控件 + 动作执行。"""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Config
from app.core.service import DeviceInfo, MijiaService
from app.core.tasks import run_async
from app.ui.theme import active_colors
from app.ui.widgets import EmptyState, PropertyRow, badge, label, section_card


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class ActionDialog(QDialog):
    """给需要参数的动作一个 JSON 入口。"""

    def __init__(self, actions: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("高级执行动作")
        self.resize(460, 340)
        self._actions = actions

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(label("动作", "muted"))
        self.combo = QComboBox()
        for action in actions:
            self.combo.addItem(f"{action['name']}　{action.get('description', '')}", action)
        layout.addWidget(self.combo)

        layout.addWidget(label("参数（JSON 对象，留空表示无参数）", "muted"))
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText('例如：{"value": [2]}　或　{"in": ["打开台灯", 1]}')
        layout.addWidget(self.editor, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("执行")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def payload(self) -> tuple[dict, dict | None]:
        action = self.combo.currentData()
        text = self.editor.toPlainText().strip()
        if not text:
            return action, None
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("参数必须是 JSON 对象")
        return action, data


class DevicesPage(QWidget):
    status = Signal(str)
    favorite_changed = Signal()
    snapshot_loaded = Signal()

    def __init__(self, service: MijiaService, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.config = config
        self._current: DeviceInfo | None = None
        self._rows: dict[str, PropertyRow] = {}
        self._busy: set[str] = set()
        self._token = 0
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter)

        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 760])

    # ------------------------------------------------------------------ UI

    def _build_left(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索设备 / 房间 / 型号")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setAnimated(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self.tree, 1)

        self.count_label = label("尚未加载", "faint")
        layout.addWidget(self.count_label)
        return panel

    def _build_right(self) -> QWidget:
        self.stack = QStackedWidget()

        self.empty = EmptyState("还没有可显示的设备", "登录后点右上角“刷新”拉取设备列表")
        self.stack.addWidget(self.empty)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.detail = QWidget()
        detail_layout = QVBoxLayout(self.detail)
        detail_layout.setContentsMargins(2, 0, 8, 20)
        detail_layout.setSpacing(14)

        # 头部
        header, header_body = section_card("")
        self.header_card = header
        title_row = QHBoxLayout()
        self.name_label = label("", "h1")
        self.meta_row = QHBoxLayout()
        self.meta_row.setSpacing(6)
        self.star_btn = QPushButton("☆")
        self.star_btn.setProperty("kind", "star")
        self.star_btn.setCheckable(True)
        self.star_btn.setToolTip("收藏到托盘快捷菜单")
        self.star_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.star_btn.clicked.connect(self._toggle_favorite)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(lambda: self._select_device(self._current.did) if self._current else None)
        title_row.addWidget(self.name_label, 1)
        title_row.addWidget(self.star_btn)
        title_row.addWidget(self.refresh_btn)

        header_body.addLayout(title_row)
        self.meta_widget = QWidget()
        self.meta_widget.setLayout(self.meta_row)
        header_body.addWidget(self.meta_widget)
        self.meta_row.setContentsMargins(0, 0, 0, 0)

        # 操作失败时在标题下方给一行红字，比每次弹模态框友好
        self.error_label = label("", "faint")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color:#dc2626;")
        self.error_label.hide()
        header_body.addWidget(self.error_label)

        detail_layout.addWidget(header)

        self.props_card, self.props_body = section_card("属性", "")
        detail_layout.addWidget(self.props_card)

        self.actions_card, self.actions_body = section_card("动作", "点击按钮直接执行")
        self.actions_grid = QGridLayout()
        self.actions_grid.setSpacing(8)
        self.actions_body.addLayout(self.actions_grid)
        detail_layout.addWidget(self.actions_card)

        hint_card, hint_body = section_card("提示")
        hint = label(
            "部分设备（如纯传感器）只有只读属性；网关类设备返回 code=1 表示指令已下发，"
            "状态可能延迟 1~3 秒才变化。",
            "faint",
        )
        hint.setWordWrap(True)
        hint_body.addWidget(hint)
        detail_layout.addWidget(hint_card)

        detail_layout.addStretch(1)
        scroll.setWidget(self.detail)
        self.stack.addWidget(scroll)

        return self.stack

    # --------------------------------------------------------------- 数据

    def refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        self.status.emit("正在读取设备列表…")
        run_async(self.service.load_snapshot, self._on_snapshot, self._on_error)

    def _on_snapshot(self, snapshot) -> None:
        self._loading = False
        self._build_tree(snapshot.devices)
        online = sum(1 for d in snapshot.devices if d.online)
        self.count_label.setText(f"共 {len(snapshot.devices)} 台设备 · 在线 {online}")
        self.status.emit(f"设备列表已更新（{len(snapshot.devices)} 台）")
        if not snapshot.devices:
            self.stack.setCurrentIndex(0)
            self.empty.title.setText("账号下没有设备")
            self.empty.hint.setText("请先在米家 App 中添加设备，或确认账号是否正确")
        self.snapshot_loaded.emit()

    def _build_tree(self, devices: list[DeviceInfo]) -> None:
        colors = active_colors()
        current_did = self._current.did if self._current else None
        self.tree.blockSignals(True)
        self.tree.clear()

        favorites = [d for d in devices if d.did in self.config.favorites]
        if favorites:
            fav_root = QTreeWidgetItem(["★ 收藏"])
            fav_root.setFlags(Qt.ItemFlag.ItemIsEnabled)
            bold = QFont(self.font())
            bold.setBold(True)
            fav_root.setFont(0, bold)
            self.tree.addTopLevelItem(fav_root)
            for dev in favorites:
                fav_root.addChild(self._device_item(dev, colors))

        groups: dict[str, dict[str, list[DeviceInfo]]] = {}
        for dev in devices:
            groups.setdefault(dev.home or "未分组", {}).setdefault(dev.room or "未分组", []).append(dev)

        for home_name, rooms in groups.items():
            home_item = QTreeWidgetItem([home_name])
            home_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            bold = QFont(self.font())
            bold.setBold(True)
            home_item.setFont(0, bold)
            self.tree.addTopLevelItem(home_item)
            for room_name, items in rooms.items():
                room_item = QTreeWidgetItem([room_name])
                room_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                room_item.setForeground(0, QBrush(QColor(colors["muted"])))
                home_item.addChild(room_item)
                for dev in items:
                    room_item.addChild(self._device_item(dev, colors))

        self.tree.expandAll()
        self.tree.blockSignals(False)

        if current_did:
            self._select_in_tree(current_did)
        elif devices:
            first = self._first_device_item()
            if first is not None:
                self.tree.setCurrentItem(first)

    def _first_device_item(self) -> QTreeWidgetItem | None:
        queue = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while queue:
            item = queue.pop(0)
            if item is None:
                continue
            if item.data(0, Qt.ItemDataRole.UserRole):
                return item
            queue.extend(item.child(i) for i in range(item.childCount()))
        return None

    def reset(self) -> None:
        """切换账号时清空当前状态。"""
        self._token += 1
        self._current = None
        self._rows.clear()
        self.tree.clear()
        self.count_label.setText("尚未加载")
        clear_layout(self.props_body)
        clear_layout(self.actions_grid)
        self.stack.setCurrentIndex(0)

    def _device_item(self, dev: DeviceInfo, colors: dict[str, str]) -> QTreeWidgetItem:
        item = QTreeWidgetItem([dev.name])
        item.setData(0, Qt.ItemDataRole.UserRole, dev.did)
        item.setToolTip(0, f"{dev.model}\n{dev.did}")
        if not dev.online:
            item.setForeground(0, QBrush(QColor(colors["faint"])))
        return item

    def _select_in_tree(self, did: str) -> None:
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            if item.data(0, Qt.ItemDataRole.UserRole) == did:
                self.tree.setCurrentItem(item)
                return
            stack.extend(item.child(i) for i in range(item.childCount()))

    def _apply_filter(self, text: str) -> None:
        keyword = text.strip().lower()

        def visit(item: QTreeWidgetItem) -> bool:
            did = item.data(0, Qt.ItemDataRole.UserRole)
            if did:
                dev = self.service.snapshot.find(did)
                haystack = " ".join(
                    [item.text(0), dev.model if dev else "", dev.room if dev else "", dev.home if dev else ""]
                ).lower()
                visible = not keyword or keyword in haystack
                item.setHidden(not visible)
                return visible
            visible = False
            for i in range(item.childCount()):
                visible = visit(item.child(i)) or visible
            item.setHidden(not visible)
            if keyword and visible:
                item.setExpanded(True)
            return visible

        for i in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(i))

    def select(self, did: str) -> None:
        """从外部（托盘、搜索）定位到某台设备。"""
        self._select_in_tree(did)
        self._select_device(did)

    def _on_current_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is None:
            return
        did = current.data(0, Qt.ItemDataRole.UserRole)
        if not did:
            return
        self._select_device(did)

    # --------------------------------------------------------------- 详情

    def _select_device(self, did: str) -> None:
        device = self.service.snapshot.find(did)
        if device is None:
            return
        self._current = device
        self._token += 1
        token = self._token

        self.stack.setCurrentIndex(1)
        self.name_label.setText(device.name)
        self._render_meta(device)
        self.star_btn.setChecked(did in self.config.favorites)
        self.star_btn.setText("★" if did in self.config.favorites else "☆")

        clear_layout(self.props_body)
        self.props_body.addWidget(label("正在读取属性…", "faint"))
        clear_layout(self.actions_grid)
        self._rows.clear()

        def job():
            spec = self.service.spec_for(device)
            values = self.service.read_props(device) if spec else {}
            return spec, values

        run_async(job, lambda result: self._render_device(token, device, result), self._on_error)

    def _render_meta(self, device: DeviceInfo) -> None:
        clear_layout(self.meta_row)
        self.meta_row.addWidget(badge(device.model or "未知型号"))
        self.meta_row.addWidget(badge(f"{device.home} · {device.room}"))
        if device.online:
            self.meta_row.addWidget(badge("在线", "badgeOk"))
        else:
            self.meta_row.addWidget(badge("离线", "badgeWarn"))
        self.meta_row.addStretch(1)

    def _render_device(self, token: int, device: DeviceInfo, result: tuple) -> None:
        if token != self._token:
            return
        spec, values = result
        clear_layout(self.props_body)
        self._rows.clear()

        if not spec:
            self.props_body.addWidget(
                label("该设备没有可用的规格信息（缺少 spec_type 或拉取失败），无法自动生成控件。", "faint")
            )
            clear_layout(self.actions_grid)
            return

        props = [p for p in spec.get("properties", []) if p.get("rw")]
        if not props:
            self.props_body.addWidget(label("该设备没有可显示的属性", "faint"))
        for prop in props:
            row = PropertyRow(prop, values.get(prop["name"]))
            row.changed.connect(lambda name, value, p=prop: self._write(device, p, value))
            self.props_body.addWidget(row)
            self._rows[prop["name"]] = row

        clear_layout(self.actions_grid)
        actions = spec.get("actions", [])
        for index, action in enumerate(actions):
            button = QPushButton(action["name"])
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(action.get("description", ""))
            button.clicked.connect(lambda _checked=False, a=action: self._run_action(device, a, None))
            self.actions_grid.addWidget(button, index // 3, index % 3)
        if actions:
            more = QPushButton("高级执行…")
            more.setProperty("kind", "ghost")
            more.clicked.connect(lambda: self._advanced(device, actions))
            self.actions_grid.addWidget(more, len(actions) // 3 + 1, 0, 1, 1)
        else:
            self.actions_body.addWidget(label("该设备没有可执行动作", "faint"))

    # --------------------------------------------------------------- 操作

    def _write(self, device: DeviceInfo, prop: dict, value: Any) -> None:
        key = f"prop:{prop['name']}"
        if key in self._busy:
            return
        self._busy.add(key)
        self.status.emit(f"正在设置「{prop.get('description') or prop['name']}」…")
        row = self._rows.get(prop["name"])

        def done(message: str) -> None:
            self._busy.discard(key)
            self.status.emit(f"{device.name} · {prop['name']}：{message}")
            QTimer.singleShot(700, lambda: self._refresh_props(device, [prop["name"]]))

        def failed(message: str, _tb: str) -> None:
            self._busy.discard(key)
            self._on_error(message, _tb, modal=False)
            if row is not None:
                self._refresh_props(device, [prop["name"]])

        run_async(lambda: self.service.write_prop(device, prop, value), done, failed)

    def _refresh_props(self, device: DeviceInfo, names: list[str]) -> None:
        if self._current is None or self._current.did != device.did:
            return

        def job():
            return self.service.read_props(device, names)

        def done(values: dict) -> None:
            for name, value in values.items():
                row = self._rows.get(name)
                if row is not None:
                    row.set_value(value)

        run_async(job, done, lambda m, _tb: None)

    def _run_action(self, device: DeviceInfo, action: dict, params: dict | None) -> None:
        key = f"action:{action['name']}"
        if key in self._busy:
            return
        self._busy.add(key)
        self.status.emit(f"正在执行「{action['name']}」…")

        def done(message: str) -> None:
            self._busy.discard(key)
            self.status.emit(f"{device.name} · {action['name']}：{message}")
            # 动作可能改变状态，1 秒后回读一次，避免界面与实际不一致
            QTimer.singleShot(1000, lambda: self._refresh_props(device, []))

        def failed(message: str, trace: str) -> None:
            self._busy.discard(key)
            self._on_error(message, trace, modal=False)

        run_async(lambda: self.service.run_action(device, action, params), done, failed)

    def _advanced(self, device: DeviceInfo, actions: list[dict]) -> None:
        dialog = ActionDialog(actions, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            action, params = dialog.payload()
        except (ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return
        self._run_action(device, action, params)

    def _toggle_favorite(self) -> None:
        if self._current is None:
            return
        did = self._current.did
        if did in self.config.favorites:
            self.config.favorites.remove(did)
        else:
            self.config.favorites.append(did)
        self.config.save()
        self.star_btn.setChecked(did in self.config.favorites)
        self.star_btn.setText("★" if did in self.config.favorites else "☆")
        self._build_tree(self.service.snapshot.devices)
        self.favorite_changed.emit()

    def _context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        did = item.data(0, Qt.ItemDataRole.UserRole)
        if not did:
            return
        qmenu = QMenu(self)
        act_copy = qmenu.addAction("复制 did")
        act_fav = qmenu.addAction("取消收藏" if did in self.config.favorites else "收藏")
        chosen = qmenu.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen is act_copy:
            QApplication.clipboard().setText(did)
            self.status.emit("did 已复制到剪贴板")
        elif chosen is act_fav:
            self._current = self.service.snapshot.find(did)
            self._toggle_favorite()

    # --------------------------------------------------------------- 错误

    def _on_error(self, message: str, trace: str = "", modal: bool = True) -> None:
        self._loading = False
        self.status.emit(f"操作失败：{message}")
        if trace:
            import logging

            logging.getLogger("mijia.desktop").debug(trace)
        if modal:
            QMessageBox.warning(self, "操作失败", message)
        else:
            # 单次操作失败用行内提示，避免批量失败时连环弹窗
            self.error_label.setText(message)
            self.error_label.show()
            QTimer.singleShot(6000, self.error_label.hide)
