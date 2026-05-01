import re
import time
import hashlib
import asyncio
from typing import Any, Dict, List, Optional
from collections import OrderedDict

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig


API_BASE_URL = "https://api.bileizhen.top/api/pixiv"
PIXIV_ARTWORK_URL = "https://www.pixiv.net/artworks/{}"

HELP_TEXT = """🎨 Pixiv 随机图片插件 使用说明

📌 基本用法
  /pixiv               获取一张随机全年龄图片
  /pixiv help          显示此帮助信息
  /pixiv clear-cache   清除所有缓存

📌 参数选项（使用 key:value 格式，可组合使用）
  r18:0               全年龄（默认）
  r18:1               仅限 R18 内容
  r18:2               混合模式（全年龄+R18）
  tag:标签名           按标签筛选（OR匹配用 | 分隔，多个tag:指定AND匹配）
  keyword:关键词        标题/作者/标签模糊搜索
  num:1-20            获取图片数量（默认 1）
  size:original        图片尺寸：original/regular/small/thumb/mini
  excludeAI:true       排除 AI 生成作品
  uid:作者ID           指定作者 UID
  ratio:gt1.2lt1.8     长宽比筛选（gt=大于, lt=小于, 如 gt1.2lt1.8）

📌 示例
  /pixiv r18:1
  /pixiv r18:2 tag:白丝 keyword:初音ミク num:3
  /pixiv tag:萝莉 excludeAI:true num:5
  /pixiv uid:123456 num:3"""


class CacheManager:
    def __init__(self, max_size: int = 100, ttl: int = 3600):
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def _make_key(self, **kwargs) -> str:
        raw = str(sorted(kwargs.items()))
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, **kwargs) -> Optional[Any]:
        key = self._make_key(**kwargs)
        if key not in self._cache:
            return None
        timestamp, data = self._cache[key]
        if time.time() - timestamp > self._ttl:
            del self._cache[key]
            logger.debug(f"Cache expired for key: {key}")
            return None
        self._cache.move_to_end(key)
        logger.debug(f"Cache hit for key: {key}")
        return data

    def set(self, data: Any, **kwargs):
        key = self._make_key(**kwargs)
        self._cache[key] = (time.time(), data)
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
        logger.debug(f"Cache set for key: {key}")

    def clear(self):
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache cleared, removed {count} entries")
        return count


class PixivAPIClient:
    def __init__(self, timeout: int = 15):
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def fetch_images(self, **params) -> Dict[str, Any]:
        clean_params = {k: v for k, v in params.items() if v is not None}

        if "excludeAI" in clean_params:
            clean_params["excludeAI"] = str(clean_params["excludeAI"]).lower() == "true"

        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            try:
                async with session.get(API_BASE_URL, params=clean_params, allow_redirects=False) as resp:
                    if resp.status in (301, 302, 303, 307, 308):
                        redirect_url = resp.headers.get("Location", "")
                        logger.info(f"Received redirect to: {redirect_url}")
                        return {
                            "type": "redirect",
                            "url": redirect_url,
                        }

                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"API returned status {resp.status}: {error_text[:500]}")
                        raise PixivAPIError(f"API 请求失败 (HTTP {resp.status})", status_code=resp.status)

                    content_type = resp.headers.get("Content-Type", "")
                    if "image" in content_type:
                        image_url = str(resp.url)
                        logger.info(f"Received direct image response: {image_url}")
                        return {
                            "type": "redirect",
                            "url": image_url,
                        }

                    data = await resp.json()
                    logger.debug(f"API JSON response keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
                    return {"type": "json", "data": data}

            except aiohttp.ClientError as e:
                logger.error(f"Network error: {e}")
                raise PixivAPIError(f"网络请求失败: {str(e)}", status_code=0) from e
            except asyncio.TimeoutError:
                logger.error("Request timeout")
                raise PixivAPIError("API 请求超时，请稍后再试", status_code=0)


class CommandParser:
    PARAM_MAP = {
        "r18": "r18",
        "tag": "tag",
        "keyword": "keyword",
        "num": "num",
        "size": "size",
        "uid": "uid",
        "excludeai": "excludeAI",
        "exclude_ai": "excludeAI",
        "ratio": "aspectRatio",
        "date_after": "dateAfter",
        "date_before": "dateBefore",
    }

    @classmethod
    def parse(cls, raw_text: str) -> Dict[str, Any]:
        if not raw_text or not raw_text.strip():
            return {}

        text = raw_text.strip()
        params: Dict[str, Any] = {}

        key_value_pattern = re.compile(
            r'(?:^|\s)([a-zA-Z_]+):\s*([^\s]+(?:\s*[^\s]+)*?)(?=\s+[a-zA-Z_]+:|$)',
        )
        consumed_positions = []
        for match in key_value_pattern.finditer(text):
            key = match.group(1).lower()
            value = match.group(2).strip()
            mapped_key = cls.PARAM_MAP.get(key, key)

            if mapped_key == "tag":
                existing = params.get("tag", [])
                existing.append(value)
                params["tag"] = existing
            elif mapped_key in ("r18", "num"):
                try:
                    params[mapped_key] = int(value)
                except ValueError:
                    pass
            elif mapped_key == "excludeAI":
                params[mapped_key] = value.lower() in ("true", "1", "yes")
            else:
                params[mapped_key] = value
            consumed_positions.append((match.start(), match.end()))

        remaining = text
        for start, end in sorted(consumed_positions, reverse=True):
            remaining = remaining[:start] + remaining[end:]

        remaining_tokens = remaining.strip().split()
        for token in remaining_tokens:
            token_lower = token.lower()
            if token_lower == "r18":
                params.setdefault("r18", 1)
            elif token_lower == "mixed":
                params.setdefault("r18", 2)
            elif token_lower == "safe" or token_lower == "sfw":
                params.setdefault("r18", 0)

        return params


class PixivAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


@register(
    "astrbot_plugin_pixiv",
    "AstrBot Community",
    "Pixiv 随机图片插件 - 支持通过 /pixiv 指令获取随机 Pixiv 图片（含 R18 内容），支持标签筛选、关键词搜索等功能",
    "1.0.0",
)
class PixivPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        self._default_r18 = int(config.get("default_r18", 0))
        self._default_num = max(1, min(20, int(config.get("default_num", 1))))
        self._default_size = config.get("default_size", "regular")
        self._image_proxy = config.get("image_proxy", "pixiv.bileizhen.top")
        self._exclude_ai = config.get("exclude_ai", False)
        self._request_timeout = int(config.get("request_timeout", 15))

        cache_ttl = int(config.get("cache_ttl", 3600))
        max_cache_size = int(config.get("max_cache_size", 100))
        self._cache = CacheManager(max_size=max_cache_size, ttl=cache_ttl)
        self._api_client = PixivAPIClient(timeout=self._request_timeout)

        logger.info(
            f"PixivPlugin initialized: r18={self._default_r18}, num={self._default_num}, "
            f"size={self._default_size}, proxy={self._image_proxy}, excludeAI={self._exclude_ai}"
        )

    @filter.command("pixiv")
    async def pixiv_command(self, event: AstrMessageEvent):
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()

        command_prefix_pattern = re.compile(r'^[/!！]pixiv\s*', re.IGNORECASE)
        raw_args = command_prefix_pattern.sub('', message_str).strip()

        if not raw_args or raw_args.lower() in ("help", "-h", "--help", "帮助"):
            yield event.plain_result(HELP_TEXT)
            return

        if raw_args.lower() in ("clear-cache", "clearcache", "清除缓存"):
            count = self._cache.clear()
            yield event.plain_result(f"✅ 缓存已清除，共清理 {count} 条记录")
            return

        try:
            params = self._build_request_params(raw_args)

            cached_result = self._cache.get(**params)
            if cached_result is not None:
                logger.info(f"Returning cached result for user {user_name}")
                yield event.plain_result("📦 [缓存命中] 以下是之前的请求结果：")
                cached_response_items = await self._process_cached_response(cached_result, params, event)
                for item in cached_response_items:
                    yield item
                return

            api_params = self._prepare_api_params(params)
            result = await self._api_client.fetch_images(**api_params)

            self._cache.set(result, **params)

            response_items = await self._process_response(result, params, event)
            for item in response_items:
                yield item

        except PixivAPIError as e:
            logger.error(f"Pixiv API error for user {user_name}: {e}")
            error_msg = f"❌ 获取图片失败\n📝 错误信息：{str(e)}"
            if e.status_code:
                error_msg += f"\n🔢 状态码：{e.status_code}"
            error_msg += "\n💡 请稍后重试或检查参数是否正确"
            yield event.plain_result(error_msg)
        except ValueError as e:
            logger.error(f"Parameter error for user {user_name}: {e}")
            yield event.plain_result(f"❌ 参数错误：{str(e)}\n💡 发送 /pixiv help 查看使用说明")
        except Exception as e:
            logger.error(f"Unexpected error for user {user_name}: {e}", exc_info=True)
            yield event.plain_result(f"❌ 发生未知错误\n📝 错误信息：{str(e)}\n💡 请稍后重试或联系管理员")

    def _build_request_params(self, raw_args: str) -> Dict[str, Any]:
        parsed = CommandParser.parse(raw_args)

        params: Dict[str, Any] = {
            "r18": parsed.get("r18", self._default_r18),
            "num": parsed.get("num", self._default_num),
            "size": parsed.get("size", self._default_size),
        }

        if parsed.get("tag"):
            params["tag"] = parsed["tag"]
        if parsed.get("keyword"):
            params["keyword"] = parsed["keyword"]
        if parsed.get("uid"):
            params["uid"] = parsed["uid"]
        if parsed.get("aspectRatio"):
            params["aspectRatio"] = parsed["aspectRatio"]
        if parsed.get("dateAfter"):
            params["dateAfter"] = parsed["dateAfter"]
        if parsed.get("dateBefore"):
            params["dateBefore"] = parsed["dateBefore"]

        exclude_ai = parsed.get("excludeAI")
        if exclude_ai is None:
            exclude_ai = self._exclude_ai
        if exclude_ai:
            params["excludeAI"] = True

        logger.info(f"Parsed params: {params}")
        return params

    def _prepare_api_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        api_params = dict(params)
        api_params["proxy"] = self._image_proxy
        return api_params

    async def _process_response(
        self, result: Dict[str, Any], params: Dict[str, Any], event: AstrMessageEvent
    ) -> List[Any]:
        response_type = result.get("type")

        if response_type == "redirect":
            url = result.get("url", "")
            r18_label = self._get_r18_label(params.get("r18", 0))
            caption = self._build_caption({
                "url": url,
            }, r18_label)
            return [event.plain_result(caption), event.image_result(url)]

        if response_type == "json":
            data = result.get("data", {})
            items = self._extract_items(data)
            if not items:
                return [event.plain_result("😕 未找到符合条件的图片，请尝试更换参数\n💡 发送 /pixiv help 查看使用说明")]

            r18_label = self._get_r18_label(params.get("r18", 0))
            responses = []
            for i, item in enumerate(items):
                caption = self._build_caption(item, r18_label, idx=i + 1, total=len(items))
                responses.append(event.plain_result(caption))
                image_url = self._extract_image_url(item)
                if image_url:
                    responses.append(event.image_result(image_url))
                else:
                    responses.append(event.plain_result("⚠️ 未能提取到图片链接"))
            return responses

        logger.warning(f"Unknown response type: {response_type}")
        return [event.plain_result("⚠️ API 返回了未知格式的数据，请联系管理员")]

    async def _process_cached_response(
        self, cached_result: Dict[str, Any], params: Dict[str, Any], event: AstrMessageEvent
    ) -> List[Any]:
        return await self._process_response(cached_result, params, event)

    def _extract_items(self, data: Any) -> List[Dict[str, Any]]:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "illusts", "illustrations", "items", "results"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            if "illust" in data and isinstance(data["illust"], dict):
                return [data["illust"]]
            if any(isinstance(v, (list, dict)) for v in data.values()):
                for v in data.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        return v
        return []

    def _extract_image_url(self, item: Dict[str, Any]) -> Optional[str]:
        if isinstance(item.get("urls"), dict):
            urls = item["urls"]
            preferred_order = ["regular", "original", "small", "thumb", "mini"]
            for size in preferred_order:
                if urls.get(size):
                    return urls[size]
        for key in ("url", "image_url", "img_url", "regular", "original"):
            val = item.get(key)
            if val and isinstance(val, str) and val.startswith("http"):
                return val
        if item.get("pid"):
            pid = item["pid"]
            return f"https://pixiv.bileizhen.top/{pid}.jpg"
        return None

    def _build_caption(
        self, item: Dict[str, Any], r18_label: str, idx: int = 0, total: int = 1
    ) -> str:
        parts = []

        if total > 1 and idx > 0:
            parts.append(f"📷 [{idx}/{total}]")

        title = item.get("title", "")
        author = item.get("author") or item.get("user_name") or item.get("userName") or ""
        pid = item.get("pid") or item.get("id") or item.get("illust_id") or ""

        if title:
            parts.append(f"🎨 {title}")
        if author:
            parts.append(f"👤 作者：{author}")
        if pid:
            parts.append(f"🔗 {PIXIV_ARTWORK_URL.format(pid)}")

        tags = item.get("tags", [])
        if isinstance(tags, list) and tags:
            tag_names = []
            for t in tags[:8]:
                if isinstance(t, dict):
                    tag_names.append(t.get("name", str(t)))
                else:
                    tag_names.append(str(t))
            parts.append(f"🏷️ 标签：{' / '.join(tag_names)}")

        if r18_label:
            parts.append(r18_label)

        width = item.get("width", 0)
        height = item.get("height", 0)
        if width and height:
            parts.append(f"📐 尺寸：{width}×{height}")

        return "\n".join(parts)

    @staticmethod
    def _get_r18_label(r18: int) -> str:
        if r18 == 1:
            return "⚠️ [R-18] 此内容包含成人内容，请确保您已成年"
        if r18 == 2:
            return "🔞 [混合模式] 可能包含 R-18 内容"
        return ""

    async def terminate(self):
        logger.info("PixivPlugin is being terminated")
        self._cache.clear()
