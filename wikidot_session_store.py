"""Wikidot 登录会话（WIKIDOT_SESSION_ID）持久化存储。

Wikidot 登录端点颁发的会话 Cookie 有效期较长（数周量级），落盘后插件重启
无需重新登录，也避免频繁登录触发风控。会话 ID 等同于账号凭据，因此：

- 文件权限收紧为 0600（仅属主可读写）；
- 内容只存会话 ID 与少量元信息（用户名、获取时间），绝不存密码；
- 存储风格与 GroupSwitchStore 等一致：JSON + threading.Lock +
  ``.tmp`` 临时文件 + os.replace 原子写。
"""

import json
import os
import threading
import time
from typing import Optional

from astrbot.api import logger


class WikidotSessionStore:
    """WIKIDOT_SESSION_ID 的持久化存储。

    Args:
        data_dir: 数据目录（通常为 "data"）。
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = data_dir
        self._file_path = os.path.join(
            data_dir, "currentcortex_wikidot_session.json"
        )
        self._lock = threading.Lock()
        self._session_id: Optional[str] = None
        self._username: Optional[str] = None
        self._created_at: Optional[float] = None
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self) -> None:
        os.makedirs(self._data_dir, exist_ok=True)

    def _load(self) -> None:
        """从 JSON 文件恢复会话（坏数据仅告警，视为未登录）。"""
        if not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                session_id = data.get("session_id")
                if isinstance(session_id, str) and session_id:
                    self._session_id = session_id
                username = data.get("username")
                if isinstance(username, str) and username:
                    self._username = username
                created_at = data.get("created_at")
                if isinstance(created_at, (int, float)):
                    self._created_at = float(created_at)
            if self._session_id:
                logger.info(
                    "[Wikidot] 已恢复登录会话"
                    f"（用户 {self._username or '未知'}, "
                    f"保存于 {time.strftime('%Y-%m-%d %H:%M', time.localtime(self._created_at or 0))}）"
                )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[Wikidot] 加载登录会话失败: {e}")

    def _save(self) -> None:
        """将内存镜像刷盘（调用方需持有锁），并保持 0600 权限。"""
        data = {
            "session_id": self._session_id,
            "username": self._username,
            "created_at": self._created_at,
        }
        tmp_path = self._file_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            os.replace(tmp_path, self._file_path)
        except OSError as e:
            logger.warning(f"[Wikidot] 保存登录会话失败: {e}")

    def get(self) -> Optional[str]:
        """返回已保存的 WIKIDOT_SESSION_ID；无会话返回 None。"""
        with self._lock:
            return self._session_id

    def get_username(self) -> Optional[str]:
        """返回会话对应的 Wikidot 用户名（信息性，可能为 None）。"""
        with self._lock:
            return self._username

    def set(self, session_id: str, username: Optional[str] = None) -> None:
        """保存新的登录会话。"""
        if not session_id:
            return
        with self._lock:
            self._session_id = session_id
            self._username = username or self._username
            self._created_at = time.time()
            self._save()

    def clear(self) -> None:
        """丢弃已保存的会话（登出或会话失效时调用）。"""
        with self._lock:
            if self._session_id is None:
                return
            self._session_id = None
            self._username = None
            self._created_at = None
            self._save()
