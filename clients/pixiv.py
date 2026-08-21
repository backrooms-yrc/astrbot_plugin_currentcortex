"""Pixiv 随机图片 API 客户端。"""
import asyncio
from typing import Any, Dict

import aiohttp

from astrbot.api import logger

API_BASE_URL = "https://api.bileizhen.top/api/pixiv"


class PixivAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class PixivAPIClient:
    def __init__(self, api_key: str = "", timeout: int = 15):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": "AstrBot-CurrentCortex-Plugin/1.0",
            "Accept": "application/json, image/*",
            "x-api-key": api_key,
        }

    async def fetch_images(self, **params) -> Dict[str, Any]:
        clean_params = {k: v for k, v in params.items() if v is not None}

        if "excludeAI" in clean_params:
            clean_params["excludeAI"] = bool(clean_params["excludeAI"])

        # 路由判定：只有用户显式提供「过滤参数」时才走 POST（带筛选的 JSON 接口）；
        # r18/num/size 是随机与搜索都通用、且 _build_request_params 总会填充默认值的
        # 参数，不能用于判定路由——否则纯随机请求也会被错误地强制走 POST，导致每次
        # 返回固定的同一张图（随机图固定）。
        has_filter_params = any(
            k in clean_params
            for k in (
                "tag",
                "keyword",
                "uid",
                "excludeAI",
                "aspectRatio",
                "dateAfter",
                "dateBefore",
            )
        )

        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=self._headers
        ) as session:
            try:
                if has_filter_params:
                    logger.info("[Pixiv] 有过滤参数，走 POST 筛选接口")
                    resp = await self._post_request(session, clean_params)
                else:
                    logger.info("[Pixiv] 无过滤参数，走 GET 随机接口")
                    resp = await self._get_request(session, clean_params)

                async with resp:
                    if resp.status in (301, 302, 303, 307, 308):
                        redirect_url = resp.headers.get("Location", "")
                        logger.info(f"Received redirect to: {redirect_url}")
                        return {"type": "redirect", "url": redirect_url}

                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            f"API returned status {resp.status}: {error_text[:500]}"
                        )
                        raise PixivAPIError(
                            f"API 请求失败 (HTTP {resp.status})",
                            status_code=resp.status,
                        )

                    content_type = resp.headers.get("Content-Type", "")
                    if "image" in content_type:
                        image_url = str(resp.url)
                        logger.info(f"Received direct image response: {image_url}")
                        return {"type": "redirect", "url": image_url}

                    data = await resp.json()
                    logger.debug(
                        f"API JSON response keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
                    )
                    return {"type": "json", "data": data}

            except aiohttp.ClientError as e:
                logger.error(f"Network error: {e}")
                raise PixivAPIError(f"网络请求失败: {str(e)}", status_code=0) from e
            except asyncio.TimeoutError:
                logger.error("Request timeout")
                raise PixivAPIError("API 请求超时，请稍后再试", status_code=0)

    async def _get_request(
        self, session: aiohttp.ClientSession, params: Dict[str, Any]
    ):
        logger.debug(f"GET {API_BASE_URL} params={params}")
        return await session.get(API_BASE_URL, params=params, allow_redirects=False)

    async def _post_request(
        self, session: aiohttp.ClientSession, params: Dict[str, Any]
    ):
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
            elif k == "tag":
                # CommandParser 产出的 tag 是 list（多个 tag 参数 = AND 匹配），
                # 单个字符串则包成 list，保证上游接收到的始终是数组形式。
                body[k] = v if isinstance(v, list) else [v]
            else:
                body[k] = v
        return body
