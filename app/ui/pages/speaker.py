"""小爱音箱页：自然语言指令与文本朗读。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Config
from app.core.service import MijiaService
from app.core.tasks import run_async
from app.ui.widgets import label, section_card


class SpeakerPage(QWidget):
    status = Signal(str)

    def __init__(self, service: MijiaService, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.config = config
        self._loaded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        target_card, target_body = section_card("音箱", "自动列出型号含 xiaomi.wifispeaker 的设备")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(260)
        row.addWidget(self.device_combo, 1)
        refresh = QPushButton("刷新设备")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.reload)
        row.addWidget(refresh)
        target_body.addLayout(row)
        outer.addWidget(target_card)

        command_card, command_body = section_card("执行指令", "通过 execute-text-directive 让音箱理解并执行")
        self.command_edit = QLineEdit()
        self.command_edit.setPlaceholderText("例如：打开卧室台灯 / 把亮度调到 50%")
        self.command_edit.returnPressed.connect(self._run_command)
        command_body.addWidget(self.command_edit)

        options = QHBoxLayout()
        self.quiet_check = QCheckBox("静默执行（不语音播报回复）")
        self.quiet_check.setChecked(True)
        options.addWidget(self.quiet_check)
        options.addStretch(1)
        send = QPushButton("执行")
        send.setProperty("kind", "primary")
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.clicked.connect(self._run_command)
        options.addWidget(send)
        command_body.addLayout(options)
        outer.addWidget(command_card)

        play_card, play_body = section_card("朗读文本", "通过 play-text 直接念出文字，不当作控制指令")
        self.play_edit = QPlainTextEdit()
        self.play_edit.setPlaceholderText("晚饭做好了")
        self.play_edit.setFixedHeight(90)
        play_body.addWidget(self.play_edit)
        play_row = QHBoxLayout()
        play_row.addStretch(1)
        play = QPushButton("朗读")
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        play.clicked.connect(self._play)
        play_row.addWidget(play)
        play_body.addLayout(play_row)
        outer.addWidget(play_card)

        hint = label(
            "这两个功能都是向音箱发送文字，不是接收音箱的语音输入。"
            "未安装可选依赖 fastmcp 不影响本页；指令失败时先确认音箱在线且已登录同一账号。",
            "faint",
        )
        hint.setWordWrap(True)
        outer.addWidget(hint)
        outer.addStretch(1)

    # ------------------------------------------------------------------

    def reload(self) -> None:
        self._loaded = False
        self.ensure_data()

    def reset(self) -> None:
        self._loaded = False
        self.device_combo.clear()

    def ensure_data(self) -> None:
        if self._loaded:
            return
        devices = self.service.snapshot.devices
        if devices:
            self._fill(devices)
            return

        def done(snapshot) -> None:
            self._fill(snapshot.devices)

        run_async(self.service.load_snapshot, done, lambda m, _t: self.status.emit(f"加载失败：{m}"))

    def _fill(self, _devices) -> None:
        speakers = self.service.speakers()
        self._loaded = True
        self.device_combo.clear()
        for dev in speakers:
            self.device_combo.addItem(f"{dev.name}　{dev.room}", dev.did)
        index = self.device_combo.findData(self.config.speaker_device)
        if index >= 0:
            self.device_combo.setCurrentIndex(index)
        if not speakers:
            self.status.emit("没有找到小爱音箱设备")

    def _current_(self):
        did = self.device_combo.currentData()
        if not did:
            raise ValueError("请先选择一台小爱音箱")
        device = self.service.snapshot.find(did)
        if device is None:
            raise ValueError("设备不在当前列表中，请先刷新")
        return device

    def _run_command(self) -> None:
        text = self.command_edit.text().strip()
        if not text:
            return
        try:
            device = self._current_()
        except ValueError as exc:
            QMessageBox.information(self, "提示", str(exc))
            return
        self.config.speaker_device = device.did
        self.config.save()
        self.status.emit(f"正在让「{device.name}」执行：{text}")

        run_async(
            lambda: self.service.speaker_send(device, text, quiet=self.quiet_check.isChecked()),
            lambda _r: self.status.emit("指令已发送"),
            self._on_error,
        )

    def _play(self) -> None:
        text = self.play_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "请输入要朗读的文本")
            return
        try:
            device = self._current_()
        except ValueError as exc:
            QMessageBox.information(self, "提示", str(exc))
            return
        self.status.emit(f"正在让「{device.name}」朗读…")
        run_async(
            lambda: self.service.speaker_send(device, text, play_only=True),
            lambda _r: self.status.emit("已发送朗读请求"),
            self._on_error,
        )

    def _on_error(self, message: str, _trace: str = "") -> None:
        self.status.emit(f"音箱操作失败：{message}")
        QMessageBox.warning(self, "操作失败", message)
