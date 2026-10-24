"""核心层单元测试（不依赖 Qt 界面，可直接跑）。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 隔离配置目录，避免测试写进真实 %APPDATA% / Application Support
_SCRATCH_HOME = str(ROOT / ".testrun" / "home")
os.environ["HOME"] = _SCRATCH_HOME
os.environ["USERPROFILE"] = _SCRATCH_HOME
os.environ["APPDATA"] = _SCRATCH_HOME
os.environ["XDG_CONFIG_HOME"] = str(ROOT / ".testrun" / "home" / ".config")

import requests  # noqa: E402

from app.core import config as config_module  # noqa: E402
from app.core.config import Config  # noqa: E402
from app.core.logbus import _RedactFilter  # noqa: E402
from app.core.net import DEFAULT_TIMEOUT  # noqa: E402
from app.core.service import (  # noqa: E402
    PROP_BATCH,
    AccountStore,
    DeviceInfo,
    LoginTicket,
    MijiaService,
    ServiceError,
    _check_result,
    _to_number,
)

SCRATCH = ROOT / ".testrun"


def scratch(name: str) -> Path:
    path = SCRATCH / f"{name}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class ConfigTests(unittest.TestCase):
    def test_non_object_json_falls_back_to_defaults(self) -> None:
        root = scratch("cfg-list")
        target = root / "settings.json"
        target.write_text("[]", encoding="utf-8")
        with patch.object(config_module, "CONFIG_ROOT", root), patch.object(
            config_module, "CONFIG_FILE", target
        ):
            cfg = Config.load()
        self.assertEqual(cfg.theme, "light")
        self.assertEqual(cfg.account, "")

    def test_partial_and_unknown_fields(self) -> None:
        root = scratch("cfg-partial")
        target = root / "settings.json"
        target.write_text(json.dumps({"theme": "dark", "unknown_key": 1}), encoding="utf-8")
        with patch.object(config_module, "CONFIG_ROOT", root), patch.object(
            config_module, "CONFIG_FILE", target
        ):
            cfg = Config.load()
        self.assertEqual(cfg.theme, "dark")
        self.assertFalse(hasattr(cfg, "unknown_key"))

    def test_save_and_reload(self) -> None:
        root = scratch("cfg-save")
        target = root / "settings.json"
        with patch.object(config_module, "CONFIG_ROOT", root), patch.object(
            config_module, "CONFIG_FILE", target
        ):
            cfg = Config(theme="dark", auto_refresh=60)
            cfg.save()
            again = Config.load()
        self.assertTrue(target.exists())
        self.assertEqual(again.theme, "dark")
        self.assertEqual(again.auto_refresh, 60)


class AccountStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = AccountStore(scratch("accounts"))

    def test_create_writes_placeholder_and_lists(self) -> None:
        path = self.store.create("客厅平板")
        self.assertTrue(path.exists())
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {})
        self.assertIn("客厅平板", self.store.list())
        self.assertFalse(self.store.has_credentials("客厅平板"))

    def test_duplicate_name_reports_file(self) -> None:
        self.store.create("a/b")
        with self.assertRaises(ServiceError) as ctx:
            self.store.create("a:b")  # 非法字符替换后同名
        self.assertIn("已存在", str(ctx.exception))

    def test_credentials_detection(self) -> None:
        path = self.store.create("主账号")
        path.write_text(json.dumps({"ssecurity": "x", "serviceToken": "y"}), encoding="utf-8")
        self.assertTrue(self.store.has_credentials("主账号"))

    def test_delete_removes_login_file(self) -> None:
        login = self.store.login_path("主账号")
        login.write_text("{}", encoding="utf-8")
        self.store.create("主账号")
        self.store.delete("主账号")
        self.assertFalse(self.store.path("主账号").exists())
        self.assertFalse(login.exists())

    def test_login_path_is_separate(self) -> None:
        self.assertNotEqual(self.store.login_path("a"), self.store.path("a"))


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = scratch("service")
        self.cfg = Config()
        self.cfg.account = "测试"
        self.service = MijiaService(self.cfg)
        self.service.accounts = AccountStore(self.root)
        self.service.accounts.create("测试")

    def test_api_rejects_placeholder(self) -> None:
        with self.assertRaises(ServiceError) as ctx:
            _ = self.service.api
        self.assertIn("尚未登录", str(ctx.exception))

    def test_has_credentials(self) -> None:
        self.assertFalse(self.service.has_credentials())
        self.service.accounts.path("测试").write_text(
            json.dumps({"ssecurity": "s", "serviceToken": "t"}), encoding="utf-8"
        )
        self.assertTrue(self.service.has_credentials())

    def test_read_props_batches_requests(self) -> None:
        props = [
            {"name": f"p{i}", "type": "uint", "rw": "r", "method": {"siid": 1, "piid": i}}
            for i in range(1, 46)
        ]
        spec = {"properties": props, "actions": []}
        device = DeviceInfo("d1", "灯", "m", "spec-x", True, "家", "房")

        class FakeApi:
            def __init__(self) -> None:
                self.calls: list[list[dict]] = []

            def get_devices_prop(self, params):  # noqa: ANN001
                self.calls.append(list(params))
                return [
                    {"siid": p["siid"], "piid": p["piid"], "code": 0, "value": p["piid"]}
                    for p in params
                ]

        fake = FakeApi()
        self.service._api = fake
        self.service._auth_path = self.service.auth_path
        self.service._spec["spec-x"] = spec

        values = self.service.read_props(device)
        self.assertEqual(len(values), 45)
        self.assertEqual(len(fake.calls), 3)
        self.assertTrue(all(len(call) <= PROP_BATCH for call in fake.calls))
        self.assertEqual(values["p1"], 1)
        self.assertEqual(values["p45"], 45)

    def test_wait_login_replaces_placeholder(self) -> None:
        login_path = self.service.accounts.login_path("测试")
        final_path = self.service.accounts.path("测试")

        class FakeFlow:
            def wait(self):  # noqa: ANN201
                login_path.write_text(
                    json.dumps({"ssecurity": "s", "serviceToken": "t"}), encoding="utf-8"
                )

        ticket = LoginTicket(
            refreshed=False, flow=FakeFlow(), login_path=login_path, final_path=final_path
        )
        self.assertTrue(self.service.wait_login(ticket))
        self.assertFalse(login_path.exists())
        self.assertTrue(final_path.exists())
        self.assertTrue(self.service.has_credentials())

    def test_wait_login_failure_keeps_account(self) -> None:
        login_path = self.service.accounts.login_path("测试")
        final_path = self.service.accounts.path("测试")

        class BoomFlow:
            def wait(self):  # noqa: ANN201
                raise RuntimeError("扫码超时")

        ticket = LoginTicket(
            refreshed=False, flow=BoomFlow(), login_path=login_path, final_path=final_path
        )
        with self.assertRaises(RuntimeError):
            self.service.wait_login(ticket)
        self.assertFalse(login_path.exists())
        self.assertTrue(final_path.exists(), "失败后账号的占位文件必须还在")
        self.assertIn("测试", self.service.accounts.list())


class HelperTests(unittest.TestCase):
    def test_check_result(self) -> None:
        self.assertEqual(_check_result({"code": 0}, "x"), "成功")
        self.assertIn("异步", _check_result({"code": 1}, "x"))
        with self.assertRaises(ServiceError):
            _check_result({"code": -1, "message": "设备离线"}, "x")

    def test_to_number(self) -> None:
        self.assertEqual(_to_number(3), 3.0)
        self.assertEqual(_to_number("4.5"), 4.5)
        self.assertEqual(_to_number("[6.5]"), 6.5)
        self.assertIsNone(_to_number("not-a-number"))
        self.assertIsNone(_to_number(None))


class NetworkTests(unittest.TestCase):
    def test_default_timeout_injected(self) -> None:
        captured: dict = {}

        def fake_send(self, request, **kwargs):  # noqa: ANN001
            captured.update(kwargs)
            raise requests.RequestException("intercepted")

        with patch.object(requests.sessions.Session, "send", fake_send):
            with self.assertRaises(requests.RequestException):
                requests.get("http://example.invalid/")
        self.assertEqual(captured.get("timeout"), DEFAULT_TIMEOUT)


class RedactTests(unittest.TestCase):
    def test_auth_data_is_masked(self) -> None:
        import logging

        record = logging.LogRecord(
            "mijiaAPI", logging.DEBUG, __file__, 1,
            "认证数据: {'serviceToken': 'secret'}", None, None,
        )
        _RedactFilter().filter(record)
        self.assertNotIn("secret", record.getMessage())
        self.assertIn("已脱敏", record.getMessage())

    def test_normal_message_untouched(self) -> None:
        import logging

        record = logging.LogRecord("mijiaAPI", logging.INFO, __file__, 1, "请求 URI: /home", None, None)
        _RedactFilter().filter(record)
        self.assertEqual(record.getMessage(), "请求 URI: /home")


if __name__ == "__main__":
    unittest.main()
