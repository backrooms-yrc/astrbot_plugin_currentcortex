"""按会话（群聊）的插件开关状态存储（支持按功能域 scope 分级）。

存储后端为 JSON 文件（data/currentcortex_group_switch.json），用 threading.Lock
保护读写，与插件内 CrossGroupMemoryStore / DeviceStore 等持久化风格一致，完全自
包含、不依赖 AstrBot 核心数据库。

语义为「黑名单」：未被显式记录的会话视为启用（默认启用），只有被显式禁用的会话
（set_disabled）才会被守卫处理器拦截。这样既能精准关闭个别群，又不会影响老群或
新群。

分级开关：存储 key 由两部分组成——
    - 全局禁用：key 就是原始 umo（关闭本群全部插件命令，等价旧版本行为）
    - 域级禁用：key 为 ``umo|scope``（如 ``aiocqhttp:GroupMessage:123|media``），
      只关闭该群某一类功能（媒体解析/点歌/图片等），其余功能不受影响。
umo 内部不含 ``|`` 字符（各平台 umo 均以 ``:`` 分段），scope 名为受控白名单
（media/image/music/utility/dglab/memory），因此 ``|`` 可安全作为分隔符；
旧版本落盘的纯 umo key 加载后自动视为全局禁用，无需迁移。

每个被禁用的条目额外记录一个可选的到期时间戳（until）：
    - until 为 None：永久禁用，需手动 /开关 on [scope] 重新启用。
    - until 为具体时间戳：到期后自动视为启用（懒惰过期，在 is_enabled /
      list_disabled 调用时惰性清理，不需要额外的定时任务或后台线程）。
"""

import json
import os
import threading
import time
from typing import List, Optional


from astrbot.api import logger

# 全局禁用 key 与域级禁用 key 的分隔符（umo 与 scope 名均不含该字符）
SCOPE_SEPARATOR = "|"


class GroupSwitchStore:
    """按 unified_msg_origin 记录「是否被禁用」的持久化存储（支持 scope 分级）。

    Args:
        data_dir: 数据目录（通常为 "data"）。
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = data_dir
        self._file_path = os.path.join(
            data_dir, "currentcortex_group_switch.json"
        )
        self._lock = threading.Lock()
        # 被禁用的条目：key -> until（unix 时间戳；None 表示永久禁用）
        # key 为原始 umo（全局禁用）或 "umo|scope"（仅禁用该功能域）
        self._disabled: dict[str, Optional[float]] = {}
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self) -> None:
        os.makedirs(self._data_dir, exist_ok=True)

    @staticmethod
    def _scoped_key(umo: str, scope: Optional[str]) -> str:
        """把 (umo, scope) 组合成存储 key；scope 为 None 时即原始 umo（全局）。"""
        if scope:
            return f"{umo}{SCOPE_SEPARATOR}{scope}"
        return umo

    @staticmethod
    def _split_key(key: str) -> tuple:
        """把存储 key 拆回 (umo, scope)；无分隔符的旧条目 scope 为 None。"""
        if SCOPE_SEPARATOR in key:
            umo, _, scope = key.partition(SCOPE_SEPARATOR)
            return umo, (scope or None)
        return key, None

    def _load(self) -> None:
        """从 JSON 文件加载被禁用的会话集合（兼容旧版 list 格式）。"""
        if not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                disabled = data.get("disabled", [])
                if isinstance(disabled, list):
                    # 旧版本格式：["umo1", "umo2", ...]，均视为全局永久禁用。
                    for x in disabled:
                        if isinstance(x, str):
                            self._disabled[x] = None
                elif isinstance(disabled, dict):
                    # 新版本格式：{"umo1|scope": until|null, ...}
                    # （无 "|" 的 key 即旧版全局禁用条目，自然兼容）
                    for key, until in disabled.items():
                        if not isinstance(key, str):
                            continue
                        if until is None or isinstance(until, (int, float)):
                            self._disabled[key] = (
                                float(until) if until is not None else None
                            )
            logger.info(
                f"[GroupSwitch] 已加载 {len(self._disabled)} 个被禁用的条目"
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[GroupSwitch] 加载开关状态失败: {e}")

    def _save(self) -> None:
        """将内存镜像刷盘（调用方需持有锁）。"""
        data = {"disabled": dict(sorted(self._disabled.items()))}
        tmp_path = self._file_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._file_path)
        except OSError as e:
            logger.warning(f"[GroupSwitch] 保存开关状态失败: {e}")

    def _purge_expired_locked(self) -> bool:
        """清理已过期的禁用记录（调用方需持有锁）。

        Returns:
            是否有记录被清理（用于判断是否需要刷盘）。
        """
        now = time.time()
        expired = [
            key
            for key, until in self._disabled.items()
            if until is not None and until <= now
        ]
        for key in expired:
            del self._disabled[key]
        return bool(expired)

    def is_enabled(self, umo: str, scope: Optional[str] = None) -> bool:
        """该会话（或其某个功能域）是否启用。

        Args:
            umo: 会话标识。
            scope: 功能域名（如 "media"）；None 表示查询全局开关。

        判定规则：
            - 全局被禁用 → 任何 scope 都视为禁用（全局优先）。
            - scope=None：仅看全局条目（保持旧版本行为）。
            - scope 非空：全局启用且该 scope 未被单独禁用才为启用。
        """
        with self._lock:
            if self._purge_expired_locked():
                self._save()
            if umo in self._disabled:
                return False
            if scope and self._scoped_key(umo, scope) in self._disabled:
                return False
            return True

    def has_disabled_entry(self, umo: str, scope: Optional[str] = None) -> bool:
        """该（全局或域级）禁用条目本身是否存在。

        与 is_enabled 不同：不考虑「全局禁用对 scope 的连带影响」，
        只看这一个条目有没有被显式设置——用于区分「域被单独关闭」和
        「仅因全局关闭而不可用」。
        """
        with self._lock:
            self._purge_expired_locked()
            return self._scoped_key(umo, scope) in self._disabled

    def set_disabled(
        self,
        umo: str,
        scope: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        """显式禁用某会话（全局）或其某个功能域。

        Args:
            umo: 会话标识。
            scope: 功能域名；None 表示全局禁用（关闭全部命令）。
            duration_seconds: 禁用时长（秒）；None 表示永久禁用，需手动重新启用。
        """
        with self._lock:
            until = time.time() + duration_seconds if duration_seconds else None
            self._disabled[self._scoped_key(umo, scope)] = until
            self._save()

    def set_enabled(self, umo: str, scope: Optional[str] = None) -> bool:
        """重新启用某会话（全局）或其某个功能域。

        Args:
            umo: 会话标识。
            scope: 功能域名；None 表示解除全局禁用（不影响各 scope 条目）。

        Returns:
            是否实际发生了状态变更（即之前确实是禁用状态）。
        """
        with self._lock:
            self._purge_expired_locked()
            key = self._scoped_key(umo, scope)
            if key in self._disabled:
                del self._disabled[key]
                self._save()
                return True
            return False

    def get_until(
        self, umo: str, scope: Optional[str] = None
    ) -> Optional[float]:
        """返回指定条目的禁用到期时间戳；未禁用或永久禁用则分别返回 None。

        调用前建议先用 is_enabled 判断，避免把「已过期」误当「永久禁用」。
        """
        with self._lock:
            self._purge_expired_locked()
            return self._disabled.get(self._scoped_key(umo, scope))

    def list_disabled(self) -> List[str]:
        """返回所有（未过期）被禁用的存储 key 列表（排序后）。

        全局条目即原始 umo；域级条目为 ``umo|scope`` 复合 key。
        """
        with self._lock:
            if self._purge_expired_locked():
                self._save()
            return sorted(self._disabled.keys())

    def list_disabled_detail(self) -> List[dict]:
        """返回所有（未过期）被禁用条目的详情列表，用于可视化展示。

        Returns:
            按 key 排序的列表，每项为
            ``{"umo": str, "scope": str|None, "until": float|None,
            "permanent": bool}``。scope=None 表示全局禁用。
        """
        with self._lock:
            if self._purge_expired_locked():
                self._save()
            details = []
            for key, until in sorted(self._disabled.items()):
                umo, scope = self._split_key(key)
                details.append(
                    {
                        "umo": umo,
                        "scope": scope,
                        "until": until,
                        "permanent": until is None,
                    }
                )
            return details
