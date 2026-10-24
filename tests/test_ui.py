"""界面层冒烟测试（无头渲染）。

需要 PySide6；CI 与本地都通过 QT_QPA_PLATFORM=offscreen 运行。
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 必须在导入 app.core.config 之前设置，才能隔离配置目录
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH_HOME = str(ROOT / ".testrun" / "home")
os.environ["HOME"] = _SCRATCH_HOME
os.environ["USERPROFILE"] = _SCRATCH_HOME
os.environ["APPDATA"] = _SCRATCH_HOME
os.environ["XDG_CONFIG_HOME"] = str(ROOT / ".testrun" / "home" / ".config")
os.environ["MIJIA_DESKTOP_SKIP_BOOTSTRAP"] = "1"

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from app.core.config import Config, ensure_dirs  # noqa: E402
from app.core.service import MijiaService  # noqa: E402
from app.demo import install_demo  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.pages.consumables import _percent  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402
from app.ui.widgets import PropertyRow  # noqa: E402


def pump(app: QApplication, ms: int = 200) -> None:
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


class PercentTests(unittest.TestCase):
    def test_only_trustworthy_percent(self) -> None:
        self.assertEqual(_percent("87%"), 87)
        self.assertEqual(_percent("45", "%"), 45)
        self.assertIsNone(_percent("30"))          # 30 天不该画成 30%
        self.assertIsNone(_percent("已使用 320 小时"))
        self.assertIsNone(_percent("120", "%"))    # 超过 100 不算


class PropertyRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app, "light")

    def test_readonly_enum_shows_description(self) -> None:
        prop = {
            "name": "mode",
            "description": "Mode / 模式",
            "type": "uint",
            "rw": "r",
            "range": [0, 2, 1],
            "value-list": [
                {"value": 0, "description": "阅读"},
                {"value": 1, "description": "影院"},
            ],
            "method": {"siid": 2, "piid": 4},
        }
        row = PropertyRow(prop, 1)
        self.assertIsInstance(row.control, QLabel)
        self.assertEqual(row.control.text(), "影院")

    def test_writable_bool_uses_switch(self) -> None:
        prop = {
            "name": "on",
            "description": "Switch / 开关",
            "type": "bool",
            "rw": "rw",
            "method": {"siid": 2, "piid": 1},
        }
        row = PropertyRow(prop, True)
        self.assertIsNotNone(row._switch)
        self.assertTrue(row._switch.isChecked())


class MainWindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app, "light")
        ensure_dirs()

    def test_all_pages_render(self) -> None:
        cfg = Config()
        cfg.account = "演示账号"
        service = MijiaService(cfg)
        install_demo(service)

        window = MainWindow(service, cfg)
        window.resize(1120, 760)
        window.show()
        pump(self.app, 400)

        for index in range(7):
            window.goto(index)
            pump(self.app, 250)

        self.assertEqual(window.stack.count(), 7)
        self.assertEqual(window.stack.currentIndex(), 6)

        window.hide()
        pump(self.app, 100)


if __name__ == "__main__":
    unittest.main()
