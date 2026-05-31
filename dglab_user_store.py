"""DG-LAB 用户系统 - 注册/登录/会话管理"""

import json
import os
import hashlib
import secrets
import threading
import time
from typing import Dict, Optional
from dataclasses import dataclass, asdict

from astrbot.api import logger


@dataclass
class UserInfo:
    username: str
    phone: str
    qq: str
    password_hash: str
    salt: str
    created_at: float
    public_device: bool = False
    allow_requests: bool = False


@dataclass
class Session:
    token: str
    username: str
    created_at: float
    expires_at: float


class UserStore:
    def __init__(self, data_dir: str = "data"):
        self._data_dir = data_dir
        self._file_path = os.path.join(data_dir, "dglab_users.json")
        self._sessions_path = os.path.join(data_dir, "dglab_sessions.json")
        self._lock = threading.Lock()
        self._users: Dict[str, UserInfo] = {}
        self._sessions: Dict[str, Session] = {}
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self):
        os.makedirs(self._data_dir, exist_ok=True)

    def _load(self):
        if os.path.exists(self._file_path):
            try:
                with open(self._file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    with self._lock:
                        for username, udata in data.items():
                            if isinstance(udata, dict):
                                try:
                                    self._users[username] = UserInfo(**udata)
                                except Exception as e:
                                    logger.error(f"[DGLab User] 加载用户 {username} 失败: {e}")
                logger.info(f"[DGLab User] 已加载 {len(self._users)} 个用户")
            except Exception as e:
                logger.error(f"[DGLab User] 加载用户数据失败: {e}")

        if os.path.exists(self._sessions_path):
            try:
                with open(self._sessions_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    now = time.time()
                    with self._lock:
                        for token, sdata in data.items():
                            if isinstance(sdata, dict):
                                try:
                                    session = Session(**sdata)
                                    if session.expires_at > now:
                                        self._sessions[token] = session
                                except Exception:
                                    pass
            except Exception:
                pass

    def _save_users(self):
        try:
            with self._lock:
                data = {u: asdict(info) for u, info in self._users.items()}
            temp = self._file_path + '.tmp'
            with open(temp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, self._file_path)
        except Exception as e:
            logger.error(f"[DGLab User] 保存用户数据失败: {e}")

    def _save_sessions(self):
        try:
            with self._lock:
                data = {t: asdict(s) for t, s in self._sessions.items()}
            temp = self._sessions_path + '.tmp'
            with open(temp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, self._sessions_path)
        except Exception as e:
            logger.error(f"[DGLab User] 保存会话数据失败: {e}")

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.sha256((salt + password).encode('utf-8')).hexdigest()

    def register(self, username: str, phone: str, qq: str, password: str) -> tuple:
        with self._lock:
            if username in self._users:
                return False, "用户名已存在"
            for u in self._users.values():
                if u.qq == qq:
                    return False, "该QQ号已被注册"

        salt = secrets.token_hex(16)
        password_hash = self._hash_password(password, salt)
        user = UserInfo(
            username=username,
            phone=phone,
            qq=qq,
            password_hash=password_hash,
            salt=salt,
            created_at=time.time(),
        )
        with self._lock:
            self._users[username] = user
        self._save_users()
        logger.info(f"[DGLab User] 新用户注册: {username} (QQ: {qq})")
        return True, "注册成功"

    def login(self, username: str, password: str) -> tuple:
        with self._lock:
            user = self._users.get(username)
        if not user:
            return None, "用户名或密码错误"
        if self._hash_password(password, user.salt) != user.password_hash:
            return None, "用户名或密码错误"

        token = secrets.token_urlsafe(32)
        session = Session(
            token=token,
            username=username,
            created_at=time.time(),
            expires_at=time.time() + 7 * 24 * 3600,
        )
        with self._lock:
            self._sessions[token] = session
        self._save_sessions()
        return token, "登录成功"

    def validate_session(self, token: str) -> Optional[str]:
        with self._lock:
            session = self._sessions.get(token)
        if not session:
            return None
        if time.time() > session.expires_at:
            with self._lock:
                self._sessions.pop(token, None)
            self._save_sessions()
            return None
        return session.username

    def logout(self, token: str):
        with self._lock:
            self._sessions.pop(token, None)
        self._save_sessions()

    def get_user(self, username: str) -> Optional[UserInfo]:
        with self._lock:
            return self._users.get(username)

    def get_user_by_qq(self, qq: str) -> Optional[UserInfo]:
        with self._lock:
            for u in self._users.values():
                if u.qq == qq:
                    return u
        return None

    def update_settings(self, username: str, public_device: bool, allow_requests: bool) -> bool:
        with self._lock:
            user = self._users.get(username)
            if not user:
                return False
            user.public_device = public_device
            user.allow_requests = allow_requests
        self._save_users()
        return True

    def list_public_users(self) -> list:
        with self._lock:
            return [
                {"username": u.username, "qq": u.qq}
                for u in self._users.values()
                if u.public_device
            ]
