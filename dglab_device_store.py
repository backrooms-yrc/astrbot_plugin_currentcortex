"""DG-LAB 设备管理模块 - 用户-设备绑定关系持久化存储"""

import json
import os
import threading
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from astrbot.api import logger


@dataclass
class DeviceBinding:
    """设备绑定信息"""
    user_id: str           # 用户唯一标识（如QQ号、Telegram ID等）
    client_id: str         # DG-LAB客户端ID
    target_id: str         # APP端ID
    server_url: str        # 中转服务器地址
    bound_time: str        # 绑定时间 (ISO格式)
    last_active: str       # 最后活跃时间 (ISO格式)
    nickname: str = ""     # 用户昵称（可选）
    shared: bool = False   # 是否允许他人操控（False=仅本人可控）


class DeviceStore:
    """线程安全的设备绑定关系持久化存储

    存储路径: data/dglab_bindings.json
    符合Astrbot插件开发规范：持久化数据存储于data目录
    """

    def __init__(self, data_dir: str = "data"):
        self._data_dir = data_dir
        self._file_path = os.path.join(data_dir, "dglab_bindings.json")
        self._lock = threading.Lock()
        self._bindings: Dict[str, DeviceBinding] = {}
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self):
        """确保data目录存在"""
        os.makedirs(self._data_dir, exist_ok=True)

    def _load(self):
        """从文件加载绑定数据"""
        if not os.path.exists(self._file_path):
            logger.info(f"[DGLab] 绑定数据文件不存在，将创建新文件: {self._file_path}")
            return

        try:
            with open(self._file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 类型安全验证：确保加载的数据是字典
            if not isinstance(data, dict):
                logger.warning(
                    f"[DGLab] ⚠️ 绑定数据文件格式异常: 期望 dict，实际为 {type(data).__name__}，"
                    f"将重置为空数据"
                )
                self._bindings = {}
                return

            with self._lock:
                self._bindings = {}
                for user_id, binding_data in data.items():
                    if not isinstance(binding_data, dict):
                        logger.warning(
                            f"[DGLab] ⚠️ 用户 {user_id} 的绑定数据格式异常: "
                            f"期望 dict，实际为 {type(binding_data).__name__}，已跳过"
                        )
                        continue

                    try:
                        self._bindings[user_id] = DeviceBinding(**binding_data)
                    except Exception as e:
                        logger.error(
                            f"[DGLab] ❌ 用户 {user_id} 的绑定数据解析失败: {e}，已跳过"
                        )

            logger.info(f"[DGLab] 已加载 {len(self._bindings)} 条设备绑定记录")

        except json.JSONDecodeError as e:
            logger.error(f"[DGLab] ❌ 绑定数据文件 JSON 解析失败（可能文件损坏）: {e}")
            self._bindings = {}
        except Exception as e:
            logger.error(f"[DGLab] 加载绑定数据失败: {e}")
            self._bindings = {}

    def _save(self):
        """保存绑定数据到文件（整个操作在锁内完成，防止并发写入损坏）"""
        try:
            with self._lock:
                data = {
                    user_id: asdict(binding)
                    for user_id, binding in self._bindings.items()
                }

                temp_file = self._file_path + '.tmp'
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                os.replace(temp_file, self._file_path)
                logger.debug(f"[DGLab] 已保存 {len(data)} 条绑定记录")

        except Exception as e:
            logger.error(f"[DGLab] 保存绑定数据失败: {e}")

    def get_binding(self, user_id: str) -> Optional[DeviceBinding]:
        """获取用户的设备绑定信息"""
        with self._lock:
            return self._bindings.get(user_id)

    def set_binding(self, binding: DeviceBinding):
        """设置/更新用户绑定"""
        with self._lock:
            self._bindings[binding.user_id] = binding
        self._save()
        logger.info(f"[DGLab] 用户 {binding.user_id} 已绑定设备 (client_id={binding.client_id})")

    def remove_binding(self, user_id: str) -> bool:
        """移除用户绑定"""
        removed = False
        with self._lock:
            if user_id in self._bindings:
                del self._bindings[user_id]
                removed = True
        if removed:
            self._save()
            logger.info(f"[DGLab] 用户 {user_id} 已解绑设备")
        return removed

    def update_last_active(self, user_id: str):
        """更新最后活跃时间"""
        updated = False
        with self._lock:
            if user_id in self._bindings:
                self._bindings[user_id].last_active = datetime.now().isoformat()
                updated = True
        if updated:
            self._save()

    def update_target_id(self, user_id: str, target_id: str):
        """更新绑定的目标ID（APP扫码后由回调写入）"""
        updated = False
        with self._lock:
            if user_id in self._bindings:
                self._bindings[user_id].target_id = target_id
                self._bindings[user_id].last_active = datetime.now().isoformat()
                updated = True
        if updated:
            self._save()

    def list_all_bindings(self) -> Dict[str, DeviceBinding]:
        """获取所有绑定（管理员用）"""
        with self._lock:
            return dict(self._bindings)

    def count(self) -> int:
        """获取绑定总数"""
        with self._lock:
            return len(self._bindings)

    def exists(self, user_id: str) -> bool:
        """检查用户是否已绑定"""
        with self._lock:
            return user_id in self._bindings

    def set_shared(self, user_id: str, shared: bool) -> bool:
        """设置用户设备的共享状态，返回是否成功"""
        with self._lock:
            if user_id not in self._bindings:
                return False
            self._bindings[user_id].shared = shared
        self._save()
        return True

