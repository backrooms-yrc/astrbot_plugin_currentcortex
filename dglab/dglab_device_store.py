"""DG-LAB 设备管理模块 - 用户-设备绑定关系持久化存储

支持同一用户绑定并控制多台设备。每台设备由唯一的 device_id 标识，
并分配一个 1-based 的 device_index（展示序号）供聊天命令引用。

存储路径: data/dglab_bindings.json
存储结构: { user_id: { device_id: {DeviceBinding字段} } }
兼容: 自动迁移旧版平铺格式 { user_id: {DeviceBinding字段} }
"""

import json
import os
import uuid
import threading
from typing import Dict, List, Optional, Iterator, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime

from astrbot.api import logger


@dataclass
class DeviceBinding:
    """单台设备的绑定信息"""
    user_id: str           # 用户唯一标识（如QQ号、Telegram ID等）
    device_id: str         # 设备唯一标识（uuid4，绑定时分配）
    device_index: int = 1  # 展示序号（1-based，用于聊天命令 /电击 强度 2 ...）
    client_id: str = ""    # DG-LAB客户端ID（中转服务器分配）
    target_id: str = ""    # APP端ID（扫码后填充）
    server_url: str = ""   # 中转服务器地址
    bound_time: str = ""   # 绑定时间 (ISO格式)
    last_active: str = ""  # 最后活跃时间 (ISO格式)
    nickname: str = ""     # 用户昵称（可选，便于展示）
    shared: bool = False   # 是否允许他人操控（user级：控制该用户所有设备）
    protocol: str = "auto"  # 中转服务器协议: auto(自动识别)/v3/v4


class DeviceStore:
    """线程安全的设备绑定关系持久化存储（多设备）

    存储路径: data/dglab_bindings.json
    内存结构: { user_id: { device_id: DeviceBinding } }
    符合Astrbot插件开发规范：持久化数据存储于data目录
    """

    def __init__(self, data_dir: str = "data"):
        self._data_dir = data_dir
        self._file_path = os.path.join(data_dir, "dglab_bindings.json")
        self._lock = threading.Lock()
        # user_id -> { device_id -> DeviceBinding }
        self._bindings: Dict[str, Dict[str, DeviceBinding]] = {}
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self):
        """确保data目录存在"""
        os.makedirs(self._data_dir, exist_ok=True)

    @staticmethod
    def _is_legacy_flat(binding_data) -> bool:
        """判断一条记录是否是旧版平铺格式（单设备）。

        旧格式: { "client_id": "...", "target_id": "...", ... }（直接是 DeviceBinding 字段）
        新格式: { "device_id_hex": { "device_id":..., "client_id":... } }（device_id -> 字段）
        """
        if not isinstance(binding_data, dict):
            return False
        # 旧平铺格式含有 client_id / target_id / server_url 这类设备字段，
        # 且 value 不是嵌套 dict（新格式 value 是 dict）
        return any(
            k in binding_data
            for k in ("client_id", "target_id", "server_url")
        )

    def _load(self):
        """从文件加载绑定数据，自动迁移旧版平铺格式"""
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

            migrated = False
            with self._lock:
                self._bindings = {}
                for user_id, payload in data.items():
                    if self._is_legacy_flat(payload):
                        # 旧版平铺格式 → 迁移为该用户的 #1 设备
                        migrated = True
                        try:
                            payload.setdefault("user_id", user_id)
                            payload.setdefault("device_id", uuid.uuid4().hex)
                            payload.setdefault("device_index", 1)
                            b = DeviceBinding(**payload)
                            self._bindings[user_id] = {b.device_id: b}
                        except Exception as e:
                            logger.error(
                                f"[DGLab] ❌ 用户 {user_id} 的旧版绑定数据迁移失败: {e}，已跳过"
                            )
                    elif isinstance(payload, dict):
                        # 新版嵌套格式: { device_id: {字段} }
                        user_devices: Dict[str, DeviceBinding] = {}
                        for device_id, binding_data in payload.items():
                            if not isinstance(binding_data, dict):
                                logger.warning(
                                    f"[DGLab] ⚠️ 用户 {user_id} 设备 {device_id} 数据格式异常，已跳过"
                                )
                                continue
                            try:
                                binding_data.setdefault("user_id", user_id)
                                binding_data.setdefault("device_id", device_id)
                                b = DeviceBinding(**binding_data)
                                user_devices[b.device_id] = b
                            except Exception as e:
                                logger.error(
                                    f"[DGLab] ❌ 用户 {user_id} 设备 {device_id} 解析失败: {e}，已跳过"
                                )
                        if user_devices:
                            self._bindings[user_id] = user_devices
                    else:
                        logger.warning(
                            f"[DGLab] ⚠️ 用户 {user_id} 的绑定数据格式异常: "
                            f"实际为 {type(payload).__name__}，已跳过"
                        )

            total = sum(len(d) for d in self._bindings.values())
            logger.info(f"[DGLab] 已加载 {len(self._bindings)} 个用户 / {total} 台设备绑定记录")
            if migrated:
                logger.info("[DGLab] 已将旧版平铺绑定数据自动迁移为多设备格式（每用户 #1 设备）")

        except json.JSONDecodeError as e:
            logger.error(f"[DGLab] ❌ 绑定数据文件 JSON 解析失败（可能文件损坏）: {e}")
            self._bindings = {}
        except Exception as e:
            logger.error(f"[DGLab] 加载绑定数据失败: {e}")
            self._bindings = {}

    def _save(self):
        """保存绑定数据到文件（调用方应确保数据一致性）"""
        try:
            with self._lock:
                data = {
                    user_id: {
                        device_id: asdict(binding)
                        for device_id, binding in devices.items()
                    }
                    for user_id, devices in self._bindings.items()
                }

            temp_file = self._file_path + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            os.replace(temp_file, self._file_path)
            total = sum(len(d) for d in data.values())
            logger.debug(f"[DGLab] 已保存 {len(data)} 个用户 / {total} 台设备绑定记录")

        except Exception as e:
            logger.error(f"[DGLab] 保存绑定数据失败: {e}")

    # ---------- 查询 ----------

    def get_device(self, user_id: str, device_id: str) -> Optional[DeviceBinding]:
        """获取指定设备"""
        with self._lock:
            return self._bindings.get(user_id, {}).get(device_id)

    def get_device_by_index(self, user_id: str, index: int) -> Optional[DeviceBinding]:
        """按展示序号获取设备（1-based）"""
        with self._lock:
            for b in self._bindings.get(user_id, {}).values():
                if b.device_index == index:
                    return b
        return None

    def list_devices(self, user_id: str) -> List[DeviceBinding]:
        """获取用户的所有设备，按 device_index 升序"""
        with self._lock:
            devices = list(self._bindings.get(user_id, {}).values())
        devices.sort(key=lambda b: b.device_index)
        return devices

    def get_binding(self, user_id: str) -> Optional[DeviceBinding]:
        """便捷封装：获取用户的 #1 设备（向后兼容单设备调用方）"""
        devices = self.list_devices(user_id)
        return devices[0] if devices else None

    def iter_all_device_bindings(self) -> Iterator[Tuple[str, str, DeviceBinding]]:
        """遍历所有 (user_id, device_id, binding)，供列表/广场展开使用"""
        with self._lock:
            items = [
                (uid, did, b)
                for uid, devices in self._bindings.items()
                for did, b in devices.items()
            ]
        for uid, did, b in items:
            yield uid, did, b

    def list_all_bindings(self) -> Dict[str, Dict[str, DeviceBinding]]:
        """获取完整绑定映射（管理员/调试用）：{ user_id: { device_id: DeviceBinding } }"""
        with self._lock:
            return {uid: dict(devs) for uid, devs in self._bindings.items()}

    def device_count(self, user_id: str) -> int:
        """用户已绑定设备数"""
        with self._lock:
            return len(self._bindings.get(user_id, {}))

    def count(self) -> int:
        """获取设备总数（非用户数）"""
        with self._lock:
            return sum(len(d) for d in self._bindings.values())

    def exists(self, user_id: str) -> bool:
        """用户是否绑定了至少一台设备"""
        with self._lock:
            return bool(self._bindings.get(user_id))

    def next_device_index(self, user_id: str) -> int:
        """为用户分配下一个展示序号（现有最大 index + 1，空则 1）"""
        with self._lock:
            devices = self._bindings.get(user_id, {})
            if not devices:
                return 1
            return max(b.device_index for b in devices.values()) + 1

    # ---------- 写入 ----------

    def add_binding(self, binding: DeviceBinding):
        """追加一台新设备绑定（不覆盖已有设备）。

        若 binding.device_id 为空则自动分配；device_index 为空则取 next。
        """
        with self._lock:
            if not binding.device_id:
                binding.device_id = uuid.uuid4().hex
            if not binding.device_index:
                existing = self._bindings.get(binding.user_id, {})
                binding.device_index = (
                    (max(b.device_index for b in existing.values()) + 1)
                    if existing else 1
                )
            self._bindings.setdefault(binding.user_id, {})[binding.device_id] = binding
        self._save()
        logger.info(
            f"[DGLab] 用户 {binding.user_id} 已绑定设备 #{binding.device_index} "
            f"(device_id={binding.device_id[:8]}...)"
        )

    def set_binding(self, binding: DeviceBinding):
        """设置/更新单台设备（按 device_id 定位）。

        向后兼容：若 binding 无 device_id，则视为新增。
        """
        if not binding.device_id:
            self.add_binding(binding)
            return
        with self._lock:
            self._bindings.setdefault(binding.user_id, {})[binding.device_id] = binding
        self._save()

    def update_last_active(self, user_id: str, device_id: str):
        """更新设备最后活跃时间"""
        updated = False
        with self._lock:
            b = self._bindings.get(user_id, {}).get(device_id)
            if b:
                b.last_active = datetime.now().isoformat()
                updated = True
        if updated:
            self._save()

    def update_target_id(self, user_id: str, device_id: str, target_id: str):
        """更新设备绑定的目标ID（APP扫码后由回调写入）"""
        updated = False
        with self._lock:
            b = self._bindings.get(user_id, {}).get(device_id)
            if b:
                b.target_id = target_id
                b.last_active = datetime.now().isoformat()
                updated = True
        if updated:
            self._save()

    def remove_device(self, user_id: str, device_id: str) -> bool:
        """移除指定设备，并重排剩余设备序号保持连续（1,2,3...）"""
        removed = False
        with self._lock:
            devices = self._bindings.get(user_id, {})
            if device_id in devices:
                del devices[device_id]
                removed = True
                # 重排序号
                for i, b in enumerate(
                    sorted(devices.values(), key=lambda x: x.device_index), start=1
                ):
                    b.device_index = i
                if not devices:
                    del self._bindings[user_id]
        if removed:
            self._save()
            logger.info(f"[DGLab] 用户 {user_id} 已解绑设备 {device_id[:8]}...")
        return removed

    def remove_binding(self, user_id: str) -> bool:
        """移除用户的所有设备（向后兼容：原解绑全部）"""
        removed = False
        with self._lock:
            if user_id in self._bindings:
                del self._bindings[user_id]
                removed = True
        if removed:
            self._save()
            logger.info(f"[DGLab] 用户 {user_id} 已解绑全部设备")
        return removed

    def set_shared(self, user_id: str, shared: bool) -> bool:
        """设置用户所有设备的共享状态（user级），返回是否成功"""
        with self._lock:
            devices = self._bindings.get(user_id, {})
            if not devices:
                return False
            for b in devices.values():
                b.shared = shared
        self._save()
        return True
