"""气象预警：中央气象台预警聚合、群聊白名单与播报。

数据源（公开、免 Key）：
- 中央气象台预警列表 ``https://www.nmc.cn/rest/findAlarm``（标题含省/市/县、
  预警类型与颜色等级，``alertid`` 全局唯一）；
- 新预警可选抓取详情页正文（含发布内容与防御指南）。

与地震预警共用的一套逻辑/代码：
- 群聊白名单（群主/群管理员按城市启用，一个群可多个城市，最多 20 个）——
  复用 ``earthquake.py`` 的 normalize_groups / upsert_group / add_group_location
  / remove_group_location / resolve_city_location 等纯函数；
- 轮询 + alertid 去重 + 已播报状态持久化（重启不重复播报）；
- ``/开关 off weather`` 可按群静音。

差异（相对地震预警）：
- 区域匹配按「标题行政区路径 vs 白名单城市名」而不是震中距离；
- 无倒计时/到达概念，播报为单条图文文本；
- 级别过滤（蓝/黄/橙/红，默认黄色及以上）；
- 预警变化缓慢，轮询间隔默认 120 秒。
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # pragma: no cover
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

from astrbot.api import logger

try:  # 包内导入 / 测试脚本顶层导入
    from .earthquake import (
        add_group_location,
        find_group,
        format_time,
        group_locations,
        normalize_groups,
        remove_group_location,
        resolve_city_location,
        set_group_enabled,
        upsert_group,
    )
    from .earthquake_locations import lookup_city as _lookup_city
except ImportError:  # pragma: no cover
    from earthquake import (  # type: ignore[no-redef]
        add_group_location,
        find_group,
        format_time,
        group_locations,
        normalize_groups,
        remove_group_location,
        resolve_city_location,
        set_group_enabled,
        upsert_group,
    )
    from earthquake_locations import lookup_city as _lookup_city  # type: ignore[no-redef]

PLUGIN_DATA_DIR = os.path.join("data", "plugin_data", "astrbot_plugin_currentcortex")
STATE_FILENAME = "currentcortex_weather.json"

WEATHER_ALERT_LIST_URL = "https://www.nmc.cn/rest/findAlarm"
WEATHER_DETAIL_BASE = "https://www.nmc.cn"
WEATHER_UA = (
    "CurrentCortex-Weather/1.0 "
    "(AstrBot plugin; +https://github.com/backrooms-yrc/astrbot_plugin_currentcortex)"
)
WEATHER_SOURCE_LABEL = "中央气象台"

# 预警颜色等级（数值越大越严重）
LEVEL_ORDER: Dict[str, int] = {"蓝色": 1, "黄色": 2, "橙色": 3, "红色": 4}
# 常见预警类型（解析兜底用，未命中时取「发布」与颜色之间的原文）
KNOWN_WARNING_TYPES = (
    "台风", "暴雨", "暴雪", "寒潮", "大风", "沙尘暴", "低温", "高温", "干旱",
    "雷电", "冰雹", "霜冻", "大雾", "道路结冰", "雷雨大风", "森林火险",
    "强对流", "海上大风", "高温中暑", "寒冷", "灰霾", "地质灾害",
)
_LEVEL_RE = re.compile(r"(蓝色|黄色|橙色|红色)")
_TYPE_RE = re.compile(r"发布(.+?)(蓝色|黄色|橙色|红色)预警")
_REGION_RE = re.compile(r"^(.*?)气象台")
_ISSUETIME_FORMATS = ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M")

# 每轮轮询最多播报的新预警数（防上游批量补录时刷屏）
MAX_BROADCAST_PER_POLL = 5
# 已播报预警的保留时长（超出后从状态清理；预警本身有效期通常数小时）
SEEN_RETENTION_SEC = 48 * 3600

_DEFAULT_STATE: Dict[str, Any] = {
    "version": 1,
    "seen": {},  # alertid -> {"title":..., "alerted_ts":..., "groups":N}
    "last_warning": None,
    "stats": {"broadcasts": 0, "polls": 0, "last_poll_ts": 0.0},
    "source": {},
}


@dataclass
class WarningEvent:
    """归一化后的气象预警事件。"""

    alert_id: str
    title: str
    region: str  # 行政区路径，如「安徽省蚌埠市五河县」
    wtype: str  # 预警类型，如「大雾」「暴雨」
    level: str  # 蓝/黄/橙/红
    issue_ts: float
    detail_url: str = ""
    body: str = ""

    @property
    def level_rank(self) -> int:
        return LEVEL_ORDER.get(self.level, 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "title": self.title,
            "region": self.region,
            "wtype": self.wtype,
            "level": self.level,
            "issue_time": format_time(self.issue_ts),
            "issue_ts": self.issue_ts,
            "detail_url": self.detail_url,
        }


def parse_issuetime(raw: Any) -> float:
    """解析列表页 issuetime（如 2026/10/25 23:48），失败返回当前时间。"""
    from datetime import datetime

    text = str(raw or "").strip()
    for fmt in _ISSUETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return time.time()


def parse_warning_item(item: Any) -> Optional[WarningEvent]:
    """把 findAlarm 列表项解析为 WarningEvent；字段缺失返回 None。"""
    if not isinstance(item, dict):
        return None
    alert_id = str(item.get("alertid") or "").strip()
    title = str(item.get("title") or "").strip()
    if not alert_id or not title:
        return None
    region_match = _REGION_RE.match(title)
    region = region_match.group(1) if region_match else ""
    level_match = _LEVEL_RE.search(title)
    level = level_match.group(1) if level_match else ""
    type_match = _TYPE_RE.search(title)
    if type_match:
        wtype = type_match.group(1).strip()
    else:
        wtype = ""
    if not wtype or wtype not in KNOWN_WARNING_TYPES:
        # 兜底：取「发布」到「色」之间的文本，去掉常见干扰词
        fallback = re.sub(r"(继续|解除|更新|发布)$", "", wtype or "")
        wtype = fallback if fallback in KNOWN_WARNING_TYPES else (wtype or "气象")
    if not level:
        level = "黄色"
    return WarningEvent(
        alert_id=alert_id,
        title=title,
        region=region,
        wtype=wtype,
        level=level,
        issue_ts=parse_issuetime(item.get("issuetime")),
        detail_url=str(item.get("url") or "").strip(),
    )


def parse_warning_list(payload: Any) -> List[WarningEvent]:
    """解析 findAlarm 响应 JSON。"""
    try:
        items = (
            ((payload or {}).get("data") or {}).get("page") or {}
        ).get("list") or []
    except AttributeError:
        return []
    events = []
    for item in items:
        event = parse_warning_item(item)
        if event is not None:
            events.append(event)
    return events


async def fetch_warnings(session: Any, timeout: float = 10.0) -> List[WarningEvent]:
    """拉取预警列表。失败抛异常，由调用方记录源状态。"""
    if aiohttp is None:
        raise RuntimeError("aiohttp 未安装")
    async with session.get(
        WEATHER_ALERT_LIST_URL,
        params={"pageNo": 1, "pageSize": 60},
        timeout=aiohttp.ClientTimeout(total=timeout),
        headers={"User-Agent": WEATHER_UA, "Referer": f"{WEATHER_DETAIL_BASE}/publish/alarm.html"},
    ) as resp:
        text = await resp.text()
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
    return parse_warning_list(json.loads(text.lstrip("\ufeff")))


async def fetch_warning_detail(session: Any, event: WarningEvent, timeout: float = 10.0) -> str:
    """抓取预警详情页正文（发布内容 + 防御指南）。失败返回空串。"""
    if aiohttp is None or not event.detail_url:
        return ""
    url = event.detail_url
    if url.startswith("/"):
        url = WEATHER_DETAIL_BASE + url
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={"User-Agent": WEATHER_UA, "Referer": f"{WEATHER_DETAIL_BASE}/publish/alarm.html"},
        ) as resp:
            if resp.status != 200:
                return ""
            html = await resp.text(errors="ignore")
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[Weather] 预警详情抓取失败（{event.alert_id}）: {e}")
        return ""
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)
    # 正文位于「发布日期：…」与「防御指南/推荐服务」之间；去掉重复的导航尾巴
    m = re.search(
        r"发布日期：[0-9年月日时分]+\s*(?:进入.*?天气预报\s*)*(.+?)(?:防御指南|推荐服务|$)",
        joined,
        re.S,
    )
    if not m:
        return ""
    body = m.group(1).strip()
    body = re.sub(r"\s+", " ", body)
    guide_idx = joined.find("防御指南")
    guide = ""
    if guide_idx >= 0:
        guide_seg = joined[guide_idx: guide_idx + 1200]
        guide = re.sub(r"\s+", " ", guide_seg.split("推荐服务", 1)[0]).strip()
    parts = []
    if body:
        parts.append(body)
    if guide:
        parts.append(guide[:600])
    return "\n".join(parts)[:1200]


# --------------------------------------------------------------------------- #
# 区域匹配：标题行政区路径 vs 白名单城市名
# --------------------------------------------------------------------------- #


def city_match_tokens(place: str) -> List[str]:
    """把白名单城市名拆成可匹配 token。

    「蚌埠市（安徽省）」→ [蚌埠市, 蚌埠, 安徽省, 安徽]；
    「金安区，六安市」→ [金安区, 六安市]；「北京」→ [北京]。
    裸城市名（无省份后缀）会额外用内置城市表反查所属省，
    使省级预警（region=安徽省）也能命中。
    """
    text = str(place or "").strip()
    if not text:
        return []
    tokens: List[str] = []

    def _add(part: str, suffixes: str) -> None:
        part = part.strip()
        if len(part) >= 2:
            tokens.append(part)
            stripped = re.sub(f"({suffixes})$", "", part)
            if len(stripped) >= 2:
                tokens.append(stripped)

    paren = re.search(r"（(.+?)）|\((.+?)\)", text)
    core = re.sub(r"（.*?）|\(.*?\)", "", text).strip()
    for part in re.split(r"[，,、\s]+", core):
        _add(part, "市|县|区|旗|地区|盟|自治州|自治区|特别行政区")
    for group in (paren.groups() if paren else ()):
        if group:
            for part in re.split(r"[，,、\s]+", group):
                _add(part, "省|市|自治区|特别行政区")
    # 裸城市名：用内置表反查省份（如「六安」→ 安徽省）
    if not any(tok.endswith("省") for tok in tokens):
        probe = re.split(r"[，,、\s]+", core)[0] if core else ""
        for candidate in (
            probe,
            re.sub(r"(市|县|区)$", "", probe) if probe else "",
        ):
            if not candidate:
                continue
            try:
                resolved = _lookup_city(candidate)
            except Exception:  # noqa: BLE001
                resolved = None
            if resolved:
                m = re.search(r"（(.+?)）|\((.+?)\)", str(resolved[2]))
                if m:
                    province = next(g for g in m.groups() if g)
                    _add(province, "省|市|自治区|特别行政区")
                break
    return tokens


def region_matches(region: str, place: str) -> bool:
    """预警标题的行政区路径是否覆盖白名单城市。"""
    region = str(region or "")
    if not region:
        return False
    for token in city_match_tokens(place):
        if token and token in region:
            return True
    return False


def level_at_least(level: str, minimum: str) -> bool:
    return LEVEL_ORDER.get(level, 0) >= LEVEL_ORDER.get(minimum, 0)


# --------------------------------------------------------------------------- #
# 文案
# --------------------------------------------------------------------------- #

_LEVEL_EMOJI = {"蓝色": "🔵", "黄色": "🟡", "橙色": "🟠", "红色": "🔴"}


def format_warning_message(event: WarningEvent, body: str = "") -> str:
    emoji = _LEVEL_EMOJI.get(event.level, "⚠️")
    lines = [
        f"{emoji} 气象预警 · {event.wtype}{event.level}预警信号",
        f"区域：{event.region or '见标题'}",
        f"发布时间：{format_time(event.issue_ts)}",
        f"来源：{WEATHER_SOURCE_LABEL}（{event.title.split('气象台', 1)[0]}气象台）",
    ]
    if body:
        lines.append("")
        lines.append(body)
    lines.append("")
    lines.append("详情：https://www.nmc.cn/publish/alarm.html")
    lines.append("请以当地气象部门最新发布为准。")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 状态持久化
# --------------------------------------------------------------------------- #


class WeatherStateStore:
    """已播报 alertid 与源状态，防止重启后重复播报。"""

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
            logger.warning(f"[Weather] 读取状态文件失败，使用空状态: {e}")
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
                    dir=directory, prefix=".currentcortex_weather.", suffix=".tmp"
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
                logger.warning(f"[Weather] 保存状态文件失败: {e}")


def _normalize_state(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    state = copy.deepcopy(_DEFAULT_STATE)
    state.update(data)
    stats = dict(_DEFAULT_STATE["stats"])
    if isinstance(data.get("stats"), dict):
        stats.update(data["stats"])
    state["stats"] = stats
    seen = data.get("seen") if isinstance(data.get("seen"), dict) else {}
    state["seen"] = {str(k): v for k, v in seen.items() if isinstance(v, dict)}
    if not isinstance(state.get("source"), dict):
        state["source"] = {}
    if state.get("last_warning") is not None and not isinstance(state["last_warning"], dict):
        state["last_warning"] = None
    return state


# --------------------------------------------------------------------------- #
# 预警服务
# --------------------------------------------------------------------------- #


class WeatherService:
    """轮询中央气象台预警、按白名单城市匹配并播报。"""

    def __init__(self, plugin: Any, data_dir: str = PLUGIN_DATA_DIR):
        self.plugin = plugin
        self.store = WeatherStateStore(data_dir)
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._session: Any = None
        self._broadcast_tasks: set = set()
        self._poll_lock = asyncio.Lock()
        self._last_poll_ts = 0.0
        self._last_poll_error = ""
        self._last_candidates = 0

    # ---------------- 配置 ----------------
    def _cfg(self, key: str, default: Any) -> Any:
        try:
            return self.plugin.config.get(key, default)
        except Exception:
            return default

    def _enabled(self) -> bool:
        return bool(self._cfg("weather_enable", True))

    def _poll_interval(self) -> int:
        try:
            return max(60, int(self._cfg("weather_poll_interval", 120) or 120))
        except (TypeError, ValueError):
            return 120

    def _min_level(self) -> str:
        value = str(self._cfg("weather_min_level", "黄色及以上") or "黄色及以上").strip()
        for level in LEVEL_ORDER:
            if value.startswith(level):
                return level
        return "黄色"

    def _detail_enabled(self) -> bool:
        return bool(self._cfg("weather_detail_enable", True))

    def _http_timeout(self) -> float:
        try:
            return max(3.0, float(self._cfg("weather_http_timeout", 10) or 10))
        except (TypeError, ValueError):
            return 10.0

    def _broadcast_interval(self) -> float:
        try:
            return max(0.0, float(self._cfg("weather_broadcast_interval", 0.6) or 0))
        except (TypeError, ValueError):
            return 0.0

    def _active_groups(self) -> List[Dict[str, Any]]:
        groups = normalize_groups(self._cfg("weather_group_whitelist", []))
        return [g for g in groups if g.get("enabled", True)]

    def _is_muted(self, umo: str) -> bool:
        checker = getattr(self.plugin, "is_weather_muted", None)
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
            logger.warning("[Weather] 当前无事件循环，气象预警轮询未启动")
            return
        self._stop = asyncio.Event()
        self._task = loop.create_task(self._run(), name="currentcortex-weather")
        logger.info(
            f"[Weather] 气象预警轮询已启动（间隔 {self._poll_interval()}s，"
            f"白名单群 {len(self._active_groups())} 个，级别 ≥{self._min_level()}）"
        )

    async def stop(self) -> None:
        self._stop.set()
        tasks = [t for t in [self._task, *list(self._broadcast_tasks)] if t is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._task = None
        self._broadcast_tasks.clear()
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
        logger.info("[Weather] 气象预警轮询已停止")

    async def _run(self) -> None:
        try:
            await asyncio.sleep(3)
            while not self._stop.is_set():
                try:
                    await self.poll_once()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    self._last_poll_error = str(e)[:300]
                    logger.error(f"[Weather] 轮询异常: {e}", exc_info=True)
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
        if self._session is not None and not getattr(self._session, "closed", False):
            return
        if aiohttp is None:
            raise RuntimeError("aiohttp 未安装，无法请求气象预警源")
        self._session = aiohttp.ClientSession(
            headers={"User-Agent": WEATHER_UA}
        )

    # ---------------- 轮询与播报 ----------------
    async def poll_once(self) -> Dict[str, Any]:
        async with self._poll_lock:
            return await self._poll_once_impl()

    async def _poll_once_impl(self) -> Dict[str, Any]:
        now = time.time()
        if not self._enabled():
            return {"ok": False, "reason": "气象预警全局开关已关闭"}
        groups = self._active_groups()
        if not groups:
            return {"ok": False, "reason": "暂无启用的群聊白名单"}
        await self._ensure_session()
        state = self.store.snapshot()

        try:
            events = await fetch_warnings(self._session, self._http_timeout())
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            state["source"] = {
                "label": WEATHER_SOURCE_LABEL,
                "ok": False,
                "last_ts": now,
                "count": 0,
                "error": str(e)[:200],
            }
            self._last_poll_error = str(e)[:300]
            self.store.save(state)
            logger.warning(f"[Weather] 预警列表请求失败: {e}")
            return {"ok": False, "reason": f"源请求失败: {e}"}
        self._last_candidates = len(events)
        self._last_poll_error = ""
        state["source"] = {
            "label": WEATHER_SOURCE_LABEL,
            "ok": True,
            "last_ts": now,
            "count": len(events),
            "error": "",
        }

        min_level = self._min_level()
        seen = state["seen"]
        # 清理过期已播报记录
        expired = [
            alert_id
            for alert_id, record in seen.items()
            if now - float(record.get("alerted_ts") or 0) > SEEN_RETENTION_SEC
        ]
        for alert_id in expired:
            seen.pop(alert_id, None)

        broadcast = 0
        for event in events:
            if broadcast >= MAX_BROADCAST_PER_POLL:
                break
            if not level_at_least(event.level, min_level):
                continue
            if event.alert_id in seen:
                continue
            targets = self._targets(event)
            if not targets:
                seen[event.alert_id] = {
                    "title": event.title,
                    "alerted_ts": now,
                    "groups": 0,
                }
                continue
            body = ""
            if self._detail_enabled():
                body = await fetch_warning_detail(self._session, event, self._http_timeout())
            message = format_warning_message(event, body)
            sent = 0
            for umo in targets:
                if await self._send(umo, message):
                    sent += 1
            seen[event.alert_id] = {
                "title": event.title,
                "alerted_ts": now,
                "groups": sent,
            }
            state["last_warning"] = event.to_dict()
            state["stats"]["broadcasts"] = (
                int(state["stats"].get("broadcasts", 0)) + max(1, sent)
            )
            broadcast += 1
            logger.info(
                f"[Weather] 已播报预警 {event.alert_id}（{event.wtype}{event.level}，"
                f"{event.region}）至 {sent} 个群"
            )

        state["stats"]["polls"] = int(state["stats"].get("polls", 0)) + 1
        state["stats"]["last_poll_ts"] = now
        self.store.save(state)
        self._last_poll_ts = now
        return {
            "ok": True,
            "candidates": len(events),
            "broadcast": broadcast,
        }

    def _targets(self, event: WarningEvent) -> List[str]:
        """命中的白名单群 umo：群的任一接收城市落在预警区域路径内。"""
        targets: List[str] = []
        for group in self._active_groups():
            umo = group["umo"]
            if self._is_muted(umo):
                continue
            for location in group_locations(group):
                if region_matches(event.region, str(location.get("place") or "")):
                    targets.append(umo)
                    break
        return targets

    async def _send(self, umo: str, text: str) -> bool:
        if not umo or self._is_muted(umo) or not self._is_active_group(umo):
            return False
        ok = False
        try:
            from astrbot.api.event import MessageChain

            chain = MessageChain().message(text)
            ok = await asyncio.wait_for(
                self.plugin.context.send_message(umo, chain), timeout=15.0
            )
            if not ok:
                logger.warning(f"[Weather] 发送到 {umo} 失败（平台未找到）")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Weather] 发送到 {umo} 失败: {e}")
            ok = False
        if self._broadcast_interval() > 0:
            await asyncio.sleep(self._broadcast_interval())
        return bool(ok)

    # ---------------- 状态 ----------------
    def status(self) -> Dict[str, Any]:
        state = self.store.snapshot()
        groups = normalize_groups(self._cfg("weather_group_whitelist", []))
        active = [g for g in groups if g.get("enabled", True)]
        source = state.get("source") or {}
        running = bool(
            self._enabled() and self._task is not None and not self._task.done()
        )
        return {
            "enabled": self._enabled(),
            "running": running,
            "poll_interval": self._poll_interval(),
            "min_level": self._min_level(),
            "groups": groups,
            "active_groups": len(active),
            "source": {
                "label": WEATHER_SOURCE_LABEL,
                "url": WEATHER_ALERT_LIST_URL,
                **source,
            },
            "last_poll_ts": self._last_poll_ts
            or float(state["stats"].get("last_poll_ts", 0) or 0),
            "last_poll_candidates": self._last_candidates,
            "last_poll_error": self._last_poll_error,
            "last_warning": state.get("last_warning"),
            "recent_warnings": [
                {"alert_id": k, **v} for k, v in list(state["seen"].items())[-10:]
            ],
            "stats": state.get("stats") or {},
            "state_file": self.store.path,
        }
