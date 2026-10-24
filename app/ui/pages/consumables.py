"""耗材页：滤芯、刷头等剩余量。"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.service import ConsumableInfo, MijiaService
from app.core.tasks import run_async
from app.ui.widgets import Card, EmptyState, HLine, badge, label


def _percent(value) -> int | None:
    text = str(value)
    match = re.search(r"(\d{1,3})\s*%", text)
    if match:
        return max(0, min(100, int(match.group(1))))
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if 0 <= number <= 100:
        return int(number)
    return None


class ConsumableRow(Card):
    def __init__(self, item: ConsumableInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent, flat=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        name = label(item.device_name or item.did, "h2")
        top.addWidget(name)
        if item.home:
            top.addWidget(badge(item.home))
        top.addStretch(1)
        top.addWidget(label(str(item.value) + (item.unit or ""), "value"))
        layout.addLayout(top)

        layout.addWidget(label(item.description, "muted"))

        percent = _percent(item.value)
        if percent is not None:
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(percent)
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            bar.setMaximumWidth(320)
            layout.addWidget(bar)


class ConsumablesPage(QWidget):
    status = Signal(str)

    def __init__(self, service: MijiaService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        head = QHBoxLayout()
        self.count = label("尚未加载", "muted")
        head.addWidget(self.count)
        head.addStretch(1)
        outer.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 8, 12)
        self.list_layout.setSpacing(10)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)
        outer.addWidget(self.scroll, 1)

        self.empty = EmptyState("没有耗材信息", "设备类型不支持，或家里还没有需要更换的耗材")
        outer.addWidget(self.empty)
        self.empty.hide()

    def refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        self.status.emit("正在读取耗材…")
        run_async(self.service.load_consumables, self._on_loaded, self._on_error)

    def ensure_data(self) -> None:
        if self.list_layout.count() == 0 and not self._loading:
            self.refresh()

    def reset(self) -> None:
        self._loading = False
        while self.list_layout.count():
            entry = self.list_layout.takeAt(0)
            if entry.widget():
                entry.widget().deleteLater()
        self.count.setText("尚未加载")
        self.scroll.hide()
        self.empty.show()

    def _on_loaded(self, items: list[ConsumableInfo]) -> None:
        self._loading = False
        while self.list_layout.count():
            entry = self.list_layout.takeAt(0)
            if entry.widget():
                entry.widget().deleteLater()

        self.count.setText(f"共 {len(items)} 项耗材")
        self.status.emit(f"耗材已更新（{len(items)} 项）")

        if not items:
            self.scroll.hide()
            self.empty.show()
            return
        self.empty.hide()
        self.scroll.show()
        for index, item in enumerate(items):
            if index:
                self.list_layout.addWidget(HLine())
            self.list_layout.addWidget(ConsumableRow(item, self.container))

    def _on_error(self, message: str, _trace: str = "") -> None:
        self._loading = False
        self.status.emit(f"耗材读取失败：{message}")
        QMessageBox.warning(self, "读取失败", message)
