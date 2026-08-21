"""每日一言（Hitokoto）API 客户端。"""
import asyncio
from typing import Any, Dict, Optional

import aiohttp

from astrbot.api import logger

HITOKOTO_API_URL = "https://api.bileizhen.top/api/one"

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


class HitokotoAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class HitokotoAPIClient:
    def __init__(self, api_key: str = "", timeout: int = 10):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": "AstrBot-Hitokoto-Plugin/1.0",
            "Accept": "application/json",
            "x-api-key": api_key,
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

        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=self._headers
        ) as session:
            try:
                async with session.get(HITOKOTO_API_URL, params=params) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            f"Hitokoto API returned status {resp.status}: {error_text[:500]}"
                        )
                        raise HitokotoAPIError(
                            f"API 请求失败 (HTTP {resp.status})",
                            status_code=resp.status,
                        )

                    data = await resp.json()
                    logger.debug(f"Hitokoto API response: {data}")

                    if not isinstance(data, dict) or "hitokoto" not in data:
                        logger.warning(f"Unexpected hitokoto response format: {data}")
                        raise HitokotoAPIError("API 返回数据格式异常")

                    return {
                        "text": data.get("hitokoto", ""),
                        "from": data.get("from", ""),
                        "type": data.get("type", ""),
                        "category_name": HITOKOTO_CATEGORIES.get(
                            data.get("type", ""), "未知"
                        ),
                    }

            except aiohttp.ClientError as e:
                logger.error(f"Hitokoto network error: {e}")
                raise HitokotoAPIError(f"网络请求失败: {str(e)}", status_code=0) from e
            except asyncio.TimeoutError:
                logger.error("Hitokoto request timeout")
                raise HitokotoAPIError("API 请求超时，请稍后再试", status_code=0)
