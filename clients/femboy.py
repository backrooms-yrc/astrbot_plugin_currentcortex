"""男娘图片 API 客户端。"""
import asyncio
from typing import Any, Dict

import aiohttp

from astrbot.api import logger

FEMBOY_API_URL = "https://api.bileizhen.top/api/femboy"


class FemboyAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class FemboyAPIClient:
    def __init__(self, api_key: str = "", timeout: int = 15):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": "AstrBot-Femboy-Plugin/1.0",
            "Accept": "application/json, image/*",
            "x-api-key": api_key,
        }

    async def fetch_femboy_image(self) -> Dict[str, Any]:
        logger.debug("Fetching random femboy image")

        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=self._headers
        ) as session:
            try:
                async with session.get(FEMBOY_API_URL) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            f"Femboy API returned status {resp.status}: {error_text[:500]}"
                        )
                        raise FemboyAPIError(
                            f"API 请求失败 (HTTP {resp.status})",
                            status_code=resp.status,
                        )

                    content_type = resp.headers.get("Content-Type", "")

                    if "image" in content_type:
                        image_url = str(resp.url)
                        logger.info(f"Received direct image response: {image_url}")
                        return {"type": "redirect", "url": image_url}

                    data = await resp.json()
                    logger.debug(f"Femboy API JSON response: {data}")

                    if not isinstance(data, dict):
                        logger.warning(
                            f"Unexpected femboy API response format: {type(data)}"
                        )
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
                        },
                    }

            except aiohttp.ClientError as e:
                logger.error(f"Femboy network error: {e}")
                raise FemboyAPIError(f"网络请求失败: {str(e)}", status_code=0) from e
            except asyncio.TimeoutError:
                logger.error("Femboy request timeout")
                raise FemboyAPIError("API 请求超时，请稍后再试", status_code=0)
