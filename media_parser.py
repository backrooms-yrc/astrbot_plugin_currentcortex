import re
import json
import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs, unquote

import aiohttp
from astrbot.api import logger


class MediaParserError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


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

    # B站链接模式
    BILIBILI_PATTERNS = [
        re.compile(r"https?://(?:www\.)?bilibili\.com/video/(BV[0-9A-Za-z]+)"),
        re.compile(r"https?://b23\.tv/(BV[0-9A-Za-z]+|[a-zA-Z0-9]+)"),
        re.compile(r"https?://(?:www\.)?bilibili\.com/video/av(\d+)"),
    ]

    # 抖音链接模式
    DOUYIN_PATTERNS = [
        re.compile(r"https?://(?:www\.)?douyin\.com/video/(\d+)"),
        re.compile(r"https?://v\.douyin\.com/([a-zA-Z0-9]+)"),
        re.compile(r"https?://(?:www\.)?iesdouyin\.com/share/video/(\d+)"),
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
        """提取B站视频ID，返回 {'type': 'bv'|'av', 'id': str}"""
        for pattern in cls.BILIBILI_PATTERNS:
            match = pattern.search(text)
            if match:
                vid = match.group(1)
                if vid.startswith("BV"):
                    return {"type": "bv", "id": vid}
                else:
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
    def detect_platform(cls, text: str) -> Optional[str]:
        """检测链接所属平台"""
        if cls.extract_xiaohongshu(text):
            return "xiaohongshu"
        if cls.extract_bilibili(text):
            return "bilibili"
        if cls.extract_douyin(text):
            return "douyin"
        return None


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
                            f"请求失败 (HTTP {resp.status})", status_code=resp.status
                        )
                    return await resp.json()
            except aiohttp.ClientError as e:
                logger.error(f"[{self.__class__.__name__}] Network error: {e}")
                raise MediaParserError(f"网络请求失败: {str(e)}") from e
            except asyncio.TimeoutError:
                logger.error(f"[{self.__class__.__name__}] Request timeout")
                raise MediaParserError("请求超时，请稍后再试")

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
                            f"请求失败 (HTTP {resp.status})", status_code=resp.status
                        )
                    return await resp.text()
            except aiohttp.ClientError as e:
                logger.error(f"[{self.__class__.__name__}] Network error: {e}")
                raise MediaParserError(f"网络请求失败: {str(e)}") from e
            except asyncio.TimeoutError:
                logger.error(f"[{self.__class__.__name__}] Request timeout")
                raise MediaParserError("请求超时，请稍后再试")


class XiaoHongShuParser(BaseMediaParser):
    """小红书内容解析器"""

    def __init__(self, timeout: int = 20):
        super().__init__(timeout)
        self._headers["Referer"] = "https://www.xiaohongshu.com/"

    async def parse(self, url_or_text: str) -> Dict[str, Any]:
        """解析小红书链接"""
        note_id = URLExtractor.extract_xiaohongshu(url_or_text)
        if not note_id:
            raise MediaParserError("未能从小红书链接中提取到笔记ID，请检查链接格式")

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
        raise MediaParserError("短链接解析失败，请使用完整链接")

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
    """B站视频解析器"""

    def __init__(self, timeout: int = 20):
        super().__init__(timeout)
        self._headers["Referer"] = "https://www.bilibili.com/"

    async def parse(self, url_or_text: str) -> Dict[str, Any]:
        """解析B站链接"""
        video_info = URLExtractor.extract_bilibili(url_or_text)
        if not video_info:
            # 尝试从短链接解析
            if "b23.tv" in url_or_text:
                bvid = await self._resolve_short_link(url_or_text)
                video_info = {"type": "bv", "id": bvid}
            else:
                raise MediaParserError("未能从B站链接中提取到视频ID，请检查链接格式")

        vid = video_info["id"]
        vid_type = video_info["type"]

        # 如果是av号，先转为bv号
        if vid_type == "av":
            vid = self._av2bv(int(vid))

        return await self._fetch_video_detail(vid)

    async def _resolve_short_link(self, short_url: str) -> str:
        """解析B站短链接"""
        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=self._headers
        ) as session:
            try:
                async with session.get(
                    short_url, allow_redirects=True, ssl=False
                ) as resp:
                    final_url = str(resp.url)
                    match = re.search(r"/(BV[0-9A-Za-z]+)", final_url)
                    if match:
                        return match.group(1)
            except Exception as e:
                logger.error(f"[Bilibili] 短链接解析失败: {e}")
        raise MediaParserError("B站短链接解析失败，请使用完整链接")

    @staticmethod
    def _av2bv(av_number: int) -> str:
        """av号转bv号"""
        table = "fZodR9XQDSUm21yCkr6zBqiveYah8bt4xsWpHnJE7jL5VG3guMTKNPAwcF"
        tr = {table[i]: i for i in range(58)}
        s = [11, 10, 3, 8, 4, 6]
        xor = 177451812
        add = 8728348608

        av_number = (av_number ^ xor) + add
        r = list("BV1xx4x1x7x")
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
            raise MediaParserError(f"B站API错误: {message}")

        video_data = data.get("data", {})
        if not video_data:
            raise MediaParserError("未能获取到视频数据")

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

    async def _fetch_download_url(self, bvid: str, cid: int) -> Optional[str]:
        """尝试获取视频下载地址（使用官方API）"""
        api_url = "https://api.bilibili.com/x/player/playurl"
        params = {
            "bvid": bvid,
            "cid": cid,
            "qn": "80",
            "fnver": "0",
            "fnval": "16",
            "fourk": "1",
        }

        try:
            data = await self._fetch_json(api_url, params=params)
            if data.get("code") == 0:
                durl = data.get("data", {}).get("durl", [])
                if durl:
                    return durl[0].get("url", "")
        except Exception as e:
            logger.warning(f"[Bilibili] 获取下载地址失败: {e}")

        return None


class DouyinParser(BaseMediaParser):
    """抖音内容解析器"""

    def __init__(self, timeout: int = 20):
        super().__init__(timeout)
        self._headers["Referer"] = "https://www.douyin.com/"

    async def parse(self, url_or_text: str) -> Dict[str, Any]:
        """解析抖音链接"""
        video_id = URLExtractor.extract_douyin(url_or_text)
        if not video_id:
            # 尝试短链接
            if "v.douyin.com" in url_or_text:
                video_id = await self._resolve_short_link(url_or_text)
            else:
                raise MediaParserError("未能从抖音链接中提取到视频ID，请检查链接格式")

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
        raise MediaParserError("抖音短链接解析失败，请使用完整链接")

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


class MediaParserManager:
    """媒体解析管理器"""

    def __init__(self, timeout: int = 20):
        self.xiaohongshu = XiaoHongShuParser(timeout)
        self.bilibili = BilibiliParser(timeout)
        self.douyin = DouyinParser(timeout)

    async def parse(self, url_or_text: str) -> Dict[str, Any]:
        """自动识别平台并解析"""
        platform = URLExtractor.detect_platform(url_or_text)

        if platform == "xiaohongshu":
            return {
                "platform": "xiaohongshu",
                "data": await self.xiaohongshu.parse(url_or_text),
            }
        elif platform == "bilibili":
            return {
                "platform": "bilibili",
                "data": await self.bilibili.parse(url_or_text),
            }
        elif platform == "douyin":
            return {"platform": "douyin", "data": await self.douyin.parse(url_or_text)}
        else:
            raise MediaParserError(
                "未能识别链接所属平台，请检查链接格式是否支持（小红书/B站/抖音）"
            )
