"""地震预警：多源聚合、群聊白名单与倒计时播报。

数据源（公开、免 Key）：
- 中国地震台网 CENC 预警（Wolfx 镜像）
- 四川/云南地震预警（Wolfx 镜像）
- 福建地震预警（Wolfx 镜像）
- 日本气象厅 紧急地震速报（Wolfx 镜像）
- 中国地震台网 CENC 地震速报列表（Wolfx 镜像）
- USGS 最近一小时全球地震

设计要点：
- 白名单存放在插件配置 ``earthquake_group_whitelist``（list[dict]），由群主/
  群管理员用 ``/地震 开启`` 写入，也可以在插件配置页直接查看/编辑/删除。
- 轮询任务只在「全局开关开启 + 至少一个白名单群」时请求上游；源之间并行，
  单源失败不影响其他源。
- 同一地震可能同时出现在多个源：按「发震时间 ±3 分钟、震中 200km 内、
  震级差 ≤1.0」聚类，只播报一次；后续显著增强（震级/烈度 +0.5 或更高优先级
  源更新）发送一条「预警更新」，不重开倒计时。
- 到达时间按白名单群的经纬度、震源深度与 S 波速度估算；播报先发基本信息，
  再对每个群按各自剩余秒数逐条发送倒计时（最多 N 条）。
"""

from __future__ import annotations

import asyncio
import copy
import json
import math
import os
import re
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:  # pragma: no cover - 测试环境可能未安装 aiohttp
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

from astrbot.api import logger

try:  # 包内导入 / 测试脚本顶层导入
    from .earthquake_locations import lookup_city
except ImportError:  # pragma: no cover
    from earthquake_locations import lookup_city

_GEO_URL = "https://nominatim.openstreetmap.org/search"
_GEO_UA = (
    "CurrentCortex-Earthquake/1.0 "
    "(AstrBot plugin; +https://github.com/backrooms-yrc/astrbot_plugin_currentcortex)"
)
_CITY_CACHE: Dict[str, Optional[Tuple[float, float, str]]] = {}
_GEO_LOCK = asyncio.Lock()
_GEO_LAST_TS = 0.0

# 与 main.py 的插件数据目录保持一致（避免循环导入，这里重复常量）
PLUGIN_DATA_DIR = os.path.join("data", "plugin_data", "astrbot_plugin_currentcortex")
STATE_FILENAME = "currentcortex_earthquake.json"
CST = timezone(timedelta(hours=8))
JST = timezone(timedelta(hours=9))

# 数据源定义。priority 越大越优先；kind=eew 为预警，report 为正式速报。
SOURCE_DEFS: Dict[str, Dict[str, Any]] = {
    "cenc_eew": {
        "label": "中国地震台网·预警",
        "url": "https://api.wolfx.jp/cenc_eew.json",
        "priority": 100,
        "kind": "eew",
    },
    "sc_eew": {
        "label": "四川/云南地震预警",
        "url": "https://api.wolfx.jp/sc_eew.json",
        "priority": 90,
        "kind": "eew",
    },
    "fj_eew": {
        "label": "福建地震预警",
        "url": "https://api.wolfx.jp/fj_eew.json",
        "priority": 85,
        "kind": "eew",
    },
    "jma_eew": {
        "label": "日本气象厅·紧急地震速报",
        "url": "https://api.wolfx.jp/jma_eew.json",
        "priority": 80,
        "kind": "eew",
    },
    "cenc_eqlist": {
        "label": "中国地震台网·速报",
        "url": "https://api.wolfx.jp/cenc_eqlist.json",
        "priority": 60,
        "kind": "report",
    },
    "usgs": {
        "label": "USGS 全球地震",
        "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson",
        "priority": 50,
        "kind": "report",
    },
}

_UMO_SEP = ":"
_GROUP_MESSAGE = "GroupMessage"
_DEFAULT_STATE: Dict[str, Any] = {
    "version": 1,
    "events": [],
    "last_event": None,
    "last_simulation": None,
    "stats": {"alerts": 0, "simulations": 0, "polls": 0, "last_poll_ts": 0.0},
    "sources": {},
    "sim_last_ts": 0.0,
    "extreme_last_ts": 0.0,
}


# --------------------------------------------------------------------------- #
# 基础类型与纯函数
# --------------------------------------------------------------------------- #


@dataclass
class QuakeEvent:
    """归一化后的地震事件。"""

    source: str
    source_label: str
    event_id: str
    origin_ts: float
    report_ts: float
    place: str
    latitude: float
    longitude: float
    magnitude: float
    depth_km: float = 10.0
    max_intensity: Optional[float] = None
    report_num: int = 1
    kind: str = "eew"
    final: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def priority(self) -> int:
        return int(SOURCE_DEFS.get(self.source, {}).get("priority", 0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "source_label": self.source_label,
            "event_id": self.event_id,
            "origin_ts": self.origin_ts,
            "report_ts": self.report_ts,
            "origin_time": format_time(self.origin_ts),
            "place": self.place,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "magnitude": self.magnitude,
            "depth_km": self.depth_km,
            "max_intensity": self.max_intensity,
            "report_num": self.report_num,
            "kind": self.kind,
            "final": self.final,
        }


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """宽松地把上游字段转为 float（兼容 "12km"、"M4.6"、"" 等）。"""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nan", "-", "不明", "unknown"}:
        return default
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return default
    try:
        return float(match.group())
    except ValueError:
        return default


def parse_time(value: Any, tz: timezone = CST) -> Optional[float]:
    """解析上游时间：支持 epoch 秒/毫秒、ISO、两种日期格式（无时区按 tz）。"""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        stamp = float(value)
        if stamp > 1e11:  # 毫秒
            stamp /= 1000.0
        return stamp if stamp > 0 else None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return parse_time(int(text), tz)
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=tz).timestamp()
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tz)
        return parsed.timestamp()
    except ValueError:
        return None


def format_time(stamp: Optional[float]) -> str:
    if not stamp:
        return "-"
    try:
        return datetime.fromtimestamp(float(stamp), CST).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """两点球面距离（km）。"""
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(a)))


def estimate_arrival(
    event: QuakeEvent,
    latitude: float,
    longitude: float,
    s_wave_km_s: float = 3.5,
    now: Optional[float] = None,
) -> Tuple[float, float]:
    """估算接收点的震中距（km）与剩余到达秒数（S 波）。

    剩余秒数 = 震源距 / S 波速度 - 已过去时间，最小 0。负值表示可能已到达。
    """
    distance = haversine_km(event.latitude, event.longitude, latitude, longitude)
    hypocentral = math.sqrt(distance * distance + max(0.0, event.depth_km) ** 2)
    travel = hypocentral / max(0.5, float(s_wave_km_s or 3.5))
    elapsed = max(0.0, float(now if now is not None else time.time()) - event.origin_ts)
    return distance, max(0.0, travel - elapsed)


def countdown_ticks(arrival_sec: Optional[float], max_ticks: int) -> int:
    """倒计时条数：不超过剩余整秒数，也不超过配置上限。"""
    if arrival_sec is None:
        return 0
    try:
        seconds = float(arrival_sec)
    except (TypeError, ValueError):
        return 0
    if seconds <= 0:
        return 0
    return max(0, min(int(math.floor(seconds)), max(1, int(max_ticks))))


def _make_event(
    source: str,
    event_id: Any,
    origin: Any,
    report: Any,
    place: Any,
    latitude: Any,
    longitude: Any,
    magnitude: Any,
    depth: Any,
    intensity: Any = None,
    report_num: Any = 1,
    kind: Optional[str] = None,
    final: bool = False,
    raw: Optional[Dict[str, Any]] = None,
) -> Optional[QuakeEvent]:
    spec = SOURCE_DEFS.get(source)
    if spec is None:
        return None
    origin_ts = parse_time(origin)
    report_ts = parse_time(report) or origin_ts
    lat = to_float(latitude)
    lon = to_float(longitude)
    mag = to_float(magnitude)
    if origin_ts is None or lat is None or lon is None or mag is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    depth_km = to_float(depth, 10.0)
    if depth_km is None or depth_km < 0:
        depth_km = 10.0
    try:
        num = max(1, int(to_float(report_num, 1) or 1))
    except (TypeError, ValueError):
        num = 1
    return QuakeEvent(
        source=source,
        source_label=str(spec["label"]),
        event_id=str(event_id or f"{source}-{int(origin_ts)}"),
        origin_ts=origin_ts,
        report_ts=report_ts,
        place=str(place or "未知震中").strip() or "未知震中",
        latitude=lat,
        longitude=lon,
        magnitude=mag,
        depth_km=depth_km,
        max_intensity=to_float(intensity),
        report_num=num,
        kind=kind or str(spec.get("kind") or "eew"),
        final=bool(final),
        raw=dict(raw or {}),
    )


def _parse_cenc_eew(data: Any) -> List[QuakeEvent]:
    if not isinstance(data, dict):
        return []
    event = _make_event(
        "cenc_eew",
        data.get("EventID") or data.get("ID"),
        data.get("OriginTime") or data.get("ReportTime"),
        data.get("ReportTime"),
        data.get("HypoCenter") or data.get("placeName") or data.get("location"),
        data.get("Latitude"),
        data.get("Longitude"),
        data.get("Magnitude") or data.get("Magunitude"),
        data.get("Depth"),
        data.get("MaxIntensity") or data.get("intensity"),
        data.get("ReportNum"),
        final=str(data.get("type", "")).lower() == "reviewed" or bool(data.get("Final")),
        raw=data,
    )
    return [event] if event else []


def _parse_sc_eew(data: Any) -> List[QuakeEvent]:
    if not isinstance(data, dict):
        return []
    event = _make_event(
        "sc_eew",
        data.get("EventID") or data.get("ID"),
        data.get("OriginTime") or data.get("ReportTime"),
        data.get("ReportTime"),
        data.get("HypoCenter") or data.get("placeName"),
        data.get("Latitude"),
        data.get("Longitude"),
        data.get("Magnitude") or data.get("Magunitude"),
        data.get("Depth"),
        data.get("MaxIntensity") or data.get("EstimatedIntensity"),
        data.get("ReportNum"),
        final=bool(data.get("Final")),
        raw=data,
    )
    return [event] if event else []


def _parse_fj_eew(data: Any) -> List[QuakeEvent]:
    if not isinstance(data, dict):
        return []
    event = _make_event(
        "fj_eew",
        data.get("EventID") or data.get("ID"),
        data.get("OriginTime") or data.get("ReportTime"),
        data.get("ReportTime"),
        data.get("HypoCenter") or data.get("placeName"),
        data.get("Latitude"),
        data.get("Longitude"),
        data.get("Magnitude") or data.get("Magunitude"),
        10.0,
        data.get("MaxIntensity"),
        data.get("ReportNum"),
        final=bool(data.get("Final")),
        raw=data,
    )
    return [event] if event else []


def _parse_jma_eew(data: Any) -> List[QuakeEvent]:
    if not isinstance(data, dict):
        return []
    if data.get("isTraining") or data.get("isAssumption") or data.get("isCancel"):
        return []
    event = _make_event(
        "jma_eew",
        data.get("EventID"),
        parse_time(data.get("OriginTime"), tz=JST),
        parse_time(data.get("AnnouncedTime") or data.get("ReportTime"), tz=JST),
        data.get("Hypocenter") or data.get("PlaceName"),
        data.get("Latitude"),
        data.get("Longitude"),
        data.get("Magnitude") or data.get("Magunitude"),
        data.get("Depth"),
        data.get("MaxIntensity"),
        data.get("Serial") or data.get("ReportNum"),
        final=bool(data.get("isFinal")),
        raw=data,
    )
    return [event] if event else []


def _parse_cenc_eqlist(data: Any) -> List[QuakeEvent]:
    if not isinstance(data, dict):
        return []
    events: List[QuakeEvent] = []
    for key, row in data.items():
        if not isinstance(row, dict):
            continue
        event = _make_event(
            "cenc_eqlist",
            row.get("EventID") or key,
            row.get("time"),
            row.get("ReportTime") or row.get("time"),
            row.get("placeName") or row.get("location"),
            row.get("latitude"),
            row.get("longitude"),
            row.get("magnitude"),
            row.get("depth"),
            row.get("intensity"),
            1,
            final=str(row.get("type", "")).lower() == "reviewed",
            raw=row,
        )
        if event:
            events.append(event)
    return events


def _parse_usgs(data: Any) -> List[QuakeEvent]:
    if not isinstance(data, dict):
        return []
    events: List[QuakeEvent] = []
    for feature in data.get("features") or []:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            continue
        if props.get("type") not in (None, "earthquake"):
            continue
        event = _make_event(
            "usgs",
            feature.get("id"),
            props.get("time"),
            props.get("updated") or props.get("time"),
            props.get("place") or props.get("title"),
            coords[1],
            coords[0],
            props.get("mag"),
            coords[2] if len(coords) > 2 else 10.0,
            props.get("mmi") or props.get("cdi"),
            1,
            final=str(props.get("status", "")).lower() == "reviewed",
            raw=props,
        )
        if event:
            events.append(event)
    return events


_PARSERS: Dict[str, Callable[[Any], List[QuakeEvent]]] = {
    "cenc_eew": _parse_cenc_eew,
    "sc_eew": _parse_sc_eew,
    "fj_eew": _parse_fj_eew,
    "jma_eew": _parse_jma_eew,
    "cenc_eqlist": _parse_cenc_eqlist,
    "usgs": _parse_usgs,
}


def parse_source(source: str, payload: Any) -> List[QuakeEvent]:
    """把某个上游的原始 JSON 解析成归一化事件列表。"""
    parser = _PARSERS.get(source)
    if parser is None:
        return []
    try:
        return parser(payload)
    except Exception as e:  # noqa: BLE001 - 上游字段异常不应拖垮轮询
        logger.warning(f"[Earthquake] 解析 {source} 失败: {e}")
        return []


async def fetch_source(session: Any, source: str, timeout: float = 10.0) -> List[QuakeEvent]:
    """请求单个源并解析。失败抛异常，由调用方记录源状态。"""
    spec = SOURCE_DEFS.get(source)
    if spec is None:
        return []
    if aiohttp is None:
        raise RuntimeError("aiohttp 未安装")
    async with session.get(
        str(spec["url"]), timeout=aiohttp.ClientTimeout(total=timeout)
    ) as resp:
        text = await resp.text()
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
    payload = json.loads(text.lstrip("\ufeff"))
    return parse_source(source, payload)


def _pick_nominatim(rows: Any) -> Optional[Tuple[float, float, str]]:
    """从 Nominatim 结果中优先选行政区边界，避免选中山峰/车站等同名地点。"""
    if not isinstance(rows, list):
        return None
    ranked: List[Tuple[int, Dict[str, Any], float, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        lat = to_float(row.get("lat"))
        lon = to_float(row.get("lon"))
        if lat is None or lon is None:
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            continue
        cls = str(row.get("class") or "")
        typ = str(row.get("type") or "")
        if cls == "boundary" and typ == "administrative":
            rank = 0
        elif cls == "place":
            rank = 1
        elif cls == "boundary":
            rank = 2
        else:
            rank = 3
        ranked.append((rank, row, lat, lon))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    _, row, lat, lon = ranked[0]
    display = str(row.get("display_name") or row.get("name") or "").strip()
    parts = [part.strip() for part in display.split(",") if part.strip()]
    if parts:
        display = "，".join(parts[:2])
    if not display:
        display = str(row.get("name") or "").strip() or "已解析位置"
    return lat, lon, display[:80]


async def resolve_city_location(
    query: str, timeout: float = 10.0
) -> Optional[Tuple[float, float, str]]:
    """把城市/区县名解析为 (纬度, 经度, 展示名)。

    优先查内置地级市表（离线、秒回）；未收录的区县/境外地名调用
    OpenStreetMap Nominatim（免 Key，按使用政策限制 1 次/秒并缓存）。
    找不到或网络失败返回 None。
    """
    text = str(query or "").strip()
    if not text:
        return None
    cached = _CITY_CACHE.get(text)
    if cached is not None:
        return cached
    offline = lookup_city(text)
    if offline is not None:
        _CITY_CACHE[text] = offline
        return offline
    if aiohttp is None:
        return None

    global _GEO_LAST_TS
    async with _GEO_LOCK:
        cached = _CITY_CACHE.get(text)
        if cached is not None:
            return cached
        wait = 1.1 - (time.monotonic() - _GEO_LAST_TS)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with aiohttp.ClientSession(
                headers={"User-Agent": _GEO_UA}
            ) as session:
                async with session.get(
                    _GEO_URL,
                    params={
                        "q": text,
                        "format": "json",
                        "limit": 5,
                        "accept-language": "zh-CN",
                        "addressdetails": 1,
                    },
                    timeout=aiohttp.ClientTimeout(total=max(3.0, timeout)),
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise RuntimeError(f"HTTP {resp.status}")
            rows = json.loads(body.lstrip("\ufeff"))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Earthquake] 城市解析失败（{text}）: {e}")
            return None
        finally:
            _GEO_LAST_TS = time.monotonic()
        result = _pick_nominatim(rows)
        if result is not None:
            _CITY_CACHE[text] = result
        return result


# --------------------------------------------------------------------------- #
# 白名单（配置中的 list[dict]）与事件聚类
# --------------------------------------------------------------------------- #


def parse_umo(umo: str) -> Tuple[str, str, str]:
    """把 ``platform:GroupMessage:群号`` 拆为 (platform_id, type, group_id)。"""
    parts = str(umo or "").split(_UMO_SEP, 2)
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    return "", "", str(umo or "")


MAX_GROUP_LOCATIONS = 20


def normalize_location_entry(entry: Any) -> Optional[Dict[str, Any]]:
    """规范化一个接收城市：支持城市名、字符串或 {place,latitude,longitude}。

    离线表能解析的城市名会补全坐标；解析不了的返回 None（命令层会再走在线解析）。
    """
    if isinstance(entry, str):
        resolved = lookup_city(entry)
        if resolved is None:
            return None
        latitude, longitude, display = resolved
        return {"place": display, "latitude": latitude, "longitude": longitude}
    if not isinstance(entry, dict):
        return None
    place = str(entry.get("place") or entry.get("city") or "").strip()
    latitude = to_float(entry.get("latitude"))
    longitude = to_float(entry.get("longitude"))
    if latitude is None or longitude is None:
        resolved = lookup_city(place) if place else None
        if resolved is None:
            return None
        latitude, longitude, place = resolved
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None
    if latitude == 0.0 and longitude == 0.0:
        return None
    return {
        "place": place or "未命名",
        "latitude": round(float(latitude), 6),
        "longitude": round(float(longitude), 6),
    }


def normalize_locations(raw: Any) -> List[Dict[str, Any]]:
    """规范化接收城市列表，按坐标/名称去重，最多 20 个。"""
    if isinstance(raw, (str, dict)):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    result: List[Dict[str, Any]] = []
    seen = set()
    for item in raw:
        location = normalize_location_entry(item)
        if location is None:
            continue
        key = (
            round(location["latitude"], 4),
            round(location["longitude"], 4),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(location)
        if len(result) >= MAX_GROUP_LOCATIONS:
            break
    return result


def group_locations(group: Dict[str, Any]) -> List[Dict[str, Any]]:
    """读取群聊的接收城市列表；兼容旧版单城市 place/latitude/longitude。"""
    locations = normalize_locations(group.get("locations"))
    if locations:
        return locations
    legacy = normalize_location_entry(
        {
            "place": group.get("place"),
            "latitude": group.get("latitude"),
            "longitude": group.get("longitude"),
        }
    )
    return [legacy] if legacy else []


def _sync_primary_location(group: Dict[str, Any]) -> Dict[str, Any]:
    locations = normalize_locations(group.get("locations"))
    group = dict(group)
    group["locations"] = locations
    if locations:
        group["place"] = locations[0]["place"]
        group["latitude"] = locations[0]["latitude"]
        group["longitude"] = locations[0]["longitude"]
    else:
        group["place"] = ""
        group["latitude"] = None
        group["longitude"] = None
    return group


def add_group_location(
    group: Dict[str, Any], location: Any
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """向群聊追加接收城市；同坐标则更新名称。返回 (新群聊, 城市) 。"""
    normalized = normalize_location_entry(location)
    if normalized is None:
        return dict(group), None
    locations = group_locations(group)
    key = (round(normalized["latitude"], 4), round(normalized["longitude"], 4))
    replaced = False
    for idx, old in enumerate(locations):
        if (
            round(old["latitude"], 4),
            round(old["longitude"], 4),
        ) == key:
            locations[idx] = normalized
            replaced = True
            break
    if not replaced:
        locations.append(normalized)
    locations = normalize_locations(locations)
    updated = dict(group)
    updated["locations"] = locations
    updated = _sync_primary_location(updated)
    return updated, normalized


def remove_group_location(
    group: Dict[str, Any], query: str
) -> Tuple[Dict[str, Any], bool, Optional[Dict[str, Any]]]:
    """按城市名/坐标移除接收城市；返回 (新群聊, 是否移除, 被移除城市)。"""
    text = str(query or "").strip()
    if not text:
        return dict(group), False, None
    locations = group_locations(group)
    target = lookup_city(text)
    removed: Optional[Dict[str, Any]] = None
    remaining: List[Dict[str, Any]] = []
    for location in locations:
        match = False
        place = str(location.get("place") or "")
        if place and (text in place or place in text):
            match = True
        if target is not None:
            if (
                haversine_km(
                    target[0],
                    target[1],
                    location["latitude"],
                    location["longitude"],
                )
                <= 20.0
            ):
                match = True
        if match and removed is None:
            removed = location
            continue
        remaining.append(location)
    if removed is None:
        return dict(group), False, None
    updated = dict(group)
    updated["locations"] = remaining
    updated = _sync_primary_location(updated)
    return updated, True, removed


def set_group_countdown(
    group: Dict[str, Any], enabled: bool
) -> Dict[str, Any]:
    updated = dict(group)
    updated["countdown_enabled"] = bool(enabled)
    return updated


def normalize_group_entry(entry: Any) -> Optional[Dict[str, Any]]:
    """兼容字符串与 dict 两种白名单写法，输出统一结构。"""
    if isinstance(entry, str):
        entry = {"umo": entry}
    if not isinstance(entry, dict):
        return None
    umo = str(entry.get("umo") or "").strip()
    platform_id = str(entry.get("platform_id") or "").strip()
    group_id = str(entry.get("group_id") or "").strip()
    if not umo and platform_id and group_id:
        umo = f"{platform_id}{_UMO_SEP}{_GROUP_MESSAGE}{_UMO_SEP}{group_id}"
    if not umo:
        return None
    if not platform_id or not group_id:
        parsed_platform, _, parsed_group = parse_umo(umo)
        platform_id = platform_id or parsed_platform
        group_id = group_id or parsed_group
    locations = normalize_locations(entry.get("locations"))
    legacy = normalize_location_entry(
        {
            "place": entry.get("place"),
            "latitude": entry.get("latitude"),
            "longitude": entry.get("longitude"),
        }
    )
    if legacy is not None:
        key = (round(legacy["latitude"], 4), round(legacy["longitude"], 4))
        if not any(
            (round(loc["latitude"], 4), round(loc["longitude"], 4)) == key
            for loc in locations
        ):
            locations.insert(0, legacy)
    primary = locations[0] if locations else None
    return {
        "umo": umo,
        "platform_id": platform_id,
        "group_id": group_id,
        "place": primary["place"] if primary else "",
        "latitude": primary["latitude"] if primary else None,
        "longitude": primary["longitude"] if primary else None,
        "locations": locations,
        "countdown_enabled": bool(entry.get("countdown_enabled", True)),
        "enabled": bool(entry.get("enabled", True)),
        "enabled_by": str(entry.get("enabled_by") or "").strip(),
        "enabled_at": str(entry.get("enabled_at") or "").strip(),
    }


def normalize_groups(raw: Any) -> List[Dict[str, Any]]:
    """规范化白名单，按 umo 去重（保留第一次出现）。"""
    groups: List[Dict[str, Any]] = []
    seen = set()
    if not isinstance(raw, (list, tuple)):
        return groups
    for item in raw:
        group = normalize_group_entry(item)
        if group is None or group["umo"] in seen:
            continue
        seen.add(group["umo"])
        groups.append(group)
    return groups


def find_group(groups: Sequence[Dict[str, Any]], umo: str) -> Optional[Dict[str, Any]]:
    for group in groups:
        if group.get("umo") == umo:
            return group
    return None


def upsert_group(
    groups: Sequence[Dict[str, Any]], entry: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """新增或合并一个白名单群；同 umo 时只覆盖 entry 明确提供的字段。"""
    normalized = normalize_group_entry(entry)
    if normalized is None:
        return list(groups)
    if not isinstance(entry, dict):
        entry = {"umo": normalized["umo"]}
    result = [dict(g) for g in groups]
    for idx, group in enumerate(result):
        if group.get("umo") == normalized["umo"]:
            merged = dict(group)
            for key in (
                "platform_id",
                "group_id",
                "enabled",
                "enabled_by",
                "enabled_at",
                "countdown_enabled",
            ):
                if key in entry and entry[key] is not None:
                    merged[key] = normalized.get(key)
            if any(
                key in entry
                for key in ("locations", "place", "latitude", "longitude")
            ):
                merged["locations"] = normalized.get("locations", [])
                merged["place"] = normalized.get("place", "")
                merged["latitude"] = normalized.get("latitude")
                merged["longitude"] = normalized.get("longitude")
            result[idx] = merged
            return result
    result.append(normalized)
    return result


def set_group_enabled(
    groups: Sequence[Dict[str, Any]],
    umo: str,
    enabled: bool,
    *,
    operator: str = "",
    timestamp: str = "",
) -> List[Dict[str, Any]]:
    """启用/停用白名单群；不存在且要求启用时自动追加。"""
    result = [dict(g) for g in groups]
    for group in result:
        if group.get("umo") == umo:
            group["enabled"] = bool(enabled)
            if operator:
                group["enabled_by"] = operator
            if timestamp:
                group["enabled_at"] = timestamp
            return result
    if enabled:
        result.append(
            {
                "umo": umo,
                "platform_id": parse_umo(umo)[0],
                "group_id": parse_umo(umo)[2],
                "place": "",
                "latitude": None,
                "longitude": None,
                "locations": [],
                "countdown_enabled": True,
                "enabled": True,
                "enabled_by": operator,
                "enabled_at": timestamp,
            }
        )
    return result


def events_match(event: QuakeEvent, record: Dict[str, Any]) -> bool:
    """判断新事件与已记录事件是否为同一次地震（跨源聚类）。"""
    try:
        origin = float(record.get("origin_ts", 0))
        if abs(event.origin_ts - origin) > 180.0:
            return False
        lat = float(record.get("latitude"))
        lon = float(record.get("longitude"))
        if haversine_km(event.latitude, event.longitude, lat, lon) > 200.0:
            return False
        old_mag = float(record.get("magnitude", event.magnitude))
        return abs(event.magnitude - old_mag) <= 1.0
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------- #
# 文案
# --------------------------------------------------------------------------- #


def format_sim_notice() -> str:
    return (
        "🧪【模拟预警 · 演练开始】\n"
        "这不是真实地震！以下为模拟地震预警，仅用于功能演示，请勿恐慌。"
    )


def guidance_for_magnitude(
    magnitude: float, simulation: bool = False
) -> str:
    """按震级给出不同级别的避险/行动指引。"""
    try:
        mag = float(magnitude)
    except (TypeError, ValueError):
        mag = 0.0
    if mag < 3.0:
        action = "微震，一般无明显震感，无需特别行动；留意官方信息即可。"
    elif mag < 4.0:
        action = "有感地震：保持冷静，远离窗户、吊灯和易坠物，不必惊慌。"
    elif mag < 5.0:
        action = "明显震感：远离玻璃、高大家具和悬挂物，做好就近避险准备。"
    elif mag < 6.0:
        action = "较强地震，请立即避险：伏地、遮挡、手抓牢；不要使用电梯。"
    elif mag < 7.0:
        action = "强烈地震：立即就近伏地遮挡、保护头颈，远离外墙和玻璃。"
    else:
        action = "大地震：立即采取避险动作，保护头颈，远离建筑外墙/玻璃，听从官方指引。"
    return ("🧪 演练提示：" if simulation else "⚠️ ") + action


def format_basic(
    event: QuakeEvent,
    *,
    simulation: bool = False,
    update: bool = False,
    arrival_sec: Optional[float] = None,
    place: str = "",
    distance_km: Optional[float] = None,
    locations: Optional[List[Dict[str, Any]]] = None,
    countdown_enabled: bool = True,
) -> str:
    if simulation:
        title = "🧪 模拟地震预警（演练）"
    elif update:
        title = "🔄 地震预警更新"
    elif event.kind == "eew":
        title = "🚨 地震预警"
    else:
        title = "📢 地震速报"

    lines = [title]
    if simulation:
        lines.append("⚠️ 本次为模拟演练，不是真实地震，请勿恐慌。")
    lines.extend(
        [
            f"震中：{event.place}",
            f"震级：M{event.magnitude:g}",
            f"深度：{event.depth_km:g} km",
            f"发震时间：{format_time(event.origin_ts)}",
        ]
    )
    if event.max_intensity is not None:
        intensity_label = "最大震度" if event.source == "jma_eew" else "最大烈度"
        lines.append(f"{intensity_label}：{event.max_intensity:g}")
    if event.report_num > 1 or event.final:
        suffix = "（最终报）" if event.final else ""
        lines.append(f"报告：第 {event.report_num} 报{suffix}")

    if locations is not None:
        valid = [
            loc
            for loc in locations
            if loc.get("arrival") is not None and loc.get("distance") is not None
        ]
        if valid:
            lines.append("接收点：")
            for loc in valid[:5]:
                arrival = float(loc["arrival"])
                target = (
                    "可能已到达"
                    if arrival <= 0
                    else f"约 {int(math.ceil(arrival))} 秒后"
                )
                lines.append(
                    f"  · {loc.get('place') or '未命名'}："
                    f"震中距约 {float(loc['distance']):.0f} km，预计{target}"
                )
            if len(valid) > 5:
                lines.append(f"  · 等共 {len(valid)} 个接收城市")
            nearest = min(valid, key=lambda item: float(item["arrival"]))
            if not countdown_enabled:
                lines.append("逐条倒计时：本群已关闭")
            elif float(nearest.get("arrival") or 0) <= 0:
                lines.append("倒计时：地震波可能已到达，不再逐条倒计时")
            else:
                lines.append(f"倒计时按最近接收点：{nearest.get('place') or '未命名'}")
        elif locations:
            names = "、".join(
                str(loc.get("place") or "未命名") for loc in locations[:5]
            )
            if any(loc.get("distance") is not None for loc in locations):
                lines.append("接收点：")
                for loc in locations[:5]:
                    if loc.get("distance") is not None:
                        lines.append(
                            f"  · {loc.get('place') or '未命名'}："
                            f"震中距约 {float(loc['distance']):.0f} km"
                        )
                    else:
                        lines.append(f"  · {loc.get('place') or '未命名'}")
            else:
                lines.append(f"接收点：{names}（坐标缺失，无法估算到达）")
            if arrival_sec is not None and arrival_sec > 0:
                lines.append(f"预计到达：约 {int(math.ceil(arrival_sec))} 秒后（按模拟设定）")
            if countdown_enabled and arrival_sec is not None:
                lines.append("倒计时按设定秒数发送")
            elif not countdown_enabled:
                lines.append("逐条倒计时：本群已关闭")
        else:
            lines.append("预计到达：未设置接收位置，无法估算倒计时")
    else:
        if distance_km is not None:
            lines.append(f"震中距：约 {distance_km:.0f} km")
            if place:
                lines.append(f"接收点：{place}")
        if arrival_sec is not None:
            if arrival_sec <= 0:
                lines.append("预计到达：地震波可能已到达")
            else:
                lines.append(f"预计到达：约 {int(math.ceil(arrival_sec))} 秒后（S 波估算）")
        elif place or distance_km is None:
            lines.append("预计到达：未设置接收位置，无法估算倒计时")
        if not countdown_enabled:
            lines.append("逐条倒计时：本群已关闭")

    lines.append(f"来源：{event.source_label}")
    lines.append(guidance_for_magnitude(event.magnitude, simulation=simulation))
    if not simulation:
        lines.append("数据仅供参考，请以官方发布为准。")
    return "\n".join(lines)


def format_countdown(seconds: int, simulation: bool = False) -> str:
    """倒计时消息保持极简：纯数字 + s（如 12s）。"""
    return f"{max(0, int(seconds))}s"


def format_final(
    simulation: bool = False, magnitude: Optional[float] = None
) -> str:
    """倒计时结束后的到达提示 + 分震级规避指引（与纯数字倒计时分开）。"""
    if simulation:
        title = "🧪 [模拟] 地震波已到达（演练）"
    else:
        title = "💥 地震波已到达，请继续保持避险姿势，注意余震。"
    if magnitude is None:
        return title + "\n⚠️ 请保持避险姿势，注意余震，听从官方指引。"
    return title + "\n" + guidance_for_magnitude(magnitude, simulation=simulation)


def validate_simulation(payload: Any) -> Dict[str, Any]:
    """校验 Pages 模拟预警表单，返回规范化字段；非法则抛 ValueError。"""
    if not isinstance(payload, dict):
        raise ValueError("请求格式错误")
    place = str(payload.get("place") or "").strip()
    city = str(payload.get("city") or "").strip()
    if not place and not city:
        raise ValueError("震中名称或震中城市至少填写一项")
    if len(place) > 80 or len(city) > 80:
        raise ValueError("震中名称/城市不能超过 80 字")
    magnitude = to_float(payload.get("magnitude"))
    if magnitude is None or not (0.0 <= magnitude <= 10.0):
        raise ValueError("震级必须在 0~10 之间")
    depth = to_float(payload.get("depth"), 10.0)
    if depth is None or not (0.0 <= depth <= 700.0):
        raise ValueError("震源深度必须在 0~700 km 之间")
    latitude = to_float(payload.get("latitude"))
    longitude = to_float(payload.get("longitude"))
    if (latitude is None) != (longitude is None):
        raise ValueError("纬度和经度必须同时填写或同时留空")
    if latitude is not None and not (-90.0 <= latitude <= 90.0):
        raise ValueError("纬度必须在 -90~90 之间")
    if longitude is not None and not (-180.0 <= longitude <= 180.0):
        raise ValueError("经度必须在 -180~180 之间")
    if latitude == 0.0 and longitude == 0.0:
        raise ValueError("震中经纬度不能同时为 0；不需要距离估算时可整体留空")
    countdown = int(to_float(payload.get("countdown"), 0) or 0)
    if countdown < 0 or countdown > 60:
        raise ValueError("倒计时秒数必须在 0~60 之间（0 = 按距离自动计算）")
    extreme = bool(payload.get("extreme", False))
    confirm = str(payload.get("extreme_confirm") or "").strip()
    if extreme:
        if confirm != "极限演练":
            raise ValueError("极限演练需输入确认词「极限演练」")
        if latitude is None and not city:
            raise ValueError(
                "极限演练需填写震中城市或经纬度，不能省略震中位置"
            )
    return {
        "place": place or city,
        "city": city,
        "magnitude": round(magnitude, 1),
        "depth": round(depth, 1),
        "latitude": latitude,
        "longitude": longitude,
        "countdown": countdown,
        "extreme": extreme,
    }


# --------------------------------------------------------------------------- #
# 持久化状态
# --------------------------------------------------------------------------- #


class EarthquakeStateStore:
    """保存已播报事件、源状态与模拟冷却时间，防止重启后重复预警。"""

    def __init__(self, data_dir: str = PLUGIN_DATA_DIR):
        self.path = os.path.join(data_dir, STATE_FILENAME)
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _normalize_state(data)
        except FileNotFoundError:
            return copy.deepcopy(_DEFAULT_STATE)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Earthquake] 读取状态文件失败，使用空状态: {e}")
            return copy.deepcopy(_DEFAULT_STATE)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def save(self, data: Dict[str, Any]) -> None:
        normalized = _normalize_state(data)
        with self._lock:
            self._data = normalized
            try:
                directory = os.path.dirname(os.path.abspath(self.path)) or "."
                os.makedirs(directory, exist_ok=True)
                fd, temp_path = tempfile.mkstemp(
                    dir=directory, prefix=".currentcortex_earthquake.", suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(normalized, f, ensure_ascii=False, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(temp_path, self.path)
                    try:
                        os.chmod(self.path, 0o600)
                    except OSError:
                        pass
                finally:
                    if os.path.exists(temp_path):
                        try:
                            os.unlink(temp_path)
                        except OSError:
                            pass
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[Earthquake] 保存状态文件失败: {e}")


def _normalize_state(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    state = copy.deepcopy(_DEFAULT_STATE)
    state.update(data)
    stats = dict(_DEFAULT_STATE["stats"])
    if isinstance(data.get("stats"), dict):
        stats.update(data["stats"])
    state["stats"] = stats
    if not isinstance(state.get("sources"), dict):
        state["sources"] = {}
    events = []
    for record in state.get("events") or []:
        if isinstance(record, dict) and record.get("origin_ts") and record.get("latitude") is not None:
            events.append(record)
    state["events"] = events[-200:]
    for key in ("last_event", "last_simulation"):
        if state.get(key) is not None and not isinstance(state[key], dict):
            state[key] = None
    try:
        state["sim_last_ts"] = float(state.get("sim_last_ts") or 0.0)
    except (TypeError, ValueError):
        state["sim_last_ts"] = 0.0
    try:
        state["extreme_last_ts"] = float(state.get("extreme_last_ts") or 0.0)
    except (TypeError, ValueError):
        state["extreme_last_ts"] = 0.0
    return state


# --------------------------------------------------------------------------- #
# 预警服务
# --------------------------------------------------------------------------- #


class EarthquakeService:
    """轮询多源、聚合去重并向白名单群聊播报。"""

    def __init__(self, plugin: Any, data_dir: str = PLUGIN_DATA_DIR):
        self.plugin = plugin
        self.store = EarthquakeStateStore(data_dir)
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._session: Any = None
        self._alert_tasks: set[asyncio.Task] = set()
        self._sim_lock = asyncio.Lock()
        self._poll_lock = asyncio.Lock()
        self._last_poll_ts = 0.0
        self._last_poll_error = ""
        self._last_skip = ""
        self._last_poll_candidates = 0

    # ---------------- 配置读取（每次轮询实时读取，便于命令改白名单后立即生效） --
    def _cfg(self, key: str, default: Any) -> Any:
        try:
            return self.plugin.config.get(key, default)
        except Exception:
            return default

    def _enabled(self) -> bool:
        return bool(self._cfg("earthquake_enable", True))

    def _poll_interval(self) -> int:
        try:
            return max(10, int(self._cfg("earthquake_poll_interval", 30) or 30))
        except (TypeError, ValueError):
            return 30

    def _min_magnitude(self) -> float:
        try:
            return float(self._cfg("earthquake_min_magnitude", 4.0) or 4.0)
        except (TypeError, ValueError):
            return 4.0

    def _max_age(self) -> int:
        try:
            return max(30, int(self._cfg("earthquake_max_age_sec", 300) or 300))
        except (TypeError, ValueError):
            return 300

    def _max_distance(self) -> float:
        try:
            return max(0.0, float(self._cfg("earthquake_max_distance_km", 1000) or 0))
        except (TypeError, ValueError):
            return 1000.0

    def _http_timeout(self) -> float:
        try:
            return max(3.0, float(self._cfg("earthquake_http_timeout", 10) or 10))
        except (TypeError, ValueError):
            return 10.0

    def _s_wave_speed(self) -> float:
        try:
            return max(0.5, float(self._cfg("earthquake_s_wave_km_s", 3.5) or 3.5))
        except (TypeError, ValueError):
            return 3.5

    def _countdown_max_ticks(self) -> int:
        try:
            return max(1, min(60, int(self._cfg("earthquake_countdown_max_ticks", 30) or 30)))
        except (TypeError, ValueError):
            return 30

    def _countdown_max_wait(self) -> float:
        """剩余时间超过该值时只发基本信息，不启动长倒计时任务。"""
        try:
            return max(
                30.0,
                float(self._cfg("earthquake_countdown_max_wait_sec", 300) or 300),
            )
        except (TypeError, ValueError):
            return 300.0

    def _countdown_interval(self) -> float:
        try:
            # 倒计时数字按秒递减；发送间隔最小 1 秒，避免同一数字重复
            return max(1.0, float(self._cfg("earthquake_countdown_interval", 1.0) or 1.0))
        except (TypeError, ValueError):
            return 1.0

    def _broadcast_interval(self) -> float:
        try:
            return max(0.0, float(self._cfg("earthquake_broadcast_interval", 0.6) or 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _sim_cooldown(self) -> int:
        try:
            return max(0, int(self._cfg("earthquake_sim_cooldown", 30) or 0))
        except (TypeError, ValueError):
            return 30

    def _extreme_cooldown(self) -> int:
        try:
            return max(0, int(self._cfg("earthquake_extreme_cooldown", 300) or 0))
        except (TypeError, ValueError):
            return 300

    def _default_location(self) -> Optional[Tuple[float, float, str]]:
        lat = to_float(self._cfg("earthquake_default_lat", 0))
        lon = to_float(self._cfg("earthquake_default_lon", 0))
        if lat is None or lon is None:
            return None
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return None
        if lat == 0.0 and lon == 0.0:
            return None
        place = str(self._cfg("earthquake_default_place", "") or "").strip()
        return lat, lon, place

    def _group_location(self, group: Dict[str, Any]) -> Optional[Tuple[float, float, str]]:
        lat = to_float(group.get("latitude"))
        lon = to_float(group.get("longitude"))
        if lat is not None and lon is not None:
            return lat, lon, str(group.get("place") or "").strip()
        return self._default_location()

    def _active_groups(self) -> List[Dict[str, Any]]:
        groups = normalize_groups(self._cfg("earthquake_group_whitelist", []))
        return [g for g in groups if g.get("enabled", True)]

    def _is_muted(self, umo: str) -> bool:
        checker = getattr(self.plugin, "is_earthquake_muted", None)
        if not callable(checker):
            return False
        try:
            return bool(checker(umo))
        except Exception:
            return False

    def _is_active_group(self, umo: str) -> bool:
        return any(
            group.get("umo") == umo and group.get("enabled", True)
            for group in self._active_groups()
        )

    # ---------------- 生命周期 ----------------
    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("[Earthquake] 当前无事件循环，预警轮询未启动")
            return
        self._stop = asyncio.Event()
        self._task = loop.create_task(self._run(), name="currentcortex-earthquake")
        logger.info(
            f"[Earthquake] 预警轮询已启动（间隔 {self._poll_interval()}s，"
            f"白名单群 {len(self._active_groups())} 个）"
        )

    async def stop(self) -> None:
        self._stop.set()
        tasks = [t for t in [self._task, *list(self._alert_tasks)] if t is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._task = None
        self._alert_tasks.clear()
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
        logger.info("[Earthquake] 预警轮询已停止")

    async def _run(self) -> None:
        # 启动错峰，避免多实例同时打上游
        try:
            await asyncio.sleep(2)
            while not self._stop.is_set():
                try:
                    await self.poll_once()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    self._last_poll_error = str(e)[:300]
                    logger.error(f"[Earthquake] 轮询异常: {e}", exc_info=True)
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=float(self._poll_interval())
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            if self._session is not None:
                try:
                    await self._session.close()
                except Exception:
                    pass
                self._session = None

    async def _ensure_session(self) -> None:
        if aiohttp is None:
            raise RuntimeError("aiohttp 未安装，无法请求地震预警源")
        if self._session is None or getattr(self._session, "closed", False):
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": (
                        "CurrentCortex-Earthquake/1.0 "
                        "(AstrBot plugin; +https://github.com/backrooms-yrc/"
                        "astrbot_plugin_currentcortex)"
                    )
                }
            )

    # ---------------- 轮询与聚合 ----------------
    async def poll_once(self) -> Dict[str, Any]:
        # 定时轮询与 Pages「立即检查」可能并发触发；串行化避免同一事件重复播报
        async with self._poll_lock:
            return await self._poll_once_impl()

    async def _poll_once_impl(self) -> Dict[str, Any]:
        now = time.time()
        if not self._enabled():
            self._last_skip = "地震预警全局开关已关闭"
            return {"ok": False, "reason": self._last_skip}
        groups = self._active_groups()
        if not groups:
            self._last_skip = "暂无启用的群聊白名单"
            return {"ok": False, "reason": self._last_skip}
        await self._ensure_session()

        state = self.store.snapshot()
        state.setdefault("sources", {})
        results = await asyncio.gather(
            *[
                fetch_source(self._session, name, self._http_timeout())
                for name in SOURCE_DEFS
            ],
            return_exceptions=True,
        )
        candidates: List[QuakeEvent] = []
        for name, result in zip(SOURCE_DEFS.keys(), results):
            if isinstance(result, Exception):
                state["sources"][name] = {
                    "label": SOURCE_DEFS[name]["label"],
                    "ok": False,
                    "last_ts": now,
                    "count": 0,
                    "error": str(result)[:200],
                }
                logger.warning(f"[Earthquake] 源 {name} 请求失败: {result}")
                continue
            events = result or []
            state["sources"][name] = {
                "label": SOURCE_DEFS[name]["label"],
                "ok": True,
                "last_ts": now,
                "count": len(events),
                "error": "",
            }
            candidates.extend(events)

        self._last_poll_candidates = len(candidates)
        self._last_skip = ""
        self._last_poll_error = ""
        min_mag = self._min_magnitude()
        max_age = self._max_age()
        fresh: List[QuakeEvent] = []
        for event in candidates:
            if event.magnitude < min_mag:
                continue
            age = now - max(event.origin_ts, event.report_ts)
            if age > max_age or age < -120:
                continue
            fresh.append(event)
        fresh.sort(key=lambda e: (-e.priority, -e.origin_ts))

        alerted = 0
        for event in fresh:
            existing = self._find_record(state, event)
            if existing is None:
                targets = self._targets(event)
                if not targets:
                    continue
                self._remember(state, event, now, alerted=True)
                self._spawn_alert(event, targets)
                alerted += 1
                if alerted >= 3:
                    break
                continue
            improved = self._record_improved(existing, event, now)
            self._update_record(existing, event, now)
            if improved:
                targets = self._targets(event)
                if targets:
                    self._spawn_alert(event, targets, update=True)
                    existing["last_update_ts"] = now

        state["stats"]["polls"] = int(state["stats"].get("polls", 0)) + 1
        state["stats"]["last_poll_ts"] = now
        if alerted:
            state["stats"]["alerts"] = int(state["stats"].get("alerts", 0)) + alerted
        try:
            self.store.save(state)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Earthquake] 保存轮询状态失败: {e}")
        self._last_poll_ts = now
        return {
            "ok": True,
            "candidates": len(candidates),
            "fresh": len(fresh),
            "alerts": alerted,
        }

    @staticmethod
    def _find_record(state: Dict[str, Any], event: QuakeEvent) -> Optional[Dict[str, Any]]:
        for record in state.get("events") or []:
            if events_match(event, record):
                return record
        return None

    @staticmethod
    def _remember(
        state: Dict[str, Any], event: QuakeEvent, now: float, *, alerted: bool
    ) -> None:
        record = event.to_dict()
        record.update(
            {
                "priority": event.priority,
                "last_seen_ts": now,
                "last_alert_ts": now if alerted else 0.0,
                "last_update_ts": now if alerted else 0.0,
                "alerted": bool(alerted),
            }
        )
        state.setdefault("events", []).append(record)
        state["events"] = state["events"][-200:]
        state["last_event"] = event.to_dict()

    @staticmethod
    def _record_improved(
        record: Dict[str, Any], event: QuakeEvent, now: float
    ) -> bool:
        if not record.get("alerted"):
            return True
        try:
            last_update = float(record.get("last_update_ts", 0) or 0)
        except (TypeError, ValueError):
            last_update = 0.0
        if now - last_update < 60.0:
            return False
        try:
            old_mag = float(record.get("magnitude", event.magnitude))
        except (TypeError, ValueError):
            old_mag = event.magnitude
        try:
            old_intensity = float(record.get("max_intensity") or 0)
        except (TypeError, ValueError):
            old_intensity = 0.0
        new_intensity = float(event.max_intensity or 0)
        old_priority = int(record.get("priority", 0) or 0)
        old_report = int(record.get("report_num", 1) or 1)
        return bool(
            event.priority > old_priority
            or event.report_num > old_report
            or (event.final and not record.get("final"))
            or event.magnitude >= old_mag + 0.5
            or new_intensity >= old_intensity + 0.5
        )

    @staticmethod
    def _update_record(
        record: Dict[str, Any], event: QuakeEvent, now: float
    ) -> None:
        old_report = int(record.get("report_num", 1) or 1)
        old_priority = int(record.get("priority", 0) or 0)
        record["last_seen_ts"] = now
        record["magnitude"] = event.magnitude
        record["max_intensity"] = event.max_intensity
        if event.priority >= old_priority:
            record.update(event.to_dict())
            record["priority"] = event.priority
        record["report_num"] = max(old_report, event.report_num)

    # ---------------- 目标群与播报 ----------------
    def _targets(self, event: QuakeEvent) -> List[Dict[str, Any]]:
        targets: List[Dict[str, Any]] = []
        max_distance = self._max_distance()
        now = time.time()
        for group in self._active_groups():
            umo = group["umo"]
            if self._is_muted(umo):
                continue
            locations = group_locations(group)
            if not locations:
                default = self._default_location()
                if default is not None:
                    locations = [
                        {
                            "place": default[2] or "默认位置",
                            "latitude": default[0],
                            "longitude": default[1],
                        }
                    ]
            if not locations:
                targets.append(
                    {
                        "group": group,
                        "umo": umo,
                        "locations": [],
                        "nearest": None,
                        "countdown_enabled": bool(
                            group.get("countdown_enabled", True)
                        ),
                        "arrival": None,
                        "distance": None,
                        "place": "",
                    }
                )
                continue
            location_infos: List[Dict[str, Any]] = []
            no_coords = event.source == "simulation" and not event.raw.get(
                "has_coords", True
            )
            for location in locations:
                latitude = float(location["latitude"])
                longitude = float(location["longitude"])
                place = str(location.get("place") or "")
                if no_coords:
                    # 模拟预警未填震中坐标时，不伪造震中距/到达时间
                    location_infos.append(
                        {
                            "place": place,
                            "latitude": latitude,
                            "longitude": longitude,
                            "distance": None,
                            "arrival": None,
                        }
                    )
                    continue
                distance, arrival = estimate_arrival(
                    event,
                    latitude,
                    longitude,
                    s_wave_km_s=self._s_wave_speed(),
                    now=now,
                )
                if (
                    max_distance > 0
                    and distance > max_distance
                    and event.source != "simulation"
                ):
                    continue
                location_infos.append(
                    {
                        "place": place,
                        "latitude": latitude,
                        "longitude": longitude,
                        "distance": distance,
                        "arrival": arrival,
                    }
                )
            if not location_infos:
                continue
            nearest = min(
                location_infos,
                key=lambda item: (
                    item.get("arrival") is None,
                    float(item.get("arrival") or 0.0),
                ),
            )
            targets.append(
                {
                    "group": group,
                    "umo": umo,
                    "locations": location_infos,
                    "nearest": nearest,
                    "countdown_enabled": bool(
                        group.get("countdown_enabled", True)
                    ),
                    "arrival": nearest.get("arrival"),
                    "distance": nearest.get("distance"),
                    "place": nearest.get("place") or "",
                }
            )
        # 近处先发：多群时让最先到达的群优先收到基本信息和倒计时
        targets.sort(
            key=lambda item: (
                item.get("arrival") is None,
                float(item.get("arrival") or 0.0),
            )
        )
        return targets

    def _spawn_alert(
        self,
        event: QuakeEvent,
        targets: Sequence[Dict[str, Any]],
        *,
        simulation: bool = False,
        countdown_override: int = 0,
        update: bool = False,
    ) -> None:
        if self._stop.is_set():
            return
        task = asyncio.create_task(
            self._alert_event(
                event,
                list(targets),
                simulation=simulation,
                countdown_override=countdown_override,
                update=update,
            ),
            name=f"currentcortex-earthquake-alert-{event.event_id}",
        )
        self._alert_tasks.add(task)
        task.add_done_callback(self._alert_tasks.discard)

    async def _alert_event(
        self,
        event: QuakeEvent,
        targets: List[Dict[str, Any]],
        *,
        simulation: bool = False,
        countdown_override: int = 0,
        update: bool = False,
    ) -> None:
        try:
            if not targets:
                return
            if simulation:
                # 必须先提醒「仅为模拟」，再发基本信息
                for target in targets:
                    await self._send(target["umo"], format_sim_notice(), gap=True)
            for target in targets:
                locations = list(target.get("locations") or [])
                nearest = target.get("nearest")
                display_locations: List[Dict[str, Any]] = []
                no_coords = event.source == "simulation" and not event.raw.get(
                    "has_coords", True
                )
                if not no_coords and countdown_override <= 0:
                    # 群多时逐条发送需要时间，按发送时刻重新估算各接收点剩余秒数
                    send_now = time.time()
                    for location in locations:
                        if location.get("latitude") is None:
                            display_locations.append(dict(location))
                            continue
                        distance, arrival = estimate_arrival(
                            event,
                            float(location["latitude"]),
                            float(location["longitude"]),
                            s_wave_km_s=self._s_wave_speed(),
                            now=send_now,
                        )
                        display_locations.append(
                            {**location, "distance": distance, "arrival": arrival}
                        )
                else:
                    # 模拟未填坐标 / 指定倒计时：保留城市名；有坐标时仍展示震中距
                    for location in locations:
                        distance = None
                        if not no_coords and location.get("latitude") is not None:
                            distance = haversine_km(
                                event.latitude,
                                event.longitude,
                                float(location["latitude"]),
                                float(location["longitude"]),
                            )
                        display_locations.append(
                            {
                                **location,
                                "distance": distance,
                                "arrival": None,
                            }
                        )
                text = format_basic(
                    event,
                    simulation=simulation,
                    update=update,
                    arrival_sec=(
                        float(countdown_override)
                        if countdown_override > 0
                        else (nearest or {}).get("arrival")
                    ),
                    place=(
                        (nearest or {}).get("place")
                        or target.get("place")
                        or ""
                    ),
                    distance_km=(nearest or {}).get("distance"),
                    locations=display_locations,
                    countdown_enabled=bool(
                        target.get("countdown_enabled", True)
                    ),
                )
                await self._send(target["umo"], text, gap=True)
            if update:
                return
            countdown_tasks = []
            for target in targets:
                countdown_enabled = bool(target.get("countdown_enabled", True))
                nearest = target.get("nearest") or {}
                if countdown_override > 0:
                    seconds = float(countdown_override)
                    ticks = (
                        max(1, min(60, int(countdown_override)))
                        if countdown_enabled
                        else 0
                    )
                else:
                    if event.source == "simulation" and not event.raw.get(
                        "has_coords", True
                    ):
                        continue
                    if nearest.get("latitude") is None:
                        continue
                    _, arrival = estimate_arrival(
                        event,
                        float(nearest["latitude"]),
                        float(nearest["longitude"]),
                        s_wave_km_s=self._s_wave_speed(),
                        now=time.time(),
                    )
                    if arrival is None or arrival <= 0:
                        continue
                    # 太远的事件只发基本信息，避免到达提示任务挂起数分钟
                    if arrival > self._countdown_max_wait():
                        continue
                    seconds = float(arrival)
                    ticks = (
                        countdown_ticks(seconds, self._countdown_max_ticks())
                        if countdown_enabled
                        else 0
                    )
                if countdown_enabled and ticks <= 0:
                    continue
                # 关闭逐条倒计时时仍保留一条到达提示（ticks=0）
                countdown_tasks.append(
                    asyncio.create_task(
                        self._countdown_group(
                            target,
                            ticks,
                            seconds,
                            simulation,
                            event.magnitude,
                        )
                    )
                )
            if countdown_tasks:
                await asyncio.gather(*countdown_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.error(f"[Earthquake] 播报失败: {e}", exc_info=True)

    async def _countdown_group(
        self,
        target: Dict[str, Any],
        ticks: int,
        arrival_sec: float,
        simulation: bool,
        magnitude: Optional[float] = None,
    ) -> None:
        interval = self._countdown_interval()
        step = max(1, int(round(interval)))
        deadline = time.monotonic() + max(0.0, arrival_sec)
        # ticks=0 表示只发送到达提示（群内关闭了逐条倒计时）
        start = max(0, int(ticks))
        umo = target["umo"]
        for remaining in range(start, 0, -step):
            due = deadline - remaining
            delay = due - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            if self._stop.is_set() or not self._is_active_group(umo) or self._is_muted(umo):
                return
            await self._send(umo, format_countdown(remaining, simulation))
        delay = deadline - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        if self._stop.is_set() or not self._is_active_group(umo) or self._is_muted(umo):
            return
        if start > 0:
            # 倒计时数字收尾：0s；随后单独发送到达提示与规避指引
            await self._send(umo, "0s")
        await self._send(umo, format_final(simulation, magnitude))

    async def _send(self, umo: str, text: str, *, gap: bool = False) -> bool:
        if not umo or self._is_muted(umo) or not self._is_active_group(umo):
            return False
        ok = False
        try:
            # 延迟导入，测试环境无需完整 astrbot
            from astrbot.api.event import MessageChain

            chain = MessageChain().message(text)
            ok = await asyncio.wait_for(
                self.plugin.context.send_message(umo, chain), timeout=15.0
            )
            if not ok:
                logger.warning(f"[Earthquake] 发送到 {umo} 失败（平台未找到）")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Earthquake] 发送到 {umo} 失败: {e}")
            ok = False
        if gap and self._broadcast_interval() > 0:
            await asyncio.sleep(self._broadcast_interval())
        return bool(ok)

    # ---------------- 模拟预警 / 极限演练 ----------------
    async def simulate(self, payload: Any) -> Dict[str, Any]:
        async with self._sim_lock:
            if not self._enabled():
                raise ValueError("地震预警全局开关已关闭，请先在插件配置中开启")
            data = validate_simulation(payload)
            extreme = bool(data.get("extreme"))
            if data["city"] and data["latitude"] is None:
                resolved = await resolve_city_location(data["city"])
                if resolved is None:
                    raise ValueError(
                        f"未找到城市「{data['city']}」，请换一个城市名或直接填写经纬度"
                    )
                data["latitude"], data["longitude"], _display = resolved
            groups = self._active_groups()
            if not groups:
                raise ValueError("暂无启用的群聊白名单，请先在群内发送 /地震 开启")
            now = time.time()
            state = self.store.snapshot()
            if extreme:
                cooldown = self._extreme_cooldown()
                last = float(state.get("extreme_last_ts") or 0.0)
                if cooldown and now - last < cooldown:
                    remain = int(math.ceil(cooldown - (now - last)))
                    raise ValueError(f"极限演练冷却中，请 {remain} 秒后再试")
            else:
                cooldown = self._sim_cooldown()
                last = float(state.get("sim_last_ts") or 0.0)
                if cooldown and now - last < cooldown:
                    remain = int(math.ceil(cooldown - (now - last)))
                    raise ValueError(f"模拟预警冷却中，请 {remain} 秒后再试")
            event = QuakeEvent(
                # 极限演练使用真实源标识，群成员看到的消息与真实预警一致
                source="cenc_eew" if extreme else "simulation",
                source_label=(
                    "中国地震台网·预警" if extreme else "模拟演练"
                ),
                event_id=f"{'extreme' if extreme else 'sim'}-{uuid.uuid4().hex[:8]}",
                origin_ts=now,
                report_ts=now,
                place=data["place"],
                latitude=data["latitude"] if data["latitude"] is not None else 0.0,
                longitude=data["longitude"] if data["longitude"] is not None else 0.0,
                magnitude=data["magnitude"],
                depth_km=data["depth"],
                max_intensity=None,
                report_num=1,
                kind="eew",
                final=False,
                raw={
                    "simulation": not extreme,
                    "extreme": extreme,
                    "countdown": data["countdown"],
                    "has_coords": data["latitude"] is not None,
                },
            )
            targets = self._targets(event)
            if not targets:
                raise ValueError("白名单群聊均被 /开关 关闭或超出距离过滤，未发送")
            if extreme:
                state["extreme_last_ts"] = now
                logger.warning(
                    "[Earthquake] ⚠️ 极限演练广播（无模拟提示）："
                    f"{event.place} M{event.magnitude:g}，{len(targets)} 个群，"
                    f"event={event.event_id}"
                )
            else:
                state["sim_last_ts"] = now
            state["stats"]["simulations"] = int(state["stats"].get("simulations", 0)) + 1
            # 极限演练完全按真实预警的 S 波估算走，忽略表单里的“倒计时秒数”
            countdown_override = 0 if extreme else data["countdown"]
            state["last_simulation"] = {
                **event.to_dict(),
                "extreme": extreme,
                "countdown": countdown_override,
                "groups": len(targets),
                "simulated_at": now,
            }
            self.store.save(state)
            self._spawn_alert(
                event,
                targets,
                simulation=not extreme,
                countdown_override=countdown_override,
            )
            if extreme:
                message = (
                    f"极限演练已发起，将向 {len(targets)} 个白名单群聊发送"
                    "与真实地震预警完全相同的消息"
                )
            else:
                message = (
                    f"模拟预警已发起，将向 {len(targets)} 个白名单群聊发送"
                    + ("（先发送模拟提醒）" if targets else "")
                )
            return {
                "ok": True,
                "extreme": extreme,
                "simulation_id": event.event_id,
                "groups": len(targets),
                "countdown": countdown_override,
                "message": message,
            }

    # ---------------- 状态 ----------------
    def status(self) -> Dict[str, Any]:
        state = self.store.snapshot()
        groups = normalize_groups(self._cfg("earthquake_group_whitelist", []))
        active = [g for g in groups if g.get("enabled", True)]
        sources: Dict[str, Any] = {}
        stored_sources = state.get("sources") or {}
        for name, spec in SOURCE_DEFS.items():
            stored = stored_sources.get(name) or {}
            sources[name] = {
                "label": spec["label"],
                "ok": bool(stored.get("ok")),
                "last_ts": stored.get("last_ts", 0),
                "count": stored.get("count", 0),
                "error": stored.get("error", ""),
                "url": spec["url"],
            }
        running = bool(self._enabled() and self._task is not None and not self._task.done())
        return {
            "enabled": self._enabled(),
            "running": running,
            "poll_interval": self._poll_interval(),
            "min_magnitude": self._min_magnitude(),
            "max_age_sec": self._max_age(),
            "max_distance_km": self._max_distance(),
            "countdown_max_ticks": self._countdown_max_ticks(),
            "countdown_max_wait_sec": self._countdown_max_wait(),
            "countdown_interval": self._countdown_interval(),
            "s_wave_km_s": self._s_wave_speed(),
            "sim_cooldown": self._sim_cooldown(),
            "extreme_cooldown": self._extreme_cooldown(),
            "groups": groups,
            "active_groups": len(active),
            "last_poll_ts": self._last_poll_ts
            or float(state["stats"].get("last_poll_ts", 0) or 0),
            "last_poll_candidates": self._last_poll_candidates,
            "last_poll_error": self._last_poll_error,
            "last_skip": self._last_skip,
            "last_event": state.get("last_event"),
            "last_simulation": state.get("last_simulation"),
            "stats": state.get("stats") or {},
            "sources": sources,
            "state_file": self.store.path,
        }
