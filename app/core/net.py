"""网络层默认配置。

`mijiaAPI` 的业务请求没有设置超时，遇到 DNS 污染或半死代理会让线程永久阻塞，
GUI 的线程池很快被占满。这里统一注入默认超时，一处覆盖所有 requests 调用。
"""

from __future__ import annotations

import functools
import logging

import requests

logger = logging.getLogger("mijia.desktop")

DEFAULT_TIMEOUT: tuple[float, float] = (5.0, 20.0)

_installed = False


def install_default_timeout(timeout: tuple[float, float] = DEFAULT_TIMEOUT) -> None:
    """给 requests 的所有调用加默认超时（幂等）。"""
    global _installed
    if _installed:
        return

    original = requests.sessions.Session.request

    @functools.wraps(original)
    def request(self, method, url, **kwargs):  # type: ignore[no-untyped-def]
        if not kwargs.get("timeout"):
            kwargs["timeout"] = timeout
        return original(self, method, url, **kwargs)

    requests.sessions.Session.request = request  # type: ignore[method-assign]
    _installed = True
    logger.debug("已启用默认请求超时 %s", timeout)
