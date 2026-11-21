"""Pixiv website search with anonymous all-age access by default.

Random requests sample the daily ranking, while searches sample up to three
result pages per query. R18/mixed works require a logged-in Cookie whose
account has enabled R18 viewing; anonymous access remains all-age only.
"""

import asyncio
import itertools
import os
import random
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar
from urllib.parse import quote, urlsplit

import aiohttp


class PixivAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class PixivUsageError(PixivAPIError):
    """Invalid local input or configuration; safe to show to users."""


class PixivWebAPIClient:
    BASE = "https://www.pixiv.net"
    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.pixiv.net/",
    }
    MAX_IMAGE_BYTES = 32 * 1024 * 1024
    MAX_DETAILS = 60

    def __init__(
        self, timeout: int = 15, *, cookie: str = "", max_pages: int = 20
    ):
        self.timeout = max(1, timeout)
        self._cookie = cookie.strip()
        self.max_pages_per_work = max(1, int(max_pages))

    async def _get(self, session, path, params=None):
        async with session.get(
            self.BASE + path,
            params=params,
            headers={"Cookie": self._cookie} if self._cookie else None,
            allow_redirects=not self._cookie,
        ) as response:
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
            raise PixivUsageError(
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
        restrict = item.get("xRestrict")
        if restrict is None or item.get("isMasked") or item.get("is_masked"):
            return False
        level = int(params.get("r18", 0) or 0)
        if level == 0 and restrict != 0:
            return False
        if level == 1 and restrict not in (1, 2):
            return False
        if level == 2 and restrict not in (0, 1, 2):
            return False
        if level not in (0, 1, 2):
            return False
        if params.get("excludeAI") and item.get("aiType") != 1:
            return False
        uid = params.get("uid")
        if uid:
            uids = uid if isinstance(uid, list) else str(uid).split(",")
            if str(item.get("userId")) not in {str(u) for u in uids}:
                return False
        exact_tags = params.get("exact_tags", False)
        tags = item.get("tags") or []
        if isinstance(tags, dict):
            tags = tags.get("tags") or []
        names = []
        for tag in tags:
            if isinstance(tag, dict):
                names.append(str(tag.get("tag", "")))
                if not exact_tags:
                    names.extend(str(v) for v in (tag.get("translation") or {}).values())
            else:
                names.append(str(tag))
        if any(
            not any(
                term.casefold() == name.casefold()
                if exact_tags
                else term.casefold() in name.casefold()
                for term in group
                for name in names
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

    async def _account_status(self, session) -> dict[str, Any]:
        """Best-effort login/R18 check for the configured Cookie.

        Returns ``logged_in`` as True/False/None (None = could not verify) and
        ``r18`` as the account's R18 viewing setting when Pixiv exposes it.
        """
        try:
            data = await self._get(session, "/ajax/user/self")
        except (PixivAPIError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            return {"logged_in": None, "r18": None, "error": type(exc).__name__}
        user = data.get("userData")
        if not isinstance(user, dict):
            body = data.get("body")
            if isinstance(body, dict):
                user = body.get("userData")
        if not isinstance(user, dict):
            return {"logged_in": False, "r18": None}
        logged_in = bool(
            user.get("id") or user.get("userId") or user.get("user_id")
        )
        r18 = None
        for key in (
            "xRestrict", "x_restrict", "user_x_restrict", "r18", "r18Enabled",
        ):
            if key in user:
                try:
                    r18 = int(user[key])
                except (TypeError, ValueError):
                    pass
                break
        return {"logged_in": logged_in, "r18": r18}

    @staticmethod
    def _pick_page_url(urls: dict, size: str) -> str:
        """Pick a page URL; the pages endpoint uses thumb_mini instead of thumb/mini."""
        if size in urls:
            return urls[size]
        if size in ("thumb", "mini"):
            return (
                urls.get("thumb_mini")
                or urls.get("small")
                or urls.get("regular")
                or ""
            )
        return (
            urls.get("regular")
            or urls.get("original")
            or urls.get("small")
            or urls.get("thumb_mini")
            or ""
        )

    async def _page_urls(self, session, pid, size: str) -> list[str]:
        """Fetch every page of a multi-page artwork, capped to avoid spam."""
        data = await self._get(session, f"/ajax/illust/{pid}/pages")
        body = data.get("body")
        if not isinstance(body, list):
            return []
        urls = []
        for page in body[: self.max_pages_per_work]:
            if not isinstance(page, dict):
                continue
            page_urls = page.get("urls")
            if not isinstance(page_urls, dict):
                continue
            url = self._pick_page_url(page_urls, size)
            if url:
                urls.append(url)
        return urls

    async def _candidates(self, session, params):
        uid = params.get("uid")
        if uid:
            uids = uid if isinstance(uid, list) else str(uid).split(",")
            if len(uids) > 20 or any(not str(u).isdigit() for u in uids):
                raise PixivUsageError("作者 UID 必须为数字，最多 20 个")
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

        search_mode = "s_tag_full" if params.get("exact_tags") else "s_tag"
        if params.get("keyword"):
            search_mode = "s_tc"
        # Pixiv web search modes: safe = all-age, r18 = adult only,
        # all = safe + adult (requires a logged-in R18-enabled Cookie).
        content_mode = {0: "safe", 1: "r18", 2: "all"}.get(
            int(params.get("r18", 0) or 0), "safe"
        )
        candidates = []
        for query in queries:
            search_params = {
                "word": query,
                "mode": content_mode,
                "type": "all",
                "order": "date_d",
                "s_mode": search_mode,
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
            level = int(params.get("r18", 0) or 0)
            saw_details = False
            saw_adult = False
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
                    if item:
                        saw_details = True
                    if item.get("xRestrict") in (1, 2):
                        saw_adult = True
                    if not self._matches(item, params) or item.get("illustType") == 2:
                        continue
                    pid = item.get("id") or item.get("illustId")
                    page_count = int(item.get("pageCount") or 1)
                    urls = item.get("urls") or {}
                    url = urls.get(
                        {"thumb": "thumb_mini", "mini": "mini"}.get(size, size)
                    )
                    if not url:
                        url = urls.get("regular") or urls.get("original")
                    if not url:
                        continue
                    page_urls = []
                    if page_count > 1 and pid:
                        try:
                            page_urls = await self._page_urls(session, pid, size)
                        except (
                            PixivAPIError,
                            aiohttp.ClientError,
                            asyncio.TimeoutError,
                        ):
                            # 组图页获取失败时退回详情首图，不影响其他作品。
                            page_urls = []
                    tags = item.get("tags", {})
                    if isinstance(tags, dict):
                        tags = [t.get("tag", "") for t in tags.get("tags", [])]
                    items.append(
                        {
                            "pid": pid,
                            "title": item.get("title"),
                            "author": item.get("userName"),
                            "tags": tags,
                            "width": item.get("width"),
                            "height": item.get("height"),
                            "urls": {size: url},
                            "page_count": page_count,
                            "page_urls": page_urls,
                            "source": "pixiv_web",
                        }
                    )
                    if len(items) == limit:
                        return {"type": "json", "data": {"data": items}}

            if level == 1 and saw_details and not saw_adult:
                # Pixiv silently returns all-age works for mode=r18 when the
                # Cookie is not logged in or the account has R18 viewing off.
                status = await self._account_status(session)
                logged_in = status.get("logged_in")
                if logged_in is False:
                    raise PixivUsageError(
                        "Pixiv 未返回成人作品：yuri_pixiv_cookie 未登录或已失效。"
                        "请在浏览器登录 Pixiv 后复制完整 Cookie（至少包含 "
                        "PHPSESSID，可直接粘贴整段 Cookie 头）并重新填写；"
                        "若使用环境变量也请一并更新"
                    )
                if logged_in is True:
                    if status.get("r18") == 0:
                        raise PixivUsageError(
                            "Pixiv 未返回成人作品：Cookie 已登录，但账号的 R18 "
                            "显示设置为 0（未开启）。请在 Pixiv 设置 → 浏览限制 "
                            "中开启 R-18/R-18G 后重试"
                        )
                    raise PixivUsageError(
                        "Pixiv 未返回成人作品：Cookie 已登录，但未返回成人作品。"
                        "请确认账号已在 Pixiv 设置中开启 R18 显示；若已开启，"
                        "请调整标签/关键词或稍后重试"
                    )
                raise PixivUsageError(
                    "Pixiv 未返回成人作品，且暂时无法验证 Cookie 登录状态。"
                    "请检查网络后重试，并确认 yuri_pixiv_cookie 是完整且未过期的 Cookie"
                )
            return {"type": "json", "data": {"data": items}}

    async def fetch_images(self, **params):
        try:
            level = int(params.get("r18", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise PixivUsageError(
                "分级仅支持 0（全年龄）/ 1（成人）/ 2（混合）"
            ) from exc
        if level not in (0, 1, 2):
            raise PixivUsageError(
                "分级仅支持 0（全年龄）/ 1（成人）/ 2（混合）"
            )
        if level != 0 and not self._cookie:
            raise PixivUsageError(
                "Pixiv 网页源默认仅支持全年龄作品。/yuri 请求成人/混合需在插件"
                "配置的 yuri_pixiv_cookie 中填写已登录且已开启 R18 显示的 "
                "Pixiv Cookie（或设置环境变量 CURRENTCORTEX_YURI_PIXIV_COOKIE）；"
                "/pixiv 请将 pixiv_source 切换为 leiz 并填写 LeiZ Key"
            )
        ratio = params.get("aspectRatio")
        if ratio and not re.fullmatch(
            r"(?:(?:gte|lte|gt|lt|eq)\d+(?:\.\d+)?){1,2}", str(ratio)
        ):
            raise PixivUsageError("长宽比格式错误，例如 gt1 或 gt1.7lt1.8")
        uid = params.get("uid")
        if uid:
            uids = uid if isinstance(uid, list) else str(uid).split(",")
            if len(uids) > 20 or any(not str(u).isdigit() for u in uids):
                raise PixivUsageError("作者 UID 必须为数字，最多 20 个")
        for key in ("dateAfter", "dateBefore"):
            if params.get(key) is not None:
                try:
                    float(params[key])
                except (TypeError, ValueError) as exc:
                    raise PixivUsageError("时间筛选必须为毫秒时间戳") from exc
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
