"""应用包初始化。

PyInstaller 以 ``console=False``（窗口模式）打包后，Windows 上 ``sys.stdout`` /
``sys.stderr`` 会是 ``None``。而 mijiaAPI 的 logger 在导入阶段就调用了
``sys.stdout.isatty()``，直接崩溃。

这个模块会在任何子模块（包括 mijiaAPI）被导入之前执行，先用一个哑流补位，
既避免 ``AttributeError``，也不会让第三方库往不存在的手柄写数据。
"""

from __future__ import annotations

import sys


class _NullStream:
    """最小可用的文本流替身：吞掉所有写入，``isatty()`` 恒为 False。"""

    encoding = "utf-8"
    errors = "replace"

    def write(self, text: str) -> int:  # noqa: D102 - 鸭子类型
        return len(text) if text else 0

    def writelines(self, lines) -> None:  # noqa: D102
        for _ in lines:
            pass

    def flush(self) -> None:  # noqa: D102
        return None

    def isatty(self) -> bool:  # noqa: D102
        return False

    def readable(self) -> bool:  # noqa: D102
        return False

    def writable(self) -> bool:  # noqa: D102
        return True

    def seekable(self) -> bool:  # noqa: D102
        return False

    def close(self) -> None:  # noqa: D102
        return None

    def fileno(self) -> int:  # noqa: D102
        raise OSError("stream has no file descriptor")


def _patch(name: str) -> None:
    if getattr(sys, name, None) is None:
        setattr(sys, name, _NullStream())


for _stream_name in ("stdin", "stdout", "stderr"):
    _patch(_stream_name)

del _stream_name
