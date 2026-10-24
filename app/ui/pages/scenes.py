"""场景页：手动场景卡片，一键执行。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.service import MijiaService, SceneInfo
from app.core.tasks import run_async
from app.ui.widgets import Card, EmptyState, badge, label


class SceneCard(Card):
    def __init__(self, scene: SceneInfo, on_run, parent: QWidget | None = None) -> None:
        super().__init__(parent, flat=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        name = label(scene.name, "h2")
        name.setWordWrap(True)
        layout.addWidget(name)

        meta = QHBoxLayout()
        meta.setSpacing(6)
        if scene.home:
            meta.addWidget(badge(scene.home))
        meta.addWidget(badge(f"ID {scene.scene_id}"))
        meta.addStretch(1)
        layout.addLayout(meta)

        layout.addStretch(1)
        run = QPushButton("执行")
        run.setProperty("kind", "primary")
        run.setCursor(Qt.CursorShape.PointingHandCursor)
        run.clicked.connect(lambda: on_run(scene))
        run.setFixedWidth(104)
        layout.addWidget(run, alignment=Qt.AlignmentFlag.AlignLeft)
        self.setFixedHeight(152)


class ScenesPage(QWidget):
    status = Signal(str)

    def __init__(self, service: MijiaService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._scenes: list[SceneInfo] = []
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
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 8, 12)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)
        outer.addWidget(self.scroll, 1)

        self.empty = EmptyState("还没有手动场景", "在米家 App 的「智能 → 手动控制」里创建场景后会显示在这里")
        outer.addWidget(self.empty)
        self.empty.hide()

    def refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        self.status.emit("正在读取场景…")
        run_async(self.service.load_scenes, self._on_loaded, self._on_error)

    def ensure_data(self) -> None:
        if not self._scenes and not self._loading:
            self.refresh()

    def reset(self) -> None:
        self._scenes = []
        self._loading = False
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.count.setText("尚未加载")
        self.scroll.hide()
        self.empty.show()

    def _on_loaded(self, scenes: list[SceneInfo]) -> None:
        self._loading = False
        self._scenes = scenes
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.count.setText(f"共 {len(scenes)} 个手动场景")
        self.status.emit(f"场景已更新（{len(scenes)} 个）")

        if not scenes:
            self.scroll.hide()
            self.empty.show()
            return
        self.empty.hide()
        self.scroll.show()
        columns = 3
        for index, scene in enumerate(scenes):
            card = SceneCard(scene, self._run, self.container)
            self.grid.addWidget(card, index // columns, index % columns)

    def _run(self, scene: SceneInfo) -> None:
        self.status.emit(f"正在执行场景「{scene.name}」…")

        def done(_result) -> None:
            self.status.emit(f"场景「{scene.name}」已执行")

        run_async(lambda: self.service.run_scene(scene), done, self._on_error)

    def _on_error(self, message: str, _trace: str = "") -> None:
        self._loading = False
        self.status.emit(f"场景操作失败：{message}")
        QMessageBox.warning(self, "操作失败", message)
