"""校验版本号在各处保持一致（app/version.py 为唯一来源）。

CI 在构建前运行，避免出现「安装包叫 1.0.0、程序里显示 1.0.1」这类漂移。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    source = (ROOT / "app" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([\d.]+)"', source)
    if not match:
        print("✗ app/version.py 中找不到 __version__")
        return 1
    version = match.group(1)
    print(f"版本号：{version}")

    problems: list[str] = []

    version_info = (ROOT / "build" / "version_info.txt").read_text(encoding="utf-8")
    if f"'{version}.0'" not in version_info:
        problems.append(f"build/version_info.txt 未更新到 {version}.0")

    installer = (ROOT / "build" / "installer.iss").read_text(encoding="utf-8")
    if f'#define AppVersion "{version}"' not in installer:
        problems.append(f"build/installer.iss 未更新到 {version}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if f"MijiaConsole-Setup-{version}-x64.exe" not in readme:
        problems.append(f"README.md 中的安装包文件名未更新到 {version}")

    if problems:
        for item in problems:
            print(f"✗ {item}")
        return 1

    print("✓ 版本号一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
