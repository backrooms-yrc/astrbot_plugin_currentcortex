import re
import asyncio
from typing import Any, Dict, List, Optional

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

import os
import tempfile
import astrbot.api.message_components as Comp

from .dglab_device_store import DeviceStore
from .dglab_connection_pool import DeviceConnectionPool
from .dglab_commands import DGLabCommandHandler


API_BASE_URL = "https://api.bileizhen.top/api/pixiv"
HITOKOTO_API_URL = "https://api.bileizhen.top/api/one"
WEATHER_API_URL = "https://api.bileizhen.top/api/weather"
FEMBOY_API_URL = "https://api.bileizhen.top/api/femboy"
NETEASE_API_URL = "https://api.bileizhen.top/api/netease"
NETEASE_SEARCH_URL = "https://api.bileizhen.top/api/netease/search"
PIXIV_ARTWORK_URL = "https://www.pixiv.net/artworks/{}"

HITOKOTO_CATEGORIES = {
    "a": "动画",
    "b": "漫画",
    "c": "游戏",
    "d": "文学",
    "e": "原创",
    "f": "来自网络",
    "g": "其他",
    "h": "影视",
    "i": "诗词",
    "j": "网易云",
    "k": "哲学",
    "l": "抖机灵",
}

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

HITOKOTO_HELP_TEXT = """✨ 每日一言 使用说明

📌 基本命令
  /hitokoto             获取一条随机一言（默认全部分类）
  /hitokoto help       显示此帮助信息

📌 分类选项（使用分类代码）
  a - 动画            g - 其他
  b - 漫画            h - 影视
  c - 游戏            i - 诗词
  d - 文学            j - 网易云
  e - 原创            k - 哲学
  f - 来自网络        l - 抖机灵

📌 使用示例
  基础用法：
    /hitokoto                  随机获取一言
    /hitokoto help             显示帮助

  指定分类：
    /hitokoto a               获取动画类一言
    /hitokoto d               获取文学类一言
    /hitokoto i               获取诗词类一言

⚠️ 注意事项
  • 每次调用都会实时获取最新数据，无缓存
  • 一言内容来源于社区贡献，仅供参考
  • 如遇问题可发送 /hitokoto help 查看帮助"""

WEATHER_HELP_TEXT = """🌤️ 天气查询 使用说明

📌 基本命令
  /weather <城市名>     查询指定城市的天气
  /weather help         显示此帮助信息

📌 使用示例
  基础用法：
    /weather 广州市           查询广州市天气
    /weather 北京             查询北京市天气
    /weather 上海             查询上海市天气
    /weather help             显示帮助

📌 返回信息
  • 当前城市名称
  • 未来3天天气预报
  • 温度、天气状况、风力等信息

⚠️ 注意事项
  • 请输入正确的城市名称（支持中文）
  • 每次查询都会实时获取最新数据，无缓存
  • 数据来源于第三方API，仅供参考
  • 如遇问题可发送 /weather help 查看帮助"""


MUSIC_HELP_TEXT = """🎵 网易云音乐 使用说明

📌 基本命令
  /music <歌曲名>       搜索并获取歌曲信息（点歌）
  /music id:<歌曲ID>    通过歌曲ID获取详细信息
  /music search <关键词> 搜索歌曲列表
  /music help           显示此帮助信息

📌 使用示例
  点歌（搜索并返回第一首）：
    /music 孤勇者              搜索并获取「孤勇者」
    /music 周杰伦 晴天         搜索「周杰伦 晴天」

  通过ID获取：
    /music id:1901371647       获取指定ID的歌曲信息

  搜索歌曲列表：
    /music search 陈奕迅       搜索陈奕迅相关歌曲列表

📌 返回信息
  • 歌曲名称、艺术家、专辑
  • 专辑封面图片
  • 音质信息（码率、格式）
  • 播放链接

⚠️ 注意事项
  • 部分VIP歌曲可能无法获取播放链接
  • 播放链接有时效性，请及时使用
  • 数据来源于网易云音乐，仅供个人试听
  • 如遇问题可发送 /music help 查看帮助"""


FEMBOY_HELP_TEXT = """👗 男娘图片 使用说明

📌 基本命令
  /femboy              获取一张随机男娘图片（WebP 格式）
  /femboy help         显示此帮助信息

📌 功能特点
  • 随机返回南梁（男娘）主题图片
  • 图片格式为 WebP，加载速度快
  • 显示图片来源与备注信息
  • 支持自定义 API 密钥配置

📌 使用示例
  基础用法：
    /femboy                  获取随机男娘图片
    /femboy help             显示帮助

📌 返回信息
  • 图片内容（WebP 格式）
  • 图片来源信息
  • 备注说明（如有）

⚙️ 配置要求
  ⚠️ 使用前必须配置 API 密钥：
  1. 打开插件配置面板
  2. 填写「femboy_api_key」字段（您的 x-api-key）
  3. 保存配置并重启插件

⚠️ 注意事项
  • 图片来源于社区上传，仅供娱乐
  • 每次调用都会实时获取随机图片
  • 需要有效的 API 密钥才能使用此功能
  • 如遇问题可发送 /femboy help 查看帮助"""


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


class HitokotoAPIClient:
    def __init__(self, timeout: int = 10):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": "AstrBot-Hitokoto-Plugin/1.0",
            "Accept": "application/json",
        }

    async def fetch_hitokoto(
        self,
        category: Optional[str] = None,
        min_length: int = 0,
        max_length: int = 30,
    ) -> Dict[str, Any]:
        params = {
            "encode": "json",
            "min_length": min_length,
            "max_length": max_length,
        }
        if category and category.lower() in HITOKOTO_CATEGORIES:
            params["c"] = category.lower()

        logger.debug(f"Fetching hitokoto with params: {params}")

        async with aiohttp.ClientSession(timeout=self._timeout, headers=self._headers) as session:
            try:
                async with session.get(HITOKOTO_API_URL, params=params) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Hitokoto API returned status {resp.status}: {error_text[:500]}")
                        raise HitokotoAPIError(f"API 请求失败 (HTTP {resp.status})", status_code=resp.status)

                    data = await resp.json()
                    logger.debug(f"Hitokoto API response: {data}")

                    if not isinstance(data, dict) or "hitokoto" not in data:
                        logger.warning(f"Unexpected hitokoto response format: {data}")
                        raise HitokotoAPIError("API 返回数据格式异常")

                    return {
                        "text": data.get("hitokoto", ""),
                        "from": data.get("from", ""),
                        "type": data.get("type", ""),
                        "category_name": HITOKOTO_CATEGORIES.get(data.get("type", ""), "未知"),
                    }

            except aiohttp.ClientError as e:
                logger.error(f"Hitokoto network error: {e}")
                raise HitokotoAPIError(f"网络请求失败: {str(e)}", status_code=0) from e
            except asyncio.TimeoutError:
                logger.error("Hitokoto request timeout")
                raise HitokotoAPIError("API 请求超时，请稍后再试", status_code=0)


class WeatherAPIClient:
    def __init__(self, timeout: int = 15):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": "AstrBot-Weather-Plugin/1.0",
            "Accept": "application/json",
        }

    async def fetch_weather(self, city: str) -> Dict[str, Any]:
        if not city or not city.strip():
            raise WeatherAPIError("城市名称不能为空")

        params = {
            "dz": city.strip(),
            "return": "json",
        }

        logger.debug(f"Fetching weather for city: {city}")

        async with aiohttp.ClientSession(timeout=self._timeout, headers=self._headers) as session:
            try:
                async with session.get(WEATHER_API_URL, params=params) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Weather API returned status {resp.status}: {error_text[:500]}")
                        raise WeatherAPIError(f"API 请求失败 (HTTP {resp.status})", status_code=resp.status)

                    content_type = resp.headers.get("Content-Type", "")
                    if "json" not in content_type:
                        text_data = await resp.text()
                        logger.debug(f"Weather API returned text format: {text_data[:500]}")
                        return {"type": "text", "data": text_data}

                    data = await resp.json()
                    logger.debug(f"Weather API JSON response: {data}")

                    if not isinstance(data, dict):
                        logger.warning(f"Unexpected weather API response format: {type(data)}")
                        raise WeatherAPIError("API 返回数据格式异常")

                    if data.get("error"):
                        error_msg = data.get("error", "未知错误")
                        logger.error(f"Weather API returned error: {error_msg}")
                        raise WeatherAPIError(f"API 错误: {error_msg}")

                    weather_data = data.get("data", {})
                    if not weather_data:
                        logger.warning(f"Weather API returned empty data: {data}")
                        raise WeatherAPIError("API 返回数据为空")

                    return {
                        "type": "json",
                        "data": weather_data,
                        "city": weather_data.get("city", city),
                        "raw_response": data
                    }

            except aiohttp.ClientError as e:
                logger.error(f"Weather network error: {e}")
                raise WeatherAPIError(f"网络请求失败: {str(e)}", status_code=0) from e
            except asyncio.TimeoutError:
                logger.error("Weather request timeout")
                raise WeatherAPIError("API 请求超时，请稍后再试", status_code=0)


class FemboyAPIClient:
    def __init__(self, api_key: str = "", timeout: int = 15):
        if not api_key or not api_key.strip():
            raise ValueError("API 密钥不能为空，请在插件配置中填写 femboy_api_key")

        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": "AstrBot-Femboy-Plugin/1.0",
            "Accept": "application/json, image/*",
            "x-api-key": api_key.strip(),
        }

    async def fetch_femboy_image(self) -> Dict[str, Any]:
        logger.debug("Fetching random femboy image")

        async with aiohttp.ClientSession(timeout=self._timeout, headers=self._headers) as session:
            try:
                async with session.get(FEMBOY_API_URL) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Femboy API returned status {resp.status}: {error_text[:500]}")
                        raise FemboyAPIError(f"API 请求失败 (HTTP {resp.status})", status_code=resp.status)

                    content_type = resp.headers.get("Content-Type", "")

                    if "image" in content_type:
                        image_url = str(resp.url)
                        logger.info(f"Received direct image response: {image_url}")
                        return {"type": "redirect", "url": image_url}

                    data = await resp.json()
                    logger.debug(f"Femboy API JSON response: {data}")

                    if not isinstance(data, dict):
                        logger.warning(f"Unexpected femboy API response format: {type(data)}")
                        raise FemboyAPIError("API 返回数据格式异常")

                    if "url" not in data:
                        logger.warning(f"Femboy API missing url field: {data}")
                        raise FemboyAPIError("API 返回数据缺少图片链接")

                    return {
                        "type": "json",
                        "data": {
                            "url": data.get("url", ""),
                            "from": data.get("from", "未知来源"),
                            "note": data.get("note", ""),
                        }
                    }

            except aiohttp.ClientError as e:
                logger.error(f"Femboy network error: {e}")
                raise FemboyAPIError(f"网络请求失败: {str(e)}", status_code=0) from e
            except asyncio.TimeoutError:
                logger.error("Femboy request timeout")
                raise FemboyAPIError("API 请求超时，请稍后再试", status_code=0)


class NeteaseAPIClient:
    def __init__(self, timeout: int = 15):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": "AstrBot-Music-Plugin/1.0",
            "Accept": "application/json",
        }

    async def get_song(self, song_id: str) -> Dict[str, Any]:
        """通过歌曲ID获取歌曲信息和播放链接"""
        if not song_id or not song_id.strip():
            raise NeteaseAPIError("歌曲ID不能为空")

        params = {"id": song_id.strip()}
        logger.debug(f"[Netease] Fetching song by id: {song_id}")

        async with aiohttp.ClientSession(timeout=self._timeout, headers=self._headers) as session:
            try:
                async with session.get(NETEASE_API_URL, params=params) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"[Netease] API returned status {resp.status}: {error_text[:500]}")
                        raise NeteaseAPIError(f"API 请求失败 (HTTP {resp.status})", status_code=resp.status)

                    data = await resp.json()
                    logger.debug(f"[Netease] Song response: {data}")

                    if not isinstance(data, dict):
                        raise NeteaseAPIError("API 返回数据格式异常")

                    if not data.get("success"):
                        msg = data.get("message", "未知错误")
                        raise NeteaseAPIError(f"获取歌曲失败: {msg}")

                    song_data = data.get("data", {})
                    if not song_data:
                        raise NeteaseAPIError("API 返回歌曲数据为空")

                    return song_data

            except aiohttp.ClientError as e:
                logger.error(f"[Netease] Network error: {e}")
                raise NeteaseAPIError(f"网络请求失败: {str(e)}", status_code=0) from e
            except asyncio.TimeoutError:
                logger.error("[Netease] Request timeout")
                raise NeteaseAPIError("API 请求超时，请稍后再试", status_code=0)

    async def search_songs(self, query: str) -> List[Dict[str, Any]]:
        """通过关键词搜索歌曲"""
        if not query or not query.strip():
            raise NeteaseAPIError("搜索关键词不能为空")

        params = {"q": query.strip()}
        logger.debug(f"[Netease] Searching songs: {query}")

        async with aiohttp.ClientSession(timeout=self._timeout, headers=self._headers) as session:
            try:
                async with session.get(NETEASE_SEARCH_URL, params=params) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"[Netease] Search API returned status {resp.status}: {error_text[:500]}")
                        raise NeteaseAPIError(f"API 请求失败 (HTTP {resp.status})", status_code=resp.status)

                    data = await resp.json()
                    logger.debug(f"[Netease] Search response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

                    if not isinstance(data, dict):
                        raise NeteaseAPIError("API 返回数据格式异常")

                    if not data.get("success"):
                        msg = data.get("message", "未知错误")
                        raise NeteaseAPIError(f"搜索失败: {msg}")

                    songs = data.get("data", [])
                    if not isinstance(songs, list):
                        raise NeteaseAPIError("API 返回搜索结果格式异常")

                    return songs

            except aiohttp.ClientError as e:
                logger.error(f"[Netease] Search network error: {e}")
                raise NeteaseAPIError(f"网络请求失败: {str(e)}", status_code=0) from e
            except asyncio.TimeoutError:
                logger.error("[Netease] Search request timeout")
                raise NeteaseAPIError("API 请求超时，请稍后再试", status_code=0)


class NeteaseAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class HitokotoAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class WeatherAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class FemboyAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


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
        self._femboy_api_key = config.get("femboy_api_key", "").strip()

        if not self._femboy_api_key:
            logger.warning("⚠️ 未配置男娘图片 API 密钥 (femboy_api_key)，/femboy 命令将无法使用")
            logger.warning("请在插件配置面板中填写 femboy_api_key 字段")
            self._femboy_client = None
        else:
            try:
                self._femboy_client = FemboyAPIClient(
                    api_key=self._femboy_api_key,
                    timeout=self._request_timeout
                )
                logger.info("✅ 男娘图片 API 客户端初始化成功")
            except ValueError as e:
                logger.error(f"❌ 男娘图片 API 客户端初始化失败: {e}")
                self._femboy_client = None

        self._api_client = PixivAPIClient(timeout=self._request_timeout)
        self._hitokoto_client = HitokotoAPIClient(timeout=self._request_timeout)
        self._weather_client = WeatherAPIClient(timeout=self._request_timeout)
        self._netease_client = NeteaseAPIClient(timeout=self._request_timeout)

        dglab_config = config.get("dglab", {})
        server_url = dglab_config.get("server_url", "").strip()
        heartbeat_interval = float(dglab_config.get("heartbeat_interval", 60))
        auto_connect = dglab_config.get("auto_connect", False)

        self._device_store = DeviceStore(data_dir="data")
        self._connection_pool = DeviceConnectionPool(
            device_store=self._device_store,
            max_connections=50,
            idle_timeout=300,
            operation_timeout=10.0,
        )
        self._dglab_handler = DGLabCommandHandler(
            connection_pool=self._connection_pool,
            device_store=self._device_store,
        )

        if server_url:
            logger.info(f"✅ DG-LAB模块已初始化 (server={server_url}, auto_connect={auto_connect})")
        else:
            logger.info("ℹ️ DG-LAB模块已就绪（未配置服务器地址，用户需手动指定）")

        asyncio.create_task(self._connection_pool.start())

        logger.info(
            f"PixivPlugin initialized: r18={self._default_r18}, num={self._default_num}, "
            f"size={self._default_size}, proxy={self._image_proxy}, excludeAI={self._exclude_ai}"
        )

    @filter.command("hitokoto")
    async def hitokoto_command(self, event: AstrMessageEvent):
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()

        logger.debug(f"[Hitokoto] 收到消息: '{message_str}' from {user_name}")

        if self._is_help_command(message_str):
            logger.info(f"[Hitokoto] Help command triggered by {user_name}")
            yield event.plain_result(HITOKOTO_HELP_TEXT)
            return

        try:
            category = self._parse_hitokoto_params(message_str)
            logger.info(f"[Hitokoto] Fetching for user {user_name}, category={category}")

            result = await self._hitokoto_client.fetch_hitokoto(category=category)

            response_text = self._format_hitokoto_response(result)
            logger.info(f"[Hitokoto] Successfully fetched hitokoto for {user_name}")
            yield event.plain_result(response_text)

        except HitokotoAPIError as e:
            logger.error(f"[Hitokoto] API error for user {user_name}: {e}")
            error_msg = f"❌ 获取一言失败\n📝 错误信息：{str(e)}"
            if e.status_code:
                error_msg += f"\n🔢 状态码：{e.status_code}"
            error_msg += "\n💡 请稍后重试或发送 /hitokoto help 查看帮助"
            yield event.plain_result(error_msg)
        except Exception as e:
            logger.error(f"[Hitokoto] Unexpected error for user {user_name}: {e}", exc_info=True)
            yield event.plain_result(f"❌ 发生未知错误\n📝 错误信息：{str(e)}\n💡 请稍后重试")

    def _parse_hitokoto_params(self, message: str) -> Optional[str]:
        cleaned = re.sub(r'^[/!！]\s*hitokoto\s*', '', message.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'^hitokoto\s*', '', cleaned.strip(), flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        if not cleaned or cleaned.lower() in ('help', '-h', '--help', '帮助'):
            return None

        category = cleaned.lower()
        if category in HITOKOTO_CATEGORIES:
            return category
        return None

    def _format_hitokoto_response(self, result: Dict[str, Any]) -> str:
        text = result.get("text", "")
        source = result.get("from", "未知来源")
        category = result.get("category_name", "未知")

        response_parts = [
            f"✨ 每日一言",
            f"",
            f"「{text}」",
            f"",
            f"—— {source}",
            f"📂 分类：{category}",
        ]

        return "\n".join(response_parts)

    @filter.command("weather")
    async def weather_command(self, event: AstrMessageEvent):
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()

        logger.debug(f"[Weather] 收到消息: '{message_str}' from {user_name}")

        if self._is_help_command(message_str):
            logger.info(f"[Weather] Help command triggered by {user_name}")
            yield event.plain_result(WEATHER_HELP_TEXT)
            return

        try:
            city = self._parse_weather_params(message_str)
            if not city:
                logger.warning(f"[Weather] No city specified by user {user_name}")
                yield event.plain_result("❌ 请指定城市名称\n💡 用法：/weather 广州市\n💡 发送 /weather help 查看帮助")
                return

            if len(city) > 50:
                logger.warning(f"[Weather] City name too long ({len(city)} chars) from user {user_name}")
                yield event.plain_result("❌ 城市名称过长（最多50个字符）\n💡 请输入正确的城市名称")
                return

            logger.info(f"[Weather] Fetching weather for user {user_name}, city={city}")

            result = await self._weather_client.fetch_weather(city)

            logger.debug(f"[Weather] API response received for {city}, type={result.get('type')}")

            response_text = self._format_weather_response(result)
            logger.info(f"[Weather] Successfully formatted weather response for {user_name}, city={city}")
            yield event.plain_result(response_text)

        except WeatherAPIError as e:
            logger.error(f"[Weather] API error for user {user_name}: {e} (status_code={e.status_code})")
            error_msg = f"❌ 查询天气失败\n📝 错误信息：{str(e)}"
            if e.status_code:
                error_msg += f"\n🔢 状态码：{e.status_code}"
            error_msg += "\n💡 请稍后重试或检查城市名称是否正确"
            error_msg += "\n💡 支持的城市示例：广州市、北京市、上海市"
            yield event.plain_result(error_msg)
        except ValueError as e:
            logger.error(f"[Weather] Parameter validation error for user {user_name}: {e}")
            yield event.plain_result(f"❌ 参数错误：{str(e)}\n💡 用法：/weather 城市名称")
        except Exception as e:
            logger.error(f"[Weather] Unexpected error for user {user_name}: {e}", exc_info=True)
            yield event.plain_result(f"❌ 发生未知错误\n📝 错误信息：{str(e)}\n💡 请稍后重试或联系管理员")

    def _parse_weather_params(self, message: str) -> Optional[str]:
        cleaned = re.sub(r'^[/!！]\s*weather\s*', '', message.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'^weather\s*', '', cleaned.strip(), flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        if not cleaned or cleaned.lower() in ('help', '-h', '--help', '帮助'):
            return None

        return cleaned if cleaned else None

    def _format_weather_response(self, result: Dict[str, Any]) -> str:
        response_type = result.get("type", "text")

        if response_type == "text":
            text_data = result.get("data", "")
            return f"🌤️ 天气查询\n\n{text_data}"

        data = result.get("data", {})
        city = result.get("city", "未知城市")

        if not isinstance(data, dict):
            logger.warning(f"[Weather] Invalid data format in response: {type(data)}")
            return f"🌤️ {city} 天气信息\n\n⚠️ 数据格式异常"

        response_parts = [f"🌤️ {city} 天气预报"]

        adm = data.get("adm", "")
        if adm:
            response_parts.append(f"📍 {adm}")

        now = data.get("now")
        if isinstance(now, dict) and now:
            response_parts.append("\n☀️ 当前天气")
            temp = now.get("temp", "")
            weather = now.get("weather", "")
            wind_dir = now.get("windDir", "")
            wind_scale = now.get("windScale", "")
            humidity = now.get("humidity", "")
            feels_like = now.get("feelsLike", "")

            if temp:
                response_parts.append(f"🌡️ 温度：{temp}")
            if weather:
                response_parts.append(f"☁️ 天气：{weather}")
            if feels_like:
                response_parts.append(f"🤒 体感温度：{feels_like}")
            if wind_dir and wind_scale:
                response_parts.append(f"💨 风力：{wind_dir} {wind_scale}级")
            elif wind_dir:
                response_parts.append(f"💨 风向：{wind_dir}")
            if humidity:
                response_parts.append(f"💧 湿度：{humidity}%")

        forecast_list = data.get("forecast")
        if isinstance(forecast_list, list) and forecast_list:
            response_parts.append("\n📅 未来天气预报")
            for i, forecast in enumerate(forecast_list[:3], 1):
                if not isinstance(forecast, dict):
                    continue

                date = forecast.get("date", "")
                weekday = forecast.get("weekday", "")
                weather = forecast.get("weather", "")
                temp_min = forecast.get("tempMin", "")
                temp_max = forecast.get("tempMax", "")
                wind_dir = forecast.get("windDir", "")
                wind_scale = forecast.get("windScale", "")
                humidity_f = forecast.get("humidity", "")

                day_label = f"\n📆 第{i}天"
                if date and weekday:
                    day_label += f"：{date}（{weekday}）"
                elif date:
                    day_label += f"：{date}"

                response_parts.append(day_label)

                if weather:
                    response_parts.append(f"   ☁️ 天气：{weather}")
                if temp_min or temp_max:
                    temp_str = f"{temp_min}~{temp_max}" if temp_min and temp_max else (temp_max or temp_min)
                    response_parts.append(f"   🌡️ 温度：{temp_str}")
                if wind_dir and wind_scale:
                    response_parts.append(f"   💨 风力：{wind_dir} {wind_scale}级")
                elif wind_dir:
                    response_parts.append(f"   � 风向：{wind_dir}")
                if humidity_f:
                    response_parts.append(f"   💧 湿度：{humidity_f}%")

        final_response = "\n".join([p for p in response_parts if p])

        if len(final_response.strip()) <= len(f"🌤️ {city} 天气预报"):
            logger.warning(f"[Weather] Response appears empty after formatting. Raw data keys: {list(data.keys())}")
            raw_data = result.get("raw_response", {})
            return f"🌤️ {city} 天气信息\n\n⚠️ 未能解析天气数据\n原始数据：{str(raw_data)[:200]}"

        logger.info(f"[Weather] Formatted response with {len(response_parts)} parts for city: {city}")
        return final_response

    @filter.command("femboy")
    async def femboy_command(self, event: AstrMessageEvent):
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()

        logger.debug(f"[Femboy] 收到消息: '{message_str}' from {user_name}")

        if self._is_help_command(message_str):
            logger.info(f"[Femboy] Help command triggered by {user_name}")
            yield event.plain_result(FEMBOY_HELP_TEXT)
            return

        if not self._femboy_client:
            logger.warning(f"[Femboy] API client not initialized for user {user_name}")
            yield event.plain_result(
                "❌ 男娘图片功能未启用\n\n"
                "📝 原因：未配置 API 密钥\n"
                "💡 解决方法：\n"
                "   1. 打开插件配置面板\n"
                "   2. 找到「男娘图片 API 密钥 (femboy_api_key)」字段\n"
                "   3. 填写您的 x-api-key\n"
                "   4. 保存配置并重启插件\n\n"
                "⚠️ 配置完成后即可使用 /femboy 命令"
            )
            return

        try:
            logger.info(f"[Femboy] Fetching image for user {user_name}")

            result = await self._femboy_client.fetch_femboy_image()

            response_items = await self._process_femboy_response(result, event)
            for item in response_items:
                yield item

        except FemboyAPIError as e:
            logger.error(f"[Femboy] API error for user {user_name}: {e}")
            error_msg = f"❌ 获取男娘图片失败\n📝 错误信息：{str(e)}"
            if e.status_code:
                error_msg += f"\n🔢 状态码：{e.status_code}"
            error_msg += "\n💡 请稍后重试或发送 /femboy help 查看帮助"
            yield event.plain_result(error_msg)
        except Exception as e:
            logger.error(f"[Femboy] Unexpected error for user {user_name}: {e}", exc_info=True)
            yield event.plain_result(f"❌ 发生未知错误\n📝 错误信息：{str(e)}\n💡 请稍后重试")

    async def _process_femboy_response(
        self, result: Dict[str, Any], event: AstrMessageEvent
    ) -> List[Any]:
        response_type = result.get("type")

        if response_type == "redirect":
            url = result.get("url", "")
            caption = "👗 随机男娘图片"
            return [event.plain_result(caption), event.image_result(url)]

        if response_type == "json":
            data = result.get("data", {})
            image_url = data.get("url", "")
            source = data.get("from", "未知来源")
            note = data.get("note", "")

            if not image_url:
                return [event.plain_result("⚠️ 未能获取到图片链接\n💡 请稍后重试")]

            response_parts = ["👗 随机男娘图片"]
            if source and source != "未知来源":
                response_parts.append(f"📸 来源：{source}")
            if note:
                response_parts.append(f"📝 备注：{note}")

            caption = "\n".join(response_parts)
            return [event.plain_result(caption), event.image_result(image_url)]

        logger.warning(f"[Femboy] Unknown response type: {response_type}")
        return [event.plain_result("⚠️ API 返回了未知格式的数据，请联系管理员")]

    @filter.command("music")
    async def music_command(self, event: AstrMessageEvent):
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()

        logger.debug(f"[Music] 收到消息: '{message_str}' from {user_name}")

        if self._is_help_command(message_str):
            logger.info(f"[Music] Help command triggered by {user_name}")
            yield event.plain_result(MUSIC_HELP_TEXT)
            return

        try:
            query = self._parse_music_params(message_str)
            if not query:
                yield event.plain_result("❌ 请输入歌曲名或ID\n💡 用法：/music 歌曲名\n💡 发送 /music help 查看帮助")
                return

            # 通过ID获取歌曲
            id_match = re.match(r'^id\s*[:：]\s*(\d+)$', query, re.IGNORECASE)
            if id_match:
                song_id = id_match.group(1)
                logger.info(f"[Music] Fetching song by ID {song_id} for user {user_name}")
                song_data = await self._netease_client.get_song(song_id)
                response_items = await self._format_song_response(song_data, event)
                for item in response_items:
                    yield item
                return

            # 搜索模式：仅列出搜索结果
            search_match = re.match(r'^search\s+(.+)$', query, re.IGNORECASE)
            if search_match:
                search_query = search_match.group(1).strip()
                logger.info(f"[Music] Searching songs '{search_query}' for user {user_name}")
                songs = await self._netease_client.search_songs(search_query)
                if not songs:
                    yield event.plain_result(f"😕 未找到与「{search_query}」相关的歌曲\n💡 请尝试其他关键词")
                    return
                response_text = self._format_search_results(songs, search_query)
                yield event.plain_result(response_text)
                return

            # 点歌模式：搜索并获取第一首歌的详细信息
            logger.info(f"[Music] Quick play '{query}' for user {user_name}")
            songs = await self._netease_client.search_songs(query)
            if not songs:
                yield event.plain_result(f"😕 未找到与「{query}」相关的歌曲\n💡 请尝试其他关键词")
                return

            first_song = songs[0]
            song_id = str(first_song.get("id", ""))
            if not song_id:
                yield event.plain_result("⚠️ 搜索结果异常，未能获取歌曲ID")
                return

            song_data = await self._netease_client.get_song(song_id)
            response_items = await self._format_song_response(song_data, event)
            for item in response_items:
                yield item

        except NeteaseAPIError as e:
            logger.error(f"[Music] API error for user {user_name}: {e}")
            error_msg = f"❌ 获取音乐失败\n📝 错误信息：{str(e)}"
            if e.status_code:
                error_msg += f"\n🔢 状态码：{e.status_code}"
            error_msg += "\n💡 请稍后重试或发送 /music help 查看帮助"
            yield event.plain_result(error_msg)
        except Exception as e:
            logger.error(f"[Music] Unexpected error for user {user_name}: {e}", exc_info=True)
            yield event.plain_result(f"❌ 发生未知错误\n📝 错误信息：{str(e)}\n💡 请稍后重试")

    def _parse_music_params(self, message: str) -> Optional[str]:
        cleaned = re.sub(r'^[/!！]\s*music\s*', '', message.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'^music\s*', '', cleaned.strip(), flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        if not cleaned or cleaned.lower() in ('help', '-h', '--help', '帮助'):
            return None

        return cleaned

    async def _format_song_response(self, song_data: Dict[str, Any], event: AstrMessageEvent) -> List[Any]:
        name = song_data.get("name", "未知歌曲")
        artists = song_data.get("artists", "未知艺术家")
        album = song_data.get("album", "")
        pic_url = song_data.get("pic", "")
        url = song_data.get("url", "")
        level = song_data.get("level", "")
        bitrate = song_data.get("bitrate", 0)
        file_type = song_data.get("type", "")
        size = song_data.get("size", 0)

        parts = [f"🎵 {name}", f"👤 艺术家：{artists}"]
        if album:
            parts.append(f"💿 专辑：{album}")

        quality_parts = []
        if level:
            level_map = {"standard": "标准", "higher": "较高", "exhigh": "极高", "lossless": "无损", "hires": "Hi-Res"}
            quality_parts.append(level_map.get(level, level))
        if file_type:
            quality_parts.append(file_type.upper())
        if bitrate:
            quality_parts.append(f"{bitrate // 1000}kbps")
        if quality_parts:
            parts.append(f"🎧 音质：{' / '.join(quality_parts)}")

        if size:
            size_mb = size / (1024 * 1024)
            parts.append(f"📦 大小：{size_mb:.1f}MB")

        if url:
            parts.append(f"🔗 播放链接：{url}")
        else:
            parts.append("⚠️ 无法获取播放链接（可能需要VIP权限）")

        caption = "\n".join(parts)
        results = [event.plain_result(caption)]

        if pic_url:
            results.append(event.image_result(pic_url))

        # 如果有播放链接，尝试下载音频并通过 Comp.Record 发送语音条
        if url:
            try:
                local_path = await self._download_audio_to_temp(url, name)
                if local_path:
                    record_comp = Comp.Record(file=local_path, url=local_path)
                    results.append(event.chain_result([record_comp]))
                    logger.info(f"[Music] 已添加语音消息: {name} -> {local_path}")
            except Exception as e:
                logger.warning(f"[Music] 发送语音消息失败: {e}，仅发送文本链接")

        return results

    async def _download_audio_to_temp(self, url: str, name: str) -> Optional[str]:
        """下载音频文件到临时目录，返回本地文件路径"""
        try:
            # 确定文件扩展名
            ext = ".mp3"
            if ".flac" in url.lower():
                ext = ".flac"
            elif ".wav" in url.lower():
                ext = ".wav"
            elif ".m4a" in url.lower():
                ext = ".m4a"

            # 创建临时目录
            temp_dir = os.path.join(tempfile.gettempdir(), "astrbot_music")
            os.makedirs(temp_dir, exist_ok=True)

            # 生成安全的文件名
            safe_name = re.sub(r'[^\w\-.]', '_', name)[:50]
            temp_path = os.path.join(temp_dir, f"{safe_name}{ext}")

            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning(f"[Music] 下载音频失败: HTTP {resp.status}")
                        return None

                    with open(temp_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)

            logger.debug(f"[Music] 音频已下载到: {temp_path}")
            return temp_path

        except Exception as e:
            logger.warning(f"[Music] 下载音频异常: {e}")
            return None

    def _format_search_results(self, songs: List[Dict[str, Any]], query: str) -> str:
        parts = [f"🔍 搜索「{query}」结果：\n"]
        for i, song in enumerate(songs[:10], 1):
            name = song.get("name", "未知")
            artists = song.get("artists", "未知")
            song_id = song.get("id", "")
            parts.append(f"  {i}. {name} - {artists}")
            if song_id:
                parts.append(f"     ID: {song_id}")

        parts.append(f"\n💡 使用 /music id:<歌曲ID> 获取详细信息和播放链接")
        return "\n".join(parts)

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
        if hasattr(self, '_connection_pool'):
            await self._connection_pool.stop()
            logger.info("✅ DG-LAB连接池已停止")

    @filter.command("dglab")
    async def dglab_command(self, event: AstrMessageEvent):
        """DG-LAB设备管理命令入口"""
        message_str = event.message_str.strip()
        
        try:
            async for result in self._dglab_handler.handle_command(event, message_str):
                yield result
        except Exception as e:
            logger.error(f"[DGLab] 命令处理异常: {e}", exc_info=True)
            yield event.plain_result(
                f"❌ DG-LAB命令执行失败\n"
                f"📝 错误: {str(e)}\n"
                f"💡 发送 /dglab help 查看帮助"
            )
