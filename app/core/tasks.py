"""把阻塞调用丢到线程池，结果回到 Qt 主线程。"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str, str)      # 用户可读消息, 完整 traceback
    done = Signal()


class Worker(QRunnable):
    """执行 fn(*args, **kwargs)，不吞异常。"""

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D102
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - 统一转成 UI 错误
            self.signals.failed.emit(str(exc) or exc.__class__.__name__, traceback.format_exc())
        else:
            self.signals.finished.emit(result)
        finally:
            self.signals.done.emit()


# 保持 Worker 引用，避免 Python GC 提前回收正在运行的 QRunnable
_alive: set[Worker] = set()


def run_async(
    fn: Callable[..., Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[str, str], None] | None = None,
    *args: Any,
    **kwargs: Any,
) -> Worker:
    """在全局线程池执行 fn，回调在主线程触发。"""
    worker = Worker(fn, *args, **kwargs)
    _alive.add(worker)

    def _cleanup() -> None:
        _alive.discard(worker)

    if on_done is not None:
        worker.signals.finished.connect(on_done)
    if on_error is not None:
        worker.signals.failed.connect(on_error)
    worker.signals.done.connect(_cleanup)
    QThreadPool.globalInstance().start(worker)
    return worker
