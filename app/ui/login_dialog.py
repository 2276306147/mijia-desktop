"""扫码登录对话框：窗口内显示二维码，后台长轮询等待。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.service import LoginTicket, MijiaService
from app.core.tasks import run_async, run_detached
from app.ui.widgets import label


class LoginDialog(QDialog):
    logged_in = Signal()

    def __init__(self, service: MijiaService, account: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.account = account
        self._token = 0
        self._ticket: LoginTicket | None = None

        self.setWindowTitle("扫码登录")
        self.setFixedSize(392, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)

        title = label("使用米家 App 扫码登录", "h1")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = label(f"账号：{account}", "faint")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        self.qr = QLabel("正在生成二维码…")
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr.setFixedSize(280, 280)
        self.qr.setStyleSheet("background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;color:#9ca3af;")
        holder = QHBoxLayout()
        holder.addStretch(1)
        holder.addWidget(self.qr)
        holder.addStretch(1)
        layout.addLayout(holder)

        self.status = label("请稍候", "muted")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.retry_btn = QPushButton("刷新二维码")
        self.retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_btn.clicked.connect(self.start)
        close_btn = QPushButton("取消")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(self.retry_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        hint = label("二维码 2 分钟内有效；登录成功后会自动关闭本窗口。", "faint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        QTimer.singleShot(120, self.start)

    # ------------------------------------------------------------------

    def start(self) -> None:
        self._token += 1
        token = self._token
        self.retry_btn.setEnabled(False)
        self.status.setText("正在获取二维码…")
        self.qr.setPixmap(QPixmap())
        self.qr.setText("正在生成二维码…")

        def done(ticket: LoginTicket) -> None:
            if token != self._token:
                return
            self._ticket = ticket
            if ticket.refreshed:
                self.status.setText("本地凭证仍然有效，无需扫码")
                self.logged_in.emit()
                QTimer.singleShot(500, self.accept)
                return
            pixmap = QPixmap()
            if ticket.qr_png:
                pixmap.loadFromData(ticket.qr_png)
            self.qr.setPixmap(pixmap.scaled(262, 262, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.qr.setText("")
            self.status.setText("请用米家 App「扫一扫」扫描二维码")
            self.retry_btn.setEnabled(True)
            self._wait(ticket, token)

        def failed(message: str, _trace: str) -> None:
            if token != self._token:
                return
            self.status.setText(f"获取二维码失败：{message}")
            self.qr.setText("二维码获取失败")
            self.retry_btn.setEnabled(True)

        run_async(self.service.start_login, done, failed)

    def _wait(self, ticket: LoginTicket, token: int) -> None:
        self.status.setText("等待扫码确认…（请勿关闭窗口）")

        def done(_result) -> None:
            if token != self._token:
                return
            # 重置状态放到主线程，避免工作线程清空界面正在读取的缓存
            self.service.reset()
            self.status.setText("登录成功")
            self.logged_in.emit()
            QTimer.singleShot(400, self.accept)

        def failed(message: str, _trace: str) -> None:
            if token != self._token:
                return
            self.status.setText(f"登录失败或已超时：{message}\n可点击“刷新二维码”重试")
            self.retry_btn.setEnabled(True)

        # 扫码长轮询最长 120s，用独立线程，避免占满 Qt 的全局线程池
        run_detached(lambda: self.service.wait_login(ticket), done, failed)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._token += 1
        super().closeEvent(event)
