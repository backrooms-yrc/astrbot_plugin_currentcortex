"""DG-LAB 权限控制系统 - 设备广场/控制申请/授权管理"""

import json
import os
import secrets
import threading
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from astrbot.api import logger


class RequestStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


DURATION_MAP = {
    "1h": 3600,
    "1d": 86400,
    "7d": 604800,
    "30d": 2592000,
    "permanent": 0,
}


@dataclass
class ControlRequest:
    request_id: str
    from_username: str
    from_qq: str
    to_username: str
    to_qq: str
    created_at: float
    status: str = "pending"
    duration_key: str = ""
    approved_at: float = 0.0
    expires_at: float = 0.0
    revoked_at: float = 0.0


class PermissionStore:
    def __init__(self, data_dir: str = "data"):
        self._data_dir = data_dir
        self._file_path = os.path.join(data_dir, "dglab_permissions.json")
        self._lock = threading.Lock()
        self._requests: Dict[str, ControlRequest] = {}
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self):
        os.makedirs(self._data_dir, exist_ok=True)

    def _load(self):
        if not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                with self._lock:
                    for rid, rdata in data.items():
                        if isinstance(rdata, dict):
                            try:
                                self._requests[rid] = ControlRequest(**rdata)
                            except Exception as e:
                                logger.error(f"[DGLab Perm] 加载申请 {rid} 失败: {e}")
            logger.info(f"[DGLab Perm] 已加载 {len(self._requests)} 条权限记录")
        except Exception as e:
            logger.error(f"[DGLab Perm] 加载权限数据失败: {e}")

    def _save(self):
        try:
            with self._lock:
                data = {rid: asdict(r) for rid, r in self._requests.items()}
            temp = self._file_path + '.tmp'
            with open(temp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, self._file_path)
        except Exception as e:
            logger.error(f"[DGLab Perm] 保存权限数据失败: {e}")

    def create_request(self, from_username: str, from_qq: str, to_username: str, to_qq: str) -> str:
        with self._lock:
            for r in self._requests.values():
                if (r.from_username == from_username and r.to_username == to_username
                        and r.status == "pending"):
                    return ""

        request_id = secrets.token_urlsafe(12)
        req = ControlRequest(
            request_id=request_id,
            from_username=from_username,
            from_qq=from_qq,
            to_username=to_username,
            to_qq=to_qq,
            created_at=time.time(),
        )
        with self._lock:
            self._requests[request_id] = req
        self._save()
        return request_id

    def get_pending_requests(self, to_username: str) -> List[ControlRequest]:
        now = time.time()
        with self._lock:
            return [
                r for r in self._requests.values()
                if r.to_username == to_username and r.status == "pending"
                and (now - r.created_at) < 7 * 86400
            ]

    def approve_request(self, request_id: str, duration_key: str) -> bool:
        with self._lock:
            req = self._requests.get(request_id)
            if not req or req.status != "pending":
                return False
            req.status = "approved"
            req.duration_key = duration_key
            req.approved_at = time.time()
            if duration_key == "permanent":
                req.expires_at = 0.0
            else:
                req.expires_at = time.time() + DURATION_MAP.get(duration_key, 3600)
        self._save()
        return True

    def reject_request(self, request_id: str) -> bool:
        with self._lock:
            req = self._requests.get(request_id)
            if not req or req.status != "pending":
                return False
            req.status = "rejected"
        self._save()
        return True

    def revoke_permission(self, request_id: str) -> bool:
        with self._lock:
            req = self._requests.get(request_id)
            if not req or req.status != "approved":
                return False
            req.status = "revoked"
            req.revoked_at = time.time()
        self._save()
        return True

    def get_granted_permissions(self, to_username: str) -> List[ControlRequest]:
        now = time.time()
        with self._lock:
            return [
                r for r in self._requests.values()
                if r.to_username == to_username and r.status == "approved"
                and (r.expires_at == 0.0 or r.expires_at > now)
            ]

    def get_my_permissions(self, from_username: str) -> List[ControlRequest]:
        now = time.time()
        with self._lock:
            return [
                r for r in self._requests.values()
                if r.from_username == from_username and r.status == "approved"
                and (r.expires_at == 0.0 or r.expires_at > now)
            ]

    def has_permission(self, from_username: str, to_qq: str) -> bool:
        now = time.time()
        with self._lock:
            for r in self._requests.values():
                if (r.from_username == from_username and r.to_qq == to_qq
                        and r.status == "approved"):
                    if r.expires_at == 0.0 or r.expires_at > now:
                        return True
        return False

    def get_sent_requests(self, from_username: str) -> List[ControlRequest]:
        with self._lock:
            return [
                r for r in self._requests.values()
                if r.from_username == from_username
            ]
