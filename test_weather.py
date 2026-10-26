#!/usr/bin/env python3
"""气象预警模块离线测试。

运行：python3 test_weather.py
覆盖：列表解析、级别过滤、区域匹配（含省级预警反查）、alertid 去重、
命令权限/白名单操作、播报文案。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
import types

# ---------------------------------------------------------------------------
# 打桩 astrbot.api / astrbot.api.event / astrbot.api.message_components
# ---------------------------------------------------------------------------
astrbot_mod = types.ModuleType("astrbot")
api_mod = types.ModuleType("astrbot.api")
api_mod.logger = logging.getLogger("test.weather")
sys.modules.setdefault("astrbot", astrbot_mod)
sys.modules.setdefault("astrbot.api", api_mod)

event_mod = types.ModuleType("astrbot.api.event")


class FakeMessageChain:
    def __init__(self, chain=None):
        self.text = ""
        self.chain = list(chain or [])

    def message(self, text):
        self.text = text
        self.chain.append(("text", text))
        return self


class _FakePlain:
    def __init__(self, text=""):
        self.text = text


class _FakeImage:
    def __init__(self, file=""):
        self.file = file

    @staticmethod
    def fromFileSystem(path):
        return _FakeImage(file=path)


event_mod.MessageChain = FakeMessageChain
sys.modules.setdefault("astrbot.api.event", event_mod)
components_mod = types.ModuleType("astrbot.api.message_components")
components_mod.Plain = _FakePlain
components_mod.Image = _FakeImage
sys.modules.setdefault("astrbot.api.message_components", components_mod)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weather as w  # noqa: E402

# ---------------------------------------------------------------------------
# 样例数据
# ---------------------------------------------------------------------------
ALARM_LIST = {
    "msg": "success",
    "code": 0,
    "data": {
        "page": {
            "pageNo": 1,
            "pageSize": 20,
            "count": 660,
            "list": [
                {
                    "alertid": "34032241600000_20261025234832",
                    "issuetime": "2026/10/25 23:48",
                    "title": "安徽省蚌埠市五河县气象台发布大雾黄色预警信号",
                    "url": "/publish/alarm/34032241600000_20261025234832.html",
                },
                {
                    "alertid": "14088141600000_20261025234500",
                    "issuetime": "2026/10/25 23:45",
                    "title": "山西省运城市永济市气象台发布大风蓝色预警信号",
                    "url": "/publish/alarm/14088141600000_20261025234500.html",
                },
                {
                    "alertid": "34000041600000_20261025234000",
                    "issuetime": "2026/10/25 23:40",
                    "title": "安徽省气象台发布寒潮橙色预警信号",
                    "url": "/publish/alarm/34000041600000_20261025234000.html",
                },
                {
                    "alertid": "44000041600000_20261025233000",
                    "issuetime": "2026/10/25 23:30",
                    "title": "广东省气象台发布台风红色预警信号",
                    "url": "/publish/alarm/44000041600000_20261025233000.html",
                },
                {
                    "alertid": "11000041600000_20261025232000",
                    "issuetime": "2026/10/25 23:20",
                    "title": "北京市气象台发布高温黄色预警信号",
                    "url": "/publish/alarm/11000041600000_20261025232000.html",
                },
            ],
        }
    },
}


def test_parse_warning_list():
    events = w.parse_warning_list(ALARM_LIST)
    assert len(events) == 5
    first = events[0]
    assert first.region == "安徽省蚌埠市五河县"
    assert first.wtype == "大雾" and first.level == "黄色"
    assert first.alert_id == "34032241600000_20261025234832"
    # 蓝色识别
    assert events[1].level == "蓝色" and events[1].wtype == "大风"
    # 省级预警 region 只有省名
    assert events[2].region == "安徽省" and events[2].wtype == "寒潮"
    assert events[2].level == "橙色"
    # 红色 + 台风
    assert events[3].level == "红色" and events[3].wtype == "台风"
    # 直辖市
    assert events[4].region == "北京市"
    # 解析容错
    assert w.parse_warning_list(None) == []
    assert w.parse_warning_item({"title": "无alertid"}) is None


def test_level_filter():
    assert w.level_at_least("蓝色", "黄色") is False
    assert w.level_at_least("黄色", "黄色") is True
    assert w.level_at_least("红色", "橙色") is True
    assert w.level_at_least("橙色", "红色") is False


def test_region_matches():
    cases = [
        ("安徽省蚌埠市五河县", "蚌埠市（安徽省）", True),
        ("安徽省蚌埠市五河县", "五河县", True),
        ("安徽省", "六安", True),          # 裸城市名反查省份
        ("安徽省", "合肥市（安徽省）", True),
        ("山西省运城市永济市", "运城", True),
        ("北京市", "北京", True),
        ("山西省运城市永济市", "六安", False),
        ("广东省", "北京", False),
        ("贵州省黔南布依族苗族自治州长顺县", "长顺县", True),
        ("", "北京", False),
    ]
    for region, place, expect in cases:
        got = w.region_matches(region, place)
        assert got == expect, f"{region} vs {place}: {got} != {expect}"


def test_format_warning_message():
    events = w.parse_warning_list(ALARM_LIST)
    text = w.format_warning_message(events[2], "寒潮影响期间请注意防风保暖。防御指南：1.…")
    assert "气象预警" in text and "寒潮橙色" in text
    assert "区域：安徽省" in text
    assert "中央气象台" in text
    assert "寒潮影响期间" in text


class FakeContext:
    def __init__(self):
        self.sent = []

    async def send_message(self, umo, chain):
        self.sent.append((umo, getattr(chain, "text", str(chain))))
        return True


class FakePlugin:
    def __init__(self, config):
        self.config = config
        self.context = FakeContext()

    def is_weather_muted(self, umo):
        return False


async def test_poll_dedup_and_targeting():
    with tempfile.TemporaryDirectory() as tmp:
        plugin = FakePlugin(
            {
                "weather_enable": True,
                "weather_min_level": "黄色及以上",
                "weather_broadcast_interval": 0,
                "weather_detail_enable": False,
                "weather_group_whitelist": [
                    {
                        "umo": "aiocqhttp:GroupMessage:80001",
                        "locations": [
                            {"place": "六安市（安徽省）", "latitude": 31.7, "longitude": 116.3}
                        ],
                    },
                    {
                        "umo": "aiocqhttp:GroupMessage:80002",
                        "locations": [
                            {"place": "北京", "latitude": 39.9, "longitude": 116.4}
                        ],
                    },
                ],
            }
        )
        service = w.WeatherService(plugin, data_dir=tmp)
        events = w.parse_warning_list(ALARM_LIST)
        # 跳过真实会话创建（fetch 已打桩）
        service._session = object()

        async def _fake_fetch(session, timeout=10.0):
            return events

        async def _no_detail(session, event, timeout=10.0):
            return ""

        original_fetch = w.fetch_warnings
        original_detail = w.fetch_warning_detail
        w.fetch_warnings = _fake_fetch
        w.fetch_warning_detail = _no_detail
        try:
            first = await service.poll_once()
            # 过滤后：蓝(大风)被级别过滤；广东台风/北京高温不命中两群 → 各群命中各自区域
            # 80001 命中：五河大雾(蚌埠∈安徽)、安徽寒潮；80002 命中：北京高温
            assert first["ok"] and first["candidates"] == 5
            targets_1 = [t for t, _ in plugin.context.sent if t.endswith("80001")]
            targets_2 = [t for t, _ in plugin.context.sent if t.endswith("80002")]
            texts_1 = [x for t, x in plugin.context.sent if t.endswith("80001")]
            assert len(texts_1) == 2, texts_1
            assert any("大雾黄色" in x for x in texts_1)
            assert any("寒潮橙色" in x for x in texts_1)
            texts_2 = [x for t, x in plugin.context.sent if t.endswith("80002")]
            assert len(texts_2) == 1 and "高温黄色" in texts_2[0]
            # 蓝色预警不播报
            assert not any("大风蓝色" in x for _, x in plugin.context.sent)

            # 第二轮：全部去重，不再发送
            count_before = len(plugin.context.sent)
            second = await service.poll_once()
            assert second["broadcast"] == 0
            assert len(plugin.context.sent) == count_before
            status = service.status()
            assert status["active_groups"] == 2
            assert status["last_warning"]["wtype"] in ("大雾", "寒潮", "高温")
        finally:
            w.fetch_warnings = original_fetch
            w.fetch_warning_detail = original_detail
            await service.stop()


async def test_disabled_or_empty_skips():
    with tempfile.TemporaryDirectory() as tmp:
        # 全局关闭
        service = w.WeatherService(
            FakePlugin({"weather_enable": False}), data_dir=tmp
        )
        result = await service.poll_once()
        assert result["ok"] is False and "开关" in result["reason"]
        await service.stop()
        # 白名单为空
        service2 = w.WeatherService(
            FakePlugin({"weather_enable": True}), data_dir=tmp
        )
        result2 = await service2.poll_once()
        assert result2["ok"] is False and "白名单" in result2["reason"]
        await service2.stop()


def test_state_store_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        store = w.WeatherStateStore(data_dir=tmp)
        state = store.snapshot()
        state["seen"]["a1"] = {"title": "t", "alerted_ts": time.time(), "groups": 2}
        state["stats"]["broadcasts"] = 1
        store.save(state)
        reloaded = w.WeatherStateStore(data_dir=tmp).snapshot()
        assert reloaded["seen"]["a1"]["groups"] == 2
        assert reloaded["stats"]["broadcasts"] == 1


def test_issuetime_parse():
    ts = w.parse_issuetime("2026/10/25 23:48")
    assert ts > 1.7e9
    assert w.parse_issuetime(None) > 1.7e9


TESTS = [
    ("预警列表解析", test_parse_warning_list),
    ("级别过滤", test_level_filter),
    ("区域匹配（含省级反查）", test_region_matches),
    ("播报文案", test_format_warning_message),
    ("轮询去重与定向", lambda: asyncio.run(test_poll_dedup_and_targeting())),
    ("关闭/空名单跳过", lambda: asyncio.run(test_disabled_or_empty_skips())),
    ("状态持久化", test_state_store_roundtrip),
    ("发布时间解析", test_issuetime_parse),
]


def main_test():
    failed = 0
    for name, fn in TESTS:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print()
    print("=" * 50)
    print(f"结果: {len(TESTS) - failed} 通过, {failed} 失败 (共 {len(TESTS)} 项)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main_test())
