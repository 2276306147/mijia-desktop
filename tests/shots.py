"""无头截图：验证界面能构建、能渲染、各页面不崩。

用法：
    QT_QPA_PLATFORM=offscreen python tests/shots.py
输出：
    .shots/*.png
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = str(ROOT / ".testhome")  # 隔离配置，避免污染真实数据
os.environ["XDG_CONFIG_HOME"] = str(ROOT / ".testhome" / ".config")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.config import Config, ensure_dirs  # noqa: E402
from app.core.service import MijiaService  # noqa: E402
from app.demo import install_demo  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402

OUT = ROOT / ".shots"


def pump(app: QApplication, ms: int = 400) -> None:
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ensure_dirs()

    app = QApplication([])
    apply_theme(app, "light")

    config = Config()
    config.account = "演示账号"
    config.theme = "light"
    config.close_to_tray = False

    service = MijiaService(config)
    install_demo(service)

    window = MainWindow(service, config)
    window.resize(1200, 780)
    window.show()
    pump(app, 900)

    pages = ["devices", "scenes", "stats", "consumables", "speaker", "mcp", "settings"]
    for index, name in enumerate(pages):
        window.goto(index)
        pump(app, 700 if name in ("devices", "scenes", "stats") else 250)
        path = OUT / f"{index:02d}-{name}.png"
        window.grab().save(str(path))
        print("saved", path)

    # 深色主题再截一张
    apply_theme(app, "dark")
    window.goto(0)
    pump(app, 500)
    window.grab().save(str(OUT / "07-dark-devices.png"))
    print("saved dark")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
