#!/usr/bin/env python3
"""地震预警模块离线测试。

运行：python3 test_earthquake.py
覆盖：多源解析、时间/数值容错、距离与到达估算、倒计时条数、白名单增删、
跨源事件聚类、播报文案、模拟表单校验，以及模拟预警的「先提醒再倒计时」发送顺序。
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
from datetime import datetime

# ---------------------------------------------------------------------------
# 打桩 astrbot.api（earthquake.py 只依赖 logger；发送时才导入 MessageChain）
# ---------------------------------------------------------------------------
astrbot_mod = types.ModuleType("astrbot")
api_mod = types.ModuleType("astrbot.api")
api_mod.logger = logging.getLogger("test.earthquake")
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


_components_mod = types.ModuleType("astrbot.api.message_components")
_components_mod.Plain = _FakePlain
_components_mod.Image = _FakeImage
sys.modules.setdefault("astrbot.api.message_components", _components_mod)


event_mod.MessageChain = FakeMessageChain
sys.modules.setdefault("astrbot.api.event", event_mod)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import earthquake as eq  # noqa: E402


# ---------------------------------------------------------------------------
# 样例数据
# ---------------------------------------------------------------------------
CENC_EEW = {
    "ID": "b4io6usmdwwyy",
    "EventID": "202610241629.0001",
    "ReportTime": "2026-10-24 16:29:22",
    "ReportNum": 1,
    "OriginTime": "2026-10-24 16:29:22",
    "HypoCenter": "新疆伊犁州巩留县",
    "Latitude": 43.337,
    "Longitude": 82.033,
    "Magnitude": 4.6,
    "Depth": 12,
    "MaxIntensity": 5.9,
}

JMA_EEW = {
    "EventID": "20261024023136",
    "Serial": 3,
    "AnnouncedTime": "2026/10/24 02:32:17",
    "OriginTime": "2026/10/24 02:31:22",
    "Hypocenter": "浦河沖",
    "Latitude": 42.4,
    "Longitude": 142.2,
    "Magnitude": 3.5,
    "Depth": 100,
    "MaxIntensity": "2",
    "isFinal": True,
    "isTraining": False,
    "isAssumption": False,
    "isCancel": False,
}

USGS = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "mag": 4.8,
                "place": "100 km E of Tokyo, Japan",
                "time": 1792850199523,
                "updated": 1792850242032,
                "type": "earthquake",
                "status": "automatic",
            },
            "geometry": {"type": "Point", "coordinates": [140.5, 35.6, 22.0]},
            "id": "us7000abcd",
        }
    ],
}


def test_parse_cenc_eew():
    events = eq.parse_source("cenc_eew", CENC_EEW)
    assert len(events) == 1
    event = events[0]
    assert event.source == "cenc_eew"
    assert event.place == "新疆伊犁州巩留县"
    assert abs(event.magnitude - 4.6) < 1e-6
    assert abs(event.depth_km - 12.0) < 1e-6
    assert abs(event.max_intensity - 5.9) < 1e-6
    assert event.kind == "eew"


def test_parse_jma_skips_training():
    training = dict(JMA_EEW, isTraining=True)
    assert eq.parse_source("jma_eew", training) == []
    events = eq.parse_source("jma_eew", JMA_EEW)
    assert len(events) == 1
    event = events[0]
    assert event.place == "浦河沖"
    assert event.report_num == 3
    assert event.final is True
    assert event.source_label.startswith("日本气象厅")
    # JMA 时间是 JST（UTC+9），不能按北京时间解析
    expected = datetime(2026, 10, 24, 2, 31, 22, tzinfo=eq.JST).timestamp()
    assert abs(event.origin_ts - expected) < 1
    assert eq.format_time(event.origin_ts).endswith("01:31:22")


def test_parse_sc_fj_and_list():
    sc = eq.parse_source(
        "sc_eew",
        {
            "EventID": "202610231016.0001_2",
            "ReportTime": "2026-10-23 10:17:10",
            "ReportNum": 2,
            "OriginTime": "2026-10-23 10:16:58",
            "HypoCenter": "云南丽江市宁蒗县",
            "Latitude": 27.824,
            "Longitude": 100.582,
            "Magunitude": 4.3,
            "Magnitude": 4.3,
            "Depth": 0.0,
            "MaxIntensity": 6.3,
        },
    )
    assert len(sc) == 1 and sc[0].magnitude == 4.3 and sc[0].report_num == 2

    fj = eq.parse_source(
        "fj_eew",
        {
            "EventID": "202609150258_1",
            "OriginTime": "2026-09-15 02:58:20",
            "ReportTime": "2026-09-15 02:58:33",
            "HypoCenter": "福建莆田市秀屿区",
            "Latitude": 25.18,
            "Longitude": 119.39,
            "Magunitude": 3.1,
        },
    )
    assert len(fj) == 1 and fj[0].magnitude == 3.1

    cenc_list = eq.parse_source(
        "cenc_eqlist",
        {
            "No1": {
                "type": "reviewed",
                "EventID": "CD.1",
                "time": "2026-10-24 21:26:31",
                "ReportTime": "2026-10-24 21:32:27",
                "placeName": "西藏那曲市巴青县",
                "magnitude": "3.9",
                "depth": "10",
                "latitude": "32.45",
                "longitude": "93.89",
                "intensity": "5",
            }
        },
    )
    assert len(cenc_list) == 1
    assert cenc_list[0].magnitude == 3.9
    assert cenc_list[0].kind == "report"
    assert cenc_list[0].final is True


def test_parse_usgs():
    events = eq.parse_source("usgs", USGS)
    assert len(events) == 1
    event = events[0]
    assert event.place.startswith("100 km E")
    assert event.magnitude == 4.8
    assert event.depth_km == 22.0
    assert event.latitude == 35.6


def test_time_and_float_fallbacks():
    assert eq.to_float("12km") == 12.0
    assert eq.to_float("") is None
    assert eq.to_float("不明") is None
    assert eq.to_float("M4.6") == 4.6
    assert eq.parse_time("2026-10-24 16:29:22") is not None
    assert eq.parse_time("2026/10/24 02:32:17") is not None
    assert eq.parse_time(1792850199523) == 1792850199.523
    assert eq.parse_time("not-a-time") is None


def test_distance_and_arrival():
    # 北京 -> 唐山附近
    distance = eq.haversine_km(39.9042, 116.4074, 39.6, 118.2)
    assert 140 < distance < 190

    now = time.time()
    event = eq.QuakeEvent(
        source="cenc_eew",
        source_label="测试",
        event_id="t1",
        origin_ts=now,
        report_ts=now,
        place="测试震中",
        latitude=39.6,
        longitude=118.2,
        magnitude=5.0,
        depth_km=10.0,
    )
    epicentral, arrival = eq.estimate_arrival(event, 39.9042, 116.4074, 3.5, now)
    assert abs(epicentral - distance) < 1e-6
    assert arrival > 0
    # 发震 10 秒后才播报，剩余时间应少约 10 秒
    _, later = eq.estimate_arrival(event, 39.9042, 116.4074, 3.5, now + 10)
    assert abs((arrival - later) - 10) < 5


def test_countdown_ticks():
    # 兼容包装：条数 = 计划长度
    assert eq.countdown_ticks(5.2, 60) == 5
    assert eq.countdown_ticks(0.4, 60) == 0
    assert eq.countdown_ticks(None, 60) == 0


def test_countdown_schedule():
    # ≤ 末段：每秒一条，从真实剩余秒数开始
    assert eq.countdown_schedule(5.2, 60) == [5, 4, 3, 2, 1]
    assert eq.countdown_schedule(30, 60) == list(range(30, 0, -1))
    assert eq.countdown_schedule(60, 60) == list(range(60, 0, -1))
    # > 末段：稀疏段（步长≥5）+ 末段每秒
    assert eq.countdown_schedule(61, 60) == [61] + list(range(60, 0, -1))
    assert eq.countdown_schedule(76, 60) == [76, 71, 66, 61] + list(
        range(60, 0, -1)
    )
    # 远事件：稀疏步长自动放大（300s → 每 20s 一条 + 末段 60s）
    schedule = eq.countdown_schedule(300, 60)
    assert schedule[:12] == [300, 280, 260, 240, 220, 200, 180, 160, 140, 120, 100, 80]
    assert schedule[12:] == list(range(60, 0, -1))
    assert len(schedule) == 72
    # interval>1：末段按步长递减
    assert eq.countdown_schedule(76, 60, 2.0)[:6] == [76, 71, 66, 61, 60, 58]
    # 严格递减且首条 = 剩余整秒数
    for sec in (4.2, 30, 61, 76, 90, 300):
        values = eq.countdown_schedule(sec, 60)
        assert all(a > b for a, b in zip(values, values[1:]))
        assert values[0] == int(sec)


def test_whitelist_helpers():
    raw = [
        "aiocqhttp:GroupMessage:10001",
        {
            "umo": "aiocqhttp:GroupMessage:10002",
            "group_id": "10002",
            "platform_id": "aiocqhttp",
            "place": "北京",
            "latitude": 39.9,
            "longitude": 116.4,
            "enabled": True,
        },
        {"umo": "aiocqhttp:GroupMessage:10001", "enabled": False},
    ]
    groups = eq.normalize_groups(raw)
    assert len(groups) == 2
    assert groups[0]["group_id"] == "10001"

    merged = eq.upsert_group(
        groups,
        {
            "umo": "aiocqhttp:GroupMessage:10002",
            "place": "上海",
            "latitude": 31.2,
            "longitude": 121.5,
        },
    )
    target = eq.find_group(merged, "aiocqhttp:GroupMessage:10002")
    assert target["place"] == "上海"
    assert target["latitude"] == 31.2
    assert target["group_id"] == "10002"

    disabled = eq.set_group_enabled(
        merged, "aiocqhttp:GroupMessage:10001", False, operator="tester", timestamp="now"
    )
    assert eq.find_group(disabled, "aiocqhttp:GroupMessage:10001")["enabled"] is False
    assert eq.find_group(disabled, "aiocqhttp:GroupMessage:10001")["enabled_by"] == "tester"

    added = eq.set_group_enabled(
        disabled, "aiocqhttp:GroupMessage:10003", True, operator="tester", timestamp="now"
    )
    assert eq.find_group(added, "aiocqhttp:GroupMessage:10003")["enabled"] is True


def test_event_clustering():
    now = time.time()
    base = {
        "origin_ts": now,
        "latitude": 39.6,
        "longitude": 118.2,
        "magnitude": 5.0,
    }
    event = eq.QuakeEvent(
        source="usgs",
        source_label="USGS",
        event_id="u1",
        origin_ts=now + 60,
        report_ts=now + 60,
        place="唐山",
        latitude=39.62,
        longitude=118.21,
        magnitude=5.3,
        depth_km=10,
    )
    assert eq.events_match(event, base)
    assert not eq.events_match(
        event,
        dict(base, origin_ts=now - 600),
    )
    assert not eq.events_match(
        event,
        dict(base, latitude=20.0, longitude=100.0),
    )
    # 同源同 EventID：震级/震中修订也必须合并
    same_id_record = {
        "source": "jma_eew",
        "event_id": "JMA-1",
        "origin_ts": now,
        "latitude": 27.9,
        "longitude": 140.3,
        "magnitude": 6.5,
    }
    revised = eq.QuakeEvent(
        source="jma_eew",
        source_label="JMA",
        event_id="JMA-1",
        origin_ts=now + 2,
        report_ts=now + 2,
        place="小笠原",
        latitude=27.6,
        longitude=140.1,
        magnitude=7.5,
        depth_km=490,
    )
    assert eq.events_match(revised, same_id_record)


def test_update_logic_guard():
    now = time.time()
    record = {
        "source": "jma_eew",
        "event_id": "upd-1",
        "origin_ts": now,
        "latitude": 27.9,
        "longitude": 140.3,
        "magnitude": 6.5,
        "max_intensity": 2.0,
        "priority": 80,
        "report_num": 13,
        "final": False,
        "alerted": True,
        "last_alert_ts": now - 120,
        "last_update_ts": now - 120,
        "update_count": 0,
    }
    low_final = eq.QuakeEvent(
        source="cenc_eqlist",
        source_label="CENC",
        event_id="cenc-1",
        origin_ts=now,
        report_ts=now,
        place="小笠原",
        latitude=27.9,
        longitude=140.3,
        magnitude=6.5,
        depth_km=480,
        max_intensity=5.0,
        final=True,
    )
    assert eq.EarthquakeService._record_improved(record, low_final, now)
    eq.EarthquakeService._update_record(record, low_final, now)
    # 低优先级源不能覆盖主震级/烈度，但必须合并最终报标志
    assert record["magnitude"] == 6.5
    assert record["max_intensity"] == 2.0
    assert record["final"] is True
    assert not eq.EarthquakeService._record_improved(record, low_final, now + 120)
    # 每个事件最多补发一条更新
    record["update_count"] = 1
    high_revision = eq.QuakeEvent(
        source="cenc_eew",
        source_label="CENC EEW",
        event_id="eew-2",
        origin_ts=now,
        report_ts=now,
        place="小笠原",
        latitude=27.9,
        longitude=140.3,
        magnitude=7.0,
        depth_km=480,
    )
    assert not eq.EarthquakeService._record_improved(
        record, high_revision, now + 300
    )


def test_state_dedup_same_event_id():
    now = time.time()
    raw = {
        "events": [
            {
                "source": "jma_eew",
                "event_id": "dup-1",
                "origin_ts": now,
                "latitude": 27.9,
                "longitude": 140.3,
                "magnitude": 6.5,
                "report_num": 13,
                "final": False,
                "alerted": True,
                "last_alert_ts": now - 120,
                "last_update_ts": now - 120,
                "update_count": 0,
                "last_seen_ts": now - 60,
            },
            {
                "source": "jma_eew",
                "event_id": "dup-1",
                "origin_ts": now + 2,
                "latitude": 27.6,
                "longitude": 140.1,
                "magnitude": 7.5,
                "report_num": 19,
                "final": True,
                "alerted": True,
                "last_alert_ts": now - 60,
                "last_update_ts": now,
                "update_count": 1,
                "last_seen_ts": now,
            },
        ]
    }
    state = eq._normalize_state(raw)
    assert len(state["events"]) == 1
    record = state["events"][0]
    assert record["magnitude"] == 7.5 and record["final"] is True
    assert record["report_num"] == 19 and record["update_count"] == 1
    assert record["last_alert_ts"] == now - 120


def test_map_geometry_helpers():
    # 经纬度 <-> 瓦片坐标往返
    lat, lon = 39.9042, 116.4074
    for zoom in (3, 5, 8):
        x, y = eq._deg2num(lat, lon, zoom)
        back_lat, back_lon = eq._num2deg(x, y, zoom)
        assert abs(back_lat - lat) < 1.0 and abs(back_lon - lon) < 1.0

    # 缩放选择：近点用大 zoom，远点自动缩小
    assert eq._pick_map_zoom((39.6, 118.2), [(39.9, 116.4)], 3) >= 6
    assert eq._pick_map_zoom((27.9, 140.3), [(39.9, 116.4)], 3) <= 5

    if eq._PILImage is None:
        return
    event = eq.QuakeEvent(
        source="cenc_eew",
        source_label="测试",
        event_id="map-1",
        origin_ts=time.time(),
        report_ts=time.time(),
        place="测试震中",
        latitude=39.6,
        longitude=118.2,
        magnitude=5.0,
        depth_km=10,
    )
    # 注入假瓦片，验证拼装与标注绘制
    tile = eq._PILImage.new("RGB", (256, 256), (240, 240, 240))
    for key in list(eq._TILE_CACHE):
        eq._TILE_CACHE.pop(key)
    zoom = eq._pick_map_zoom((39.6, 118.2), [(39.9042, 116.4074)], 3)
    cx, cy = eq._deg2num(39.6, 118.2, zoom)
    for tx in range(int(cx) - 3, int(cx) + 4):
        for ty in range(int(cy) - 3, int(cy) + 4):
            eq._TILE_CACHE[(zoom, tx, ty)] = tile
    img = eq.assemble_epicenter_map(
        event,
        [
            {
                "place": "北京",
                "latitude": 39.9042,
                "longitude": 116.4074,
            }
        ],
        3,
        zoom,
    )
    assert img is not None and img.size == (768, 768)
    px = img.load()
    red = sum(
        1
        for y in range(0, 768, 2)
        for x in range(0, 768, 2)
        if px[x, y][0] > 190 and px[x, y][1] < 90 and px[x, y][2] < 90
    )
    assert red > 10, "震中星标缺失"


def test_map_config_gates():
    with tempfile.TemporaryDirectory() as tmp:
        plugin = FakePlugin(
            {
                "earthquake_enable": True,
                "earthquake_map_enable": False,
                "earthquake_group_whitelist": [
                    {
                        "umo": "aiocqhttp:GroupMessage:70001",
                        "locations": [
                            {"place": "北京", "latitude": 39.9042, "longitude": 116.4074}
                        ],
                    }
                ],
            }
        )
        service = eq.EarthquakeService(plugin, data_dir=tmp)
        assert service._map_enabled() is False
        # 关闭示意图时播报不生成图片（极端演练也遵守开关）
        now = time.time()
        event = eq.QuakeEvent(
            source="cenc_eew",
            source_label="中国地震台网·预警",
            event_id="gate-1",
            origin_ts=now,
            report_ts=now,
            place="测试",
            latitude=39.6,
            longitude=118.2,
            magnitude=5.0,
            depth_km=10,
        )
        target = service._targets(event)[0]
        import unittest.mock as _mock

        with _mock.patch.object(service, "_render_map_for") as render:
            render.return_value = None
            service._render_map_for(target, event)
            render.assert_called_once()


def test_aftershock_suppression():
    now = time.time()
    main = {
        "alerted": True,
        "magnitude": 6.5,
        "origin_ts": now - 3600,
        "latitude": 27.9,
        "longitude": 140.3,
    }
    state = {"events": [main]}

    def event(mag, lat=27.8, lon=140.2, age=60):
        return eq.QuakeEvent(
            source="usgs",
            source_label="USGS",
            event_id=f"aft-{mag}",
            origin_ts=now - age,
            report_ts=now - age,
            place="余震",
            latitude=lat,
            longitude=lon,
            magnitude=mag,
            depth_km=10,
        )

    assert eq.EarthquakeService._is_aftershock(state, event(4.8))
    assert not eq.EarthquakeService._is_aftershock(state, event(5.5))
    assert not eq.EarthquakeService._is_aftershock(state, event(4.8, lat=32.0, lon=145.0))
    assert not eq.EarthquakeService._is_aftershock(state, event(4.8, age=12000))


async def test_late_report_no_update():
    """迟到的速报（发震已超过时效）不能触发新预警或更新。"""
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "earthquake_enable": True,
            "earthquake_max_age_sec": 300,
            "earthquake_update_window_sec": 600,
            "earthquake_group_whitelist": [
                {
                    "umo": "aiocqhttp:GroupMessage:60001",
                    "locations": [
                        {"place": "北京", "latitude": 39.9042, "longitude": 116.4074}
                    ],
                }
            ],
        }
        plugin = FakePlugin(config)
        service = eq.EarthquakeService(plugin, data_dir=tmp)
        now = time.time()
        state = service.store.snapshot()
        state["events"] = [
            {
                "source": "cenc_eqlist",
                "event_id": "late-1",
                "origin_ts": now - 1800,
                "latitude": 39.6,
                "longitude": 118.2,
                "magnitude": 6.5,
                "max_intensity": 5.0,
                "priority": 60,
                "report_num": 1,
                "final": False,
                "alerted": True,
                "last_alert_ts": now - 1700,
                "last_update_ts": now - 1700,
                "update_count": 0,
            }
        ]
        service.store.save(state)
        late_event = eq.QuakeEvent(
            source="cenc_eqlist",
            source_label="CENC",
            event_id="late-1",
            origin_ts=now - 1800,
            report_ts=now,
            place="唐山",
            latitude=39.6,
            longitude=118.2,
            magnitude=6.5,
            depth_km=10,
            max_intensity=5.0,
            final=True,
        )
        calls = {"n": 0}

        async def _no_session():
            return None

        async def _fake_fetch(session, source, timeout=10.0):
            calls["n"] += 1
            return [late_event] if source == "cenc_eqlist" else []

        service._ensure_session = _no_session
        original = eq.fetch_source
        eq.fetch_source = _fake_fetch
        try:
            result = await service.poll_once()
            await asyncio.sleep(0.2)
            assert result["fresh"] == 0, result
            assert result["alerts"] == 0, result
            assert not plugin.sent, plugin.sent
            assert service.store.snapshot()["events"][0]["update_count"] == 0
        finally:
            eq.fetch_source = original
            await service.stop()


def test_formatting():
    event = eq.QuakeEvent(
        source="cenc_eew",
        source_label="中国地震台网·预警",
        event_id="fmt",
        origin_ts=time.time(),
        report_ts=time.time(),
        place="测试震中",
        latitude=39.6,
        longitude=118.2,
        magnitude=5.0,
        depth_km=10,
        max_intensity=6.0,
    )
    notice = eq.format_sim_notice()
    assert "模拟" in notice and "不是真实地震" in notice
    basic = eq.format_basic(event, simulation=True, arrival_sec=12.4, place="北京", distance_km=160)
    assert "模拟" in basic and "M5" in basic and "约 13 秒后" in basic and "北京" in basic
    assert "较强地震" in basic and "演练提示" in basic
    # 倒计时必须是纯数字 + s；到达提示单独一条
    assert eq.format_countdown(12, simulation=True) == "12s"
    final = eq.format_final(False, 5.0)
    assert "已到达" in final and "较强地震" in final
    sim_final = eq.format_final(True, 5.0)
    assert "模拟" in sim_final and "演练" in sim_final and "较强地震" in sim_final
    assert "微震" in eq.guidance_for_magnitude(2.5)
    assert "有感地震" in eq.guidance_for_magnitude(3.5)
    assert "明显震感" in eq.guidance_for_magnitude(4.5)
    assert "较强地震" in eq.guidance_for_magnitude(5.5)
    assert "强烈地震" in eq.guidance_for_magnitude(6.5)
    assert "大地震" in eq.guidance_for_magnitude(7.2)


def test_validate_simulation():
    data = eq.validate_simulation(
        {
            "magnitude": "5.2",
            "place": "测试市",
            "depth": 12,
            "latitude": 39.9,
            "longitude": 116.4,
            "countdown": 10,
        }
    )
    assert data["magnitude"] == 5.2 and data["countdown"] == 10

    city_only = eq.validate_simulation(
        {"magnitude": 5, "place": "", "city": "北京", "countdown": 5}
    )
    assert city_only["city"] == "北京" and city_only["place"] == "北京"

    for bad in (
        {"magnitude": 5, "place": ""},
        {"magnitude": 11, "place": "x"},
        {"magnitude": 5, "place": "x", "depth": -1},
        {"magnitude": 5, "place": "x", "latitude": 39.9},
        {"magnitude": 5, "place": "x", "countdown": 61},
    ):
        try:
            eq.validate_simulation(bad)
        except ValueError:
            continue
        raise AssertionError(f"应当拒绝: {bad}")


class FakePlugin:
    def __init__(self, config):
        self.config = config
        self.context = FakeContext()
        self.sent = self.context.sent

    def is_earthquake_muted(self, umo):
        return False


class FakeContext:
    def __init__(self):
        self.sent = []

    async def send_message(self, umo, chain):
        self.sent.append(
            (
                umo,
                getattr(chain, "text", "")
                or "".join(
                    getattr(c, "text", "") for c in getattr(chain, "chain", [])
                )
                or str(chain),
            )
        )
        return True


async def test_simulation_broadcast_order():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "earthquake_enable": True,
            "earthquake_group_whitelist": [
                {
                    "umo": "aiocqhttp:GroupMessage:20001",
                    "platform_id": "aiocqhttp",
                    "group_id": "20001",
                    "place": "北京",
                    "latitude": 39.9042,
                    "longitude": 116.4074,
                    "enabled": True,
                },
                {
                    "umo": "aiocqhttp:GroupMessage:20002",
                    "platform_id": "aiocqhttp",
                    "group_id": "20002",
                    "place": "唐山",
                    "latitude": 39.6,
                    "longitude": 118.2,
                    "enabled": True,
                },
            ],
            "earthquake_countdown_interval": 0.5,
            "earthquake_broadcast_interval": 0,
            "earthquake_sim_cooldown": 0,
        }
        plugin = FakePlugin(config)
        service = eq.EarthquakeService(plugin, data_dir=tmp)
        result = await service.simulate(
            {
                "magnitude": 5.0,
                "place": "模拟震中",
                "city": "北京",
                "depth": 10,
                "countdown": 1,
            }
        )
        assert result["ok"] and result["groups"] == 2

        # 等待播报任务完成（模拟提醒 + 基本信息 + 1 条倒计时 + 结束）
        for _ in range(40):
            if not service._alert_tasks:
                break
            await asyncio.sleep(0.1)
        sent = plugin.sent
        assert len(sent) >= 8, sent
        first_group = [text for umo, text in sent if umo.endswith("20001")]
        assert first_group, sent
        assert "模拟" in first_group[0] and "不是真实地震" in first_group[0]
        assert "模拟" in first_group[1] and "M5" in first_group[1]
        assert "1s" in first_group
        assert "0s" in first_group
        assert any("已到达" in text and "演练" in text for text in first_group)
        await service.stop()


async def test_poll_dedup_and_source_status():
    """同一事件连续两轮只播报一次，且源状态被记录。"""
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "earthquake_enable": True,
            "earthquake_group_whitelist": [
                {
                    "umo": "aiocqhttp:GroupMessage:30001",
                    "platform_id": "aiocqhttp",
                    "group_id": "30001",
                    "place": "北京",
                    "latitude": 39.9042,
                    "longitude": 116.4074,
                    "enabled": True,
                }
            ],
            "earthquake_min_magnitude": 4.0,
            "earthquake_max_age_sec": 300,
            "earthquake_countdown_interval": 1.0,
            "earthquake_broadcast_interval": 0,
        }
        plugin = FakePlugin(config)
        service = eq.EarthquakeService(plugin, data_dir=tmp)

        async def _no_session():
            return None

        service._ensure_session = _no_session
        now = time.time()
        event = eq.QuakeEvent(
            source="cenc_eew",
            source_label="中国地震台网·预警",
            event_id="poll-1",
            origin_ts=now - 60,
            report_ts=now - 60,
            place="测试震中",
            latitude=39.8,
            longitude=116.3,
            magnitude=5.0,
            depth_km=10,
        )
        calls = {"n": 0}

        async def _fake_fetch(session, source, timeout=10.0):
            calls["n"] += 1
            return [event] if source == "cenc_eew" else []

        original = eq.fetch_source
        eq.fetch_source = _fake_fetch
        try:
            first = await service.poll_once()
            for _ in range(30):
                if not service._alert_tasks:
                    break
                await asyncio.sleep(0.05)
            assert first["alerts"] == 1, first
            assert plugin.sent, "应发送基本信息"
            first_count = len(plugin.sent)

            second = await service.poll_once()
            for _ in range(10):
                if not service._alert_tasks:
                    break
                await asyncio.sleep(0.05)
            assert second["alerts"] == 0, second
            assert len(plugin.sent) == first_count, "重复事件不应再次播报"
            status = service.status()
            assert status["sources"]["cenc_eew"]["ok"] is True
            assert status["last_event"]["event_id"] == "poll-1"
        finally:
            eq.fetch_source = original
            await service.stop()


def test_city_lookup_offline():
    from earthquake_locations import lookup_city

    beijing = lookup_city("北京")
    assert beijing and abs(beijing[0] - 39.9) < 0.2
    tangshan = lookup_city("唐山市")
    assert tangshan and abs(tangshan[0] - 39.63) < 0.2
    # 省名回退到省会
    hebei = lookup_city("河北")
    assert hebei and "石家庄" in hebei[2]
    assert "北京" in lookup_city("北京朝阳")[2]
    assert "唐山" in lookup_city("河北唐山")[2]
    assert lookup_city("不存在的城市名") is None


async def test_city_resolution_offline():
    resolved = await eq.resolve_city_location("唐山")
    assert resolved is not None
    latitude, longitude, display = resolved
    assert 39.4 < latitude < 39.9 and 117.9 < longitude < 118.5
    assert "唐山" in display


def test_config_schema_keys():
    """配置 schema 必须包含地震预警全部键与白名单对象模板。"""
    schema = json.load(open("_conf_schema.json", encoding="utf-8"))
    required = [
        "earthquake_enable",
        "earthquake_poll_interval",
        "earthquake_min_magnitude",
        "earthquake_max_age_sec",
        "earthquake_max_distance_km",
        "earthquake_default_lat",
        "earthquake_default_lon",
        "earthquake_default_place",
        "earthquake_countdown_max_ticks",
        "earthquake_countdown_max_wait_sec",
        "earthquake_countdown_interval",
        "earthquake_s_wave_km_s",
        "earthquake_broadcast_interval",
        "earthquake_http_timeout",
        "earthquake_sim_cooldown",
        "earthquake_group_whitelist",
    ]
    for key in required:
        assert key in schema, key
    whitelist = schema["earthquake_group_whitelist"]
    assert whitelist["type"] == "list"
    assert isinstance(whitelist["items"], dict)
    assert "umo" in whitelist["items"] and "latitude" in whitelist["items"]


def test_multi_location_helpers():
    group = eq.normalize_group_entry(
        {
            "umo": "aiocqhttp:GroupMessage:40001",
            "locations": [
                {"place": "北京", "latitude": 39.9, "longitude": 116.4},
                {"place": "上海", "latitude": 31.2, "longitude": 121.5},
            ],
        }
    )
    assert len(group["locations"]) == 2
    assert group["place"] == "北京"
    updated, added = eq.add_group_location(
        group, {"place": "广州", "latitude": 23.13, "longitude": 113.26}
    )
    assert added and len(updated["locations"]) == 3
    removed_group, removed, removed_loc = eq.remove_group_location(updated, "上海")
    assert removed and removed_loc["place"] == "上海"
    assert len(removed_group["locations"]) == 2
    off = eq.set_group_countdown(removed_group, False)
    assert off["countdown_enabled"] is False
    # 旧版单城市字段自动迁移为 locations
    legacy = eq.normalize_group_entry(
        {
            "umo": "aiocqhttp:GroupMessage:40002",
            "place": "北京",
            "latitude": 39.9,
            "longitude": 116.4,
        }
    )
    assert len(legacy["locations"]) == 1 and "北京" in legacy["locations"][0]["place"]


def test_targets_multiple_locations():
    config = {
        "earthquake_enable": True,
        "earthquake_max_distance_km": 0,
        "earthquake_group_whitelist": [
            {
                "umo": "aiocqhttp:GroupMessage:40003",
                "locations": [
                    {"place": "北京", "latitude": 39.9042, "longitude": 116.4074},
                    {"place": "上海", "latitude": 31.2222, "longitude": 121.4581},
                ],
            }
        ],
    }
    service = eq.EarthquakeService(FakePlugin(config), data_dir=tempfile.mkdtemp())
    now = time.time()
    event = eq.QuakeEvent(
        source="cenc_eew",
        source_label="测试",
        event_id="multi",
        origin_ts=now,
        report_ts=now,
        place="唐山",
        latitude=39.6,
        longitude=118.2,
        magnitude=5.0,
        depth_km=10,
    )
    targets = service._targets(event)
    assert len(targets) == 1
    assert len(targets[0]["locations"]) == 2
    assert "北京" in targets[0]["nearest"]["place"]


async def test_countdown_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "earthquake_enable": True,
            "earthquake_sim_cooldown": 0,
            "earthquake_broadcast_interval": 0,
            "earthquake_countdown_interval": 0.5,
            "earthquake_group_whitelist": [
                {
                    "umo": "aiocqhttp:GroupMessage:40004",
                    "locations": [
                        {"place": "北京", "latitude": 39.9042, "longitude": 116.4074}
                    ],
                    "countdown_enabled": False,
                }
            ],
        }
        plugin = FakePlugin(config)
        service = eq.EarthquakeService(plugin, data_dir=tmp)
        result = await service.simulate(
            {"magnitude": 5.0, "place": "模拟", "city": "北京", "countdown": 1}
        )
        assert result["ok"]
        for _ in range(30):
            if not service._alert_tasks:
                break
            await asyncio.sleep(0.1)
        texts = [text for _, text in plugin.sent]
        assert not any(text in ("1s", "0s") for text in texts), texts
        assert any("逐条倒计时：本群已关闭" in text for text in texts)
        assert any("已到达" in text and "演练" in text for text in texts)
        await service.stop()


async def test_extreme_drill_broadcast():
    """极限演练不出现任何模拟提示，消息与真实预警一致。"""
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "earthquake_enable": True,
            "earthquake_sim_cooldown": 0,
            "earthquake_extreme_cooldown": 300,
            "earthquake_broadcast_interval": 0,
            "earthquake_countdown_interval": 1.0,
            "earthquake_group_whitelist": [
                {
                    "umo": "aiocqhttp:GroupMessage:50001",
                    "locations": [
                        {"place": "北京近郊", "latitude": 39.8, "longitude": 116.5}
                    ],
                    "countdown_enabled": True,
                }
            ],
        }
        plugin = FakePlugin(config)
        service = eq.EarthquakeService(plugin, data_dir=tmp)

        # 缺少确认词 / 缺少震中位置时必须拒绝
        for bad in (
            {"magnitude": 5, "place": "测试", "city": "北京", "extreme": True},
            {"magnitude": 5, "place": "测试", "extreme": True, "extreme_confirm": "极限演练"},
        ):
            try:
                await service.simulate(bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f"极限演练应拒绝: {bad}")

        result = await service.simulate(
            {
                "magnitude": 5.0,
                "place": "测试城市",
                "city": "北京",
                "countdown": 1,
                "extreme": True,
                "extreme_confirm": "极限演练",
            }
        )
        assert result["ok"] and result["extreme"] is True
        for _ in range(80):
            if not service._alert_tasks:
                break
            await asyncio.sleep(0.1)
        texts = [text for _, text in plugin.sent]
        assert texts, "极限演练应有广播"
        assert not any("模拟" in text or "演练" in text for text in texts), texts
        assert texts[0].startswith("🚨 地震预警"), texts[0]
        assert "中国地震台网·预警" in texts[0]
        assert "1s" in texts and "0s" in texts
        assert any("已到达" in text and "较强地震" in text for text in texts)

        # 独立冷却
        try:
            await service.simulate(
                {
                    "magnitude": 5.0,
                    "place": "测试城市",
                    "city": "北京",
                    "countdown": 1,
                    "extreme": True,
                    "extreme_confirm": "极限演练",
                }
            )
        except ValueError as e:
            assert "冷却" in str(e)
        else:
            raise AssertionError("极限演练冷却未生效")
        await service.stop()


TESTS = [
    ("CENC EEW 解析", test_parse_cenc_eew),
    ("JMA 速报过滤与解析", test_parse_jma_skips_training),
    ("川滇/福建/CENC速报解析", test_parse_sc_fj_and_list),
    ("USGS 解析", test_parse_usgs),
    ("时间/数值容错", test_time_and_float_fallbacks),
    ("距离与到达估算", test_distance_and_arrival),
    ("倒计时条数", test_countdown_ticks),
    ("倒计时计划（稀疏+末段）", test_countdown_schedule),
    ("白名单增删与合并", test_whitelist_helpers),
    ("跨源事件聚类", test_event_clustering),
    ("更新去重与主数据保护", test_update_logic_guard),
    ("历史重复记录清理", test_state_dedup_same_event_id),
    ("震中示意图几何与标注", test_map_geometry_helpers),
    ("示意图开关", test_map_config_gates),
    ("余震抑制", test_aftershock_suppression),
    ("迟到速报不更新", lambda: asyncio.run(test_late_report_no_update())),
    ("播报文案", test_formatting),
    ("模拟表单校验", test_validate_simulation),
    ("模拟播报顺序", lambda: asyncio.run(test_simulation_broadcast_order())),
    ("轮询去重与源状态", lambda: asyncio.run(test_poll_dedup_and_source_status())),
    ("城市名离线解析", test_city_lookup_offline),
    ("城市名解析入口", lambda: asyncio.run(test_city_resolution_offline())),
    ("多城市白名单", test_multi_location_helpers),
    ("多城市最近点选择", test_targets_multiple_locations),
    ("关闭倒计时", lambda: asyncio.run(test_countdown_disabled())),
    ("极限演练广播", lambda: asyncio.run(test_extreme_drill_broadcast())),
    ("配置 schema 完整性", test_config_schema_keys),
]


def main_test():
    failed = 0
    for name, fn in TESTS:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print()
    print("=" * 50)
    print(f"结果: {len(TESTS) - failed} 通过, {failed} 失败 (共 {len(TESTS)} 项)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main_test())
