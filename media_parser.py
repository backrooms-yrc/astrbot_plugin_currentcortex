import re
import json
import asyncio
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs, unquote

import aiohttp
from astrbot.api import logger


class MediaParserError(Exception):
    """媒体解析统一异常。

    kind 用于失败原因分级（见 _MEDIA_ERROR_HINTS 的消费端），便于把原始异常
    翻译成用户可理解的提示，而不是直接甩一坨异常文本：
        - format:  链接格式不识别 / 提取不到内容 ID
        - expired: 短链失效、链接过期
        - deleted: 内容已删除 / 设为私密 / 不存在
        - blocked: 平台反爬 / 风控拦截（403/412/418/429 等）
        - timeout: 网络超时
        - network: 网络连接异常
        - api:     上游接口返回业务错误（其余 HTTP 状态码）
        - unknown: 未分类异常
    """

    KIND_FORMAT = "format"
    KIND_EXPIRED = "expired"
    KIND_DELETED = "deleted"
    KIND_BLOCKED = "blocked"
    KIND_TIMEOUT = "timeout"
    KIND_NETWORK = "network"
    KIND_API = "api"
    KIND_UNKNOWN = "unknown"

    def __init__(self, message: str, status_code: int = 0, kind: str = "unknown"):
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind

    @staticmethod
    def kind_from_status(status_code: int) -> str:
        """把 HTTP 状态码映射为失败原因分级。"""
        if status_code in (403, 412, 418, 429):
            return MediaParserError.KIND_BLOCKED
        if status_code == 404:
            return MediaParserError.KIND_DELETED
        if status_code in (408, 504):
            return MediaParserError.KIND_TIMEOUT
        if status_code >= 400:
            return MediaParserError.KIND_API
        return MediaParserError.KIND_UNKNOWN


class URLExtractor:
    """从各种格式的分享链接中提取平台内容ID"""

    # 小红书链接模式
    XHS_PATTERNS = [
        re.compile(r"https?://(?:www\.)?xiaohongshu\.com/explore/([a-zA-Z0-9]+)"),
        re.compile(r"https?://xhslink\.com/([a-zA-Z0-9]+)"),
        re.compile(
            r"https?://(?:www\.)?xiaohongshu\.com/discovery/item/([a-zA-Z0-9]+)"
        ),
    ]

    # B站链接模式（短链模式单独持有引用：短码不是视频 ID，需跳转还原）
    BILIBILI_SHORT_PATTERN = re.compile(
        r"https?://b23\.tv/(BV[0-9A-Za-z]+|[a-zA-Z0-9]+)"
    )
    BILIBILI_PATTERNS = [
        re.compile(r"https?://(?:www\.)?bilibili\.com/video/(BV[0-9A-Za-z]+)"),
        BILIBILI_SHORT_PATTERN,
        re.compile(r"https?://(?:www\.)?bilibili\.com/video/av(\d+)"),
    ]

    # 抖音链接模式
    DOUYIN_PATTERNS = [
        re.compile(r"https?://(?:www\.)?douyin\.com/video/(\d+)"),
        re.compile(r"https?://v\.douyin\.com/([a-zA-Z0-9]+)"),
        re.compile(r"https?://(?:www\.)?iesdouyin\.com/share/video/(\d+)"),
    ]

    # 微博链接模式（含普通网页版微博正文、m 站移动版、短链）
    WEIBO_PATTERNS = [
        re.compile(r"https?://(?:www\.)?weibo\.com/\d+/([a-zA-Z0-9]+)"),
        re.compile(r"https?://m\.weibo\.cn/(?:detail|status)/([a-zA-Z0-9]+)"),
        re.compile(r"https?://weibo\.cn/status/([a-zA-Z0-9]+)"),
        re.compile(r"https?://t\.cn/([a-zA-Z0-9]+)"),
    ]

    @classmethod
    def extract_xiaohongshu(cls, text: str) -> Optional[str]:
        """提取小红书笔记ID"""
        for pattern in cls.XHS_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1)
        return None

    @classmethod
    def extract_bilibili(cls, text: str) -> Optional[Dict[str, str]]:
        """提取B站视频ID，返回 {'type': 'bv'|'av'|'short', 'id': str}

        b23.tv 短链的短码（如 KZclOli）不是 av 号，标记为 'short'，
        由解析器跟随 302 跳转还原成 BV 号后再取详情。
        """
        for pattern in cls.BILIBILI_PATTERNS:
            match = pattern.search(text)
            if match:
                vid = match.group(1)
                if vid.startswith("BV"):
                    return {"type": "bv", "id": vid}
                if pattern is cls.BILIBILI_SHORT_PATTERN:
                    return {"type": "short", "id": vid}
                return {"type": "av", "id": vid}
        return None

    @classmethod
    def extract_douyin(cls, text: str) -> Optional[str]:
        """提取抖音视频ID"""
        for pattern in cls.DOUYIN_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1)
        return None

    @classmethod
    def extract_weibo(cls, text: str) -> Optional[str]:
        """提取微博帖子ID（mid，或 t.cn 短链的短码，短链需再跳转解析）"""
        for pattern in cls.WEIBO_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1)
        return None

    @classmethod
    def detect_platform(cls, text: str) -> Optional[str]:
        """检测链接所属平台"""
        if cls.extract_xiaohongshu(text):
            return "xiaohongshu"
        if cls.extract_bilibili(text):
            return "bilibili"
        if cls.extract_douyin(text):
            return "douyin"
        if cls.extract_weibo(text):
            return "weibo"
        return None


class LeiZMediaAPI:
    """LeiZ API 媒体解析客户端（B站/抖音，x-api-key 鉴权）。

    站点前置 Cloudflare，必须携带浏览器 UA；任何失败（网络/非 JSON/
    success=false/HTTP 非 200）一律返回 None 并记日志，由调用方回退到
    平台官方路径解析——LeiZ 是增强而非硬依赖。

    B站视频流是服务端合并产物：解析响应给出一组票据 URL（merged.*，
    均为相对路径），完整 MP4 需先 POST prepareUrl 启动合并、轮询
    statusUrl 到 ready 后才能从 url 下载；票据约 1 小时过期。
    """

    BASE = "https://api.bileizhen.top"

    def __init__(self, api_key: str = "", timeout: int = 20):
        self._api_key = (api_key or "").strip()
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def _abs(self, path: str) -> str:
        """LeiZ 响应里的流地址是相对路径（/api/bilibili/stream?token=...）。"""
        if not path:
            return ""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return self.BASE + path

    async def _get_json(self, path: str, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """GET 并校验 {success, data} 包装；任何异常返回 None。"""
        headers = {**self._headers, "x-api-key": self._api_key}
        try:
            async with aiohttp.ClientSession(
                timeout=self._timeout, headers=headers
            ) as session:
                async with session.get(self.BASE + path, params=params, ssl=False) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning(
                            f"[LeiZMedia] HTTP {resp.status} {path}: {text[:120]}"
                        )
                        return None
                    try:
                        payload = await resp.json()
                    except (aiohttp.ClientError, ValueError, json.JSONDecodeError) as e:
                        # Cloudflare 质询页/HTML 兜底页会走到这里
                        logger.warning(f"[LeiZMedia] 响应非 JSON {path}: {e}")
                        return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"[LeiZMedia] 请求失败 {path}: {e}")
            return None
        if not isinstance(payload, dict) or not payload.get("success"):
            logger.warning(
                f"[LeiZMedia] 业务失败 {path}: {str(payload.get('message'))[:120]}"
            )
            return None
        data = payload.get("data")
        return data if isinstance(data, dict) else None

    async def parse_bilibili(self, url_or_text: str) -> Optional[Dict[str, Any]]:
        """B站解析：直接把分享链接交给 LeiZ（b23.tv 短链也由它展开）。"""
        match = re.search(r"https?://[^\s]+", url_or_text or "")
        target = match.group(0).rstrip("，。,.！!）)") if match else (url_or_text or "").strip()
        if not target:
            return None
        data = await self._get_json(
            "/api/bilibili", {"url": target, "qn": "80", "codec": "avc"}
        )
        if not data or not data.get("bvid"):
            return None
        merged = data.get("merged") or {}
        download = None
        if merged.get("url"):
            download = {
                "url": self._abs(merged["url"]),
                "prepare_url": self._abs(merged.get("prepareUrl", "")),
                "status_url": self._abs(merged.get("statusUrl", "")),
                "size": 0,
                "segments": 1,
                "quality": int(data.get("actualQuality", 0) or 0),
                "quality_label": str(data.get("qualityLabel", "")),
            }
        return {
            "bvid": data.get("bvid", ""),
            "aid": data.get("aid", 0),
            "title": data.get("title", ""),
            "desc": "",
            "cover": data.get("cover", ""),
            "duration": int(data.get("duration", 0) or 0),
            "pubdate": 0,
            "link": f"https://www.bilibili.com/video/{data.get('bvid', '')}",
            "owner": {
                "name": data.get("owner", ""),
                "mid": data.get("ownerUid", 0),
                "face": data.get("ownerFace", ""),
            },
            "stat": {},
            "pages": [
                {
                    "cid": data.get("cid", 0),
                    "page": data.get("page", 1),
                    "part": data.get("partTitle", ""),
                    "duration": int(data.get("duration", 0) or 0),
                }
            ],
            "page_count": int(data.get("pageCount", 1) or 1),
            "download_url": download,
            "source": "leiz",
        }

    async def parse_douyin(self, url_or_text: str) -> Optional[Dict[str, Any]]:
        """抖音解析：支持分享链接/文案/作品 ID，返回无水印资源。"""
        match = re.search(r"https?://[^\s]+", url_or_text or "")
        target = match.group(0).rstrip("，。,.！!）)") if match else (url_or_text or "").strip()
        if not target:
            return None
        data = await self._get_json("/api/douyin", {"url": target})
        if not data:
            return None
        aweme_id = str(data.get("aweme_id", "") or "")
        stats = data.get("statistics") or {}
        qualities = data.get("qualities") or []
        nwm_url = data.get("nwm_url") or (qualities[0].get("url", "") if qualities else "")
        images = []
        if data.get("content_type") == "image":
            images = [
                u for u in ((data.get("image_data") or {}).get("image_urls") or []) if u
            ]
        return {
            "video_id": aweme_id,
            "title": str(data.get("desc", "") or "")[:100],
            "desc": str(data.get("desc", "") or ""),
            "cover": data.get("cover_url", ""),
            "video_url": nwm_url if data.get("content_type") != "image" else "",
            "author": data.get("author_nickname", ""),
            "author_avatar": data.get(
                "author_avatar_url", (data.get("author") or {}).get("avatar_url", "")
            ),
            "likes": str(stats.get("digg_count", "") or ""),
            "comments": str(stats.get("comment_count", "") or ""),
            "shares": str(stats.get("share_count", "") or ""),
            "images": images,
            "url": f"https://www.douyin.com/video/{aweme_id}" if aweme_id else "",
            "source": "leiz",
        }


class BaseMediaParser:
    """媒体解析基类"""

    def __init__(self, timeout: int = 20):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, text/html, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    async def _fetch_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """获取JSON数据"""
        merged_headers = {**self._headers, **(headers or {})}
        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=merged_headers
        ) as session:
            try:
                async with session.get(url, params=params, ssl=False) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            f"[{self.__class__.__name__}] HTTP {resp.status}: {error_text[:500]}"
                        )
                        raise MediaParserError(
                            f"请求失败 (HTTP {resp.status})",
                            status_code=resp.status,
                            kind=MediaParserError.kind_from_status(resp.status),
                        )
                    return await resp.json()
            except aiohttp.ClientError as e:
                logger.error(f"[{self.__class__.__name__}] Network error: {e}")
                raise MediaParserError(
                    f"网络请求失败: {str(e)}", kind=MediaParserError.KIND_NETWORK
                ) from e
            except asyncio.TimeoutError:
                logger.error(f"[{self.__class__.__name__}] Request timeout")
                raise MediaParserError(
                    "请求超时，请稍后再试", kind=MediaParserError.KIND_TIMEOUT
                )

    async def _fetch_text(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        allow_redirects: bool = True,
    ) -> str:
        """获取文本数据"""
        merged_headers = {**self._headers, **(headers or {})}
        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=merged_headers
        ) as session:
            try:
                async with session.get(
                    url,
                    headers=merged_headers,
                    allow_redirects=allow_redirects,
                    ssl=False,
                ) as resp:
                    if resp.status not in (200, 301, 302, 307, 308):
                        error_text = await resp.text()
                        logger.error(
                            f"[{self.__class__.__name__}] HTTP {resp.status}: {error_text[:500]}"
                        )
                        raise MediaParserError(
                            f"请求失败 (HTTP {resp.status})",
                            status_code=resp.status,
                            kind=MediaParserError.kind_from_status(resp.status),
                        )
                    return await resp.text()
            except aiohttp.ClientError as e:
                logger.error(f"[{self.__class__.__name__}] Network error: {e}")
                raise MediaParserError(
                    f"网络请求失败: {str(e)}", kind=MediaParserError.KIND_NETWORK
                ) from e
            except asyncio.TimeoutError:
                logger.error(f"[{self.__class__.__name__}] Request timeout")
                raise MediaParserError(
                    "请求超时，请稍后再试", kind=MediaParserError.KIND_TIMEOUT
                )


class XiaoHongShuParser(BaseMediaParser):
    """小红书内容解析器"""

    def __init__(self, timeout: int = 20):
        super().__init__(timeout)
        self._headers["Referer"] = "https://www.xiaohongshu.com/"

    async def parse(self, url_or_text: str) -> Dict[str, Any]:
        """解析小红书链接"""
        note_id = URLExtractor.extract_xiaohongshu(url_or_text)
        if not note_id:
            raise MediaParserError(
                "未能从小红书链接中提取到笔记ID，请检查链接格式",
                kind=MediaParserError.KIND_FORMAT,
            )

        # 短链接需要展开
        if "xhslink.com" in url_or_text:
            note_id = await self._resolve_short_link(url_or_text)

        return await self._fetch_note_detail(note_id)

    async def _resolve_short_link(self, short_url: str) -> str:
        """解析短链接获取真实笔记ID"""
        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=self._headers
        ) as session:
            try:
                async with session.get(
                    short_url, allow_redirects=True, ssl=False
                ) as resp:
                    final_url = str(resp.url)
                    match = re.search(r"/explore/([a-zA-Z0-9]+)", final_url)
                    if match:
                        return match.group(1)
            except Exception as e:
                logger.error(f"[XiaoHongShu] 短链接解析失败: {e}")
        raise MediaParserError(
            "短链接解析失败，请使用完整链接", kind=MediaParserError.KIND_EXPIRED
        )

    async def _fetch_note_detail(self, note_id: str) -> Dict[str, Any]:
        """获取笔记详情"""
        # 方法1: 尝试通过网页获取初始数据
        url = f"https://www.xiaohongshu.com/explore/{note_id}"

        try:
            html = await self._fetch_text(url)
            return self._parse_note_html(html, note_id)
        except MediaParserError:
            pass

        # 如果网页解析失败，返回基础信息
        return {
            "note_id": note_id,
            "title": "",
            "desc": "",
            "images": [],
            "video": None,
            "author": "",
            "likes": "",
            "url": url,
        }

    def _parse_note_html(self, html: str, note_id: str) -> Dict[str, Any]:
        """从小红书网页HTML中解析笔记数据"""
        result = {
            "note_id": note_id,
            "title": "",
            "desc": "",
            "images": [],
            "video": None,
            "author": "",
            "likes": "",
            "url": f"https://www.xiaohongshu.com/explore/{note_id}",
        }

        # 提取初始状态JSON
        init_state_match = re.search(
            r"window\.__INITIAL_STATE__\s*=\s*({.+?})\s*</script>", html
        )
        if init_state_match:
            try:
                # 安全截断JSON
                json_str = init_state_match.group(1)
                data = json.loads(json_str)
                note_data = (
                    data.get("note", {})
                    .get("noteDetailMap", {})
                    .get(note_id, {})
                    .get("note", {})
                )
                if note_data:
                    result["title"] = note_data.get("title", "")
                    result["desc"] = note_data.get("desc", "")
                    result["likes"] = str(
                        note_data.get("interactInfo", {}).get("likedCount", "")
                    )

                    author = note_data.get("user", {})
                    result["author"] = author.get("nickname", "")

                    # 提取图片（无水印）
                    image_list = note_data.get("imageList", [])
                    for img in image_list:
                        if isinstance(img, dict):
                            # 优先使用无水印原图URL
                            img_url = (
                                img.get("urlDefault", "")
                                or img.get("url", "")
                                or img.get("infoList", [{}])[0].get("url", "")
                            )
                            if img_url:
                                result["images"].append(
                                    {
                                        "url": img_url,
                                        "width": img.get("width", 0),
                                        "height": img.get("height", 0),
                                    }
                                )

                    # 提取视频
                    video_info = note_data.get("video", {})
                    if video_info:
                        result["video"] = {
                            "url": video_info.get("media", {})
                            .get("stream", {})
                            .get("h264", [{}])[0]
                            .get("masterUrl", ""),
                            "cover": video_info.get("cover", {}).get("url", ""),
                        }

                    return result
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.error(f"[XiaoHongShu] JSON解析失败: {e}")

        # 备用方案：提取 og 标签
        og_title = re.search(
            r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html
        )
        og_image = re.search(
            r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html
        )
        og_desc = re.search(
            r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html
        )

        if og_title:
            result["title"] = og_title.group(1)
        if og_image:
            result["images"].append({"url": og_image.group(1), "width": 0, "height": 0})
        if og_desc:
            result["desc"] = og_desc.group(1)

        return result


class BilibiliParser(BaseMediaParser):
    """B站视频解析器（优先 LeiZ API，失败回退官方接口）"""

    def __init__(self, timeout: int = 20, leiz_api_key: str = ""):
        super().__init__(timeout)
        self._headers["Referer"] = "https://www.bilibili.com/"
        self._leiz = LeiZMediaAPI(leiz_api_key, timeout)

    async def parse(self, url_or_text: str) -> Dict[str, Any]:
        """解析B站链接"""
        # 优先走 LeiZ API：支持分享短链直达、站长账号可解锁 1080P+、
        # 服务端合并 DASH 出完整 MP4（无 Referer 防盗链问题）
        if self._leiz.available:
            result = await self._leiz.parse_bilibili(url_or_text)
            if result is not None:
                return result
            logger.info("[Bilibili] LeiZ 解析失败，回退官方接口")
        video_info = URLExtractor.extract_bilibili(url_or_text)
        # b23.tv 短码不是视频 ID，需要跟随跳转还原成 BV 号
        if not video_info or video_info["type"] == "short":
            # 尝试从短链接解析
            if "b23.tv" in url_or_text:
                bvid = await self._resolve_short_link(url_or_text)
                video_info = {"type": "bv", "id": bvid}
            else:
                raise MediaParserError(
                    "未能从B站链接中提取到视频ID，请检查链接格式",
                    kind=MediaParserError.KIND_FORMAT,
                )

        vid = video_info["id"]
        vid_type = video_info["type"]

        # 如果是av号，先转为bv号
        if vid_type == "av":
            vid = self._av2bv(int(vid))

        return await self._fetch_video_detail(vid)

    async def _resolve_short_link(self, short_url: str) -> str:
        """解析B站短链接，跟随跳转从最终 URL 中还原 BV 号"""
        # 分享文案可能带前缀文字（如「【标题】 https://b23.tv/xxx」），先抽出 URL 本身
        url_match = re.search(r"https?://b23\.tv/[^\s，。,.！!）)]+", short_url)
        if url_match:
            request_url = url_match.group(0)
        else:
            bare = re.search(r"b23\.tv/([a-zA-Z0-9]+)", short_url)
            if not bare:
                raise MediaParserError(
                    "B站短链接格式无法识别，请发送完整链接",
                    kind=MediaParserError.KIND_FORMAT,
                )
            request_url = f"https://b23.tv/{bare.group(1)}"
        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=self._headers
        ) as session:
            try:
                async with session.get(
                    request_url, allow_redirects=True, ssl=False
                ) as resp:
                    final_url = str(resp.url)
                    match = re.search(r"/(BV[0-9A-Za-z]+)", final_url)
                    if match:
                        return match.group(1)
            except Exception as e:
                logger.error(f"[Bilibili] 短链接解析失败: {e}")
        raise MediaParserError(
            "B站短链接解析失败（可能已失效或不是视频链接），请使用完整链接",
            kind=MediaParserError.KIND_EXPIRED,
        )

    @staticmethod
    def _av2bv(av_number: int) -> str:
        """av号转bv号"""
        table = "fZodR9XQDSUm21yCkr6zBqiveYah8bt4xsWpHnJE7jL5VG3guMTKNPAwcF"
        tr = {table[i]: i for i in range(58)}
        s = [11, 10, 3, 8, 4, 6]
        xor = 177451812
        add = 8728348608

        av_number = (av_number ^ xor) + add
        # 模板必须 12 位（BV 号固定长度），末位下标 11 会被 s[0] 覆盖，
        # 少一位会导致 r[11] 赋值越界
        r = list("BV1xx4x1x7xx")
        for i in range(6):
            r[s[i]] = table[av_number // 58**i % 58]
        return "".join(r)

    async def _fetch_video_detail(self, bvid: str) -> Dict[str, Any]:
        """获取B站视频详情"""
        api_url = "https://api.bilibili.com/x/web-interface/view"
        params = {"bvid": bvid}

        data = await self._fetch_json(api_url, params=params)

        if data.get("code") != 0:
            message = data.get("message", "未知错误")
            # B站「稿件不可见/不存在」类业务错误（如 -404 啊叻？不见了），
            # 归类为内容已删除而非接口异常
            kind = (
                MediaParserError.KIND_DELETED
                if any(kw in str(message) for kw in ("不存在", "不见了", "删除", "失效"))
                else MediaParserError.KIND_API
            )
            raise MediaParserError(f"B站API错误: {message}", kind=kind)

        video_data = data.get("data", {})
        if not video_data:
            raise MediaParserError(
                "未能获取到视频数据（视频可能已被删除或设为私密）",
                kind=MediaParserError.KIND_DELETED,
            )

        # 构建返回结果
        result = {
            "bvid": bvid,
            "aid": video_data.get("aid", 0),
            "title": video_data.get("title", ""),
            "desc": video_data.get("desc", ""),
            "cover": video_data.get("pic", ""),
            "duration": video_data.get("duration", 0),
            "pubdate": video_data.get("pubdate", 0),
            "link": f"https://www.bilibili.com/video/{bvid}",
            "owner": {
                "name": video_data.get("owner", {}).get("name", ""),
                "mid": video_data.get("owner", {}).get("mid", 0),
                "face": video_data.get("owner", {}).get("face", ""),
            },
            "stat": {
                "view": video_data.get("stat", {}).get("view", 0),
                "like": video_data.get("stat", {}).get("like", 0),
                "coin": video_data.get("stat", {}).get("coin", 0),
                "favorite": video_data.get("stat", {}).get("favorite", 0),
                "share": video_data.get("stat", {}).get("share", 0),
                "reply": video_data.get("stat", {}).get("reply", 0),
            },
            "pages": [],
            "download_url": None,
        }

        # 提取分P信息
        pages = video_data.get("pages", [])
        for page in pages:
            result["pages"].append(
                {
                    "cid": page.get("cid", 0),
                    "page": page.get("page", 1),
                    "part": page.get("part", ""),
                    "duration": page.get("duration", 0),
                }
            )

        # 尝试获取视频下载地址（需要cid）
        if pages:
            try:
                cid = pages[0]["cid"]
                download_info = await self._fetch_download_url(bvid, cid)
                result["download_url"] = download_info
            except Exception as e:
                logger.warning(f"[Bilibili] 获取下载地址失败: {e}")

        return result

    async def _fetch_download_url(
        self, bvid: str, cid: int
    ) -> Optional[Dict[str, Any]]:
        """尝试获取视频下载地址（官方 playurl 接口，游客身份）。

        注意 fnval 必须传 0（传统模式）：B 站在 fnval=16（DASH）下只返回
        音视频分离的 dash 流、不再填 durl，而分离流没有音轨不能直接播放。
        fnval=0 返回合并好的 mp4/flv（durl），游客一般可拿到最高 720p。
        长视频 durl 会切成多段，segments>1 时只发首段是不完整视频，
        该信息透传给上层决定是否发送。

        Returns:
            ``{"url": 直链, "size": 字节数, "segments": 段数, "quality": 清晰度}``，
            失败返回 None。
        """
        api_url = "https://api.bilibili.com/x/player/playurl"
        params = {
            "bvid": bvid,
            "cid": cid,
            "qn": "80",
            "fnver": "0",
            "fnval": "0",
            "fourk": "1",
        }

        try:
            data = await self._fetch_json(api_url, params=params)
            if data.get("code") == 0:
                durl = data.get("data", {}).get("durl", []) or []
                if durl:
                    first = durl[0]
                    url = first.get("url", "")
                    if url.startswith("//"):
                        url = "https:" + url
                    if url:
                        return {
                            "url": url,
                            "size": int(first.get("size", 0) or 0),
                            "segments": len(durl),
                            "quality": int(
                                data.get("data", {}).get("quality", 0) or 0
                            ),
                        }
        except Exception as e:
            logger.warning(f"[Bilibili] 获取下载地址失败: {e}")

        return None


class DouyinParser(BaseMediaParser):
    """抖音内容解析器（优先 LeiZ API，失败回退网页解析）"""

    def __init__(self, timeout: int = 20, leiz_api_key: str = ""):
        super().__init__(timeout)
        self._headers["Referer"] = "https://www.douyin.com/"
        self._leiz = LeiZMediaAPI(leiz_api_key, timeout)

    async def parse(self, url_or_text: str) -> Dict[str, Any]:
        """解析抖音链接"""
        # 优先走 LeiZ API：无水印直链、图集、评论与统计，覆盖分享文案
        if self._leiz.available:
            result = await self._leiz.parse_douyin(url_or_text)
            if result is not None:
                return result
            logger.info("[Douyin] LeiZ 解析失败，回退网页解析")
        video_id = URLExtractor.extract_douyin(url_or_text)
        if not video_id:
            # 尝试短链接
            if "v.douyin.com" in url_or_text:
                video_id = await self._resolve_short_link(url_or_text)
            else:
                raise MediaParserError(
                    "未能从抖音链接中提取到视频ID，请检查链接格式",
                    kind=MediaParserError.KIND_FORMAT,
                )

        return await self._fetch_video_detail(video_id)

    async def _resolve_short_link(self, short_url: str) -> str:
        """解析抖音短链接"""
        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=self._headers
        ) as session:
            try:
                async with session.get(
                    short_url, allow_redirects=True, ssl=False
                ) as resp:
                    final_url = str(resp.url)
                    match = re.search(r"/video/(\d+)", final_url)
                    if match:
                        return match.group(1)
            except Exception as e:
                logger.error(f"[Douyin] 短链接解析失败: {e}")
        raise MediaParserError(
            "抖音短链接解析失败，请使用完整链接", kind=MediaParserError.KIND_EXPIRED
        )

    async def _fetch_video_detail(self, video_id: str) -> Dict[str, Any]:
        """获取抖音视频详情"""
        url = f"https://www.douyin.com/video/{video_id}"

        try:
            html = await self._fetch_text(url)
            return self._parse_video_html(html, video_id)
        except MediaParserError as e:
            logger.error(f"[Douyin] 网页获取失败: {e}")

        # 如果网页解析失败，返回基础信息
        return {
            "video_id": video_id,
            "title": "",
            "desc": "",
            "cover": "",
            "video_url": "",
            "author": "",
            "likes": "",
            "url": url,
        }

    def _parse_video_html(self, html: str, video_id: str) -> Dict[str, Any]:
        """从抖音网页HTML中解析视频数据"""
        result = {
            "video_id": video_id,
            "title": "",
            "desc": "",
            "cover": "",
            "video_url": "",
            "author": "",
            "author_avatar": "",
            "likes": "",
            "comments": "",
            "shares": "",
            "url": f"https://www.douyin.com/video/{video_id}",
        }

        # 提取初始状态JSON（SSR渲染数据）
        render_data_match = re.search(
            r'<script[^>]*id="RENDER_DATA"[^>]*type="application/json"[^>]*>([^<]+)</script>',
            html,
        )
        if render_data_match:
            try:
                json_str = unquote(render_data_match.group(1))
                data = json.loads(json_str)

                # 定位视频数据
                app_state = data.get("app", {})
                video_detail = None

                # 尝试多种路径定位视频详情
                for key in app_state:
                    if "videoInfo" in str(key).lower() or "item" in str(key).lower():
                        video_detail = app_state[key]
                        break

                if video_detail and isinstance(video_detail, dict):
                    info = video_detail.get("videoInfo", video_detail)
                    if isinstance(info, dict):
                        result["title"] = info.get("title", "")
                        result["desc"] = info.get("desc", "")

                        # 提取作者信息
                        author_info = info.get("authorInfo", {})
                        if author_info:
                            result["author"] = author_info.get("nickname", "")
                            result["author_avatar"] = author_info.get("avatar", "")

                        # 提取统计数据
                        interact = info.get("interactInfo", {})
                        if interact:
                            result["likes"] = str(interact.get("diggCount", ""))
                            result["comments"] = str(interact.get("commentCount", ""))
                            result["shares"] = str(interact.get("shareCount", ""))

                        # 提取视频地址（无水印）
                        video_list = info.get("video", {}).get("playAddr", [])
                        if video_list and isinstance(video_list, list):
                            result["video_url"] = video_list[0]
                        elif isinstance(video_list, str):
                            result["video_url"] = video_list

                        # 提取封面
                        cover_list = info.get("video", {}).get("coverUrl", [])
                        if cover_list and isinstance(cover_list, list):
                            result["cover"] = cover_list[0]
                        elif isinstance(cover_list, str):
                            result["cover"] = cover_list

                        return result
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.error(f"[Douyin] JSON解析失败: {e}")

        # 备用方案：提取 og 标签
        og_title = re.search(
            r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html
        )
        og_image = re.search(
            r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html
        )
        og_video = re.search(
            r'<meta[^>]+property="og:video"[^>]+content="([^"]+)"', html
        )

        if og_title:
            result["title"] = og_title.group(1)
        if og_image:
            result["cover"] = og_image.group(1)
        if og_video:
            result["video_url"] = og_video.group(1)

        return result


class WeiboParser(BaseMediaParser):
    """微博内容解析器"""

    def __init__(self, timeout: int = 20):
        super().__init__(timeout)
        self._headers["Referer"] = "https://m.weibo.cn/"

    async def parse(self, url_or_text: str) -> Dict[str, Any]:
        """解析微博链接"""
        mid = URLExtractor.extract_weibo(url_or_text)
        if not mid:
            raise MediaParserError(
                "未能从微博链接中提取到帖子ID，请检查链接格式",
                kind=MediaParserError.KIND_FORMAT,
            )

        # t.cn 短链需要先跳转拿到真实 mid
        if "t.cn/" in url_or_text:
            mid = await self._resolve_short_link(url_or_text)

        return await self._fetch_post_detail(mid, url_or_text)

    async def _resolve_short_link(self, short_url: str) -> str:
        """解析微博 t.cn 短链，返回最终 URL 中的帖子 ID"""
        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=self._headers
        ) as session:
            try:
                async with session.get(
                    short_url, allow_redirects=True, ssl=False
                ) as resp:
                    final_url = str(resp.url)
                    mid = URLExtractor.extract_weibo(final_url)
                    if mid:
                        return mid
            except Exception as e:
                logger.error(f"[Weibo] 短链接解析失败: {e}")
        raise MediaParserError(
            "微博短链接解析失败，请使用完整链接", kind=MediaParserError.KIND_EXPIRED
        )

    async def _fetch_post_detail(self, mid: str, original_url: str) -> Dict[str, Any]:
        """通过移动版接口获取微博详情，失败时回退到网页 og 标签解析"""
        api_url = f"https://m.weibo.cn/statuses/show?id={mid}"
        try:
            data = await self._fetch_json(api_url)
            payload = data.get("data") if isinstance(data, dict) else None
            if payload:
                return self._parse_status_payload(payload, mid, original_url)
        except MediaParserError as e:
            logger.error(f"[Weibo] API 获取失败，尝试网页兜底: {e}")

        try:
            html = await self._fetch_text(f"https://m.weibo.cn/detail/{mid}")
            return self._parse_html_fallback(html, mid, original_url)
        except MediaParserError as e:
            logger.error(f"[Weibo] 网页兜底也失败: {e}")

        return {
            "mid": mid,
            "title": "",
            "text": "",
            "author": "",
            "images": [],
            "url": original_url,
        }

    @staticmethod
    def _strip_html_tags(text: str) -> str:
        return re.sub(r"<[^>]+>", "", text or "").strip()

    def _parse_status_payload(
        self, payload: Dict[str, Any], mid: str, original_url: str
    ) -> Dict[str, Any]:
        """解析 m.weibo.cn statuses/show 接口返回的 JSON 结构"""
        user = payload.get("user", {}) if isinstance(payload.get("user"), dict) else {}
        pics = payload.get("pics", [])
        images = []
        if isinstance(pics, list):
            for pic in pics:
                pic_url = pic.get("large", {}).get("url") if isinstance(pic, dict) else None
                if pic_url:
                    images.append(pic_url)

        page_info = payload.get("page_info", {})
        video_url = ""
        if isinstance(page_info, dict) and page_info.get("type") == "video":
            media_info = page_info.get("media_info", {})
            video_url = media_info.get("stream_url_hd") or media_info.get("stream_url", "")

        return {
            "mid": mid,
            "text": self._strip_html_tags(payload.get("text", "")),
            "author": user.get("screen_name", ""),
            "reposts": str(payload.get("reposts_count", "")),
            "comments": str(payload.get("comments_count", "")),
            "likes": str(payload.get("attitudes_count", "")),
            "images": images,
            "video_url": video_url,
            "url": original_url or f"https://m.weibo.cn/detail/{mid}",
        }

    def _parse_html_fallback(
        self, html: str, mid: str, original_url: str
    ) -> Dict[str, Any]:
        """从网页 og 标签中兜底提取基础信息"""
        result = {
            "mid": mid,
            "text": "",
            "author": "",
            "images": [],
            "video_url": "",
            "url": original_url or f"https://m.weibo.cn/detail/{mid}",
        }
        og_title = re.search(
            r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html
        )
        og_image = re.search(
            r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html
        )
        if og_title:
            result["text"] = og_title.group(1)
        if og_image:
            result["images"] = [og_image.group(1)]
        return result


class MediaParseCache:
    """媒体解析结果的内存 LRU 缓存（url → 解析结果，带 TTL）。

    群里经常有人重复发同一条链接，命中缓存可直接返回，减少对目标平台的
    请求频率，也降低触发反爬/封 IP 的概率。仅缓存成功结果（异常不缓存）。

    线程模型：AstrBot 命令处理器跑在事件循环内，本身单线程；加锁是防御
    未来可能的多线程调用（与插件内其他存储风格一致）。
    """

    def __init__(self, ttl_seconds: float = 600.0, max_items: int = 128):
        self._ttl = max(0.0, float(ttl_seconds))
        self._max_items = max(1, int(max_items))
        self._lock = threading.Lock()
        # key -> (expire_at, value)；OrderedDict 实现 LRU（最近访问移到末尾）
        self._store: "OrderedDict[str, tuple]" = OrderedDict()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """取缓存；过期或不存在返回 None，命中时会刷新 LRU 位置。"""
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expire_at, value = item
            if self._ttl <= 0 or time.time() >= expire_at:
                # 过期惰性清理
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return value

    def put(self, key: str, value: Dict[str, Any]) -> None:
        """写入缓存并裁剪到 max_items（淘汰最久未使用条目）。"""
        expire_at = time.time() + self._ttl if self._ttl > 0 else float("inf")
        with self._lock:
            self._store[key] = (expire_at, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_items:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


class MediaParserManager:
    """媒体解析管理器（带结果缓存）"""

    # 缓存 key 归一化：取文本中首个 URL 部分（分享文案可能带表情/前缀）
    _URL_RE = re.compile(r"https?://[^\s]+")

    def __init__(
        self,
        timeout: int = 20,
        cache_enable: bool = True,
        cache_ttl: float = 600.0,
        cache_max_items: int = 128,
        leiz_api_key: str = "",
    ):
        self.xiaohongshu = XiaoHongShuParser(timeout)
        self.bilibili = BilibiliParser(timeout, leiz_api_key=leiz_api_key)
        self.douyin = DouyinParser(timeout, leiz_api_key=leiz_api_key)
        self.weibo = WeiboParser(timeout)
        self._cache = MediaParseCache(ttl_seconds=cache_ttl, max_items=cache_max_items) if cache_enable else None

    def _cache_key(self, url_or_text: str) -> str:
        """归一化缓存 key：取首个 URL；无 URL 时退回原文 strip。"""
        match = self._URL_RE.search(url_or_text or "")
        return (match.group(0) if match else (url_or_text or "").strip()).strip().rstrip("，。,.！!）)")

    async def parse(self, url_or_text: str) -> Dict[str, Any]:
        """自动识别平台并解析（结果走缓存）"""
        return await self.parse_platform(None, url_or_text)

    async def parse_platform(
        self, platform: Optional[str], url_or_text: str
    ) -> Dict[str, Any]:
        """解析指定平台（platform 为 None 时自动识别），统一走缓存。

        Args:
            platform: "xiaohongshu" / "bilibili" / "douyin" / "weibo"，None=自动识别。
            url_or_text: 原始链接或分享文本。

        Returns:
            ``{"platform": <平台名>, "data": <解析结果>}``。

        Raises:
            MediaParserError: 解析失败（带 kind 分级）。失败结果不缓存，
                避免瞬时网络抖动把错误固化 10 分钟。
        """
        key = self._cache_key(url_or_text)
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                logger.debug(f"[MediaParser] 缓存命中: {key[:80]}")
                return cached

        if platform is None:
            platform = URLExtractor.detect_platform(url_or_text)

        if platform == "xiaohongshu":
            result = {
                "platform": "xiaohongshu",
                "data": await self.xiaohongshu.parse(url_or_text),
            }
        elif platform == "bilibili":
            result = {
                "platform": "bilibili",
                "data": await self.bilibili.parse(url_or_text),
            }
        elif platform == "douyin":
            result = {"platform": "douyin", "data": await self.douyin.parse(url_or_text)}
        elif platform == "weibo":
            result = {"platform": "weibo", "data": await self.weibo.parse(url_or_text)}
        else:
            raise MediaParserError(
                "未能识别链接所属平台，请检查链接格式是否支持（小红书/B站/抖音/微博）",
                kind=MediaParserError.KIND_FORMAT,
            )

        if self._cache is not None:
            self._cache.put(key, result)
        return result
