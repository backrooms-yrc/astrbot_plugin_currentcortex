"""Anonymous Pixiv website search; no account credentials or third-party index.

Only publicly visible, all-age works are supported. Random requests sample the
daily ranking, while searches sample up to three result pages per query.
"""

import asyncio
import itertools
import os
import random
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import ClassVar
from urllib.parse import quote, urlsplit

import aiohttp


class PixivAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class PixivWebAPIClient:
    BASE = "https://www.pixiv.net"
    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.pixiv.net/",
    }
    MAX_IMAGE_BYTES = 32 * 1024 * 1024
    MAX_DETAILS = 60

    def __init__(self, timeout: int = 15):
        self.timeout = max(1, timeout)

    async def _get(self, session, path, params=None):
        async with session.get(self.BASE + path, params=params) as response:
            if response.status != 200:
                raise PixivAPIError(
                    f"Pixiv 网页接口 HTTP {response.status}；请稍后重试，或在配置中切换 leiz 源",
                    response.status,
                )
            try:
                data = await response.json()
            except (ValueError, aiohttp.ContentTypeError) as exc:
                raise PixivAPIError(
                    "Pixiv 返回了非 JSON 响应，可能需要验证；可切换 leiz 源"
                ) from exc
            if not isinstance(data, dict):
                raise PixivAPIError("Pixiv 网页接口返回格式异常")
            if data.get("error"):
                raise PixivAPIError(
                    f"Pixiv：{data.get('message') or '作品不可匿名访问'}"
                )
            return data

    @staticmethod
    def _tag_groups(params):
        tags = params.get("tag") or []
        if isinstance(tags, str):
            tags = [tags]
        return [
            [t.strip() for t in str(group).split("|") if t.strip()] for group in tags
        ]

    @classmethod
    def _queries(cls, params):
        groups = [g for g in cls._tag_groups(params) if g]
        variants = (
            list(itertools.islice(itertools.product(*groups), 9)) if groups else [()]
        )
        if len(variants) > 8:
            raise PixivAPIError(
                "匿名源最多支持 8 种标签组合，请减少 OR 标签或切换 leiz 源"
            )
        keyword = str(params.get("keyword") or "").strip()
        return [" ".join(filter(None, (keyword, *variant))) for variant in variants]

    @staticmethod
    def _date(value):
        return datetime.fromtimestamp(
            float(value) / 1000, timezone(timedelta(hours=9))
        ).strftime("%Y-%m-%d")

    @classmethod
    def _matches(cls, item, params):
        # Fail closed for incomplete or masked records; details supply xRestrict.
        if item.get("xRestrict") != 0 or item.get("isMasked") or item.get("is_masked"):
            return False
        if params.get("excludeAI") and item.get("aiType") != 1:
            return False
        uid = params.get("uid")
        if uid:
            uids = uid if isinstance(uid, list) else str(uid).split(",")
            if str(item.get("userId")) not in {str(u) for u in uids}:
                return False
        tags = item.get("tags", [])
        if isinstance(tags, dict):
            tags = tags.get("tags", [])
        names = []
        for tag in tags:
            if isinstance(tag, dict):
                names.append(str(tag.get("tag", "")))
                names.extend(str(v) for v in (tag.get("translation") or {}).values())
            else:
                names.append(str(tag))
        if any(
            not any(
                term.casefold() in name.casefold() for term in group for name in names
            )
            for group in cls._tag_groups(params)
            if group
        ):
            return False
        if params.get("keyword") and params.get("uid"):
            haystack = " ".join(
                names
                + [str(item.get(k) or "") for k in ("title", "description", "userName")]
            ).casefold()
            if not all(
                word.casefold() in haystack for word in str(params["keyword"]).split()
            ):
                return False
        ratio = params.get("aspectRatio")
        if ratio:
            width, height = item.get("width", 0), item.get("height", 0)
            if not width or not height:
                return False
            actual = round(width / height, 3)
            for op, val in re.findall(r"(gte|lte|gt|lt|eq)(\d+(?:\.\d+)?)", ratio):
                target = float(val)
                if not {
                    "gt": actual > target,
                    "gte": actual >= target,
                    "lt": actual < target,
                    "lte": actual <= target,
                    "eq": actual == target,
                }[op]:
                    return False
        if params.get("dateAfter") is not None or params.get("dateBefore") is not None:
            try:
                timestamp = (
                    datetime.fromisoformat(item["createDate"].replace("Z", "+00:00")).timestamp() * 1000
                )
            except (KeyError, ValueError, TypeError):
                return False
            if params.get("dateAfter") is not None and timestamp < float(
                params["dateAfter"]
            ):
                return False
            if params.get("dateBefore") is not None and timestamp > float(
                params["dateBefore"]
            ):
                return False
        return True

    async def _candidates(self, session, params):
        uid = params.get("uid")
        if uid:
            uids = uid if isinstance(uid, list) else str(uid).split(",")
            if len(uids) > 20 or any(not str(u).isdigit() for u in uids):
                raise PixivAPIError("作者 UID 必须为数字，最多 20 个")
            candidates = []
            for user in uids:
                body = (await self._get(session, f"/ajax/user/{user}/profile/all")).get(
                    "body", {}
                )
                ids = list(body.get("illusts") or {}) + list(body.get("manga") or {})
                candidates.extend({"id": pid} for pid in ids)
            return candidates

        queries = self._queries(params)
        if queries == [""]:
            # No search term: retain random-picture behavior using the ranking.
            data = await self._get(
                session,
                "/ranking.php",
                {"format": "json", "mode": "daily", "content": "illust"},
            )
            return [
                {**item, "id": item.get("illust_id")}
                for item in data.get("contents", [])
            ]

        candidates = []
        for query in queries:
            search_params = {
                "word": query,
                "mode": "safe",
                "order": "date_d",
                "s_mode": "s_tc" if params.get("keyword") else "s_tag",
                "p": 1,
            }
            if params.get("excludeAI"):
                search_params["ai_type"] = 1
            for key, target in (("dateAfter", "scd"), ("dateBefore", "ecd")):
                if params.get(key) is not None:
                    search_params[target] = self._date(params[key])
            path = "/ajax/search/artworks/" + quote(query, safe="")
            data = await self._get(session, path, search_params)
            body = data.get("body", {}).get("illustManga")
            if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                raise PixivAPIError("Pixiv 搜索响应格式已变更，请切换 leiz 源")
            candidates.extend(body["data"])
            # Include page one (new works), page two and a random deeper page.
            last_page = min(1000, max(1, int(body.get("lastPage") or 1)))
            pages = sorted({2, random.randint(2, last_page)}) if last_page >= 2 else []
            for page in pages:
                search_params["p"] = page
                extra = await self._get(session, path, search_params)
                candidates.extend(
                    extra.get("body", {}).get("illustManga", {}).get("data", [])
                )
        return candidates

    async def _fetch(self, params):
        async with aiohttp.ClientSession(
            headers=self.HEADERS,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            trust_env=True,
        ) as session:
            candidates = await self._candidates(session, params)
            unique = {
                str(item["id"]): item
                for item in candidates
                if item.get("id") and str(item["id"]).isdigit()
            }
            ids = list(unique)
            random.shuffle(ids)
            items = []
            limit = max(1, min(20, int(params.get("num", 1))))
            size = params.get("size", "regular")
            if isinstance(size, list):
                size = size[0] if size else "regular"

            async def detail(pid):
                try:
                    return (await self._get(session, f"/ajax/illust/{pid}")).get(
                        "body", {}
                    )
                except PixivAPIError as exc:
                    if exc.status_code == 404:
                        return {}
                    raise

            for offset in range(0, min(len(ids), self.MAX_DETAILS), 4):
                details = await asyncio.gather(
                    *(detail(pid) for pid in ids[offset : offset + 4])
                )
                for item in details:
                    if not self._matches(item, params) or item.get("illustType") == 2:
                        continue
                    urls = item.get("urls") or {}
                    url = urls.get(
                        {"thumb": "thumb_mini", "mini": "mini"}.get(size, size)
                    )
                    if not url:
                        url = urls.get("regular") or urls.get("original")
                    if not url:
                        continue
                    tags = item.get("tags", {})
                    if isinstance(tags, dict):
                        tags = [t.get("tag", "") for t in tags.get("tags", [])]
                    items.append(
                        {
                            "pid": item.get("id") or item.get("illustId"),
                            "title": item.get("title"),
                            "author": item.get("userName"),
                            "tags": tags,
                            "width": item.get("width"),
                            "height": item.get("height"),
                            "urls": {size: url},
                            "source": "pixiv_web",
                        }
                    )
                    if len(items) == limit:
                        return {"type": "json", "data": {"data": items}}
            return {"type": "json", "data": {"data": items}}

    async def fetch_images(self, **params):
        if int(params.get("r18", 0)) != 0:
            raise PixivAPIError(
                "Pixiv 匿名源仅支持全年龄作品；R18/混合模式请在插件配置或总 Pages → 设置 → Pixiv 图片中将 pixiv_source 切换为 leiz，并填写 LeiZ Key"
            )
        ratio = params.get("aspectRatio")
        if ratio and not re.fullmatch(
            r"(?:(?:gte|lte|gt|lt|eq)\d+(?:\.\d+)?){1,2}", str(ratio)
        ):
            raise PixivAPIError("长宽比格式错误，例如 gt1 或 gt1.7lt1.8")
        try:
            return await asyncio.wait_for(self._fetch(params), timeout=self.timeout)
        except asyncio.TimeoutError as exc:
            raise PixivAPIError("Pixiv 匿名搜索超时，请稍后重试或切换 leiz 源") from exc
        except aiohttp.ClientError as exc:
            raise PixivAPIError(
                "无法访问 Pixiv，请检查服务器网络或切换 leiz 源"
            ) from exc

    async def download_image(self, url):
        """Download with Pixiv Referer; adapters cannot reliably add headers."""
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "i.pximg.net":
            raise PixivAPIError("Pixiv 返回了非预期的图片地址")
        directory = os.path.join(tempfile.gettempdir(), "astrbot_pixiv")
        os.makedirs(directory, exist_ok=True)
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < time.time() - 3600:
                    os.unlink(path)
            except OSError:
                pass
        path = None
        try:
            async with (
                aiohttp.ClientSession(
                    headers=self.HEADERS,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    trust_env=True,
                ) as session,
                session.get(url, allow_redirects=False) as response,
            ):
                if response.status != 200 or not response.headers.get(
                    "Content-Type", ""
                ).startswith("image/"):
                    raise PixivAPIError(
                        "Pixiv 图片下载失败，请稍后重试", response.status
                    )
                extension = {
                    "image/png": ".png",
                    "image/webp": ".webp",
                    "image/gif": ".gif",
                }.get(response.headers.get("Content-Type", "").split(";")[0], ".jpg")
                with tempfile.NamedTemporaryFile(
                    dir=directory, suffix=extension, delete=False
                ) as output:
                    path = output.name
                    total = 0
                    async for chunk in response.content.iter_chunked(65536):
                        total += len(chunk)
                        if total > self.MAX_IMAGE_BYTES:
                            raise PixivAPIError(
                                "Pixiv 图片超过 32 MB，请改用 regular/small 尺寸"
                            )
                        output.write(chunk)
            return path
        except BaseException as exc:
            if path and os.path.exists(path):
                os.unlink(path)
            if isinstance(exc, (aiohttp.ClientError, asyncio.TimeoutError)):
                raise PixivAPIError("Pixiv 图片下载失败或超时，请稍后重试") from exc
            raise
