"""业务服务层：账号、认证、设备、场景、统计、耗材、音箱。

这一层不依赖 Qt，可单独测试；UI 只通过这里访问 mijiaAPI。
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mijiaAPI import get_device_info, mijiaAPI
from mijiaAPI.errors import (
    DeviceNotFoundError,
    LoginError,
    MultipleDevicesFoundError,
)
from qrcode import QRCode
from qrcode.constants import ERROR_CORRECT_M

from .config import ACCOUNTS_DIR, Config, default_auth_path
from .net import install_default_timeout

install_default_timeout()

logger = logging.getLogger("mijia.desktop")

_ILLEGAL = re.compile(r'[\\/:*?"<>|]+')

# 单次 get_devices_prop 请求的属性条数上限
PROP_BATCH = 20


class ServiceError(RuntimeError):
    """面向用户的业务错误。"""


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #


@dataclass
class DeviceInfo:
    did: str
    name: str
    model: str
    spec_type: str
    online: bool
    home: str
    room: str
    home_id: str = ""

    @property
    def key(self) -> str:
        return self.did


@dataclass
class SceneInfo:
    scene_id: str
    name: str
    home_id: str
    home: str = ""
    create_time: int = 0


@dataclass
class ConsumableInfo:
    did: str
    device_name: str
    home: str
    description: str
    value: Any
    unit: str = ""


@dataclass
class Snapshot:
    homes: list[dict] = field(default_factory=list)
    devices: list[DeviceInfo] = field(default_factory=list)
    fetched_at: float = 0.0

    def find(self, did: str) -> DeviceInfo | None:
        return next((d for d in self.devices if d.did == did), None)


@dataclass
class LoginTicket:
    """一次扫码登录会话。refreshed=True 表示无需扫码。"""

    refreshed: bool
    flow: "LoginFlow | None" = None
    qr_png: bytes | None = None
    login_url: str | None = None
    login_path: Path | None = None
    final_path: Path | None = None


class LoginFlow:
    def __init__(self, api: mijiaAPI, data: dict) -> None:
        self.api = api
        self.data = data

    def wait(self, timeout: float | None = None) -> dict:
        """阻塞等待扫码完成（内部长轮询，最长 120s）。"""
        return self.api._complete_qr_login(self.data)


# --------------------------------------------------------------------------- #
# 账号
# --------------------------------------------------------------------------- #


class AccountStore:
    def __init__(self, root: Path = ACCOUNTS_DIR) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _filename(name: str) -> str:
        safe = _ILLEGAL.sub("_", name).strip().strip(".") or "account"
        return f"{safe}.json"

    def list(self) -> list[str]:
        names = []
        for path in sorted(self.root.glob("*.json")):
            if path.name.startswith("."):
                continue
            names.append(path.stem)
        return names

    def path(self, name: str) -> Path:
        return self.root / self._filename(name)

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def login_path(self, name: str) -> Path:
        """扫码期间的临时凭证文件；成功后再替换正式文件。"""
        path = self.path(name)
        return path.with_name(f"{path.stem}.login")

    def create(self, name: str, source: Path | None = None) -> Path:
        """新建账号。

        source 为空时写一个 ``{}`` 占位文件——账号列表是靠扫目录得到的，
        没有文件就等于账号不存在（这正是“新建账号后列表没反应”的原因）。
        真正的凭证会在扫码登录成功后覆盖写入。
        """
        target = self.path(name)
        if target.exists():
            raise ServiceError(f"账号“{name}”已存在（文件名 {target.name}）")
        if source is not None and source.exists():
            target.write_bytes(source.read_bytes())
        else:
            target.write_text("{}", encoding="utf-8")
        return target

    def has_credentials(self, name: str) -> bool:
        """是否已有可用凭证（占位文件返回 False）。"""
        path = self.path(name)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (json.JSONDecodeError, OSError):
            return False
        return bool(data.get("ssecurity") and data.get("serviceToken"))

    def delete(self, name: str) -> None:
        for path in (self.path(name), self.login_path(name)):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("删除账号文件失败 %s: %s", path, exc)

    def import_default(self) -> str | None:
        """首次启动时，把 mijiaAPI 的默认凭证导入为“默认账号”。"""
        src = default_auth_path()
        if self.list() or not src.exists():
            return None
        try:
            self.create("默认账号", src)
            return "默认账号"
        except OSError as exc:
            logger.warning("导入默认凭证失败: %s", exc)
            return None


# --------------------------------------------------------------------------- #
# 服务
# --------------------------------------------------------------------------- #


class MijiaService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.accounts = AccountStore()
        self._api: mijiaAPI | None = None
        self._auth_path: Path | None = None
        self._lock = threading.RLock()
        self._spec: dict[str, dict | None] = {}
        self._snapshot = Snapshot()

    # ---------- 生命周期 ----------

    def ensure_account(self) -> str | None:
        names = self.accounts.list()
        if not names:
            imported = self.accounts.import_default()
            if imported:
                self.config.account = imported
                self.config.save()
                names = [imported]
        if self.config.account not in names:
            self.config.account = names[0] if names else ""
            self.config.save()
        return self.config.account or None

    @property
    def account(self) -> str:
        return self.config.account

    @property
    def auth_path(self) -> Path | None:
        if not self.config.account:
            return None
        return self.accounts.path(self.config.account)

    def use_account(self, name: str) -> None:
        if name and not self.accounts.exists(name):
            raise ServiceError(f"账号“{name}”不存在")
        self.config.account = name
        self.config.save()
        self.reset()

    def reset(self) -> None:
        self._api = None
        self._auth_path = None
        self._spec.clear()
        self._snapshot = Snapshot()

    def delete_account(self, name: str) -> None:
        self.accounts.delete(name)
        if self.config.account == name:
            names = self.accounts.list()
            self.config.account = names[0] if names else ""
            self.config.save()
        self.reset()

    # ---------- 认证 ----------

    def has_credentials(self, name: str | None = None) -> bool:
        target = name or self.config.account
        return bool(target) and self.accounts.has_credentials(target)

    @property
    def api(self) -> mijiaAPI:
        path = self.auth_path
        if path is None:
            raise ServiceError("尚未创建账号，请先登录")
        if self._api is not None and self._auth_path == path:
            return self._api
        with self._lock:
            if self._api is not None and self._auth_path == path:
                return self._api
            if not path.exists():
                raise ServiceError("本地没有登录凭证，请先扫码登录")
            try:
                data = json.loads(path.read_text(encoding="utf-8") or "{}")
            except json.JSONDecodeError as exc:
                raise ServiceError("凭证文件已损坏，请重新登录") from exc
            if not isinstance(data, dict) or not data.get("ssecurity") or not data.get("serviceToken"):
                # 占位文件（刚新建、还没扫码）
                raise ServiceError("该账号尚未登录，请先扫码授权")
            try:
                self._api = mijiaAPI(auth_data_path=path)
            except (KeyError, ValueError) as exc:
                raise ServiceError("凭证文件缺少必要字段，请重新登录") from exc
            self._auth_path = path
        return self._api

    def check_session(self) -> tuple[bool, str]:
        """返回 (是否可用, 说明)。会发起一次轻量网络请求。"""
        try:
            api = self.api
        except ServiceError as exc:
            return False, str(exc)
        try:
            if api.available:
                return True, "已登录"
        except Exception as exc:  # noqa: BLE001
            logger.debug("可用性检查异常: %s", exc)
        try:
            api._refresh_token()
            return (True, "Token 已续期") if api.available else (False, "凭证已失效，请重新登录")
        except LoginError as exc:
            return False, f"需要重新登录：{exc}"
        except Exception as exc:  # noqa: BLE001
            return False, f"网络或认证异常：{exc}"

    def start_login(self) -> LoginTicket:
        """获取二维码；不阻塞等待扫码。

        未登录的账号使用 ``*.login`` 临时文件，扫码成功后由 :meth:`wait_login`
        原子替换为正式凭证。这样用户中途取消也不会把账号「弄丢」。
        """
        name = self.config.account
        if not name:
            raise ServiceError("请先创建账号")
        final_path = self.accounts.path(name)
        if self.accounts.has_credentials(name):
            login_path = final_path
        else:
            login_path = self.accounts.login_path(name)
            try:
                login_path.unlink(missing_ok=True)
            except OSError as exc:
                raise ServiceError(f"无法准备登录临时文件：{exc}") from exc

        self.reset()
        api = mijiaAPI(auth_data_path=login_path)
        if not hasattr(api, "_get_qr_login_data") or not hasattr(api, "_complete_qr_login"):
            raise ServiceError("当前 mijiaAPI 版本不支持扫码登录，请安装 5.x 版本")
        data = api._get_qr_login_data()
        if data.get("refreshed"):
            self.reset()
            return LoginTicket(refreshed=True)
        png = make_qr_png(data["loginUrl"])
        return LoginTicket(
            refreshed=False,
            flow=LoginFlow(api, data),
            login_path=login_path,
            final_path=final_path,
            qr_png=png,
            login_url=data.get("qr") or data["loginUrl"],
        )

    def wait_login(self, ticket: LoginTicket) -> bool:
        """阻塞等待扫码（在工作线程调用），成功后把临时凭证换成正式凭证。

        注意：这里**不**调用 ``reset()``，避免在工作线程清空 UI 正在读的状态。
        """
        if ticket.refreshed or ticket.flow is None or ticket.login_path is None:
            return True
        try:
            ticket.flow.wait()
            if ticket.final_path is not None and ticket.login_path != ticket.final_path:
                os.replace(ticket.login_path, ticket.final_path)
            return True
        finally:
            if ticket.final_path is not None and ticket.login_path != ticket.final_path:
                try:
                    ticket.login_path.unlink(missing_ok=True)
                except OSError:
                    pass

    # ---------- 通用 ----------

    @staticmethod
    def _retry(fn, *args, **kwargs):
        """只读请求重试一次（0.4s 退避），写操作不要用。"""
        last: Exception | None = None
        for attempt in range(2):
            try:
                return fn(*args, **kwargs)
            except ServiceError:
                raise
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt == 0:
                    time.sleep(0.4)
        assert last is not None
        raise last

    # ---------- 设备 ----------

    def load_snapshot(self) -> Snapshot:
        api = self.api
        homes = self._retry(api.get_homes_list)
        devices: list[dict] = []
        for home in homes:
            home_id = str(home.get("id") or "")
            if home_id:
                devices.extend(self._retry(api.get_devices_list, home_id=home_id))
        devices.extend(self._retry(api.get_shared_devices_list))

        room_of: dict[str, tuple[str, str]] = {}
        for home in homes:
            for room in home.get("roomlist") or []:
                for did in room.get("dids") or []:
                    room_of[did] = (home.get("name", "未分组"), room.get("name", "未分组"))

        seen: set[str] = set()
        result: list[DeviceInfo] = []
        for dev in devices:
            did = dev.get("did")
            if not did or did in seen:
                continue
            seen.add(did)
            home_name, room_name = room_of.get(did, ("共享设备", "未分组"))
            result.append(
                DeviceInfo(
                    did=did,
                    name=dev.get("name") or dev.get("model") or did,
                    model=dev.get("model", ""),
                    spec_type=dev.get("spec_type") or "",
                    online=bool(dev.get("isOnline", False)),
                    home=home_name,
                    room=room_name,
                    home_id=str(dev.get("home_id", "")),
                )
            )
        result.sort(key=lambda d: (d.home, d.room, d.name))
        self._snapshot = Snapshot(homes=homes, devices=result, fetched_at=time.time())
        return self._snapshot

    @property
    def snapshot(self) -> Snapshot:
        return self._snapshot

    def spec_for(self, device: DeviceInfo) -> dict | None:
        if not device.spec_type:
            return None
        if device.spec_type in self._spec:
            return self._spec[device.spec_type]
        try:
            info = get_device_info(
                device.spec_type,
                cache_path=self.auth_path.parent if self.auth_path else None,
            )
        except Exception as exc:  # noqa: BLE001 - 规格缺失不应中断整个界面
            logger.warning("获取设备规格失败 %s: %s", device.spec_type, exc)
            info = None
        self._spec[device.spec_type] = info
        return info

    def cached_spec(self, device: DeviceInfo) -> dict | None:
        """只读缓存，不触发网络请求（供托盘菜单等即时场景使用）。"""
        if not device.spec_type:
            return None
        return self._spec.get(device.spec_type)

    def readable_props(self, device: DeviceInfo) -> list[dict]:
        spec = self.spec_for(device) or {}
        return [p for p in spec.get("properties", []) if "r" in p.get("rw", "")]

    def read_props(self, device: DeviceInfo, names: list[str] | None = None) -> dict[str, Any]:
        props = self.readable_props(device)
        if names:
            wanted = set(names)
            props = [p for p in props if p["name"] in wanted]
        if not props:
            return {}

        api = self.api
        by_key = {(p["method"]["siid"], p["method"]["piid"]): p for p in props}
        values: dict[str, Any] = {}
        # 属性多的设备（网关/空调伴侣常见 30~60 项）分批读，避免触发服务端参数上限
        for start in range(0, len(props), PROP_BATCH):
            chunk = props[start : start + PROP_BATCH]
            params = [
                {"did": device.did, "siid": p["method"]["siid"], "piid": p["method"]["piid"]}
                for p in chunk
            ]
            raw = self._retry(api.get_devices_prop, params)
            if isinstance(raw, dict):
                raw = [raw]
            for item in raw or []:
                key = (item.get("siid"), item.get("piid"))
                prop = by_key.get(key)
                if prop is None or item.get("code", 0) != 0:
                    continue
                values[prop["name"]] = item.get("value")
        return values

    def write_prop(self, device: DeviceInfo, prop: dict, value: Any) -> str:
        payload = {
            "did": device.did,
            "siid": prop["method"]["siid"],
            "piid": prop["method"]["piid"],
            "value": value,
        }
        result = self.api.set_devices_prop(payload)
        return _check_result(result, "设置属性")

    def run_action(self, device: DeviceInfo, action: dict, params: dict | None = None) -> str:
        payload = {
            "did": device.did,
            "siid": action["method"]["siid"],
            "aiid": action["method"]["aiid"],
        }
        if params:
            payload.update(params)
        result = self.api.run_action(payload)
        return _check_result(result, "执行动作")

    # ---------- 场景 / 耗材 ----------

    def load_scenes(self) -> list[SceneInfo]:
        scenes = self.api.get_scenes_list()
        home_names = {str(h.get("id")): h.get("name", "") for h in self._snapshot.homes}
        out = [
            SceneInfo(
                scene_id=str(s.get("scene_id", "")),
                name=s.get("name", "未命名场景"),
                home_id=str(s.get("home_id", "")),
                home=home_names.get(str(s.get("home_id", "")), ""),
                create_time=int(s.get("create_time") or 0),
            )
            for s in scenes or []
        ]
        out.sort(key=lambda s: (s.home, s.name))
        return out

    def run_scene(self, scene: SceneInfo) -> None:
        ok = self.api.run_scene(scene.scene_id, scene.home_id)
        if ok is False:
            raise ServiceError(f"场景“{scene.name}”执行失败")

    def load_consumables(self) -> list[ConsumableInfo]:
        items = self.api.get_consumable_items()
        home_names = {str(h.get("id")): h.get("name", "") for h in self._snapshot.homes}
        out: list[ConsumableInfo] = []
        for item in items or []:
            details = item.get("details")
            if isinstance(details, list):
                details = details[0] if details else {}
            details = details or {}
            out.append(
                ConsumableInfo(
                    did=str(item.get("did", "")),
                    device_name=item.get("name", ""),
                    home=home_names.get(str(item.get("home_id", "")), ""),
                    description=str(details.get("description") or "耗材"),
                    value=details.get("value"),
                    unit=str(details.get("unit") or ""),
                )
            )
        return out

    # ---------- 统计 ----------

    def statistics(
        self,
        did: str,
        key: str,
        data_type: str,
        limit: int = 30,
        time_start: int | None = None,
        time_end: int | None = None,
    ) -> list[tuple[int, float]]:
        end = int(time_end or time.time())
        start = int(time_start or (end - 30 * 24 * 3600))
        raw = self.api.get_statistics(
            {
                "did": did,
                "key": key,
                "data_type": data_type,
                "limit": limit,
                "time_start": start,
                "time_end": end,
            }
        )
        if isinstance(raw, dict):
            raw = [raw]
        points: list[tuple[int, float]] = []
        for row in raw or []:
            ts = row.get("time")
            num = _to_number(row.get("value"))
            if ts is None or num is None:
                continue
            points.append((int(ts), num))
        points.sort(key=lambda p: p[0])
        return points

    # ---------- 音箱 ----------

    def speakers(self) -> list[DeviceInfo]:
        return [d for d in self._snapshot.devices if "xiaomi.wifispeaker" in d.model]

    def speaker_send(self, device: DeviceInfo, text: str, *, play_only: bool = False, quiet: bool = True) -> None:
        spec = self.spec_for(device)
        if not spec:
            raise ServiceError("无法获取该音箱的规格信息")
        action_name = "play-text" if play_only else "execute-text-directive"
        action = next((a for a in spec.get("actions", []) if a["name"] == action_name), None)
        if action is None:
            raise ServiceError(f"该设备不支持 {action_name}")
        params = {"in": [text] if play_only else [text, 1 if quiet else 0]}
        self.run_action(device, action, params)


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #


def _check_result(result: Any, action: str) -> str:
    if isinstance(result, list):
        result = result[0] if result else {}
    code = int((result or {}).get("code", 0) or 0)
    message = (result or {}).get("message") or ""
    if code == 0:
        return message or "成功"
    if code == 1:
        # 网关已接收，结果异步，不算失败
        return "指令已发送（设备异步执行）"
    raise ServiceError(message or f"{action}失败（code {code}）")


def _to_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            try:
                return float(text)
            except ValueError:
                return None
        if isinstance(parsed, list):
            return float(parsed[0]) if parsed and isinstance(parsed[0], (int, float)) else None
        if isinstance(parsed, (int, float)):
            return float(parsed)
    return None


def make_qr_png(data: str, box_size: int = 8, border: int = 2) -> bytes:
    qr = QRCode(error_correction=ERROR_CORRECT_M, box_size=box_size, border=border)
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#111827", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def find_device(snapshot: Snapshot, name_or_did: str) -> DeviceInfo:
    for dev in snapshot.devices:
        if dev.did == name_or_did:
            return dev
    matches = [d for d in snapshot.devices if d.name == name_or_did]
    if not matches:
        raise DeviceNotFoundError(name_or_did)
    if len(matches) > 1:
        raise MultipleDevicesFoundError(f"存在多个名为“{name_or_did}”的设备，请改用 did")
    return matches[0]


__all__ = [
    "AccountStore",
    "ConsumableInfo",
    "DeviceInfo",
    "LoginFlow",
    "LoginTicket",
    "MijiaService",
    "SceneInfo",
    "ServiceError",
    "Snapshot",
    "find_device",
    "make_qr_png",
]
