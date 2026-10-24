"""MCP 页：生成客户端配置、检测依赖、给出启动命令。"""

from __future__ import annotations

import importlib.util
import json

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Config
from app.core.service import MijiaService
from app.ui.widgets import badge, label, section_card


class McpPage(QWidget):
    status = Signal(str)

    def __init__(self, service: MijiaService, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.config = config

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        status_card, status_body = section_card("状态", "MCP server 以 stdio 方式由 AI 客户端拉起")
        row = QHBoxLayout()
        row.setSpacing(8)
        has_fastmcp = importlib.util.find_spec("fastmcp") is not None
        row.addWidget(badge("fastmcp 已安装" if has_fastmcp else "fastmcp 未安装", "badgeOk" if has_fastmcp else "badgeWarn"))
        row.addStretch(1)
        status_body.addLayout(row)

        self.path_label = label("—", "faint")
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        status_body.addWidget(self.path_label)

        tip = label(
            "未安装 fastmcp 不影响桌面端使用；要让 AI 客户端控制设备，需要安装 mijiaAPI[mcp]。"
            "推荐用 uvx 免安装运行，客户端会自动下载依赖。",
            "faint",
        )
        tip.setWordWrap(True)
        status_body.addWidget(tip)
        outer.addWidget(status_card)

        config_card, config_body = section_card("客户端配置", "粘贴到 Claude Desktop / Cursor 的 mcpServers 中")
        self.config_view = QPlainTextEdit()
        self.config_view.setReadOnly(True)
        self.config_view.setFixedHeight(236)
        config_body.addWidget(self.config_view)

        actions = QHBoxLayout()
        copy_btn = QPushButton("复制配置")
        copy_btn.setProperty("kind", "primary")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(self._copy)
        open_btn = QPushButton("打开凭证目录")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_auth_dir)
        actions.addWidget(copy_btn)
        actions.addWidget(open_btn)
        actions.addStretch(1)
        config_body.addLayout(actions)
        outer.addWidget(config_card)

        cmd_card, cmd_body = section_card("命令行方式", "在自己的终端里启动（stdio，不要长期占用终端）")
        self.cmd_view = QPlainTextEdit()
        self.cmd_view.setReadOnly(True)
        self.cmd_view.setFixedHeight(82)
        cmd_body.addWidget(self.cmd_view)
        outer.addWidget(cmd_card)

        note = label(
            "提示：MCP 是给 AI 客户端用的，桌面端本身不托管 server；"
            "关闭桌面端不影响已配置好的客户端。",
            "faint",
        )
        note.setWordWrap(True)
        outer.addWidget(note)
        outer.addStretch(1)

        self.refresh_config()

    # ------------------------------------------------------------------

    def reset(self) -> None:
        self.refresh_config()

    def refresh_config(self) -> None:
        path = self.service.auth_path
        path_text = str(path) if path else ""
        self.path_label.setText(("凭证文件：" + path_text) if path_text else "尚未登录")

        server = {
            "command": "uvx",
            "args": ["mijiaAPI[mcp]", "mcp", "-p", path_text] if path_text else ["mijiaAPI[mcp]", "mcp"],
        }
        payload = {"mcpServers": {"mijia-api": server}}
        self.config_view.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
        self.cmd_view.setPlainText(
            'uvx "mijiaAPI[mcp]" mcp' + (f' -p "{path_text}"' if path_text else "")
        )

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.config_view.toPlainText())
        self.status.emit("MCP 配置已复制到剪贴板")

    def _open_auth_dir(self) -> None:
        path = self.service.auth_path
        target = path.parent if path else None
        if target is None or not target.exists():
            self.status.emit("凭证目录还不存在，请先登录")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
