"""CurrentCortex Cloudflare Turnstile 验证模块 - 配置管理与令牌验证"""

import asyncio
import json
import os
import threading
import time
from typing import Optional
from dataclasses import dataclass, asdict

import aiohttp

from astrbot.api import logger


@dataclass
class TurnstileConfig:
    """Cloudflare Turnstile 配置"""

    site_key: str
    secret_key: str
    enabled: bool = True


class TurnstileStore:
    """线程安全的 Cloudflare Turnstile 配置持久化存储与令牌验证

    存储路径:
      data/dglab_turnstile_config.json - Turnstile 配置（单个对象）
    """

    def __init__(self, data_dir: str = "data"):
        self._data_dir = data_dir
        self._config_path = os.path.join(data_dir, "dglab_turnstile_config.json")
        self._lock = threading.Lock()
        self._config: Optional[TurnstileConfig] = None
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self):
        os.makedirs(self._data_dir, exist_ok=True)

    def _load(self):
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    try:
                        self._config = TurnstileConfig(**data)
                        logger.info("[DGLab Turnstile] 已加载 Turnstile 配置")
                    except Exception as e:
                        logger.error(f"[DGLab Turnstile] Turnstile 配置解析失败: {e}")
            except Exception as e:
                logger.error(f"[DGLab Turnstile] 加载 Turnstile 配置失败: {e}")

    def _save(self):
        try:
            with self._lock:
                data = asdict(self._config) if self._config else {}
            temp = self._config_path + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, self._config_path)
        except Exception as e:
            logger.error(f"[DGLab Turnstile] 保存 Turnstile 配置失败: {e}")

    # ── 配置管理 ──────────────────────────────────────────

    def get_config(self) -> Optional[TurnstileConfig]:
        """加载并返回 Turnstile 配置，未配置则返回 None"""
        with self._lock:
            return self._config

    def save_config(
        self, site_key: str, secret_key: str, enabled: bool = True
    ) -> TurnstileConfig:
        """保存 Turnstile 配置并持久化"""
        config = TurnstileConfig(
            site_key=site_key,
            secret_key=secret_key,
            enabled=enabled,
        )
        with self._lock:
            self._config = config
        self._save()
        logger.info("[DGLab Turnstile] Turnstile 配置已保存")
        return config

    def is_enabled(self) -> bool:
        """Return True if Turnstile is configured and enabled."""
        with self._lock:
            return self._config is not None and self._config.enabled

    # ── 令牌验证 ──────────────────────────────────────────

    async def verify(self, token: str, remote_ip: str = "") -> tuple:
        """验证 Turnstile 令牌，返回 (success, message)

        调用 Cloudflare Turnstile API:
          POST https://challenges.cloudflare.com/turnstile/v0/siteverify
        """
        with self._lock:
            config = self._config

        if config is None:
            logger.warning("[DGLab Turnstile] 尝试验证令牌但 Turnstile 未配置")
            return False, "Turnstile 未配置"

        payload = {
            "secret": config.secret_key,
            "response": token,
        }
        if remote_ip:
            payload["remoteip"] = remote_ip

        logger.info(f"[DGLab Turnstile] 正在验证令牌 (remote_ip={remote_ip or 'N/A'})")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                    data=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    result = await resp.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"[DGLab Turnstile] API 响应错误: {e.status} - {e.message}")
            return False, f"API 响应错误: {e.status}"
        except aiohttp.ClientConnectorError as e:
            logger.error(f"[DGLab Turnstile] 连接失败: {e}")
            return False, "无法连接到 Cloudflare 验证服务器"
        except aiohttp.ClientPayloadError as e:
            logger.error(f"[DGLab Turnstile] 响应解析失败: {e}")
            return False, "验证服务器返回数据异常"
        except aiohttp.ClientError as e:
            logger.error(f"[DGLab Turnstile] 请求异常: {type(e).__name__}: {e}")
            return False, f"请求异常: {type(e).__name__}"
        except asyncio.TimeoutError:
            logger.error("[DGLab Turnstile] 请求超时")
            return False, "验证请求超时"
        except Exception as e:
            logger.error(f"[DGLab Turnstile] 验证异常: {type(e).__name__}: {e}")
            return False, f"验证异常: {type(e).__name__}"

        if result.get("success") is True:
            logger.info("[DGLab Turnstile] 验证通过")
            return True, "验证通过"

        error_codes = result.get("error-codes", [])
        if error_codes:
            error_message = ", ".join(error_codes)
        else:
            error_message = "验证失败"

        logger.warning(f"[DGLab Turnstile] 验证失败: {error_message}")
        return False, error_message
