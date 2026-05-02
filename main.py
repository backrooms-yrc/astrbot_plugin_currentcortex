import re
import asyncio
from typing import Any, Dict, List, Optional

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig


API_BASE_URL = "https://api.bileizhen.top/api/pixiv"
PIXIV_ARTWORK_URL = "https://www.pixiv.net/artworks/{}"

HELP_TEXT = """🎨 Pixiv 随机图片插件 使用说明

📌 基本命令
  /pixiv               获取一张随机全年龄图片（默认参数）
  /pixiv help          显示此帮助信息

📌 内容分级选项
  r18:0               全年龄内容（默认）
  r18:1               仅 R18 成人内容 ⚠️
  r18:2               混合模式（全年龄 + R18）🔞

📌 搜索与筛选参数（使用 key:value 格式，可组合使用）
  tag:标签名           按标签筛选图片
                       • OR 匹配：tag:萝莉|少女
                       • AND 匹配：tag:萝莉 tag:少女（多个tag参数）
  keyword:关键词       标题/作者/标签模糊搜索
  uid:作者ID           指定特定作者的 UID
  num:数量             获取图片数量（1-20，默认 1）

📌 图片设置
  size:尺寸            图片大小选项：
                       • original  - 原图（默认）
                       • regular   - 常规尺寸
                       • small     - 小图
                       • thumb     - 缩略图
                       • mini      - 迷你图
  excludeAI:true      排除 AI 生成的作品
  ratio:表达式         长宽比筛选
                       • gt1.2 = 大于 1.2
                       • lt1.8 = 小于 1.8
                       示例：ratio:gt1.2lt1.8

📌 使用示例
  基础用法：
    /pixiv                          随机全年龄图片
    /pixiv r18:1                    随机 R18 图片
    /pixiv help                     显示帮助

  高级搜索：
    /pixiv r18:1 tag:白丝 num:3     获取3张白丝R18图
    /pixiv keyword:初音ミク num:5   搜索初音未来相关图片
    /pixiv tag:萝莉 excludeAI:true  排除AI的萝莉标签图片
    /pixiv uid:123456 num:3         获取指定作者的作品

  组合筛选：
    /pixiv r18:2 tag:白丝 keyword:初音ミク num:3 size:original

⚠️ 注意事项
  • R18 内容仅限成年用户使用
  • 图片来源于 Pixiv，请遵守相关法律法规
  • 如遇问题可发送 /pixiv help 查看帮助

💡 提示：所有参数均可自由组合使用"""


class PixivAPIClient:
    def __init__(self, timeout: int = 15):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": "AstrBot-Pixiv-Plugin/1.0",
            "Accept": "application/json, image/*",
        }

    async def fetch_images(self, **params) -> Dict[str, Any]:
        clean_params = {k: v for k, v in params.items() if v is not None}

        if "excludeAI" in clean_params:
            clean_params["excludeAI"] = bool(clean_params["excludeAI"])

        has_filter_params = any(k in clean_params for k in ("r18", "num", "tag", "keyword", "uid",
                                                              "size", "excludeAI", "aspectRatio",
                                                              "dateAfter", "dateBefore"))

        async with aiohttp.ClientSession(timeout=self._timeout, headers=self._headers) as session:
            try:
                if has_filter_params:
                    resp = await self._post_request(session, clean_params)
                else:
                    resp = await self._get_request(session, clean_params)

                async with resp:
                    if resp.status in (301, 302, 303, 307, 308):
                        redirect_url = resp.headers.get("Location", "")
                        logger.info(f"Received redirect to: {redirect_url}")
                        return {"type": "redirect", "url": redirect_url}

                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"API returned status {resp.status}: {error_text[:500]}")
                        raise PixivAPIError(f"API 请求失败 (HTTP {resp.status})", status_code=resp.status)

                    content_type = resp.headers.get("Content-Type", "")
                    if "image" in content_type:
                        image_url = str(resp.url)
                        logger.info(f"Received direct image response: {image_url}")
                        return {"type": "redirect", "url": image_url}

                    data = await resp.json()
                    logger.debug(f"API JSON response keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
                    return {"type": "json", "data": data}

            except aiohttp.ClientError as e:
                logger.error(f"Network error: {e}")
                raise PixivAPIError(f"网络请求失败: {str(e)}", status_code=0) from e
            except asyncio.TimeoutError:
                logger.error("Request timeout")
                raise PixivAPIError("API 请求超时，请稍后再试", status_code=0)

    async def _get_request(self, session: aiohttp.ClientSession, params: Dict[str, Any]):
        logger.debug(f"GET {API_BASE_URL} params={params}")
        return await session.get(API_BASE_URL, params=params, allow_redirects=False)

    async def _post_request(self, session: aiohttp.ClientSession, params: Dict[str, Any]):
        body = self._normalize_post_params(params)
        logger.debug(f"POST {API_BASE_URL} body={body}")
        return await session.post(
            API_BASE_URL,
            json=body,
            allow_redirects=False,
        )

    @staticmethod
    def _normalize_post_params(params: Dict[str, Any]) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        for k, v in params.items():
            if k == "size" and isinstance(v, str):
                body[k] = [v]
            elif k == "tag" and isinstance(v, str):
                body[k] = [v]
            else:
                body[k] = v
        return body


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
            r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([^\s]+)',
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

        self._api_client = PixivAPIClient(timeout=self._request_timeout)

        logger.info(
            f"PixivPlugin initialized: r18={self._default_r18}, num={self._default_num}, "
            f"size={self._default_size}, proxy={self._image_proxy}, excludeAI={self._exclude_ai}"
        )

    @filter.command("pixiv")
    async def pixiv_command(self, event: AstrMessageEvent):
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()

        logger.debug(f"[DEBUG] 收到消息: '{message_str}'")

        if self._is_help_command(message_str):
            logger.info(f"Help command triggered by {user_name}")
            yield event.plain_result(HELP_TEXT)
            return

        try:
            params = self._build_request_params(message_str)

            logger.info(f"Fetching for user {user_name}, params={params}")

            api_params = self._prepare_api_params(params)
            result = await self._api_client.fetch_images(**api_params)

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

    def _is_help_command(self, message: str) -> bool:
        """
        检测是否为帮助命令
        支持多种格式，增强健壮性
        """
        if not message:
            return False

        msg_clean = message.strip()
        logger.debug(f"[DEBUG] 检测help命令: 原始='{msg_clean}'")

        # 标准化消息：移除命令前缀
        normalized = re.sub(r'^[/!！]', '', msg_clean).strip()
        logger.debug(f"[DEBUG] 标准化后: '{normalized}'")

        # 提取参数部分（处理 "pixiv help" 格式）
        if normalized.lower().startswith('pixiv'):
            args_part = normalized[5:].strip()
            logger.debug(f"[DEBUG] 提取参数: '{args_part}'")
        else:
            args_part = normalized

        lower_args = args_part.lower().strip()

        # 定义所有帮助关键词
        help_keywords = {'help', '-h', '--help', '帮助', 'h', '?', '？'}

        # 精确匹配
        if lower_args in help_keywords:
            logger.debug(f"[DEBUG] ✅ 精确匹配到help关键词: '{lower_args}'")
            return True

        # 处理可能的额外空格或变体
        if lower_args in ('', ' '):
            return False

        # 检查是否以帮助关键词开头（如 "help me" 这种情况也应该显示帮助）
        for kw in ['help', '帮助']:
            if lower_args == kw or lower_args.startswith(kw + ' ') or lower_args.endswith(' ' + kw):
                logger.debug(f"[DEBUG] ✅ 模式匹配到help关键词: '{lower_args}' (关键词: {kw})")
                return True

        # 使用正则表达式进行更灵活的匹配
        help_patterns = [
            r'^(/|!|！)?pixiv\s*(help|-h|--help|帮助|\?)\s*$',
            r'^(help|-h|--help|帮助|\?|？)\s*$',
            r'^(/|!|！)?pixiv\s*$',  # 仅 /pixiv 不算help
        ]

        for pattern in help_patterns[:-1]:  # 排除最后一个模式（仅 /pixiv）
            if re.match(pattern, msg_clean, re.IGNORECASE):
                logger.debug(f"[DEBUG] ✅ 正则匹配成功: pattern='{pattern}'")
                return True

        logger.debug(f"[DEBUG] ❌ 不是help命令")
        return False

    def _build_request_params(self, message: str) -> Dict[str, Any]:
        # 标准化消息：移除命令前缀和 "pixiv" 关键字
        cleaned = re.sub(r'^[/!！]\s*pixiv\s*', '', message.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'^pixiv\s*', '', cleaned.strip(), flags=re.IGNORECASE)

        logger.debug(f"[DEBUG] _build_request_params 输入: '{message}' → 清理后: '{cleaned}'")

        parsed = CommandParser.parse(cleaned)

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
            return f"https://{self._image_proxy}/{pid}.jpg"
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
