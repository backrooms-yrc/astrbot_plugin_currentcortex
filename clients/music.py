"""网易云 / 酷狗点歌 API 客户端。

两个客户端返回字段结构对齐（url/level/size/type/bitrate/name/artists/album/pic），
便于上层统一处理。共用 NeteaseAPIError 作为业务异常。
"""
import asyncio
from typing import Any, Dict, List, Optional

import aiohttp

from astrbot.api import logger

NETEASE_API_URL = "https://api.bileizhen.top/api/netease"
NETEASE_SEARCH_URL = "https://api.bileizhen.top/api/netease/search"
KUGOU_API_URL = "https://api.bileizhen.top/api/kugou"
KUGOU_SEARCH_URL = "https://api.bileizhen.top/api/kugou/search"


class NeteaseAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class NeteaseAPIClient:
    def __init__(self, api_key: str = "", timeout: int = 15):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": "AstrBot-Music-Plugin/1.0",
            "Accept": "application/json",
            "x-api-key": api_key,
        }

    # 点歌接口偶发瞬时超时（见日志），对超时/网络错误重试以提升成功率。
    # 重试策略：共 3 次尝试（初次 + 2 次重试），指数退避（0.5s → 1s），
    # 仅对 asyncio.TimeoutError / aiohttp.ClientError 重试；HTTP 业务错误
    # （401/402/5xx 等）和 API 返回的业务错误不重试——它们重试也不会成功。
    #
    # 单次请求超时独立于全局 request_timeout 配置：实测点歌接口成功的请求
    # P95 < 1.5s，卡住的请求会耗尽任何超时上限。故把单次超时压到 6s，
    # 让重试更快触发——失败场景从 15s×3=45s 降到 6s×3≈19s，成功仍秒回。
    NETEASE_MAX_ATTEMPTS = 3
    NETEASE_RETRY_BACKOFF_BASE = 0.5  # 秒；第 n 次重试前等待 base * 2^(n-1)
    NETEASE_REQUEST_TIMEOUT = 6.0  # 秒；单次请求超时（独立于全局 request_timeout）

    async def _get_with_retry(
        self, url: str, params: Dict[str, Any], tag: str
    ) -> Dict[str, Any]:
        """带重试的 GET 请求。返回解析后的 JSON dict。

        - 仅对超时/网络错误重试（共 NETEASE_MAX_ATTEMPTS 次），指数退避。
        - HTTP 非 200 与业务错误（success=false 等）直接抛出，不消耗重试次数。
        - 单次请求使用 NETEASE_REQUEST_TIMEOUT（6s），而非全局 _timeout。
        """
        per_request_timeout = aiohttp.ClientTimeout(total=self.NETEASE_REQUEST_TIMEOUT)
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.NETEASE_MAX_ATTEMPTS + 1):
            async with aiohttp.ClientSession(
                timeout=per_request_timeout, headers=self._headers
            ) as session:
                try:
                    async with session.get(url, params=params) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            logger.error(
                                f"[Netease] {tag} API returned status {resp.status}: {error_text[:500]}"
                            )
                            raise NeteaseAPIError(
                                f"API 请求失败 (HTTP {resp.status})",
                                status_code=resp.status,
                            )
                        data = await resp.json()
                        return data  # 业务校验交由调用方完成
                except asyncio.TimeoutError:
                    last_exc = NeteaseAPIError(
                        "API 请求超时，请稍后再试", status_code=0
                    )
                    logger.warning(
                        f"[Netease] {tag} timeout (attempt {attempt}/{self.NETEASE_MAX_ATTEMPTS})"
                    )
                except aiohttp.ClientError as e:
                    last_exc = NeteaseAPIError(f"网络请求失败: {str(e)}", status_code=0)
                    logger.warning(
                        f"[Netease] {tag} network error (attempt {attempt}/{self.NETEASE_MAX_ATTEMPTS}): {e}"
                    )

            # 此处仅在网络/超时错误时到达：决定是否重试
            if attempt < self.NETEASE_MAX_ATTEMPTS:
                backoff = self.NETEASE_RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                logger.debug(f"[Netease] {tag} retrying in {backoff}s")
                await asyncio.sleep(backoff)

        # 所有尝试均失败
        assert last_exc is not None
        raise last_exc

    async def get_song(
        self, song_id: str, level: Optional[str] = None
    ) -> Dict[str, Any]:
        """通过歌曲ID获取歌曲信息和播放链接"""
        if not song_id or not song_id.strip():
            raise NeteaseAPIError("歌曲ID不能为空")

        params = {"id": song_id.strip()}
        if level:
            params["level"] = level
        logger.debug(f"[Netease] Fetching song by id: {song_id}, level: {level}")

        data = await self._get_with_retry(NETEASE_API_URL, params, "get_song")
        logger.debug(f"[Netease] Song response: {data}")

        if not isinstance(data, dict):
            raise NeteaseAPIError("API 返回数据格式异常")

        if not data.get("success"):
            msg = data.get("message", "未知错误")
            raise NeteaseAPIError(f"获取歌曲失败: {msg}")

        song_data = data.get("data", {})
        if not song_data:
            raise NeteaseAPIError("API 返回歌曲数据为空")

        if not isinstance(song_data, dict):
            raise NeteaseAPIError("API 返回歌曲数据格式异常")

        return song_data

    async def search_songs(self, query: str) -> List[Dict[str, Any]]:
        """通过关键词搜索歌曲"""
        if not query or not query.strip():
            raise NeteaseAPIError("搜索关键词不能为空")

        params = {"q": query.strip()}
        logger.debug(f"[Netease] Searching songs: {query}")

        data = await self._get_with_retry(NETEASE_SEARCH_URL, params, "search_songs")
        logger.debug(
            f"[Netease] Search response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}"
        )

        if not isinstance(data, dict):
            raise NeteaseAPIError("API 返回数据格式异常")

        if not data.get("success"):
            msg = data.get("message", "未知错误")
            raise NeteaseAPIError(f"搜索失败: {msg}")

        songs = data.get("data", [])
        if not isinstance(songs, list):
            raise NeteaseAPIError("API 返回搜索结果格式异常")

        return songs


class KugouAPIClient:
    """酷狗音乐 API 客户端。返回字段结构与 NeteaseAPIClient 对齐
   （url/level/size/type/bitrate/name/artists/album/pic），便于统一处理。"""

    def __init__(self, api_key: str = "", timeout: int = 15):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {
            "User-Agent": "AstrBot-Music-Plugin/1.0",
            "Accept": "application/json",
            "x-api-key": api_key,
        }
        # 复用与网易云相同的重试/超时策略
        self.NETEASE_MAX_ATTEMPTS = 3
        self.NETEASE_RETRY_BACKOFF_BASE = 0.5
        self.NETEASE_REQUEST_TIMEOUT = 6.0

    async def _get_with_retry(
        self, url: str, params: Dict[str, Any], tag: str
    ) -> Dict[str, Any]:
        """带重试的 GET 请求（同 NeteaseAPIClient._get_with_retry）。"""
        per_request_timeout = aiohttp.ClientTimeout(total=self.NETEASE_REQUEST_TIMEOUT)
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.NETEASE_MAX_ATTEMPTS + 1):
            async with aiohttp.ClientSession(
                timeout=per_request_timeout, headers=self._headers
            ) as session:
                try:
                    async with session.get(url, params=params) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            logger.error(
                                f"[Kugou] {tag} API returned status {resp.status}: {error_text[:500]}"
                            )
                            raise NeteaseAPIError(
                                f"API 请求失败 (HTTP {resp.status})",
                                status_code=resp.status,
                            )
                        data = await resp.json()
                        return data
                except asyncio.TimeoutError:
                    last_exc = NeteaseAPIError("API 请求超时，请稍后再试", status_code=0)
                    logger.warning(
                        f"[Kugou] {tag} timeout (attempt {attempt}/{self.NETEASE_MAX_ATTEMPTS})"
                    )
                except aiohttp.ClientError as e:
                    last_exc = NeteaseAPIError(f"网络请求失败: {str(e)}", status_code=0)
                    logger.warning(
                        f"[Kugou] {tag} network error (attempt {attempt}/{self.NETEASE_MAX_ATTEMPTS}): {e}"
                    )

            if attempt < self.NETEASE_MAX_ATTEMPTS:
                backoff = self.NETEASE_RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

        assert last_exc is not None
        raise last_exc

    async def get_song(
        self, song_id: str = "", hash_val: str = ""
    ) -> Dict[str, Any]:
        """通过 hash 或内部 ID 获取歌曲信息和播放链接。

        酷狗优先用 hash（更稳定）；无 hash 时用 id。两者都无则报错。
        """
        params: Dict[str, Any] = {}
        if hash_val:
            params["hash"] = hash_val
        elif song_id:
            params["id"] = song_id
        else:
            raise NeteaseAPIError("歌曲 hash 或 ID 不能为空")

        logger.debug(f"[Kugou] Fetching song: id={song_id}, hash={hash_val}")
        data = await self._get_with_retry(KUGOU_API_URL, params, "get_song")

        if not isinstance(data, dict):
            raise NeteaseAPIError("API 返回数据格式异常")
        if not data.get("success"):
            msg = data.get("message", "未知错误")
            raise NeteaseAPIError(f"获取歌曲失败: {msg}")

        song_data = data.get("data", {})
        if not song_data or not isinstance(song_data, dict):
            raise NeteaseAPIError("API 返回歌曲数据为空")
        return song_data

    async def search_songs(self, query: str) -> List[Dict[str, Any]]:
        """通过关键词搜索歌曲。"""
        if not query or not query.strip():
            raise NeteaseAPIError("搜索关键词不能为空")

        params = {"q": query.strip()}
        logger.debug(f"[Kugou] Searching songs: {query}")
        data = await self._get_with_retry(KUGOU_SEARCH_URL, params, "search_songs")

        if not isinstance(data, dict):
            raise NeteaseAPIError("API 返回数据格式异常")
        if not data.get("success"):
            msg = data.get("message", "未知错误")
            raise NeteaseAPIError(f"搜索失败: {msg}")

        songs = data.get("data", [])
        if not isinstance(songs, list):
            raise NeteaseAPIError("API 返回搜索结果格式异常")
        return songs
