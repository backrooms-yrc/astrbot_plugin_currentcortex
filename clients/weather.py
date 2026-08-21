"""天气查询 API 客户端。"""
import asyncio
from typing import Any, Dict

import aiohttp

from astrbot.api import logger

WEATHER_API_URL = "https://api.bileizhen.top/api/weather"


class WeatherAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class WeatherAPIClient:
    def __init__(self, api_key: str = "", timeout: int = 15):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": "AstrBot-Weather-Plugin/1.0",
            "Accept": "application/json",
            "x-api-key": api_key,
        }

    async def fetch_weather(self, city: str) -> Dict[str, Any]:
        if not city or not city.strip():
            raise WeatherAPIError("城市名称不能为空")

        params = {
            "dz": city.strip(),
            "return": "json",
        }

        logger.debug(f"Fetching weather for city: {city}")

        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=self._headers
        ) as session:
            try:
                async with session.get(WEATHER_API_URL, params=params) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            f"Weather API returned status {resp.status}: {error_text[:500]}"
                        )
                        raise WeatherAPIError(
                            f"API 请求失败 (HTTP {resp.status})",
                            status_code=resp.status,
                        )

                    content_type = resp.headers.get("Content-Type", "")
                    if "json" not in content_type:
                        text_data = await resp.text()
                        logger.debug(
                            f"Weather API returned text format: {text_data[:500]}"
                        )
                        return {"type": "text", "data": text_data}

                    data = await resp.json()
                    logger.debug(f"Weather API JSON response: {data}")

                    if not isinstance(data, dict):
                        logger.warning(
                            f"Unexpected weather API response format: {type(data)}"
                        )
                        raise WeatherAPIError("API 返回数据格式异常")

                    if data.get("error"):
                        error_msg = data.get("error", "未知错误")
                        logger.error(f"Weather API returned error: {error_msg}")
                        raise WeatherAPIError(f"API 错误: {error_msg}")

                    weather_data = data.get("data", {})
                    if not weather_data:
                        logger.warning(f"Weather API returned empty data: {data}")
                        raise WeatherAPIError("API 返回数据为空")

                    if not isinstance(weather_data, dict):
                        logger.warning(
                            f"Weather API returned non-dict data: {type(weather_data).__name__}"
                        )
                        raise WeatherAPIError("API 返回数据格式异常")

                    return {
                        "type": "json",
                        "data": weather_data,
                        "city": weather_data.get("city", city),
                        "raw_response": data,
                    }

            except aiohttp.ClientError as e:
                logger.error(f"Weather network error: {e}")
                raise WeatherAPIError(f"网络请求失败: {str(e)}", status_code=0) from e
            except asyncio.TimeoutError:
                logger.error("Weather request timeout")
                raise WeatherAPIError("API 请求超时，请稍后再试", status_code=0)
