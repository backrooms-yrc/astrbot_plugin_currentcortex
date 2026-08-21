"""跨群聊记忆 - 同一平台实例下所有群聊共享的滚动记忆。

存储后端为 JSON 文件（data/currentcortex_cross_group.json），用 threading.Lock
保护读写，与插件内 UserStore/DeviceStore 的持久化风格一致，完全自包含、不依赖
AstrBot 核心数据库。每个平台实例（platform_id）一份独立的记录列表，同平台下所有
群聊共享这份记忆，重启后保留。

记录结构（每条记录为一个 dict）：
    {"ts": <unix 时间戳:float>, "tag": <话题标签:str|None>, "content": <文本:str>}

兼容旧版本纯字符串记录：加载时自动迁移为 {"ts": 0.0, "tag": None, "content": <原字符串>}，
迁移后的记录 ts=0.0，因此在启用 max_age_seconds 过滤时会被视为最旧记录，不会异常置顶。
"""

import json
import os
import re
import threading
import time
from collections import deque
from typing import Optional

from astrbot.api import logger


class CrossGroupMemoryStore:
    """按 platform_id 分桶的持久化跨群聊记忆存储。

    Args:
        data_dir: 数据目录（通常为 "data"）。
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = data_dir
        self._file_path = os.path.join(data_dir, "currentcortex_cross_group.json")
        self._lock = threading.Lock()
        # platform_id -> deque[dict]，dict 结构见模块 docstring
        self._buffers: dict[str, deque] = {}
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self) -> None:
        os.makedirs(self._data_dir, exist_ok=True)

    @staticmethod
    def _normalize_record(item) -> Optional[dict]:
        """将加载出的原始记录（新/旧格式）规整为标准 dict 结构。"""
        if isinstance(item, str):
            # 旧版本纯字符串记录，迁移时间戳记为 0（视为最旧）。
            return {"ts": 0.0, "tag": None, "content": item}
        if isinstance(item, dict) and isinstance(item.get("content"), str):
            ts = item.get("ts", 0.0)
            if not isinstance(ts, (int, float)):
                ts = 0.0
            tag = item.get("tag")
            if tag is not None and not isinstance(tag, str):
                tag = None
            return {"ts": float(ts), "tag": tag, "content": item["content"]}
        return None

    def _load(self) -> None:
        """从 JSON 文件加载历史记录到内存（自动迁移旧格式）。"""
        if not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning(
                    "[CrossGroupMemory] 存储文件格式异常（非字典），已重置为空"
                )
                return
            for platform_id, records in data.items():
                if not isinstance(records, list):
                    continue
                normalized = []
                for item in records:
                    rec = self._normalize_record(item)
                    if rec is not None:
                        normalized.append(rec)
                self._buffers[platform_id] = deque(normalized)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[CrossGroupMemory] 加载历史记忆失败: {e}")

    def _save(self) -> None:
        """将内存镜像刷盘（调用方需持有锁）。"""
        data = {pid: list(buf) for pid, buf in self._buffers.items()}
        tmp_path = self._file_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, self._file_path)
        except OSError as e:
            logger.warning(f"[CrossGroupMemory] 保存记忆失败: {e}")

    def record(
        self,
        platform_id: str,
        content: str,
        max_records: int,
        tag: Optional[str] = None,
    ) -> None:
        """追加一条记录并裁剪到 max_records，然后刷盘。

        Args:
            platform_id: 平台适配器实例 id（UMO 第一段）。
            content: 已格式化的聊天记录行。
            max_records: 每个平台保留的最大记录数。
            tag: 可选话题标签，用于 get_recent 按话题过滤；不传则为 None（不分类）。
        """
        with self._lock:
            buf = self._buffers.get(platform_id)
            if buf is None:
                buf = deque()
                self._buffers[platform_id] = buf
            buf.append({"ts": time.time(), "tag": tag, "content": content})
            while len(buf) > max_records:
                buf.popleft()
            self._save()

    def get_recent(
        self,
        platform_id: str,
        limit: int,
        max_age_seconds: Optional[float] = None,
        tag: Optional[str] = None,
    ) -> list:
        """返回某平台最近 limit 条记录（时间正序）。

        Args:
            platform_id: 平台适配器实例 id。
            limit: 最大返回条数。
            max_age_seconds: 可选，仅返回该时长内的记录（相对当前时间）；
                None 表示不做时效过滤（沿用旧行为）。
            tag: 可选，仅返回该话题标签的记录；None 表示不按话题过滤，
                返回所有标签（含未打标签）的记录。

        Returns:
            按时间正序排列的记录字符串列表（仅 content 部分，兼容旧调用方）。
        """
        if limit <= 0:
            return []
        with self._lock:
            buf = self._buffers.get(platform_id)
            if not buf:
                return []
            records = list(buf)

        if max_age_seconds is not None:
            cutoff = time.time() - max_age_seconds
            records = [r for r in records if r["ts"] >= cutoff]
        if tag is not None:
            records = [r for r in records if r.get("tag") == tag]

        return [r["content"] for r in records[-limit:]]

    def clear(self, platform_id: str) -> int:
        """清空某平台的所有记录。

        Args:
            platform_id: 平台适配器实例 id。

        Returns:
            被清除的记录数。
        """
        with self._lock:
            buf = self._buffers.get(platform_id)
            cnt = len(buf) if buf else 0
            if buf is not None:
                buf.clear()
            self._save()
            return cnt

    def forget_keyword(self, platform_id: str, keyword: str) -> int:
        """删除某平台记忆中所有内容包含指定关键词（子串匹配）的记录。

        Args:
            platform_id: 平台适配器实例 id。
            keyword: 匹配关键词（子串匹配，大小写不敏感）；空字符串直接返回 0，
                不做任何删除（避免误传空串清空全部）。

        Returns:
            被删除的记录数。
        """
        keyword = (keyword or "").strip()
        if not keyword:
            return 0
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        with self._lock:
            buf = self._buffers.get(platform_id)
            if not buf:
                return 0
            kept = deque(r for r in buf if not pattern.search(r["content"]))
            removed = len(buf) - len(kept)
            if removed > 0:
                self._buffers[platform_id] = kept
                self._save()
            return removed
