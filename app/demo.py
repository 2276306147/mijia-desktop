"""演示模式：不联网、不登录，用假数据渲染全部界面。

用途：
  * 用户在没有米家账号时预览界面（python run.py --demo）
  * CI / 开发时做无头截图与布局回归
"""

from __future__ import annotations

import time

from app.core.service import (
    ConsumableInfo,
    DeviceInfo,
    MijiaService,
    SceneInfo,
    Snapshot,
)

LAMP_SPEC = {
    "name": "米家台灯",
    "spec_type": "urn:miot-spec-v2:device:light:0000A001:yeelink-lamp4:1",
    "properties": [
        {"name": "on", "description": "Switch Status / 开关", "type": "bool", "rw": "rw",
         "range": None, "value-list": None, "method": {"siid": 2, "piid": 1}},
        {"name": "brightness", "description": "Brightness / 亮度", "type": "uint", "rw": "rw",
         "range": [1, 100, 1], "value-list": None, "method": {"siid": 2, "piid": 2}},
        {"name": "color-temperature", "description": "Color Temperature / 色温", "type": "uint", "rw": "rw",
         "range": [2700, 6500, 1], "value-list": None, "method": {"siid": 2, "piid": 3}},
        {"name": "mode", "description": "Mode / 模式", "type": "uint", "rw": "rw",
         "range": [0, 2, 1],
         "value-list": [
             {"value": 0, "description": "阅读"},
             {"value": 1, "description": "影院"},
             {"value": 2, "description": "专注"},
         ],
         "method": {"siid": 2, "piid": 4}},
    ],
    "actions": [
        {"name": "toggle", "description": "Toggle / 切换开关", "method": {"siid": 2, "aiid": 1}},
        {"name": "set-default", "description": "Set Default / 恢复默认", "method": {"siid": 2, "aiid": 2}},
    ],
}

SENSOR_SPEC = {
    "name": "温湿度传感器",
    "spec_type": "urn:miot-spec-v2:device:sensor-ht:0000A00B:lumi-sensor-ht:1",
    "properties": [
        {"name": "temperature", "description": "Temperature / 温度", "type": "float", "rw": "r",
         "range": [-30, 60, 0.1], "value-list": None, "method": {"siid": 3, "piid": 1}},
        {"name": "relative-humidity", "description": "Relative Humidity / 湿度", "type": "uint", "rw": "r",
         "range": [0, 100, 1], "value-list": None, "method": {"siid": 3, "piid": 2}},
        {"name": "battery-level", "description": "Battery Level / 电量", "type": "uint", "rw": "r",
         "range": [0, 100, 1], "value-list": None, "method": {"siid": 4, "piid": 1}},
    ],
    "actions": [],
}

SPEAKER_SPEC = {
    "name": "小爱音箱",
    "spec_type": "urn:miot-spec-v2:device:speaker:0000A015:xiaomi-lx06:1",
    "properties": [
        {"name": "volume", "description": "Volume / 音量", "type": "uint", "rw": "rw",
         "range": [0, 100, 1], "value-list": None, "method": {"siid": 2, "piid": 1}},
        {"name": "play-status", "description": "Play Status / 播放状态", "type": "uint", "rw": "r",
         "range": [0, 3, 1], "value-list": None, "method": {"siid": 2, "piid": 2}},
    ],
    "actions": [
        {"name": "play-text", "description": "Play Text / 朗读文本", "method": {"siid": 5, "aiid": 1}},
        {"name": "execute-text-directive", "description": "Execute Text Directive / 执行指令",
         "method": {"siid": 5, "aiid": 2}},
    ],
}

SPECS = {
    LAMP_SPEC["spec_type"]: LAMP_SPEC,
    SENSOR_SPEC["spec_type"]: SENSOR_SPEC,
    SPEAKER_SPEC["spec_type"]: SPEAKER_SPEC,
}

DEVICES = [
    DeviceInfo("1000001", "书桌台灯", "yeelink.light.lamp4", LAMP_SPEC["spec_type"], True, "我的家", "书房"),
    DeviceInfo("1000002", "客厅吸顶灯", "yeelink.light.ceiling", LAMP_SPEC["spec_type"], True, "我的家", "客厅"),
    DeviceInfo("1000003", "温湿度传感器", "lumi.sensor_ht", SENSOR_SPEC["spec_type"], False, "我的家", "卧室"),
    DeviceInfo("1000004", "小爱音箱 Pro", "xiaomi.wifispeaker.lx06", SPEAKER_SPEC["spec_type"], True, "我的家", "客厅"),
    DeviceInfo("1000005", "空调伴侣", "lumi.acpartner.mcn04", LAMP_SPEC["spec_type"], True, "我的家", "主卧"),
    DeviceInfo("1000006", "阳台灯", "yeelink.light.lamp4", LAMP_SPEC["spec_type"], True, "老家", "阳台"),
]

VALUES = {
    "1000001": {"on": True, "brightness": 62, "color-temperature": 4200, "mode": 0},
    "1000002": {"on": False, "brightness": 100, "color-temperature": 5000, "mode": 1},
    "1000003": {"temperature": 23.6, "relative-humidity": 48, "battery-level": 87},
    "1000004": {"volume": 35, "play-status": 0},
    "1000005": {"on": True, "brightness": 40, "color-temperature": 3500, "mode": 2},
    "1000006": {"on": True, "brightness": 80, "color-temperature": 3000, "mode": 1},
}


def install_demo(service: MijiaService) -> None:
    """把服务对象替换成假实现（仅进程内，不写任何真实凭证）。"""
    service.config.account = "演示账号"
    service.accounts.list = lambda: ["演示账号", "老家账号"]  # type: ignore[method-assign]
    service.delete_account = lambda name: None  # type: ignore[method-assign]
    service.ensure_account = lambda: "演示账号"  # type: ignore[method-assign]
    service.check_session = lambda: (True, "演示模式：数据为本地假数据，不会连接米家云端")  # type: ignore[method-assign]

    def load_snapshot() -> Snapshot:
        snapshot = Snapshot(
            homes=[{"id": "1", "name": "我的家", "roomlist": []}, {"id": "2", "name": "老家", "roomlist": []}],
            devices=list(DEVICES),
            fetched_at=time.time(),
        )
        service._snapshot = snapshot
        return snapshot

    service.load_snapshot = load_snapshot  # type: ignore[method-assign]
    service.spec_for = lambda device: SPECS.get(device.spec_type)  # type: ignore[method-assign]
    service.cached_spec = lambda device: SPECS.get(device.spec_type)  # type: ignore[method-assign]

    def read_props(device, names=None):
        values = dict(VALUES.get(device.did, {}))
        if names:
            values = {k: v for k, v in values.items() if k in names}
        return values

    def write_prop(device, prop, value):
        VALUES.setdefault(device.did, {})[prop["name"]] = value
        return "成功（演示）"

    def run_action(device, action, params=None):
        return "指令已发送（演示）"

    service.read_props = read_props  # type: ignore[method-assign]
    service.write_prop = write_prop  # type: ignore[method-assign]
    service.run_action = run_action  # type: ignore[method-assign]

    scenes = [
        SceneInfo("scene-1", "回家模式", "1", "我的家"),
        SceneInfo("scene-2", "睡眠模式", "1", "我的家"),
        SceneInfo("scene-3", "离家关灯", "1", "我的家"),
        SceneInfo("scene-4", "阳台浇水提醒", "2", "老家"),
    ]
    service.load_scenes = lambda: list(scenes)  # type: ignore[method-assign]
    service.run_scene = lambda scene: None  # type: ignore[method-assign]

    consumables = [
        ConsumableInfo("1000003", "温湿度传感器", "我的家", "电池", "87%"),
        ConsumableInfo("1000005", "空调伴侣", "我的家", "滤网", "45%"),
        ConsumableInfo("1000001", "书桌台灯", "我的家", "灯珠寿命", "已使用 320 小时"),
    ]
    service.load_consumables = lambda: list(consumables)  # type: ignore[method-assign]

    base = int(time.time()) - 30 * 24 * 3600

    def statistics(did, key, data_type, limit=30, time_start=None, time_end=None):
        scale = 1.8 if did == "1000005" else 0.6
        return [
            (base + i * 86400, round((2.4 + (i % 7) * 0.35 + (i % 3) * 0.6) * scale, 2))
            for i in range(30)
        ]

    service.statistics = statistics  # type: ignore[method-assign]
    service.speakers = lambda: [d for d in DEVICES if "wifispeaker" in d.model]  # type: ignore[method-assign]
    service.speaker_send = lambda device, text, play_only=False, quiet=True: None  # type: ignore[method-assign]
