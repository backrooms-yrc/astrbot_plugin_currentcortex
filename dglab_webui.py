"""CurrentCortex WebUI 控制界面

提供基于浏览器的设备控制面板，通过 aiohttp.web 实现 HTTP 服务器。
包含用户认证、设备隔离、权限控制功能。
"""

import os
import base64
from typing import Optional
from dataclasses import asdict

from aiohttp import web

from astrbot.api import logger

from .dglab_connection_pool import DeviceConnectionPool, ConnectionStatus
from .dglab_device_store import DeviceStore
from .dglab_commands import WAVE_PRESETS
from .dglab_user_store import UserStore
from .dglab_permission_store import PermissionStore
from .dglab_post_store import PostStore
from .dglab_chat_store import ChatStore
from .dglab_email_store import EmailStore
from .dglab_turnstile_store import TurnstileStore
import asyncio
import json as _json


class DGLabWebUI:
    def __init__(
        self,
        connection_pool: DeviceConnectionPool,
        device_store: DeviceStore,
        user_store: UserStore,
        permission_store: PermissionStore,
        host: str = "0.0.0.0",
        port: int = 9800,
    ):
        self._pool = connection_pool
        self._store = device_store
        self._user_store = user_store
        self._perm_store = permission_store
        self._post_store = PostStore(data_dir=user_store._data_dir)
        self._chat_store = ChatStore(data_dir=user_store._data_dir)
        self._email_store = EmailStore(data_dir=user_store._data_dir)
        self._turnstile_store = TurnstileStore(data_dir=user_store._data_dir)
        self._ws_clients: dict = {}  # username -> list of WebSocket connections
        # Ensure public group exists
        self._chat_store.ensure_public_group(user_store)
        self._host = host
        self._port = port
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    async def start(self):
        try:
            self._app = web.Application()
            r = self._app.router
            r.add_get("/", self._handle_index)
            r.add_get("/login", self._handle_index)
            r.add_get("/register", self._handle_index)
            r.add_get("/devices", self._handle_index)
            r.add_get("/plaza", self._handle_index)
            r.add_get("/requests", self._handle_index)
            r.add_get("/settings", self._handle_index)
            r.add_get("/admin", self._handle_index)
            r.add_get("/profile", self._handle_index)
            r.add_get("/discover", self._handle_index)
            r.add_get("/discover/new", self._handle_index)
            r.add_get("/discover/{post_id}", self._handle_index)
            r.add_get("/user/{username}", self._handle_index)
            r.add_get("/docs", self._handle_index)
            r.add_get("/chat", self._handle_index)
            r.add_get("/chat/{path:.*}", self._handle_index)
            r.add_post("/api/auth/register", self._handle_register)
            r.add_post("/api/auth/login", self._handle_login)
            r.add_post("/api/auth/logout", self._handle_logout)
            r.add_get("/api/auth/me", self._handle_me)
            r.add_get("/api/admin/users", self._handle_admin_list_users)
            r.add_post("/api/admin/users/{username}/role", self._handle_admin_set_role)
            r.add_get("/api/profile", self._handle_get_profile)
            r.add_post("/api/profile", self._handle_save_profile)
            r.add_post("/api/avatar/upload", self._handle_avatar_upload)
            r.add_get("/api/avatar/{username}", self._handle_avatar_serve)
            r.add_get("/api/posts", self._handle_list_posts)
            r.add_get("/api/posts/{post_id}", self._handle_get_post)
            r.add_post("/api/posts", self._handle_create_post)
            r.add_post("/api/posts/{post_id}/delete", self._handle_delete_post)
            r.add_get("/api/user/{username}", self._handle_user_public)
            r.add_get("/api/devices", self._handle_list_devices)
            r.add_get("/api/device/{user_id}/status", self._handle_device_status)
            r.add_post("/api/device/{user_id}/strength", self._handle_set_strength)
            r.add_post("/api/device/{user_id}/pulse", self._handle_send_pulse)
            r.add_post("/api/device/{user_id}/stop", self._handle_stop)
            r.add_get("/api/plaza", self._handle_plaza)
            r.add_post("/api/plaza/request", self._handle_plaza_request)
            r.add_get("/api/requests/pending", self._handle_pending_requests)
            r.add_post("/api/requests/{request_id}/approve", self._handle_approve)
            r.add_post("/api/requests/{request_id}/reject", self._handle_reject)
            r.add_post("/api/requests/{request_id}/revoke", self._handle_revoke)
            r.add_get("/api/requests/granted", self._handle_granted)
            r.add_get("/api/settings", self._handle_get_settings)
            r.add_post("/api/settings", self._handle_save_settings)
            # Chat API routes
            r.add_get("/api/chat/conversations", self._handle_chat_conversations)
            r.add_get(
                "/api/chat/messages/{conversation_id}", self._handle_chat_messages
            )
            r.add_post("/api/chat/messages", self._handle_chat_send)
            r.add_post(
                "/api/chat/mark-read/{conversation_id}", self._handle_chat_mark_read
            )
            r.add_get("/api/chat/friends", self._handle_chat_friends)
            r.add_post("/api/chat/friend-request", self._handle_chat_friend_request)
            r.add_get("/api/chat/friend-requests", self._handle_chat_friend_requests)
            r.add_get(
                "/api/chat/sent-friend-requests", self._handle_chat_sent_friend_requests
            )
            r.add_post(
                "/api/chat/friend-request/{request_id}/accept",
                self._handle_chat_accept_friend,
            )
            r.add_post(
                "/api/chat/friend-request/{request_id}/reject",
                self._handle_chat_reject_friend,
            )
            r.add_post("/api/chat/remove-friend", self._handle_chat_remove_friend)
            r.add_post("/api/chat/create-group", self._handle_chat_create_group)
            r.add_get(
                "/api/chat/group-members/{group_id}", self._handle_chat_group_members
            )
            r.add_post("/api/chat/invite-to-group", self._handle_chat_invite_to_group)
            r.add_get("/api/chat/group-invites", self._handle_chat_group_invites)
            r.add_post(
                "/api/chat/group-invite/{invite_id}/accept",
                self._handle_chat_accept_group_invite,
            )
            r.add_post(
                "/api/chat/group-invite/{invite_id}/reject",
                self._handle_chat_reject_group_invite,
            )
            r.add_post(
                "/api/chat/remove-group-member", self._handle_chat_remove_group_member
            )
            r.add_post("/api/chat/leave-group", self._handle_chat_leave_group)
            r.add_post("/api/chat/update-group", self._handle_chat_update_group)
            r.add_get("/api/chat/search-users", self._handle_chat_search_users)
            r.add_post("/api/chat/upload-file", self._handle_chat_upload_file)
            r.add_get("/api/chat/files/{filename}", self._handle_chat_file_serve)
            # WebSocket
            r.add_get("/ws/chat", self._handle_ws_chat)
            # Email verification routes
            r.add_post(
                "/api/auth/register-with-email", self._handle_register_with_email
            )
            r.add_post("/api/auth/verify-email", self._handle_verify_email)
            r.add_post(
                "/api/auth/resend-verification", self._handle_resend_verification
            )
            # SMTP config routes (admin only)
            r.add_get("/api/admin/smtp-config", self._handle_get_smtp_config)
            r.add_post("/api/admin/smtp-config", self._handle_save_smtp_config)
            r.add_post("/api/admin/smtp-test", self._handle_test_smtp)
            # Turnstile config routes
            r.add_get("/api/turnstile/config", self._handle_get_turnstile_config)
            r.add_post(
                "/api/admin/turnstile-config", self._handle_save_turnstile_config
            )

            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self._host, self._port)
            await self._site.start()
            logger.info(f"[CurrentCortex] 已启动: http://{self._host}:{self._port}")
        except OSError as e:
            logger.error(
                f"[CurrentCortex] 启动失败（端口 {self._port} 可能被占用）: {e}"
            )
        except Exception as e:
            logger.error(f"[CurrentCortex] 启动失败: {e}")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        logger.info("[CurrentCortex] 已停止")

    def _get_token(self, request: web.Request) -> Optional[str]:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return request.cookies.get("token")

    def _auth_user(self, request: web.Request) -> Optional[str]:
        token = self._get_token(request)
        if not token:
            return None
        return self._user_store.validate_session(token)

    async def _verify_turnstile(self, request: web.Request) -> Optional[str]:
        """Verify Turnstile token if enabled. Returns error message or None on success."""
        if not self._turnstile_store.is_enabled():
            return None
        try:
            body = await request.json()
        except Exception:
            return "无效的请求体"
        token = body.get("turnstile_token", "").strip()
        if not token:
            return "请完成人机验证"
        remote_ip = request.remote or ""
        ok, msg = await self._turnstile_store.verify(token, remote_ip)
        if not ok:
            return msg
        return None

    async def _handle_register(self, request: web.Request) -> web.Response:
        # Turnstile verification
        ts_error = await self._verify_turnstile(request)
        if ts_error:
            return web.json_response({"error": ts_error}, status=400)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        username = body.get("username", "").strip()
        email = body.get("email", "").strip()
        password = body.get("password", "")
        if not username or not email or not password:
            return web.json_response({"error": "所有字段均为必填"}, status=400)
        if len(username) < 2 or len(username) > 20:
            return web.json_response(
                {"error": "用户名长度需在2-20字符之间"}, status=400
            )
        if len(password) < 6:
            return web.json_response({"error": "密码长度不能少于6位"}, status=400)
        # Email format validation
        import re

        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            return web.json_response({"error": "邮箱格式不正确"}, status=400)
        ok, msg = self._user_store.register(username, email, password)
        if not ok:
            return web.json_response({"error": msg}, status=409)
        # Auto-add to public group
        self._chat_store.add_user_to_public_group(username, self._user_store)
        return web.json_response({"ok": True, "message": msg})

    async def _handle_login(self, request: web.Request) -> web.Response:
        # Turnstile verification
        ts_error = await self._verify_turnstile(request)
        if ts_error:
            return web.json_response({"error": ts_error}, status=400)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        username = body.get("username", "").strip()
        password = body.get("password", "")
        if not username or not password:
            return web.json_response({"error": "用户名和密码不能为空"}, status=400)
        token, msg = self._user_store.login(username, password)
        if not token:
            return web.json_response({"error": msg}, status=401)
        resp = web.json_response({"ok": True, "token": token, "message": msg})
        resp.set_cookie(
            "token", token, max_age=7 * 24 * 3600, httponly=True, samesite="Lax"
        )
        return resp

    async def _handle_logout(self, request: web.Request) -> web.Response:
        token = self._get_token(request)
        if token:
            self._user_store.logout(token)
        resp = web.json_response({"ok": True})
        resp.del_cookie("token")
        return resp

    async def _handle_me(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        user = self._user_store.get_user(username)
        if not user:
            return web.json_response({"error": "用户不存在"}, status=404)
        return web.json_response(
            {
                "username": user.username,
                "email": user.email,
                "email_verified": user.email_verified,
                "qq": user.qq,
                "phone": user.phone,
                "public_device": user.public_device,
                "allow_requests": user.allow_requests,
                "role": getattr(user, "role", "user"),
                "nickname": getattr(user, "nickname", ""),
                "gender": getattr(user, "gender", ""),
                "avatar": getattr(user, "avatar", ""),
                "bio": getattr(user, "bio", ""),
            }
        )

    async def _handle_list_devices(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        user = self._user_store.get_user(username)
        if not user:
            return web.json_response({"error": "用户不存在"}, status=404)

        bindings = self._store.list_all_bindings()
        my_devices = []
        for user_id, b in bindings.items():
            if user_id == user.qq:
                status_info = self._pool.get_user_status_info(user_id)
                feedback = self._pool.get_strength_feedback(user_id)
                my_devices.append(
                    {
                        "user_id": user_id,
                        "server_url": b.server_url,
                        "status": status_info["status"]
                        if status_info
                        else "disconnected",
                        "is_bound": status_info["is_bound"] if status_info else False,
                        "strength_a": feedback["strength_a"] if feedback else 0,
                        "strength_b": feedback["strength_b"] if feedback else 0,
                        "limit_a": feedback["limit_a"] if feedback else 200,
                        "limit_b": feedback["limit_b"] if feedback else 200,
                    }
                )

        permitted = self._perm_store.get_my_permissions(username)
        for perm in permitted:
            target_qq = perm.to_qq
            if target_qq in bindings and target_qq != user.qq:
                b = bindings[target_qq]
                status_info = self._pool.get_user_status_info(target_qq)
                feedback = self._pool.get_strength_feedback(target_qq)
                my_devices.append(
                    {
                        "user_id": target_qq,
                        "server_url": b.server_url,
                        "status": status_info["status"]
                        if status_info
                        else "disconnected",
                        "is_bound": status_info["is_bound"] if status_info else False,
                        "strength_a": feedback["strength_a"] if feedback else 0,
                        "strength_b": feedback["strength_b"] if feedback else 0,
                        "limit_a": feedback["limit_a"] if feedback else 200,
                        "limit_b": feedback["limit_b"] if feedback else 200,
                        "owner": perm.to_username,
                        "is_permitted": True,
                    }
                )

        return web.json_response({"devices": my_devices, "qq": user.qq})

    async def _handle_device_status(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        user_id = request.match_info["user_id"]
        if not self._check_device_access(username, user_id):
            return web.json_response({"error": "无权访问该设备"}, status=403)
        status_info = self._pool.get_user_status_info(user_id)
        feedback = self._pool.get_strength_feedback(user_id)
        if not status_info:
            return web.json_response({"error": "设备未连接"}, status=404)
        result = {**status_info}
        if feedback:
            result.update(feedback)
        return web.json_response(result)

    async def _handle_set_strength(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        user_id = request.match_info["user_id"]
        if not self._check_device_access(username, user_id):
            return web.json_response({"error": "无权控制该设备"}, status=403)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        channel = body.get("channel", "A").upper()
        value = body.get("value", 0)
        if channel not in ("A", "B"):
            return web.json_response({"error": "通道必须是 A 或 B"}, status=400)
        if not isinstance(value, int) or not (0 <= value <= 200):
            return web.json_response({"error": "强度值必须在 0-200 范围内"}, status=400)
        channel_num = 1 if channel == "A" else 2
        try:
            result = await self._pool.send_strength_command(
                user_id, channel_num, 2, value
            )
            return web.json_response({"ok": True, "message": result})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_send_pulse(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        user_id = request.match_info["user_id"]
        if not self._check_device_access(username, user_id):
            return web.json_response({"error": "无权控制该设备"}, status=403)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        channel = body.get("channel", "A").upper()
        preset = body.get("preset", "breathe")
        duration = body.get("duration", 5)
        if channel not in ("A", "B"):
            return web.json_response({"error": "通道必须是 A 或 B"}, status=400)
        if preset not in WAVE_PRESETS:
            return web.json_response({"error": f"未知预设: {preset}"}, status=400)
        if not isinstance(duration, int) or not (1 <= duration <= 60):
            return web.json_response({"error": "持续时间必须在 1-60 秒"}, status=400)
        pulse_data = WAVE_PRESETS[preset]["data"]
        try:
            result = await self._pool.send_pulse_command(
                user_id, channel, pulse_data, duration
            )
            return web.json_response({"ok": True, "message": result})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_stop(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        user_id = request.match_info["user_id"]
        if not self._check_device_access(username, user_id):
            return web.json_response({"error": "无权控制该设备"}, status=403)
        try:
            result = await self._pool.stop_all(user_id)
            return web.json_response({"ok": True, "message": result})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    def _check_device_access(self, username: str, device_qq: str) -> bool:
        user = self._user_store.get_user(username)
        if not user:
            return False
        if user.qq == device_qq:
            return True
        return self._perm_store.has_permission(username, device_qq)

    async def _handle_plaza(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        public_users = self._user_store.list_public_users()
        bindings = self._store.list_all_bindings()
        plaza_devices = []
        for pu in public_users:
            if pu["username"] == username:
                continue
            target_user = self._user_store.get_user(pu["username"])
            if not target_user or not target_user.allow_requests:
                continue
            qq = pu["qq"]
            if qq in bindings:
                status_info = self._pool.get_user_status_info(qq)
                plaza_devices.append(
                    {
                        "username": pu["username"],
                        "qq": qq,
                        "status": status_info["status"]
                        if status_info
                        else "disconnected",
                    }
                )
        return web.json_response({"devices": plaza_devices})

    async def _handle_plaza_request(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        user = self._user_store.get_user(username)
        if not user:
            return web.json_response({"error": "用户不存在"}, status=404)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        to_username = body.get("to_username", "").strip()
        if not to_username:
            return web.json_response({"error": "目标用户不能为空"}, status=400)
        target = self._user_store.get_user(to_username)
        if not target:
            return web.json_response({"error": "目标用户不存在"}, status=404)
        if not target.allow_requests:
            return web.json_response({"error": "该用户不接受控制申请"}, status=403)
        rid = self._perm_store.create_request(username, user.qq, to_username, target.qq)
        if not rid:
            return web.json_response({"error": "已有待处理的申请"}, status=409)
        return web.json_response({"ok": True, "request_id": rid})

    async def _handle_pending_requests(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        pending = self._perm_store.get_pending_requests(username)
        granted = self._perm_store.get_granted_permissions(username)
        return web.json_response(
            {
                "pending": [asdict(r) for r in pending],
                "granted": [asdict(r) for r in granted],
            }
        )

    async def _handle_approve(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        request_id = request.match_info["request_id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        duration_key = body.get("duration", "1h")
        if duration_key not in ("1h", "1d", "7d", "30d", "permanent"):
            return web.json_response({"error": "无效的授权时长"}, status=400)
        ok = self._perm_store.approve_request(request_id, duration_key)
        if not ok:
            return web.json_response({"error": "申请不存在或已处理"}, status=404)
        return web.json_response({"ok": True})

    async def _handle_reject(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        request_id = request.match_info["request_id"]
        ok = self._perm_store.reject_request(request_id)
        if not ok:
            return web.json_response({"error": "申请不存在或已处理"}, status=404)
        return web.json_response({"ok": True})

    async def _handle_revoke(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        request_id = request.match_info["request_id"]
        ok = self._perm_store.revoke_permission(request_id)
        if not ok:
            return web.json_response({"error": "权限不存在或已撤销"}, status=404)
        return web.json_response({"ok": True})

    async def _handle_granted(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        granted = self._perm_store.get_granted_permissions(username)
        return web.json_response({"granted": [asdict(r) for r in granted]})

    async def _handle_get_settings(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        user = self._user_store.get_user(username)
        if not user:
            return web.json_response({"error": "用户不存在"}, status=404)
        return web.json_response(
            {
                "public_device": user.public_device,
                "allow_requests": user.allow_requests,
            }
        )

    async def _handle_save_settings(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        public_device = bool(body.get("public_device", False))
        allow_requests = bool(body.get("allow_requests", False))
        ok = self._user_store.update_settings(username, public_device, allow_requests)
        if not ok:
            return web.json_response({"error": "保存失败"}, status=500)
        return web.json_response({"ok": True})

    async def _handle_get_profile(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        user = self._user_store.get_user(username)
        if not user:
            return web.json_response({"error": "用户不存在"}, status=404)
        return web.json_response(
            {
                "username": user.username,
                "nickname": getattr(user, "nickname", ""),
                "gender": getattr(user, "gender", ""),
                "avatar": getattr(user, "avatar", ""),
                "bio": getattr(user, "bio", ""),
            }
        )

    async def _handle_save_profile(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        nickname = str(body.get("nickname", "")).strip()[:30]
        gender = str(body.get("gender", "")).strip()
        if gender not in ("", "male", "female", "other"):
            gender = ""
        avatar = str(body.get("avatar", "")).strip()[:500]
        bio = str(body.get("bio", "")).strip()[:200]
        ok = self._user_store.update_profile(username, nickname, gender, avatar, bio)
        if not ok:
            return web.json_response({"error": "保存失败"}, status=500)
        return web.json_response({"ok": True, "message": "个人资料已更新"})

    async def _handle_avatar_upload(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        data_url = body.get("image", "")
        if not data_url or not data_url.startswith("data:image/"):
            return web.json_response({"error": "无效的图片数据"}, status=400)
        # Parse data URL: data:image/png;base64,xxxxx
        try:
            header, b64data = data_url.split(",", 1)
            # Determine extension from mime
            mime = header.split(":")[1].split(";")[0]  # e.g. image/png
            ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
            ext = ext_map.get(mime, "png")
            img_bytes = base64.b64decode(b64data)
        except Exception:
            return web.json_response({"error": "图片数据解析失败"}, status=400)
        # Limit size to 2MB
        if len(img_bytes) > 2 * 1024 * 1024:
            return web.json_response({"error": "图片大小不能超过2MB"}, status=400)
        # Save to avatars directory
        avatars_dir = os.path.join(self._user_store._data_dir, "avatars")
        os.makedirs(avatars_dir, exist_ok=True)
        filename = f"{username}.{ext}"
        filepath = os.path.join(avatars_dir, filename)
        try:
            with open(filepath, "wb") as f:
                f.write(img_bytes)
        except Exception as e:
            return web.json_response({"error": f"保存失败: {e}"}, status=500)
        # Update user avatar URL
        avatar_url = f"/api/avatar/{username}"
        user = self._user_store.get_user(username)
        if user:
            self._user_store.update_profile(
                username,
                getattr(user, "nickname", ""),
                getattr(user, "gender", ""),
                avatar_url,
                getattr(user, "bio", ""),
            )
        return web.json_response(
            {"ok": True, "avatar": avatar_url, "message": "头像已更新"}
        )

    async def _handle_avatar_serve(self, request: web.Request) -> web.Response:
        target = request.match_info["username"]
        avatars_dir = os.path.join(self._user_store._data_dir, "avatars")
        # Try common extensions
        for ext in ("png", "jpg", "webp"):
            filepath = os.path.join(avatars_dir, f"{target}.{ext}")
            if os.path.exists(filepath):
                mime_map = {
                    "png": "image/png",
                    "jpg": "image/jpeg",
                    "webp": "image/webp",
                }
                with open(filepath, "rb") as f:
                    data = f.read()
                return web.Response(
                    body=data,
                    content_type=mime_map.get(ext, "image/png"),
                    headers={"Cache-Control": "public, max-age=300"},
                )
        return web.Response(status=404, text="Avatar not found")

    async def _handle_list_posts(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        sort = request.query.get("sort", "newest")
        query = request.query.get("q", "")
        posts = self._post_store.list_posts(limit=50, sort=sort, query=query)
        # Attach author info (nickname, avatar)
        for p in posts:
            user = self._user_store.get_user(p["author"])
            if user:
                p["author_nickname"] = user.nickname or p["author"]
                p["author_avatar"] = user.avatar or ""
            else:
                p["author_nickname"] = p["author"]
                p["author_avatar"] = ""
        return web.json_response({"posts": posts})

    async def _handle_get_post(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        post_id = request.match_info["post_id"]
        post = self._post_store.get_post(post_id)
        if not post:
            return web.json_response({"error": "帖子不存在"}, status=404)
        # Attach author info
        user = self._user_store.get_user(post["author"])
        if user:
            post["author_nickname"] = user.nickname or post["author"]
            post["author_avatar"] = user.avatar or ""
        else:
            post["author_nickname"] = post["author"]
            post["author_avatar"] = ""
        return web.json_response({"post": post})

    async def _handle_create_post(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        title = str(body.get("title", "")).strip()
        summary = str(body.get("summary", "")).strip()
        content = str(body.get("content", "")).strip()
        if not title:
            return web.json_response({"error": "标题不能为空"}, status=400)
        if len(title) > 100:
            return web.json_response({"error": "标题不能超过100字"}, status=400)
        if len(summary) > 300:
            return web.json_response({"error": "简介不能超过300字"}, status=400)
        if len(content) > 10000:
            return web.json_response({"error": "正文不能超过10000字"}, status=400)
        post_id = self._post_store.create_post(username, title, summary, content)
        if not post_id:
            return web.json_response({"error": "发布失败"}, status=500)
        return web.json_response(
            {"ok": True, "post_id": post_id, "message": "发布成功"}
        )

    async def _handle_delete_post(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        post_id = request.match_info["post_id"]
        is_admin = self._user_store.is_admin(username)
        ok = self._post_store.delete_post(post_id, username, is_admin)
        if not ok:
            return web.json_response({"error": "删除失败或无权限"}, status=403)
        return web.json_response({"ok": True, "message": "已删除"})

    async def _handle_user_public(self, request: web.Request) -> web.Response:
        auth_user = self._auth_user(request)
        if not auth_user:
            return web.json_response({"error": "未登录"}, status=401)
        target = request.match_info["username"]
        user = self._user_store.get_user(target)
        if not user:
            return web.json_response({"error": "用户不存在"}, status=404)
        return web.json_response(
            {
                "username": user.username,
                "nickname": user.nickname or user.username,
                "gender": user.gender or "",
                "avatar": user.avatar or "",
                "bio": user.bio or "",
            }
        )

    async def _handle_admin_list_users(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        if not self._user_store.is_admin(username):
            return web.json_response({"error": "无管理员权限"}, status=403)
        users = self._user_store.list_all_users()
        return web.json_response({"users": users})

    async def _handle_admin_set_role(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        if not self._user_store.is_admin(username):
            return web.json_response({"error": "无管理员权限"}, status=403)
        target_username = request.match_info["username"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        role = body.get("role", "").strip()
        if role not in ("user", "admin"):
            return web.json_response({"error": "角色必须是 user 或 admin"}, status=400)
        ok = self._user_store.set_user_role(target_username, role)
        if not ok:
            return web.json_response({"error": "用户不存在"}, status=404)
        return web.json_response(
            {"ok": True, "message": f"已将 {target_username} 设置为 {role}"}
        )

    # --- Chat API Handlers ---

    async def _handle_chat_conversations(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        conversations = self._chat_store.get_user_conversations(username)
        # Enrich with user info
        for conv in conversations:
            if conv.get("other_user"):
                other = self._user_store.get_user(conv["other_user"])
                if other:
                    conv["other_nickname"] = other.nickname or other.username
                    conv["other_avatar"] = other.avatar
            # Get unread count
            messages = self._chat_store.get_messages(
                conv["conversation_id"], limit=100, requester=username
            )
            conv["unread_count"] = sum(
                1
                for m in messages
                if m.get("sender") != username and m.get("status") != "read"
            )
            # Get last message
            if messages:
                conv["last_message"] = messages[0]
            else:
                conv["last_message"] = None
        return web.json_response({"conversations": conversations})

    async def _handle_chat_messages(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        conversation_id = request.match_info["conversation_id"]
        limit = int(request.query.get("limit", "50"))
        before = request.query.get("before")
        before_ts = float(before) if before else None
        messages = self._chat_store.get_messages(
            conversation_id, limit=limit, before=before_ts, requester=username
        )
        return web.json_response({"messages": messages})

    async def _handle_chat_send(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        conversation_id = body.get("conversation_id", "")
        msg_type = body.get("msg_type", "text")
        content = body.get("content", "")
        file_url = body.get("file_url", "")
        file_name = body.get("file_name", "")
        file_size = body.get("file_size", 0)
        voice_duration = body.get("voice_duration", 0)
        if not conversation_id:
            return web.json_response({"error": "缺少会话ID"}, status=400)
        msg_id = self._chat_store.send_message(
            conversation_id,
            username,
            msg_type,
            content,
            file_url=file_url,
            file_name=file_name,
            file_size=file_size,
            voice_duration=voice_duration,
        )
        if not msg_id:
            return web.json_response({"error": "发送失败"}, status=400)
        # Broadcast to WebSocket clients
        conv = self._chat_store.get_conversation(conversation_id)
        if conv:
            msg_data = self._chat_store.get_messages(conversation_id, limit=1)
            if msg_data:
                for participant in conv.get("participants", []):
                    await self._broadcast_ws(
                        participant,
                        {
                            "type": "new_message",
                            "conversation_id": conversation_id,
                            "message": msg_data[0],
                        },
                    )
        return web.json_response({"ok": True, "msg_id": msg_id})

    async def _handle_chat_mark_read(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        conversation_id = request.match_info["conversation_id"]
        count = self._chat_store.mark_messages_read(conversation_id, username)
        return web.json_response({"ok": True, "marked": count})

    async def _handle_chat_friends(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        friends = self._chat_store.get_friends(username)
        # Enrich with user info
        for f in friends:
            user = self._user_store.get_user(f["username"])
            if user:
                f["nickname"] = user.nickname or user.username
                f["avatar"] = user.avatar
        return web.json_response({"friends": friends})

    async def _handle_chat_friend_request(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        to_user = body.get("to_user", "").strip()
        if not to_user:
            return web.json_response({"error": "请指定用户"}, status=400)
        ok, msg = self._chat_store.send_friend_request(username, to_user)
        if not ok:
            return web.json_response({"error": msg}, status=400)
        # Notify via WebSocket
        await self._broadcast_ws(to_user, {"type": "friend_request", "from": username})
        return web.json_response({"ok": True, "message": msg})

    async def _handle_chat_friend_requests(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        requests = self._chat_store.get_friend_requests(username)
        # Enrich with user info
        for r in requests:
            user = self._user_store.get_user(r["from_user"])
            if user:
                r["from_nickname"] = user.nickname or user.username
                r["from_avatar"] = user.avatar
        return web.json_response({"requests": requests})

    async def _handle_chat_sent_friend_requests(
        self, request: web.Request
    ) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        requests = self._chat_store.get_sent_friend_requests(username)
        for r in requests:
            user = self._user_store.get_user(r["to_user"])
            if user:
                r["to_nickname"] = user.nickname or user.username
                r["to_avatar"] = user.avatar
        return web.json_response({"requests": requests})

    async def _handle_chat_accept_friend(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        request_id = request.match_info["request_id"]
        ok, msg = self._chat_store.accept_friend_request(request_id)
        if not ok:
            return web.json_response({"error": msg}, status=400)
        # Notify via WebSocket
        await self._broadcast_ws(username, {"type": "friend_accepted"})
        return web.json_response({"ok": True, "message": msg})

    async def _handle_chat_reject_friend(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        request_id = request.match_info["request_id"]
        ok, msg = self._chat_store.reject_friend_request(request_id)
        if not ok:
            return web.json_response({"error": msg}, status=400)
        return web.json_response({"ok": True, "message": msg})

    async def _handle_chat_remove_friend(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        friend_username = body.get("username", "").strip()
        if not friend_username:
            return web.json_response({"error": "请指定用户"}, status=400)
        ok = self._chat_store.remove_friend(username, friend_username)
        if not ok:
            return web.json_response({"error": "删除失败"}, status=400)
        return web.json_response({"ok": True})

    async def _handle_chat_create_group(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        name = body.get("name", "").strip()
        description = body.get("description", "").strip()
        avatar = body.get("avatar", "").strip()
        if not name:
            return web.json_response({"error": "群组名称不能为空"}, status=400)
        conv_id = self._chat_store.create_group_conversation(
            name, description, username, avatar
        )
        return web.json_response({"ok": True, "conversation_id": conv_id})

    async def _handle_chat_group_members(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        group_id = request.match_info["group_id"]
        members = self._chat_store.get_group_members(group_id)
        # Enrich with user info
        for m in members:
            user = self._user_store.get_user(m["username"])
            if user:
                m["nickname"] = user.nickname or user.username
                m["avatar"] = user.avatar
        return web.json_response({"members": members})

    async def _handle_chat_invite_to_group(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        group_id = body.get("group_id", "").strip()
        invitee = body.get("username", "").strip()
        if not group_id or not invitee:
            return web.json_response({"error": "缺少参数"}, status=400)
        ok, msg = self._chat_store.invite_to_group(group_id, username, invitee)
        if not ok:
            return web.json_response({"error": msg}, status=400)
        # Notify via WebSocket
        await self._broadcast_ws(
            invitee, {"type": "group_invite", "group_id": group_id}
        )
        return web.json_response({"ok": True, "message": msg})

    async def _handle_chat_group_invites(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        invites = self._chat_store.get_group_invites(username)
        # Enrich with group info
        for inv in invites:
            conv = self._chat_store.get_conversation(inv["group_id"])
            if conv:
                inv["group_name"] = conv.get("name", "")
            user = self._user_store.get_user(inv["from_user"])
            if user:
                inv["from_nickname"] = user.nickname or user.username
        return web.json_response({"invites": invites})

    async def _handle_chat_accept_group_invite(
        self, request: web.Request
    ) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        invite_id = request.match_info["invite_id"]
        ok, msg = self._chat_store.accept_group_invite(invite_id)
        if not ok:
            return web.json_response({"error": msg}, status=400)
        return web.json_response({"ok": True, "message": msg})

    async def _handle_chat_reject_group_invite(
        self, request: web.Request
    ) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        invite_id = request.match_info["invite_id"]
        ok, msg = self._chat_store.reject_group_invite(invite_id)
        if not ok:
            return web.json_response({"error": msg}, status=400)
        return web.json_response({"ok": True, "message": msg})

    async def _handle_chat_remove_group_member(
        self, request: web.Request
    ) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        group_id = body.get("group_id", "").strip()
        member = body.get("username", "").strip()
        if not group_id or not member:
            return web.json_response({"error": "缺少参数"}, status=400)
        ok = self._chat_store.remove_group_member(group_id, member, username)
        if not ok:
            return web.json_response({"error": "操作失败"}, status=400)
        return web.json_response({"ok": True})

    async def _handle_chat_leave_group(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        group_id = body.get("group_id", "").strip()
        if not group_id:
            return web.json_response({"error": "缺少群组ID"}, status=400)
        ok = self._chat_store.leave_group(group_id, username)
        if not ok:
            return web.json_response({"error": "退出失败"}, status=400)
        return web.json_response({"ok": True})

    async def _handle_chat_update_group(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        conv_id = body.get("conversation_id", "").strip()
        name = body.get("name", "").strip()
        description = body.get("description", "").strip()
        avatar = body.get("avatar", "").strip()
        if not conv_id:
            return web.json_response({"error": "缺少会话ID"}, status=400)
        ok = self._chat_store.update_group_info(
            conv_id, name, description, avatar, username
        )
        if not ok:
            return web.json_response({"error": "更新失败"}, status=400)
        return web.json_response({"ok": True})

    async def _handle_chat_search_users(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        query = request.query.get("q", "").strip()
        if not query:
            return web.json_response({"users": []})
        users = self._chat_store.search_users(query, username, self._user_store)
        return web.json_response({"users": users})

    async def _handle_chat_upload_file(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username:
            return web.json_response({"error": "未登录"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        file_data = body.get("file_data", "")  # base64 encoded
        file_name = body.get("file_name", "file")
        if not file_data:
            return web.json_response({"error": "无文件数据"}, status=400)
        # Save file to data/chat_files/
        import uuid

        chat_files_dir = os.path.join(self._user_store._data_dir, "chat_files")
        os.makedirs(chat_files_dir, exist_ok=True)
        ext = os.path.splitext(file_name)[1] if file_name else ""
        file_id = uuid.uuid4().hex[:12]
        file_path = os.path.join(chat_files_dir, f"{file_id}{ext}")
        # Decode base64
        try:
            file_bytes = base64.b64decode(
                file_data.split(",")[-1] if "," in file_data else file_data
            )
            with open(file_path, "wb") as f:
                f.write(file_bytes)
        except Exception as e:
            return web.json_response({"error": f"文件保存失败: {e}"}, status=500)
        file_url = f"/api/chat/files/{file_id}{ext}"
        file_size = len(file_bytes)
        return web.json_response(
            {
                "ok": True,
                "file_url": file_url,
                "file_name": file_name,
                "file_size": file_size,
            }
        )

    async def _handle_chat_file_serve(self, request: web.Request) -> web.Response:
        filename = request.match_info["filename"]
        chat_files_dir = os.path.join(self._user_store._data_dir, "chat_files")
        file_path = os.path.join(chat_files_dir, filename)
        if not os.path.exists(file_path):
            return web.json_response({"error": "文件不存在"}, status=404)
        # Determine content type
        ext = os.path.splitext(filename)[1].lower()
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".mp4": "video/mp4",
            ".webm": "video/webm",
        }
        content_type = content_types.get(ext, "application/octet-stream")
        return web.FileResponse(file_path, headers={"Content-Type": content_type})

    # --- WebSocket Handler ---

    async def _handle_ws_chat(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        username = None
        # Authenticate via query param token
        token = request.query.get("token", "")
        if token:
            username = self._user_store.validate_session(token)
        if not username:
            await ws.close(code=4001, message=b"Unauthorized")
            return ws
        # Register connection
        if username not in self._ws_clients:
            self._ws_clients[username] = []
        self._ws_clients[username].append(ws)
        try:
            async for msg in ws:
                if msg.type == 1:  # TEXT
                    try:
                        data = _json.loads(msg.data)
                        # Handle incoming WS messages if needed (e.g., typing indicators)
                        msg_type = data.get("type", "")
                        if msg_type == "ping":
                            await ws.send_str(_json.dumps({"type": "pong"}))
                    except Exception:
                        pass
                elif msg.type == 8:  # ERROR
                    break
        finally:
            if username in self._ws_clients:
                self._ws_clients[username] = [
                    w for w in self._ws_clients[username] if w != ws
                ]
                if not self._ws_clients[username]:
                    del self._ws_clients[username]
        return ws

    async def _broadcast_ws(self, username: str, data: dict):
        """Send data to all WebSocket connections of a user."""
        if username in self._ws_clients:
            msg = _json.dumps(data)
            for ws in self._ws_clients[username]:
                try:
                    await ws.send_str(msg)
                except Exception:
                    pass

    # --- Email Verification Handlers ---

    async def _handle_register_with_email(self, request: web.Request) -> web.Response:
        """Register with email verification flow."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        username = body.get("username", "").strip()
        email = body.get("email", "").strip()
        password = body.get("password", "")
        code = body.get("code", "").strip()
        if not username or not email or not password or not code:
            return web.json_response({"error": "所有字段均为必填"}, status=400)
        if len(username) < 2 or len(username) > 20:
            return web.json_response(
                {"error": "用户名长度需在2-20字符之间"}, status=400
            )
        if len(password) < 6:
            return web.json_response({"error": "密码长度不能少于6位"}, status=400)
        import re

        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            return web.json_response({"error": "邮箱格式不正确"}, status=400)
        # Verify code first
        ok, msg = self._email_store.verify_code(email, code)
        if not ok:
            return web.json_response({"error": msg}, status=400)
        # Register user
        ok, msg = self._user_store.register(username, email, password)
        if not ok:
            return web.json_response({"error": msg}, status=409)
        # Mark email as verified
        self._user_store.verify_email(username)
        # Auto-add to public group
        self._chat_store.add_user_to_public_group(username, self._user_store)
        return web.json_response({"ok": True, "message": "注册成功"})

    async def _handle_verify_email(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        email = body.get("email", "").strip()
        code = body.get("code", "").strip()
        if not email or not code:
            return web.json_response({"error": "邮箱和验证码不能为空"}, status=400)
        ok, msg = self._email_store.verify_code(email, code)
        if not ok:
            return web.json_response({"error": msg}, status=400)
        return web.json_response({"ok": True, "message": msg})

    async def _handle_resend_verification(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        email = body.get("email", "").strip()
        if not email:
            return web.json_response({"error": "邮箱不能为空"}, status=400)
        # Check cooldown
        can_resend, remaining = self._email_store.can_resend(email)
        if not can_resend:
            return web.json_response(
                {"error": f"请{remaining}秒后再试", "remaining": remaining}, status=429
            )
        # Generate code
        code = self._email_store.generate_code(email)
        # Send email in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        ok, msg = await loop.run_in_executor(
            None, self._email_store.send_verification_email, email, code
        )
        if not ok:
            return web.json_response({"error": msg}, status=500)
        return web.json_response({"ok": True, "message": "验证码已发送"})

    # --- SMTP Config Handlers ---

    async def _handle_get_smtp_config(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username or not self._user_store.is_admin(username):
            return web.json_response({"error": "无权访问"}, status=403)
        config = self._email_store.get_config()
        if config:
            # Don't return full password, just indicate if configured
            return web.json_response(
                {
                    "configured": True,
                    "host": config.host,
                    "port": config.port,
                    "username": config.username,
                    "encryption": config.encryption,
                    "from_email": config.from_email,
                    "has_password": bool(config.password),
                }
            )
        return web.json_response({"configured": False})

    async def _handle_save_smtp_config(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username or not self._user_store.is_admin(username):
            return web.json_response({"error": "无权访问"}, status=403)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        host = body.get("host", "").strip()
        port = int(body.get("port", 587))
        smtp_user = body.get("username", "").strip()
        password = body.get("password", "").strip()
        encryption = body.get("encryption", "tls").strip()
        from_email = body.get("from_email", "").strip()
        if not host or not smtp_user:
            return web.json_response({"error": "SMTP服务器和账号不能为空"}, status=400)
        # If password is empty, keep the existing one
        if not password:
            existing = self._email_store.get_config()
            if existing:
                password = existing.password
        config = self._email_store.save_config(
            host, port, smtp_user, password, encryption, from_email
        )
        return web.json_response({"ok": True, "message": "SMTP配置已保存"})

    async def _handle_test_smtp(self, request: web.Request) -> web.Response:
        username = self._auth_user(request)
        if not username or not self._user_store.is_admin(username):
            return web.json_response({"error": "无权访问"}, status=403)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        host = body.get("host", "").strip()
        port = int(body.get("port", 587))
        smtp_user = body.get("username", "").strip()
        password = body.get("password", "").strip()
        encryption = body.get("encryption", "tls").strip()
        if not host or not smtp_user:
            return web.json_response({"error": "SMTP服务器和账号不能为空"}, status=400)
        # If password is empty, use the saved one
        if not password:
            existing = self._email_store.get_config()
            if existing:
                password = existing.password
            else:
                return web.json_response(
                    {"error": "请输入密码或先保存配置"}, status=400
                )
        # Run SMTP test in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        ok, msg = await loop.run_in_executor(
            None,
            self._email_store.test_connection,
            host,
            port,
            smtp_user,
            password,
            encryption,
        )
        if not ok:
            return web.json_response({"error": msg}, status=400)
        return web.json_response({"ok": True, "message": msg})

    # --- Turnstile Config Handlers ---

    async def _handle_get_turnstile_config(self, request: web.Request) -> web.Response:
        """Public endpoint to get Turnstile site key (no auth required)."""
        config = self._turnstile_store.get_config()
        if config and config.enabled:
            return web.json_response(
                {
                    "enabled": True,
                    "site_key": config.site_key,
                }
            )
        return web.json_response({"enabled": False, "site_key": ""})

    async def _handle_save_turnstile_config(self, request: web.Request) -> web.Response:
        """Admin endpoint to save Turnstile config."""
        username = self._auth_user(request)
        if not username or not self._user_store.is_admin(username):
            return web.json_response({"error": "无权访问"}, status=403)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        site_key = body.get("site_key", "").strip()
        secret_key = body.get("secret_key", "").strip()
        enabled = bool(body.get("enabled", True))
        if not site_key or not secret_key:
            return web.json_response(
                {"error": "Site Key 和 Secret Key 不能为空"}, status=400
            )
        config = self._turnstile_store.save_config(site_key, secret_key, enabled)
        return web.json_response({"ok": True, "message": "Turnstile 配置已保存"})

    async def _handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=INDEX_HTML, content_type="text/html")


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>CurrentCortex</title>
<script>
(function(){
  const GOOGLE_FONT='https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap';
  const GOOGLE_ICON='https://fonts.googleapis.com/icon?family=Material+Symbols+Outlined';
  const MIRROR_FONT='https://fonts.loli.net/css2?family=Roboto:wght@400;500;700&display=swap';
  const MIRROR_ICON='https://fonts.loli.net/icon?family=Material+Symbols+Outlined';
  const TIMEOUT=3000;
  function loadCSS(href){const l=document.createElement('link');l.rel='stylesheet';l.href=href;document.head.appendChild(l);return l;}
  function tryLoad(primary,fallback){
    return new Promise(resolve=>{
      const ctrl=new AbortController();
      const timer=setTimeout(()=>{ctrl.abort();loadCSS(fallback);resolve('fallback');},TIMEOUT);
      fetch(primary,{mode:'no-cors',signal:ctrl.signal})
        .then(()=>{clearTimeout(timer);loadCSS(primary);resolve('primary');})
        .catch(()=>{clearTimeout(timer);loadCSS(fallback);resolve('fallback');});
    });
  }
  tryLoad(GOOGLE_FONT,MIRROR_FONT);
  tryLoad(GOOGLE_ICON,MIRROR_ICON);
})();
</script>
<!-- PLACEHOLDER_STYLE -->
<style>
:root {
  --md-sys-color-primary: #D0BCFF;
  --md-sys-color-on-primary: #381E72;
  --md-sys-color-primary-container: #4F378B;
  --md-sys-color-on-primary-container: #EADDFF;
  --md-sys-color-secondary: #CCC2DC;
  --md-sys-color-on-secondary: #332D41;
  --md-sys-color-secondary-container: #4A4458;
  --md-sys-color-on-secondary-container: #E8DEF8;
  --md-sys-color-tertiary: #EFB8C8;
  --md-sys-color-on-tertiary: #492532;
  --md-sys-color-tertiary-container: #633B48;
  --md-sys-color-on-tertiary-container: #FFD8E4;
  --md-sys-color-error: #F2B8B5;
  --md-sys-color-on-error: #601410;
  --md-sys-color-error-container: #8C1D18;
  --md-sys-color-surface: #141218;
  --md-sys-color-on-surface: #E6E0E9;
  --md-sys-color-on-surface-variant: #CAC4D0;
  --md-sys-color-surface-container: #211F26;
  --md-sys-color-surface-container-low: #1D1B20;
  --md-sys-color-surface-container-high: #2B2930;
  --md-sys-color-surface-container-highest: #36343B;
  --md-sys-color-outline: #938F99;
  --md-sys-color-outline-variant: #49454F;
  --md-sys-color-inverse-surface: #E6E0E9;
  --md-sys-color-inverse-on-surface: #322F35;
  --md-sys-shape-corner-medium: 12px;
  --md-sys-shape-corner-large: 16px;
  --md-sys-shape-corner-extra-large: 28px;
}
*{box-sizing:border-box;margin:0;padding:0}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
body{font-family:'Roboto',sans-serif;background:var(--md-sys-color-surface);color:var(--md-sys-color-on-surface);min-height:100vh;overflow:hidden}
.material-symbols-outlined{font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 24}
.md-display-medium{font-size:2.25rem;font-weight:400;line-height:2.75rem}
.md-headline-small{font-size:1.5rem;font-weight:400;line-height:2rem}
.md-title-medium{font-size:1rem;font-weight:500;line-height:1.5rem;letter-spacing:.15px}
.md-title-small{font-size:.875rem;font-weight:500;line-height:1.25rem;letter-spacing:.1px}
.md-body-large{font-size:1rem;font-weight:400;line-height:1.5rem;letter-spacing:.5px}
.md-body-medium{font-size:.875rem;font-weight:400;line-height:1.25rem;letter-spacing:.25px}
.md-label-large{font-size:.875rem;font-weight:500;line-height:1.25rem;letter-spacing:.1px}
.on-surface-variant{color:var(--md-sys-color-on-surface-variant)}
.app-layout{display:flex;height:100vh;width:100vw;overflow:hidden}
.nav-rail{display:none;flex-direction:column;align-items:center;width:80px;min-width:80px;background:var(--md-sys-color-surface);padding:12px 0;gap:4px;border-right:1px solid var(--md-sys-color-outline-variant)}
.nav-rail-header{padding:16px 0 24px;display:flex;align-items:center;justify-content:center}
.nav-rail-logo{font-size:28px;color:var(--md-sys-color-primary)}
.nav-rail-items{display:flex;flex-direction:column;gap:4px;align-items:center}
.nav-rail-item{display:flex;flex-direction:column;align-items:center;gap:4px;padding:4px 0;border:none;background:none;cursor:pointer;color:var(--md-sys-color-on-surface-variant);width:56px;border-radius:var(--md-sys-shape-corner-large);transition:all .2s}
.nav-rail-item .material-symbols-outlined{width:56px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:16px;transition:background .2s}
.nav-rail-item .nav-label{font-size:12px;font-weight:500;letter-spacing:.5px}
.nav-rail-item:hover .material-symbols-outlined{background:var(--md-sys-color-surface-container-high)}
.nav-rail-item.active{color:var(--md-sys-color-on-surface)}
.nav-rail-item.active .material-symbols-outlined{background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container);font-variation-settings:'FILL' 1}
.nav-bottom{display:flex;justify-content:space-around;align-items:center;height:80px;background:var(--md-sys-color-surface-container);border-top:1px solid var(--md-sys-color-outline-variant);position:fixed;bottom:0;left:0;right:0;z-index:100}
.nav-bottom-item{display:flex;flex-direction:column;align-items:center;gap:4px;border:none;background:none;cursor:pointer;color:var(--md-sys-color-on-surface-variant);padding:12px 0;min-width:64px;transition:color .2s}
.nav-bottom-item .material-symbols-outlined{width:64px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:16px;transition:background .2s}
.nav-bottom-item .nav-label{font-size:12px;font-weight:500}
.nav-bottom-item.active{color:var(--md-sys-color-on-surface)}
.nav-bottom-item.active .material-symbols-outlined{background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container);font-variation-settings:'FILL' 1}
.main-content{flex:1;overflow-y:auto;padding:68px 24px 100px}
.page{display:none}
.page.active{display:block;animation:pageFadeIn .3s cubic-bezier(0.2,0,0,1) forwards}
.page.fade-out{display:block;animation:pageFadeOut .15s cubic-bezier(0.2,0,0,1) forwards}
@keyframes pageFadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@keyframes pageFadeOut{from{opacity:1;transform:none}to{opacity:0;transform:translateY(-8px)}}
.page-header{margin-bottom:32px}
.page-header h1{margin-bottom:8px}
.md-card{border-radius:var(--md-sys-shape-corner-medium);padding:24px;margin-bottom:16px}
.md-card-filled{background:var(--md-sys-color-surface-container-high)}
.md-card-outlined{background:var(--md-sys-color-surface-container-low);border:1px solid var(--md-sys-color-outline-variant)}
/* PLACEHOLDER_CSS_2 */
/* Admin page */
.admin-user-card{background:var(--md-sys-color-surface-container);border-radius:var(--md-sys-shape-corner-medium);padding:16px 20px;margin-bottom:10px;border:1px solid var(--md-sys-color-outline-variant);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}
.admin-user-info{display:flex;align-items:center;gap:12px;flex:1;min-width:200px}
.admin-user-avatar{width:40px;height:40px;border-radius:50%;background:var(--md-sys-color-primary-container);display:flex;align-items:center;justify-content:center;flex-shrink:0}
.admin-user-avatar .material-symbols-outlined{color:var(--md-sys-color-on-primary-container);font-size:20px}
.admin-user-details{display:flex;flex-direction:column;gap:2px}
.admin-user-name{font-weight:500;font-size:.9rem}
.admin-user-meta{font-size:.75rem;color:var(--md-sys-color-on-surface-variant)}
.admin-role-badge{padding:4px 10px;border-radius:12px;font-size:.75rem;font-weight:500}
.admin-role-admin{background:rgba(208,188,255,.15);color:var(--md-sys-color-primary)}
.admin-role-user{background:var(--md-sys-color-surface-container-highest);color:var(--md-sys-color-on-surface-variant)}
.admin-actions{display:flex;gap:8px;align-items:center}
.admin-select{padding:8px 12px;border-radius:8px;background:var(--md-sys-color-surface-container-highest);border:1px solid var(--md-sys-color-outline-variant);color:var(--md-sys-color-on-surface);font-size:.8rem;cursor:pointer;outline:none}
/* Profile page */
.profile-avatar-section{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.profile-avatar{width:72px;height:72px;border-radius:50%;background:var(--md-sys-color-primary-container);display:flex;align-items:center;justify-content:center;overflow:hidden;flex-shrink:0}
.profile-avatar .material-symbols-outlined{font-size:36px;color:var(--md-sys-color-on-primary-container)}
.profile-avatar img{width:100%;height:100%;object-fit:cover}
.avatar-editor-container{position:relative;width:100%;height:300px;background:var(--md-sys-color-surface-container-highest);border-radius:var(--md-sys-shape-corner-medium);overflow:hidden;margin:16px 0;cursor:grab;touch-action:none}
.avatar-editor-container:active{cursor:grabbing}
#avatar-editor-canvas{width:100%;height:100%;display:block}
.avatar-editor-tools{display:flex;justify-content:center;gap:8px;flex-wrap:wrap}
.gender-options{display:flex;gap:12px;flex-wrap:wrap}
.gender-option{display:flex;align-items:center;gap:8px;padding:8px 16px;border-radius:20px;cursor:pointer;background:var(--md-sys-color-surface-container-highest);transition:background .2s}
.gender-option:has(input:checked){background:var(--md-sys-color-secondary-container)}
.gender-option:has(input:checked) span{color:var(--md-sys-color-on-secondary-container)}
.gender-option input[type=radio]{accent-color:var(--md-sys-color-primary);width:16px;height:16px}
/* Discover page */
.post-card{background:var(--md-sys-color-surface-container);border-radius:var(--md-sys-shape-corner-medium);padding:16px 20px;margin-bottom:12px;border:1px solid var(--md-sys-color-outline-variant);cursor:pointer;transition:background .2s,border-color .2s}
.post-card:hover{background:var(--md-sys-color-surface-container-high);border-color:var(--md-sys-color-outline)}
.post-card-title{font-size:1rem;font-weight:500;color:var(--md-sys-color-on-surface);margin-bottom:4px}
.post-card-summary{font-size:.85rem;line-height:1.5;color:var(--md-sys-color-on-surface-variant);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-bottom:10px}
.post-card-footer{display:flex;justify-content:space-between;align-items:center;margin-top:8px}
.post-card-author{display:flex;align-items:center;gap:8px;cursor:pointer}
.post-card-meta{display:flex;align-items:center;gap:4px;font-size:.75rem;color:var(--md-sys-color-on-surface-variant)}
.post-author-avatar{width:32px;height:32px;border-radius:50%;background:var(--md-sys-color-primary-container);display:flex;align-items:center;justify-content:center;overflow:hidden;flex-shrink:0}
.post-author-avatar .material-symbols-outlined{font-size:16px;color:var(--md-sys-color-on-primary-container)}
.post-author-avatar img{width:100%;height:100%;object-fit:cover}
/* Discover page controls */
.discover-controls{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center}
.discover-search{flex:1;min-width:200px;display:flex;align-items:center;gap:8px;padding:8px 16px;background:var(--md-sys-color-surface-container-high);border:1px solid var(--md-sys-color-outline-variant);border-radius:28px}
.discover-search input{flex:1;border:none;background:none;color:var(--md-sys-color-on-surface);font-size:.875rem;outline:none}
.discover-sort{display:flex;gap:4px;background:var(--md-sys-color-surface-container);border-radius:20px;padding:4px;border:1px solid var(--md-sys-color-outline-variant)}
.discover-sort button{border:none;background:none;color:var(--md-sys-color-on-surface-variant);padding:6px 12px;border-radius:16px;font-size:.75rem;cursor:pointer;transition:all .2s}
.discover-sort button.active{background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container);font-weight:500}
/* FAB */
.fab{position:fixed;bottom:88px;right:24px;width:56px;height:56px;border-radius:16px;background:var(--md-sys-color-primary-container);color:var(--md-sys-color-on-primary-container);border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 3px 5px -1px rgba(0,0,0,.2),0 6px 10px 0 rgba(0,0,0,.14);transition:transform .2s,box-shadow .2s;z-index:101}
.fab:hover{transform:scale(1.05);box-shadow:0 5px 8px -2px rgba(0,0,0,.25),0 8px 14px 0 rgba(0,0,0,.18)}
@media(min-width:840px){.fab{bottom:32px;right:32px}}
/* Post detail page */
.post-detail-header{margin-bottom:24px}
.post-detail-title{font-size:1.5rem;font-weight:500;color:var(--md-sys-color-on-surface);margin-bottom:12px}
.post-detail-meta{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.post-detail-body{background:var(--md-sys-color-surface-container);border-radius:var(--md-sys-shape-corner-medium);padding:24px;border:1px solid var(--md-sys-color-outline-variant);line-height:1.7}
/* Post editor */
.editor-field{margin-bottom:16px}
.editor-field label{display:block;font-size:.8rem;font-weight:500;color:var(--md-sys-color-on-surface-variant);margin-bottom:6px;text-transform:uppercase;letter-spacing:.3px}
.editor-field input,.editor-field textarea{width:100%;padding:12px 16px;background:var(--md-sys-color-surface-container-highest);border:1px solid var(--md-sys-color-outline-variant);border-radius:var(--md-sys-shape-corner-medium);color:var(--md-sys-color-on-surface);font-size:.9rem;font-family:inherit;outline:none;transition:border-color .2s}
.editor-field input:focus,.editor-field textarea:focus{border-color:var(--md-sys-color-primary)}
.editor-field textarea{min-height:200px;resize:vertical}
.editor-mode-toggle{display:flex;gap:4px;margin-bottom:8px}
.editor-mode-toggle button{border:none;background:var(--md-sys-color-surface-container);color:var(--md-sys-color-on-surface-variant);padding:6px 14px;border-radius:16px;font-size:.8rem;cursor:pointer;transition:all .2s}
.editor-mode-toggle button.active{background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container);font-weight:500}
.editor-preview{background:var(--md-sys-color-surface-container);border:1px solid var(--md-sys-color-outline-variant);border-radius:var(--md-sys-shape-corner-medium);padding:16px;min-height:200px;line-height:1.7;display:none}
.editor-preview.show{display:block}
/* User profile page */
.user-profile-card{background:var(--md-sys-color-surface-container);border-radius:var(--md-sys-shape-corner-large);padding:32px;border:1px solid var(--md-sys-color-outline-variant);text-align:center}
.user-profile-avatar{width:96px;height:96px;border-radius:50%;background:var(--md-sys-color-primary-container);display:flex;align-items:center;justify-content:center;overflow:hidden;margin:0 auto 16px}
.user-profile-avatar img{width:100%;height:100%;object-fit:cover}
.user-profile-avatar .material-symbols-outlined{font-size:48px;color:var(--md-sys-color-on-primary-container)}
.user-profile-name{font-size:1.3rem;font-weight:500;color:var(--md-sys-color-on-surface);margin-bottom:4px}
.user-profile-username{font-size:.85rem;color:var(--md-sys-color-on-surface-variant);margin-bottom:12px}
.user-profile-bio{font-size:.9rem;color:var(--md-sys-color-on-surface);line-height:1.5;max-width:400px;margin:0 auto}
.user-profile-badges{display:flex;gap:8px;justify-content:center;margin-top:12px}
.user-profile-badge{padding:4px 12px;border-radius:12px;font-size:.75rem;background:var(--md-sys-color-surface-container-high);color:var(--md-sys-color-on-surface-variant)}
.back-btn{display:inline-flex;align-items:center;gap:4px;color:var(--md-sys-color-primary);font-size:.875rem;cursor:pointer;border:none;background:none;padding:8px 12px;border-radius:8px;margin-bottom:16px;transition:background .2s}
.back-btn:hover{background:var(--md-sys-color-surface-container-high)}
.device-card{background:var(--md-sys-color-surface-container);border-radius:var(--md-sys-shape-corner-large);padding:24px;margin-bottom:16px;border:1px solid var(--md-sys-color-outline-variant)}
.device-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.device-id{font-weight:500;font-size:1rem;color:var(--md-sys-color-on-surface)}
.status-badge{padding:4px 12px;border-radius:8px;font-size:.75rem;font-weight:500}
.status-bound{background:rgba(76,175,80,.15);color:#81C784}
.status-connected{background:rgba(255,167,38,.15);color:#FFB74D}
.status-disconnected{background:var(--md-sys-color-surface-container-highest);color:var(--md-sys-color-on-surface-variant)}
.channel-section{margin-bottom:20px}
.channel-label{font-size:.875rem;color:var(--md-sys-color-on-surface-variant);margin-bottom:8px;display:flex;justify-content:space-between;align-items:center}
.channel-name{font-weight:500;color:var(--md-sys-color-on-surface)}
.slider-row{display:flex;align-items:center;gap:12px}
.slider-row input[type=range]{flex:1;-webkit-appearance:none;appearance:none;height:4px;border-radius:2px;background:var(--md-sys-color-surface-container-highest);outline:none}
.slider-row input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:20px;height:20px;border-radius:50%;background:var(--md-sys-color-primary);cursor:pointer;box-shadow:0 1px 3px rgba(0,0,0,.3)}
.slider-row input[type=range]::-moz-range-thumb{width:20px;height:20px;border-radius:50%;background:var(--md-sys-color-primary);cursor:pointer;border:none}
.slider-value{min-width:36px;text-align:right;font-variant-numeric:tabular-nums;font-size:.875rem;color:var(--md-sys-color-on-surface-variant)}
.btn-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.md-btn{padding:10px 16px;border:none;border-radius:20px;cursor:pointer;font-size:.875rem;font-weight:500;letter-spacing:.1px;transition:all .2s;display:inline-flex;align-items:center;gap:6px}
.md-btn:hover{box-shadow:0 1px 3px rgba(0,0,0,.3)}
.md-btn:active{transform:scale(0.97)}
.md-btn-tonal{background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container)}
.md-btn-error{background:var(--md-sys-color-error-container);color:var(--md-sys-color-on-error)}
.md-btn-filled{background:var(--md-sys-color-primary);color:var(--md-sys-color-on-primary)}
.md-btn-outlined{background:transparent;color:var(--md-sys-color-primary);border:1px solid var(--md-sys-color-outline)}
.md-btn-text{background:transparent;color:var(--md-sys-color-primary);border:none}
.empty-state{text-align:center;padding:80px 24px}
.empty-icon{font-size:48px;color:var(--md-sys-color-on-surface-variant);margin-bottom:16px}
.empty-state .md-title-medium{margin-bottom:8px}
.md-snackbar{position:fixed;bottom:96px;left:50%;transform:translateX(-50%);background:var(--md-sys-color-inverse-surface);color:var(--md-sys-color-inverse-on-surface);padding:14px 24px;border-radius:var(--md-sys-shape-corner-medium);font-size:.875rem;opacity:0;transition:opacity .3s,bottom .3s;pointer-events:none;z-index:200;max-width:90vw;text-align:center;box-shadow:0 3px 5px rgba(0,0,0,.2)}
.md-snackbar.show{opacity:1}
.loading-overlay{position:fixed;inset:0;background:var(--md-sys-color-surface);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:9999;transition:opacity .4s cubic-bezier(0.2,0,0,1)}
.loading-overlay.fade-out{opacity:0;pointer-events:none}
.md-circular-progress{width:48px;height:48px;animation:rotate 1.4s linear infinite}
.md-circular-progress circle{stroke:var(--md-sys-color-primary);stroke-width:4;fill:none;stroke-linecap:round;stroke-dasharray:90,150;stroke-dashoffset:0;animation:dash 1.4s ease-in-out infinite}
@keyframes rotate{to{transform:rotate(360deg)}}
@keyframes dash{0%{stroke-dasharray:1,150;stroke-dashoffset:0}50%{stroke-dasharray:90,150;stroke-dashoffset:-35}100%{stroke-dasharray:90,150;stroke-dashoffset:-124}}
.loading-text{margin-top:16px;color:var(--md-sys-color-on-surface-variant);font-size:.875rem}
/* Auth pages */
.auth-container{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}
.auth-card{background:var(--md-sys-color-surface-container);border-radius:var(--md-sys-shape-corner-extra-large);padding:40px;width:100%;max-width:400px;border:1px solid var(--md-sys-color-outline-variant)}
.auth-header{text-align:center;margin-bottom:32px}
.auth-header .material-symbols-outlined{font-size:48px;color:var(--md-sys-color-primary);margin-bottom:12px}
.auth-header h1{font-size:1.5rem;font-weight:500;margin-bottom:4px}
.auth-header p{color:var(--md-sys-color-on-surface-variant);font-size:.875rem}
.md-text-field{position:relative;margin-bottom:20px}
.md-text-field input{width:100%;padding:16px;background:transparent;border:1px solid var(--md-sys-color-outline);border-radius:var(--md-sys-shape-corner-medium);color:var(--md-sys-color-on-surface);font-size:1rem;outline:none;transition:border-color .2s}
.md-text-field input:focus{border-color:var(--md-sys-color-primary);border-width:2px;padding:15px}
.md-text-field label{position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--md-sys-color-on-surface-variant);font-size:1rem;pointer-events:none;transition:all .2s;background:var(--md-sys-color-surface-container);padding:0 4px}
.md-text-field input:focus~label,.md-text-field input:not(:placeholder-shown)~label{top:0;font-size:.75rem;color:var(--md-sys-color-primary)}
.auth-actions{display:flex;flex-direction:column;gap:12px;margin-top:24px}
.auth-actions .md-btn{width:100%;justify-content:center;padding:14px}
.auth-switch{text-align:center;margin-top:16px;font-size:.875rem;color:var(--md-sys-color-on-surface-variant)}
.auth-switch a{color:var(--md-sys-color-primary);text-decoration:none;cursor:pointer;font-weight:500}
/* Owner tag */
.owner-tag{font-size:.75rem;padding:2px 8px;border-radius:4px;background:var(--md-sys-color-tertiary-container);color:var(--md-sys-color-on-tertiary-container);margin-left:8px}
/* Plaza */
.plaza-card{background:var(--md-sys-color-surface-container);border-radius:var(--md-sys-shape-corner-large);padding:20px;margin-bottom:12px;border:1px solid var(--md-sys-color-outline-variant);display:flex;justify-content:space-between;align-items:center}
.plaza-info{display:flex;align-items:center;gap:12px}
.plaza-avatar{width:40px;height:40px;border-radius:50%;background:var(--md-sys-color-primary-container);display:flex;align-items:center;justify-content:center}
.plaza-avatar .material-symbols-outlined{color:var(--md-sys-color-on-primary-container);font-size:20px}
/* Request cards */
.request-card{background:var(--md-sys-color-surface-container);border-radius:var(--md-sys-shape-corner-medium);padding:16px;margin-bottom:12px;border:1px solid var(--md-sys-color-outline-variant)}
.request-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.request-actions{display:flex;gap:8px;margin-top:12px}
/* Settings */
.settings-section{margin-bottom:24px}
.settings-item{display:flex;justify-content:space-between;align-items:center;padding:16px 0;border-bottom:1px solid var(--md-sys-color-outline-variant)}
.settings-item:last-child{border-bottom:none}
.settings-label{display:flex;flex-direction:column;gap:4px}
.md-switch{position:relative;width:52px;height:32px;cursor:pointer}
.md-switch input{opacity:0;width:0;height:0}
.md-switch .slider{position:absolute;inset:0;background:var(--md-sys-color-surface-container-highest);border:2px solid var(--md-sys-color-outline);border-radius:16px;transition:all .2s}
.md-switch .slider:before{content:'';position:absolute;width:16px;height:16px;left:6px;top:50%;transform:translateY(-50%);background:var(--md-sys-color-outline);border-radius:50%;transition:all .2s}
.md-switch input:checked+.slider{background:var(--md-sys-color-primary);border-color:var(--md-sys-color-primary)}
.md-switch input:checked+.slider:before{left:28px;background:var(--md-sys-color-on-primary);width:24px;height:24px}
/* Duration select dialog */
.md-dialog-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center;z-index:300;touch-action:none}
.md-dialog-overlay.show{display:flex}
.md-dialog{background:var(--md-sys-color-surface-container-high);border-radius:var(--md-sys-shape-corner-extra-large);padding:24px;width:90%;max-width:360px}
.md-dialog h3{margin-bottom:16px}
.md-dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:24px}
.duration-options{display:flex;flex-direction:column;gap:8px}
.duration-option{display:flex;align-items:center;gap:12px;padding:12px;border-radius:var(--md-sys-shape-corner-medium);cursor:pointer;transition:background .2s}
.duration-option:hover{background:var(--md-sys-color-surface-container-highest)}
.duration-option input[type=radio]{accent-color:var(--md-sys-color-primary);width:20px;height:20px}
.section-title{margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid var(--md-sys-color-outline-variant)}
/* Drawer (mobile only) */
.drawer-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:400;opacity:0;pointer-events:none;transition:opacity .25s cubic-bezier(0.2,0,0,1);touch-action:none}
.drawer-overlay.open{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;left:0;bottom:0;width:280px;background:var(--md-sys-color-surface-container);z-index:401;transform:translateX(-100%);transition:transform .3s cubic-bezier(0.2,0,0,1);display:flex;flex-direction:column;border-right:1px solid var(--md-sys-color-outline-variant)}
.drawer.open{transform:translateX(0)}
.drawer-header{display:flex;align-items:center;gap:12px;padding:24px 20px 16px;border-bottom:1px solid var(--md-sys-color-outline-variant)}
.drawer-nav{display:flex;flex-direction:column;padding:8px 12px;gap:2px;overflow-y:auto;flex:1}
.drawer-item{display:flex;align-items:center;gap:16px;padding:14px 16px;border:none;background:none;cursor:pointer;color:var(--md-sys-color-on-surface-variant);border-radius:var(--md-sys-shape-corner-large);font-size:.9rem;font-weight:500;transition:all .2s;text-align:left;width:100%}
.drawer-item:hover{background:var(--md-sys-color-surface-container-high)}
.drawer-item.active{background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container)}
.drawer-item.active .material-symbols-outlined{font-variation-settings:'FILL' 1}
.drawer-item .material-symbols-outlined{font-size:24px}
/* Top Bar */
.top-bar{position:fixed;top:0;left:0;right:0;height:56px;background:var(--md-sys-color-surface-container);border-bottom:1px solid var(--md-sys-color-outline-variant);display:flex;align-items:center;gap:12px;padding:0 8px;z-index:99}
.top-bar-btn{width:40px;height:40px;border:none;background:none;cursor:pointer;border-radius:50%;display:flex;align-items:center;justify-content:center;color:var(--md-sys-color-on-surface);transition:background .2s}
.top-bar-btn:hover{background:var(--md-sys-color-surface-container-high)}
.top-bar-title{font-size:1.1rem;font-weight:500;color:var(--md-sys-color-on-surface)}
/* Docs page */
.docs-layout{display:flex;flex-direction:column;gap:16px}
.docs-search-bar{display:flex;align-items:center;gap:10px;padding:10px 16px;background:var(--md-sys-color-surface-container-high);border:1px solid var(--md-sys-color-outline-variant);border-radius:28px;margin-bottom:8px;position:relative}
.docs-search-bar input{flex:1;border:none;background:none;color:var(--md-sys-color-on-surface);font-size:.9rem;outline:none}
.docs-search-bar .docs-search-clear{display:none;background:none;border:none;color:var(--md-sys-color-on-surface-variant);cursor:pointer;padding:4px;border-radius:50%;line-height:1}
.docs-search-bar .docs-search-clear:hover{background:var(--md-sys-color-surface-container-highest)}
.docs-search-bar .docs-search-clear.show{display:flex;align-items:center}
.docs-search-count{font-size:.75rem;color:var(--md-sys-color-on-surface-variant);margin-left:8px;white-space:nowrap}
.docs-container{display:flex;gap:24px;flex-direction:column}
.docs-toc{background:var(--md-sys-color-surface-container);border-radius:var(--md-sys-shape-corner-medium);padding:16px;border:1px solid var(--md-sys-color-outline-variant)}
.docs-toc-title{font-size:.75rem;font-weight:500;text-transform:uppercase;letter-spacing:.5px;color:var(--md-sys-color-on-surface-variant);padding:0 12px 8px;margin-bottom:4px;border-bottom:1px solid var(--md-sys-color-outline-variant)}
.docs-toc ul{list-style:none;padding:0;margin:0}
.docs-toc li{margin-bottom:2px}
.docs-toc a{display:block;padding:6px 12px;border-radius:8px;color:var(--md-sys-color-on-surface-variant);text-decoration:none;font-size:.85rem;transition:all .2s;cursor:pointer}
.docs-toc a:hover{background:var(--md-sys-color-surface-container-high);color:var(--md-sys-color-on-surface)}
.docs-toc a.active{background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container);font-weight:500}
.docs-toc a.has-match{color:var(--md-sys-color-primary)}
.docs-toc .toc-h1{font-weight:500;font-size:.85rem}
.docs-toc .toc-h2{padding-left:20px;font-size:.8rem}
.docs-toc .toc-h3{padding-left:36px;font-size:.75rem}
.docs-content{background:var(--md-sys-color-surface-container);border-radius:var(--md-sys-shape-corner-medium);padding:24px;border:1px solid var(--md-sys-color-outline-variant);line-height:1.7}
.docs-content h1{font-size:1.5rem;font-weight:500;margin:24px 0 12px;color:var(--md-sys-color-on-surface);padding-bottom:8px;border-bottom:1px solid var(--md-sys-color-outline-variant)}
.docs-content h1:first-child{margin-top:0}
.docs-content h2{font-size:1.2rem;font-weight:500;margin:20px 0 10px;color:var(--md-sys-color-on-surface)}
.docs-content h3{font-size:1rem;font-weight:500;margin:16px 0 8px;color:var(--md-sys-color-on-surface-variant)}
.docs-content p{margin:8px 0;color:var(--md-sys-color-on-surface)}
.docs-content ul,.docs-content ol{margin:8px 0;padding-left:24px}
.docs-content li{margin:4px 0;color:var(--md-sys-color-on-surface)}
.docs-content code{background:var(--md-sys-color-surface-container-highest);padding:2px 6px;border-radius:4px;font-size:.85rem;font-family:monospace;color:var(--md-sys-color-primary)}
.docs-content pre{background:var(--md-sys-color-surface-container-highest);padding:16px;border-radius:var(--md-sys-shape-corner-medium);overflow-x:auto;margin:12px 0}
.docs-content pre code{background:none;padding:0;font-size:.8rem;color:var(--md-sys-color-on-surface)}
.docs-content strong{color:var(--md-sys-color-primary);font-weight:500}
.docs-content mark{background:rgba(208,188,255,.3);color:var(--md-sys-color-on-surface);padding:1px 4px;border-radius:3px}
.docs-content blockquote{border-left:3px solid var(--md-sys-color-primary);margin:12px 0;padding:8px 16px;background:var(--md-sys-color-surface-container-high);border-radius:0 8px 8px 0}
.docs-content blockquote p{margin:4px 0;color:var(--md-sys-color-on-surface-variant)}
.docs-content table{width:100%;border-collapse:collapse;margin:12px 0;font-size:.85rem}
.docs-content th,.docs-content td{padding:8px 12px;border:1px solid var(--md-sys-color-outline-variant);text-align:left}
.docs-content th{background:var(--md-sys-color-surface-container-high);font-weight:500;color:var(--md-sys-color-on-surface)}
.docs-content td{color:var(--md-sys-color-on-surface)}
.docs-no-results{text-align:center;padding:40px;color:var(--md-sys-color-on-surface-variant)}
/* Chat page */
.chat-layout{display:flex;height:calc(100vh - 140px);gap:0;border:1px solid var(--md-sys-color-outline-variant);border-radius:var(--md-sys-shape-corner-large);overflow:hidden;background:var(--md-sys-color-surface-container)}
.chat-sidebar{width:320px;min-width:280px;display:flex;flex-direction:column;border-right:1px solid var(--md-sys-color-outline-variant);background:var(--md-sys-color-surface-container-low)}
.chat-sidebar-header{padding:12px}
.chat-search-bar{display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--md-sys-color-surface-container-high);border-radius:24px}
.chat-search-bar input{flex:1;border:none;background:none;color:var(--md-sys-color-on-surface);font-size:.85rem;outline:none}
.chat-tabs{display:flex;border-bottom:1px solid var(--md-sys-color-outline-variant);padding:0 8px}
.chat-tab{flex:1;padding:10px 0;border:none;background:none;color:var(--md-sys-color-on-surface-variant);font-size:.8rem;font-weight:500;cursor:pointer;border-bottom:2px solid transparent;transition:all .2s}
.chat-tab.active{color:var(--md-sys-color-primary);border-bottom-color:var(--md-sys-color-primary)}
.chat-tab-content{flex:1;overflow-y:auto;padding:8px}
.chat-empty{text-align:center;padding:40px 16px;color:var(--md-sys-color-on-surface-variant);font-size:.85rem}
.chat-empty p{margin-top:8px}
.chat-conv-item{display:flex;align-items:center;gap:12px;padding:12px;border-radius:var(--md-sys-shape-corner-medium);cursor:pointer;transition:background .2s}
.chat-conv-item:hover{background:var(--md-sys-color-surface-container-high)}
.chat-conv-item.active{background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container)}
.chat-conv-avatar{width:40px;height:40px;border-radius:50%;background:var(--md-sys-color-primary-container);display:flex;align-items:center;justify-content:center;flex-shrink:0;overflow:hidden}
.chat-conv-avatar .material-symbols-outlined{font-size:20px;color:var(--md-sys-color-on-primary-container)}
.chat-conv-avatar img{width:100%;height:100%;object-fit:cover}
.chat-conv-info{flex:1;min-width:0}
.chat-conv-name{font-size:.9rem;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-conv-last{font-size:.75rem;color:var(--md-sys-color-on-surface-variant);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
.chat-conv-meta{display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.chat-conv-time{font-size:.7rem;color:var(--md-sys-color-on-surface-variant)}
.chat-unread-badge{min-width:18px;height:18px;border-radius:9px;background:var(--md-sys-color-primary);color:var(--md-sys-color-on-primary);font-size:.7rem;font-weight:500;display:flex;align-items:center;justify-content:center;padding:0 5px}
.chat-friend-item{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:var(--md-sys-shape-corner-medium);cursor:pointer;transition:background .2s}
.chat-friend-item:hover{background:var(--md-sys-color-surface-container-high)}
.chat-search-result{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:var(--md-sys-shape-corner-medium)}
.chat-search-result .chat-conv-avatar{width:36px;height:36px}
.chat-search-result-info{flex:1;min-width:0}
.chat-search-result-name{font-size:.85rem;font-weight:500}
.chat-search-result-email{font-size:.75rem;color:var(--md-sys-color-on-surface-variant)}
.chat-notifications{border-top:1px solid var(--md-sys-color-outline-variant);padding:8px;max-height:200px;overflow-y:auto}
.chat-notif-header{display:flex;align-items:center;gap:6px;margin-bottom:8px}
.chat-notif-item{display:flex;align-items:center;gap:8px;padding:8px;background:var(--md-sys-color-surface-container-high);border-radius:8px;margin-bottom:6px;font-size:.8rem}
.chat-notif-item .md-btn{padding:4px 10px;font-size:.75rem}
.chat-main{flex:1;display:flex;flex-direction:column;min-width:0}
.chat-no-selection{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center}
.chat-conversation-view{flex:1;display:flex;flex-direction:column}
.chat-conv-header{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--md-sys-color-outline-variant);background:var(--md-sys-color-surface-container);min-height:52px}
.chat-conv-header-info{flex:1;min-width:0}
.chat-conv-header-name{font-size:.95rem;font-weight:500}
.chat-conv-header-status{font-size:.75rem;color:var(--md-sys-color-on-surface-variant)}
.chat-messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:8px}
.chat-msg{display:flex;gap:8px;max-width:75%}
.chat-msg.sent{align-self:flex-end;flex-direction:row-reverse}
.chat-msg.received{align-self:flex-start}
.chat-msg-avatar{width:32px;height:32px;border-radius:50%;background:var(--md-sys-color-primary-container);display:flex;align-items:center;justify-content:center;flex-shrink:0;overflow:hidden}
.chat-msg-avatar .material-symbols-outlined{font-size:16px;color:var(--md-sys-color-on-primary-container)}
.chat-msg-avatar img{width:100%;height:100%;object-fit:cover}
.chat-msg-bubble{padding:10px 14px;border-radius:16px;font-size:.875rem;line-height:1.5;word-break:break-word;position:relative}
.chat-msg.sent .chat-msg-bubble{background:var(--md-sys-color-primary);color:var(--md-sys-color-on-primary);border-bottom-right-radius:4px}
.chat-msg.received .chat-msg-bubble{background:var(--md-sys-color-surface-container-high);color:var(--md-sys-color-on-surface);border-bottom-left-radius:4px}
.chat-msg-time{font-size:.65rem;opacity:.7;margin-top:4px}
.chat-msg.sent .chat-msg-time{text-align:right}
.chat-msg-status{font-size:.65rem;opacity:.6}
.chat-msg-bubble strong{font-weight:600}
.chat-msg-bubble em{font-style:italic}
.chat-msg-bubble a{color:inherit;text-decoration:underline}
.chat-msg-file{display:flex;align-items:center;gap:8px;padding:4px 0}
.chat-msg-file-icon{font-size:24px}
.chat-msg-file-info{display:flex;flex-direction:column;gap:2px}
.chat-msg-file-name{font-size:.8rem;font-weight:500;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-msg-file-size{font-size:.7rem;opacity:.7}
.chat-msg-image{max-width:240px;max-height:200px;border-radius:8px;cursor:pointer;object-fit:cover}
.chat-msg-voice{display:flex;align-items:center;gap:8px;cursor:pointer;min-width:120px}
.chat-msg-voice-bar{display:flex;align-items:center;gap:2px;height:24px}
.chat-msg-voice-bar span{width:3px;background:currentColor;opacity:.5;border-radius:2px;animation:voiceBar .8s ease-in-out infinite}
.chat-msg-voice-duration{font-size:.75rem;opacity:.7}
@keyframes voiceBar{0%,100%{height:4px}50%{height:20px}}
.chat-input-area{display:flex;align-items:flex-end;gap:8px;padding:8px 12px;border-top:1px solid var(--md-sys-color-outline-variant);background:var(--md-sys-color-surface-container)}
.chat-input-btn{width:40px;height:40px;border:none;background:none;cursor:pointer;border-radius:50%;display:flex;align-items:center;justify-content:center;color:var(--md-sys-color-on-surface-variant);transition:background .2s}
.chat-input-btn:hover{background:var(--md-sys-color-surface-container-high)}
.chat-input-btn.recording{color:var(--md-sys-color-error);background:rgba(242,184,181,.15)}
.chat-input-field{flex:1;background:var(--md-sys-color-surface-container-high);border-radius:20px;padding:8px 16px;display:flex;align-items:center}
.chat-input-field textarea{flex:1;border:none;background:none;color:var(--md-sys-color-on-surface);font-size:.875rem;outline:none;resize:none;max-height:120px;line-height:1.4;font-family:inherit}
.chat-send-btn{width:40px;height:40px;border:none;background:var(--md-sys-color-primary);color:var(--md-sys-color-on-primary);cursor:pointer;border-radius:50%;display:flex;align-items:center;justify-content:center;transition:all .2s}
.chat-send-btn:hover{transform:scale(1.05)}
.chat-send-btn .material-symbols-outlined{font-size:20px}
.chat-upload-progress{position:absolute;bottom:60px;left:16px;right:16px;background:var(--md-sys-color-surface-container-high);border-radius:8px;padding:8px 12px;display:flex;align-items:center;gap:8px;font-size:.8rem}
.chat-upload-progress-bar{flex:1;height:4px;background:var(--md-sys-color-surface-container-highest);border-radius:2px;overflow:hidden}
.chat-upload-progress-fill{height:100%;background:var(--md-sys-color-primary);border-radius:2px;transition:width .3s}
/* Responsive */
@media(min-width:840px){
  .nav-rail{display:flex}
  .nav-bottom{display:none}
  .drawer-overlay,.drawer{display:none!important}
  .top-bar{left:80px}
  .main-content{padding:80px 48px 40px;padding-left:48px}
  .md-snackbar{bottom:32px}
  .page-header h1{font-size:2.8rem}
  .docs-container{flex-direction:row}
  .docs-toc{min-width:240px;max-width:260px;position:sticky;top:80px;align-self:flex-start;max-height:calc(100vh - 120px);overflow-y:auto;order:-1}
  .chat-layout{height:calc(100vh - 160px)}
}
/* Mobile (<=839px) */
@media(max-width:839px){
  .main-content{padding:68px 16px 96px;-webkit-overflow-scrolling:touch}
  .page-header{margin-bottom:20px}
  .page-header h1{font-size:1.6rem}
  .page-header p{font-size:.85rem}
  /* Touch targets: min 44px */
  .top-bar-btn{width:44px;height:44px}
  .nav-bottom{height:64px;padding-bottom:env(safe-area-inset-bottom,0)}
  .nav-bottom-item{min-width:48px;min-height:48px;padding:8px 0}
  .nav-bottom-item .material-symbols-outlined{width:48px;height:28px}
  .nav-bottom-item .nav-label{font-size:11px}
  .md-btn{min-height:44px;padding:10px 16px}
  .gender-option{min-height:44px;padding:10px 16px}
  .drawer-item{min-height:48px;padding:12px 16px}
  .duration-option{min-height:48px;padding:12px}
  /* Cards and layout */
  .md-card{padding:16px;margin-bottom:12px}
  .admin-user-card{padding:12px 16px;flex-direction:column;align-items:flex-start}
  .admin-user-info{min-width:0;width:100%}
  .admin-actions{width:100%;justify-content:flex-end}
  .admin-select{font-size:.8rem;padding:8px 10px}
  /* Settings */
  .settings-item{flex-wrap:wrap;gap:12px}
  .settings-label{flex:1;min-width:0}
  /* Profile */
  .profile-avatar-section{flex-direction:column;align-items:flex-start;gap:16px}
  .avatar-editor-container{height:250px}
  .avatar-editor-tools{gap:6px}
  .avatar-editor-tools .md-btn{padding:8px 12px;font-size:.8rem}
  /* Discover */
  .discover-controls{flex-direction:column;gap:10px}
  .discover-search{min-width:0;width:100%}
  .discover-sort{align-self:flex-start}
  .discover-sort button{padding:8px 14px;min-height:36px}
  .post-card{padding:14px 16px}
  .post-card-title{font-size:.95rem}
  .post-card-summary{font-size:.8rem}
  .post-card-footer{flex-wrap:wrap;gap:8px}
  .fab{bottom:76px;right:16px;width:52px;height:52px}
  /* Post detail */
  .post-detail-body{padding:16px;font-size:.9rem}
  .post-detail-meta{gap:8px;font-size:.8rem}
  /* Editor */
  .editor-field input,.editor-field textarea{padding:12px 14px;font-size:.9rem}
  .editor-field textarea{min-height:160px}
  .editor-preview{padding:12px;min-height:160px;font-size:.9rem}
  /* User profile */
  .user-profile-card{padding:24px 16px}
  /* Docs */
  .docs-content{font-size:.9rem;padding:16px}
  .docs-content pre{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}
  .docs-content table{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}
  .docs-content h1{font-size:1.3rem}
  .docs-content h2{font-size:1.1rem}
  .docs-content h3{font-size:1rem}
  .docs-toc{max-height:200px;overflow-y:auto}
  /* Dialog */
  .md-dialog{width:calc(100% - 32px);max-width:none;margin:16px}
  /* Snackbar */
  .md-snackbar{bottom:76px;left:16px;right:16px;transform:none;max-width:none}
  /* Auth */
  .auth-card{padding:24px 20px}
  .auth-container{padding:16px}
  /* Back button */
  .back-btn{min-height:44px;padding:10px 14px}
  /* Slider touch target */
  .slider-row input[type=range]::-webkit-slider-thumb{width:24px;height:24px}
  .slider-row input[type=range]::-moz-range-thumb{width:24px;height:24px}
  /* Device cards */
  .device-card{padding:16px}
  .device-header{flex-wrap:wrap;gap:8px}
  .btn-row{gap:6px}
  .btn-row .md-btn{padding:8px 12px;font-size:.8rem}
  .slider-row{gap:8px}
  /* Plaza cards */
  .plaza-card{padding:14px 16px;flex-wrap:wrap;gap:10px}
  .plaza-info{gap:10px}
  /* Request cards */
  .request-card{padding:14px 16px}
  .request-actions{flex-wrap:wrap}
  .request-actions .md-btn{flex:1;min-width:0;justify-content:center}
  .chat-layout{height:calc(100vh - 120px);flex-direction:column}
  .chat-sidebar{width:100%;min-width:0;border-right:none;border-bottom:1px solid var(--md-sys-color-outline-variant);max-height:45vh}
  .chat-main{min-height:0}
  .chat-msg{max-width:85%}
}
/* Prevent background scroll when overlay is open */
body.no-scroll .main-content{overflow:hidden!important}
/* Smooth scrolling for main content */
.main-content{scroll-behavior:smooth;overscroll-behavior-y:contain}
/* Ensure no horizontal overflow globally */
html,body{overflow-x:hidden;max-width:100vw}
.page{max-width:100%;overflow-x:hidden;word-break:break-word}
/* Safe area for notched devices */
@supports(padding-bottom:env(safe-area-inset-bottom)){
  .nav-bottom{padding-bottom:env(safe-area-inset-bottom)}
  .fab{bottom:calc(76px + env(safe-area-inset-bottom))}
  @media(min-width:840px){.fab{bottom:32px}}
}
</style>
<!-- PLACEHOLDER_BODY -->
</head>
<body>
<div class="loading-overlay" id="loading-overlay">
  <svg class="md-circular-progress" viewBox="0 0 48 48"><circle cx="24" cy="24" r="20"></circle></svg>
  <span class="loading-text">正在加载...</span>
</div>

<!-- Auth Pages -->
<div id="auth-view" style="display:none">
  <div class="auth-container">
    <div class="auth-card">
      <div class="auth-header">
        <span class="material-symbols-outlined">electric_bolt</span>
        <h1 id="auth-title">登录</h1>
        <p id="auth-subtitle">登录以使用 CurrentCortex</p>
      </div>
      <form id="auth-form" onsubmit="return handleAuth(event)">
        <div class="md-text-field" id="field-username">
          <input type="text" id="input-username" placeholder=" " required autocomplete="username">
          <label for="input-username">用户名</label>
        </div>
        <div class="md-text-field" id="field-email" style="display:none">
          <input type="email" id="input-email" placeholder=" " autocomplete="email">
          <label for="input-email">邮箱地址</label>
        </div>
        <div class="md-text-field" id="field-code" style="display:none">
          <div style="display:flex;gap:8px;align-items:center">
            <input type="text" id="input-code" placeholder=" " autocomplete="one-time-code" maxlength="6" style="flex:1">
            <label for="input-code" style="pointer-events:none">验证码</label>
          </div>
          <button type="button" class="md-btn md-btn-tonal" id="send-code-btn" onclick="sendVerificationCode()" style="position:absolute;right:8px;top:50%;transform:translateY(-50%);padding:6px 12px;font-size:.75rem;white-space:nowrap;z-index:1">发送验证码</button>
        </div>
        <div class="md-text-field">
          <input type="password" id="input-password" placeholder=" " required autocomplete="current-password">
          <label for="input-password">密码</label>
        </div>
        <div id="turnstile-widget" style="margin:12px 0;min-height:65px;display:none"></div>
        <div class="auth-actions">
          <button type="submit" class="md-btn md-btn-filled" id="auth-submit-btn">登录</button>
        </div>
      </form>
      <div class="auth-switch">
        <span id="auth-switch-text">还没有账号？</span>
        <a onclick="toggleAuthMode()"><span id="auth-switch-link">注册</span></a>
      </div>
    </div>
  </div>
</div>

<!-- App View (after login) -->
<div id="app-view" style="display:none">
  <div class="app-layout">
    <!-- Top Bar -->
    <header class="top-bar" id="top-bar">
      <button class="top-bar-btn" onclick="toggleDrawer()" aria-label="打开菜单">
        <span class="material-symbols-outlined">menu</span>
      </button>
      <span class="top-bar-title">CurrentCortex</span>
    </header>
    <nav class="nav-rail" aria-label="主导航">
      <div class="nav-rail-header">
        <span class="material-symbols-outlined nav-rail-logo">electric_bolt</span>
      </div>
      <div class="nav-rail-items">
        <button class="nav-rail-item active" data-page="devices" onclick="navigate('devices')">
          <span class="material-symbols-outlined">devices</span>
          <span class="nav-label">设备</span>
        </button>
        <button class="nav-rail-item" data-page="discover" onclick="navigate('discover')">
          <span class="material-symbols-outlined">public</span>
          <span class="nav-label">发现</span>
        </button>
        <button class="nav-rail-item" data-page="plaza" onclick="navigate('plaza')">
          <span class="material-symbols-outlined">explore</span>
          <span class="nav-label">广场</span>
        </button>
        <button class="nav-rail-item" data-page="requests" onclick="navigate('requests')">
          <span class="material-symbols-outlined">assignment</span>
          <span class="nav-label">申请</span>
        </button>
        <button class="nav-rail-item" data-page="chat" onclick="navigate('chat')">
          <span class="material-symbols-outlined">forum</span>
          <span class="nav-label">聊天</span>
        </button>
        <button class="nav-rail-item" data-page="profile" onclick="navigate('profile')">
          <span class="material-symbols-outlined">account_circle</span>
          <span class="nav-label">个人</span>
        </button>
        <button class="nav-rail-item" data-page="docs" onclick="navigate('docs')">
          <span class="material-symbols-outlined">menu_book</span>
          <span class="nav-label">文档</span>
        </button>
        <button class="nav-rail-item" data-page="settings" onclick="navigate('settings')">
          <span class="material-symbols-outlined">settings</span>
          <span class="nav-label">设置</span>
        </button>
        <button class="nav-rail-item" data-page="admin" onclick="navigate('admin')" id="nav-rail-admin">
          <span class="material-symbols-outlined">admin_panel_settings</span>
          <span class="nav-label">管理</span>
        </button>
      </div>
    </nav>
    <main class="main-content">
      <!-- PLACEHOLDER_PAGES -->
      <!-- Page: Devices -->
      <section class="page active" id="page-devices">
        <div class="page-header">
          <h1 class="md-display-medium">设备控制</h1>
          <p class="md-body-large on-surface-variant">管理和控制已绑定的设备</p>
        </div>
        <div id="device-list"></div>
        <div id="no-devices" class="empty-state" style="display:none">
          <span class="material-symbols-outlined empty-icon">devices_off</span>
          <p class="md-title-medium">暂无已绑定设备</p>
          <p class="md-body-medium on-surface-variant">请在聊天中发送 <strong>/dglab bind</strong> 指令来绑定设备</p>
        </div>
      </section>

      <!-- Page: Plaza -->
      <section class="page" id="page-plaza">
        <div class="page-header">
          <h1 class="md-display-medium">设备广场</h1>
          <p class="md-body-large on-surface-variant">发现公开设备并申请控制权限</p>
        </div>
        <div id="plaza-list"></div>
        <div id="no-plaza" class="empty-state" style="display:none">
          <span class="material-symbols-outlined empty-icon">explore_off</span>
          <p class="md-title-medium">暂无公开设备</p>
          <p class="md-body-medium on-surface-variant">当前没有用户公开了设备</p>
        </div>
      </section>

      <!-- Page: Requests -->
      <section class="page" id="page-requests">
        <div class="page-header">
          <h1 class="md-display-medium">申请管理</h1>
          <p class="md-body-large on-surface-variant">管理收到的控制申请和已授权的权限</p>
        </div>
        <h2 class="md-headline-small section-title">待处理申请</h2>
        <div id="pending-list"></div>
        <div id="no-pending" class="empty-state" style="display:none;padding:40px 24px">
          <span class="material-symbols-outlined empty-icon">inbox</span>
          <p class="md-body-medium on-surface-variant">暂无待处理的申请</p>
        </div>
        <h2 class="md-headline-small section-title" style="margin-top:32px">已授权权限</h2>
        <div id="granted-list"></div>
        <div id="no-granted" class="empty-state" style="display:none;padding:40px 24px">
          <span class="material-symbols-outlined empty-icon">shield</span>
          <p class="md-body-medium on-surface-variant">暂无已授权的权限</p>
        </div>
      </section>

      <!-- Page: Chat -->
      <section class="page" id="page-chat">
        <div class="page-header">
          <h1 class="md-display-medium">网络聊天</h1>
          <p class="md-body-large on-surface-variant">与好友和群组实时通讯</p>
        </div>
        <div class="chat-layout">
          <!-- Chat Sidebar -->
          <div class="chat-sidebar" id="chat-sidebar">
            <div class="chat-sidebar-header">
              <div class="chat-search-bar">
                <span class="material-symbols-outlined" style="font-size:20px;color:var(--md-sys-color-on-surface-variant)">search</span>
                <label for="chat-search-users" class="sr-only">搜索用户</label>
                <input type="text" id="chat-search-users" placeholder="搜索用户..." oninput="searchChatUsers()">
              </div>
            </div>
            <div id="chat-search-results" style="display:none"></div>
            <div class="chat-tabs">
              <button class="chat-tab active" data-tab="conversations" onclick="switchChatTab('conversations')">会话</button>
              <button class="chat-tab" data-tab="friends" onclick="switchChatTab('friends')">好友</button>
              <button class="chat-tab" data-tab="groups" onclick="switchChatTab('groups')">群组</button>
            </div>
            <div class="chat-tab-content" id="chat-tab-conversations">
              <div id="chat-conversation-list"></div>
              <div id="no-conversations" class="chat-empty" style="display:none">
                <span class="material-symbols-outlined" style="font-size:36px;color:var(--md-sys-color-on-surface-variant)">chat_bubble_outline</span>
                <p>暂无会话</p>
              </div>
            </div>
            <div class="chat-tab-content" id="chat-tab-friends" style="display:none">
              <div id="chat-friend-list"></div>
              <div id="no-friends" class="chat-empty" style="display:none">
                <span class="material-symbols-outlined" style="font-size:36px;color:var(--md-sys-color-on-surface-variant)">person_add</span>
                <p>暂无好友</p>
              </div>
            </div>
            <div class="chat-tab-content" id="chat-tab-groups" style="display:none">
              <button class="md-btn md-btn-tonal" style="width:100%;margin-bottom:12px" onclick="showCreateGroupDialog()">
                <span class="material-symbols-outlined" style="font-size:18px">group_add</span>创建群组
              </button>
              <div id="chat-group-list"></div>
              <div id="no-groups" class="chat-empty" style="display:none">
                <span class="material-symbols-outlined" style="font-size:36px;color:var(--md-sys-color-on-surface-variant)">groups</span>
                <p>暂无群组</p>
              </div>
            </div>
            <!-- Friend requests & group invites notification -->
            <div class="chat-notifications" id="chat-notifications" style="display:none">
              <div class="chat-notif-header">
                <span class="material-symbols-outlined" style="font-size:18px;color:var(--md-sys-color-primary)">notifications</span>
                <span class="md-body-medium" style="font-weight:500">消息通知</span>
              </div>
              <div id="chat-friend-requests"></div>
              <div id="chat-group-invites"></div>
            </div>
          </div>
          <!-- Chat Main Area -->
          <div class="chat-main" id="chat-main">
            <div class="chat-no-selection" id="chat-no-selection">
              <span class="material-symbols-outlined" style="font-size:64px;color:var(--md-sys-color-on-surface-variant)">forum</span>
              <p class="md-title-medium" style="margin-top:16px;color:var(--md-sys-color-on-surface-variant)">选择一个会话开始聊天</p>
            </div>
            <div class="chat-conversation-view" id="chat-conversation-view" style="display:none">
              <div class="chat-conv-header" id="chat-conv-header">
                <button class="top-bar-btn" id="chat-back-btn" onclick="closeChatConversation()" style="display:none">
                  <span class="material-symbols-outlined">arrow_back</span>
                </button>
                <div class="chat-conv-header-info" id="chat-conv-header-info"></div>
                <div class="chat-conv-header-actions">
                  <button class="top-bar-btn" onclick="showConvInfoDialog()" title="会话信息">
                    <span class="material-symbols-outlined">more_vert</span>
                  </button>
                </div>
              </div>
              <div class="chat-messages" id="chat-messages"></div>
              <div class="chat-input-area">
                <button class="chat-input-btn" onclick="triggerFileUpload()" title="发送文件">
                  <span class="material-symbols-outlined">attach_file</span>
                </button>
                <label for="chat-file-input" class="sr-only">上传文件</label>
                <input type="file" id="chat-file-input" style="display:none" multiple onchange="onChatFileSelected(event)">
                <button class="chat-input-btn" id="chat-voice-btn" onmousedown="startVoiceRecording()" onmouseup="stopVoiceRecording()" ontouchstart="startVoiceRecording()" ontouchend="stopVoiceRecording()" title="按住录音">
                  <span class="material-symbols-outlined">mic</span>
                </button>
                <div class="chat-input-field">
                  <label for="chat-input" class="sr-only">输入消息</label>
                <textarea id="chat-input" placeholder="输入消息..." rows="1" onkeydown="handleChatInputKey(event)" oninput="autoResizeChatInput()"></textarea>
                </div>
                <button class="chat-send-btn" onclick="sendChatMessage()" title="发送">
                  <span class="material-symbols-outlined">send</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Page: Settings -->
      <section class="page" id="page-settings">
        <div class="page-header">
          <h1 class="md-display-medium">设置</h1>
          <p class="md-body-large on-surface-variant">管理账号和设备共享偏好</p>
        </div>
        <div class="md-card md-card-outlined settings-section">
          <h3 class="md-title-medium" style="margin-bottom:12px">用户信息</h3>
          <div class="settings-item">
            <div class="settings-label"><span class="md-body-large">用户名</span></div>
            <span class="md-body-large on-surface-variant" id="settings-username">-</span>
          </div>
          <div class="settings-item">
            <div class="settings-label"><span class="md-body-large">邮箱</span></div>
            <span class="md-body-large on-surface-variant" id="settings-email">-</span>
          </div>
        </div>
        <div class="md-card md-card-outlined settings-section">
          <h3 class="md-title-medium" style="margin-bottom:12px">设备共享</h3>
          <div class="settings-item">
            <div class="settings-label">
              <span class="md-body-large">公开设备到广场</span>
              <span class="md-body-medium on-surface-variant">其他用户可以在广场看到你的设备</span>
            </div>
            <label class="md-switch"><input type="checkbox" id="switch-public" onchange="saveSettings()"><span class="slider"></span></label>
          </div>
          <div class="settings-item">
            <div class="settings-label">
              <span class="md-body-large">接受控制申请</span>
              <span class="md-body-medium on-surface-variant">允许其他用户向你发送控制申请</span>
            </div>
            <label class="md-switch"><input type="checkbox" id="switch-requests" onchange="saveSettings()"><span class="slider"></span></label>
          </div>
        </div>
        <button class="md-btn md-btn-error" onclick="logout()" style="margin-top:16px">
          <span class="material-symbols-outlined" style="font-size:18px">logout</span>退出登录
        </button>
      </section>

      <!-- Page: Admin -->
      <section class="page" id="page-admin">
        <div class="page-header">
          <h1 class="md-display-medium">后台管理</h1>
          <p class="md-body-large on-surface-variant">管理系统用户和角色</p>
        </div>
        <div class="md-card md-card-outlined" style="margin-bottom:16px;padding:16px 24px">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
            <span class="material-symbols-outlined" style="color:var(--md-sys-color-primary)">search</span>
            <label for="admin-search" class="sr-only">搜索用户</label>
            <input type="text" id="admin-search" placeholder="搜索用户名、邮箱..." oninput="filterAdminUsers()" style="flex:1;min-width:200px;padding:10px 16px;background:var(--md-sys-color-surface-container-highest);border:1px solid var(--md-sys-color-outline-variant);border-radius:20px;color:var(--md-sys-color-on-surface);font-size:.875rem;outline:none">
          </div>
        </div>
        <div id="admin-user-list"></div>
        <div id="no-admin-users" class="empty-state" style="display:none">
          <span class="material-symbols-outlined empty-icon">group_off</span>
          <p class="md-title-medium">暂无用户</p>
        </div>
        <h2 class="md-headline-small section-title" style="margin-top:32px">邮件配置 (SMTP)</h2>
        <div class="md-card md-card-outlined" style="margin-bottom:16px;padding:20px 24px">
          <div class="md-text-field" style="margin-bottom:16px">
            <input type="text" id="smtp-host" placeholder=" ">
            <label for="smtp-host">SMTP 服务器地址</label>
          </div>
          <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
            <div class="md-text-field" style="flex:1;min-width:120px">
              <input type="number" id="smtp-port" placeholder=" " value="587">
              <label for="smtp-port">端口号</label>
            </div>
            <div class="md-text-field" style="flex:1;min-width:120px">
              <label for="smtp-encryption" class="sr-only">加密方式</label>
              <select id="smtp-encryption" style="width:100%;padding:16px;background:transparent;border:1px solid var(--md-sys-color-outline);border-radius:var(--md-sys-shape-corner-medium);color:var(--md-sys-color-on-surface);font-size:1rem;outline:none">
                <option value="none">无加密</option>
                <option value="tls" selected>TLS</option>
                <option value="ssl">SSL</option>
              </select>
            </div>
          </div>
          <div class="md-text-field" style="margin-bottom:16px">
            <input type="text" id="smtp-username" placeholder=" ">
            <label for="smtp-username">发信邮箱账号</label>
          </div>
          <div class="md-text-field" style="margin-bottom:16px">
            <input type="password" id="smtp-password" placeholder=" ">
            <label for="smtp-password">密码/授权码</label>
            <button type="button" class="md-btn md-btn-text" onclick="toggleSmtpPasswordVisibility()" style="position:absolute;right:8px;top:50%;transform:translateY(-50%);padding:4px 8px;z-index:1">
              <span class="material-symbols-outlined" style="font-size:18px" id="smtp-pw-toggle-icon">visibility</span>
            </button>
          </div>
          <div class="md-text-field" style="margin-bottom:20px">
            <input type="email" id="smtp-from-email" placeholder=" ">
            <label for="smtp-from-email">发件人邮箱</label>
          </div>
          <div style="display:flex;gap:12px;flex-wrap:wrap">
            <button class="md-btn md-btn-outlined" onclick="testSmtpConnection()">
              <span class="material-symbols-outlined" style="font-size:18px">network_check</span>测试连接
            </button>
            <button class="md-btn md-btn-filled" onclick="saveSmtpConfig()">
              <span class="material-symbols-outlined" style="font-size:18px">save</span>保存配置
            </button>
          </div>
        </div>
        <h2 class="md-headline-small section-title" style="margin-top:32px">人机验证 (Cloudflare Turnstile)</h2>
        <div class="md-card md-card-outlined" style="margin-bottom:16px;padding:20px 24px">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
            <label class="md-switch">
              <input type="checkbox" id="turnstile-enabled" onchange="toggleTurnstileEnabled()">
              <span class="slider"></span>
            </label>
            <span class="md-body-large">启用 Turnstile 人机验证</span>
          </div>
          <div class="md-text-field" style="margin-bottom:16px">
            <input type="text" id="turnstile-site-key" placeholder=" ">
            <label for="turnstile-site-key">Site Key (客户端密钥)</label>
          </div>
          <div class="md-text-field" style="margin-bottom:20px">
            <input type="password" id="turnstile-secret-key" placeholder=" ">
            <label for="turnstile-secret-key">Secret Key (服务端密钥)</label>
            <button type="button" class="md-btn md-btn-text" onclick="toggleTurnstileSecretVisibility()" style="position:absolute;right:8px;top:50%;transform:translateY(-50%);padding:4px 8px;z-index:1">
              <span class="material-symbols-outlined" style="font-size:18px" id="turnstile-pw-toggle-icon">visibility</span>
            </button>
          </div>
          <div style="display:flex;gap:12px;flex-wrap:wrap">
            <button class="md-btn md-btn-filled" onclick="saveTurnstileConfig()">
              <span class="material-symbols-outlined" style="font-size:18px">save</span>保存配置
            </button>
          </div>
        </div>
      </section>

      <!-- Page: Profile -->
      <section class="page" id="page-profile">
        <div class="page-header">
          <h1 class="md-display-medium">个人中心</h1>
          <p class="md-body-large on-surface-variant">管理你的个人资料</p>
        </div>
        <div class="md-card md-card-outlined settings-section">
          <div class="profile-avatar-section">
            <div class="profile-avatar" id="profile-avatar-preview">
              <span class="material-symbols-outlined">person</span>
            </div>
            <div style="display:flex;flex-direction:column;gap:8px">
              <button class="md-btn md-btn-tonal" onclick="document.getElementById('avatar-file-input').click()">
                <span class="material-symbols-outlined" style="font-size:18px">upload</span>上传头像
              </button>
              <label for="avatar-file-input" class="sr-only">上传头像</label>
              <input type="file" id="avatar-file-input" accept="image/png,image/jpeg,image/webp" style="display:none" onchange="onAvatarFileSelected(event)">
              <span class="md-body-medium on-surface-variant">支持 JPG、PNG、WebP，最大 2MB</span>
            </div>
          </div>
          <div class="md-text-field" style="margin-top:20px">
            <input type="text" id="input-nickname" placeholder=" " maxlength="30">
            <label for="input-nickname">昵称</label>
          </div>
          <div style="margin-top:20px">
            <span class="md-body-medium on-surface-variant" style="display:block;margin-bottom:10px">性别</span>
            <div class="gender-options">
              <label class="gender-option"><input type="radio" name="gender" value=""><span>不设置</span></label>
              <label class="gender-option"><input type="radio" name="gender" value="male"><span>男</span></label>
              <label class="gender-option"><input type="radio" name="gender" value="female"><span>女</span></label>
              <label class="gender-option"><input type="radio" name="gender" value="other"><span>其他</span></label>
            </div>
          </div>
          <div class="md-text-field" style="margin-top:20px">
            <input type="text" id="input-bio" placeholder=" " maxlength="200">
            <label for="input-bio">个人简介</label>
          </div>
          <div style="margin-top:24px">
            <button class="md-btn md-btn-filled" onclick="saveProfile()">
              <span class="material-symbols-outlined" style="font-size:18px">save</span>保存资料
            </button>
          </div>
        </div>
      </section>

      <!-- Page: Discover (list) -->
      <section class="page" id="page-discover">
        <div class="page-header">
          <h1 class="md-display-medium">发现</h1>
          <p class="md-body-large on-surface-variant">浏览社区帖子</p>
        </div>
        <div class="discover-controls">
          <div class="discover-search">
            <span class="material-symbols-outlined" style="font-size:20px;color:var(--md-sys-color-on-surface-variant)">search</span>
            <label for="discover-search-input" class="sr-only">搜索帖子</label>
            <input type="text" id="discover-search-input" placeholder="搜索帖子..." oninput="searchPostsDebounced()">
          </div>
          <div class="discover-sort">
            <button class="active" data-sort="newest" onclick="setPostSort('newest')">最新</button>
            <button data-sort="popular" onclick="setPostSort('popular')">最热</button>
            <button data-sort="oldest" onclick="setPostSort('oldest')">最早</button>
          </div>
        </div>
        <div id="posts-list"></div>
        <div id="no-posts" class="empty-state" style="display:none">
          <span class="material-symbols-outlined empty-icon">article</span>
          <p class="md-title-medium">暂无帖子</p>
          <p class="md-body-medium on-surface-variant">成为第一个发帖的人吧</p>
        </div>
      </section>

      <!-- Page: Post Detail -->
      <section class="page" id="page-post-detail" style="display:none">
        <button class="back-btn" onclick="navigate('discover')">
          <span class="material-symbols-outlined" style="font-size:18px">arrow_back</span>返回发现
        </button>
        <div id="post-detail-content"></div>
      </section>

      <!-- Page: Post Editor -->
      <section class="page" id="page-post-editor" style="display:none">
        <button class="back-btn" onclick="navigate('discover')">
          <span class="material-symbols-outlined" style="font-size:18px">arrow_back</span>返回发现
        </button>
        <div class="page-header" style="margin-bottom:20px">
          <h1 class="md-display-medium" style="font-size:1.5rem">发布帖子</h1>
        </div>
        <div class="editor-field">
          <label for="editor-title">标题</label>
          <input type="text" id="editor-title" placeholder="输入帖子标题..." maxlength="100">
        </div>
        <div class="editor-field">
          <label for="editor-summary">简介</label>
          <input type="text" id="editor-summary" placeholder="一句话描述帖子内容..." maxlength="300">
        </div>
        <div class="editor-field">
          <label for="editor-content">正文</label>
          <div class="editor-mode-toggle">
            <button class="active" id="editor-mode-text" onclick="setEditorMode('text')">纯文本</button>
            <button id="editor-mode-md" onclick="setEditorMode('markdown')">Markdown</button>
          </div>
          <textarea id="editor-content" placeholder="输入正文内容..." oninput="updateEditorPreview()"></textarea>
          <div class="editor-preview docs-content" id="editor-preview"></div>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:12px;margin-top:16px">
          <button class="md-btn md-btn-text" onclick="navigate('discover')">取消</button>
          <button class="md-btn md-btn-filled" onclick="submitPost()">
            <span class="material-symbols-outlined" style="font-size:18px">send</span>发布
          </button>
        </div>
      </section>

      <!-- Page: User Profile -->
      <section class="page" id="page-user-profile" style="display:none">
        <button class="back-btn" id="user-profile-back" onclick="navigate('discover')">
          <span class="material-symbols-outlined" style="font-size:18px">arrow_back</span>返回
        </button>
        <div id="user-profile-content"></div>
      </section>

      <!-- Page: Docs -->
      <section class="page" id="page-docs">
        <div class="page-header">
          <h1 class="md-display-medium">文档中心</h1>
          <p class="md-body-large on-surface-variant">设备与插件使用指南</p>
        </div>
        <div class="docs-layout">
          <div class="docs-search-bar">
            <span class="material-symbols-outlined" style="color:var(--md-sys-color-primary)">search</span>
            <label for="docs-search" class="sr-only">搜索文档</label>
            <input type="text" id="docs-search" placeholder="搜索文档内容..." oninput="searchDocs()">
            <span class="docs-search-count" id="docs-search-count"></span>
            <button class="docs-search-clear" id="docs-search-clear" onclick="clearDocsSearch()">
              <span class="material-symbols-outlined" style="font-size:18px">close</span>
            </button>
          </div>
          <div class="docs-container">
            <article class="docs-content" id="docs-content"></article>
            <aside class="docs-toc" id="docs-toc"></aside>
          </div>
        </div>
      </section>
    </main>
    <button class="fab" id="fab-new-post" onclick="navigateToNewPost()" title="发布帖子" style="display:none">
      <span class="material-symbols-outlined" style="font-size:28px">add</span>
    </button>
    <nav class="nav-bottom" aria-label="主导航">
      <button class="nav-bottom-item active" data-page="devices" onclick="navigate('devices')">
        <span class="material-symbols-outlined">devices</span>
        <span class="nav-label">设备</span>
      </button>
      <button class="nav-bottom-item" data-page="discover" onclick="navigate('discover')">
        <span class="material-symbols-outlined">public</span>
        <span class="nav-label">发现</span>
      </button>
      <button class="nav-bottom-item" data-page="plaza" onclick="navigate('plaza')">
        <span class="material-symbols-outlined">explore</span>
        <span class="nav-label">广场</span>
      </button>
      <button class="nav-bottom-item" data-page="chat" onclick="navigate('chat')">
        <span class="material-symbols-outlined">forum</span>
        <span class="nav-label">聊天</span>
      </button>
      <button class="nav-bottom-item" data-page="profile" onclick="navigate('profile')">
        <span class="material-symbols-outlined">account_circle</span>
        <span class="nav-label">个人</span>
      </button>
    </nav>
  </div>
</div>

<!-- Mobile Drawer -->
<div class="drawer-overlay" id="drawer-overlay" onclick="closeDrawer()"></div>
<aside class="drawer" id="drawer">
  <div class="drawer-header">
    <span class="material-symbols-outlined" style="color:var(--md-sys-color-primary);font-size:28px">electric_bolt</span>
    <span class="md-title-medium">CurrentCortex</span>
  </div>
  <nav class="drawer-nav">
    <button class="drawer-item" data-page="devices" onclick="navigateFromDrawer('devices')">
      <span class="material-symbols-outlined">devices</span><span>设备控制</span>
    </button>
    <button class="drawer-item" data-page="discover" onclick="navigateFromDrawer('discover')">
      <span class="material-symbols-outlined">public</span><span>发现</span>
    </button>
    <button class="drawer-item" data-page="plaza" onclick="navigateFromDrawer('plaza')">
      <span class="material-symbols-outlined">explore</span><span>设备广场</span>
    </button>
    <button class="drawer-item" data-page="requests" onclick="navigateFromDrawer('requests')">
      <span class="material-symbols-outlined">assignment</span><span>申请管理</span>
    </button>
    <button class="drawer-item" data-page="chat" onclick="navigateFromDrawer('chat')">
      <span class="material-symbols-outlined">forum</span><span>网络聊天</span>
    </button>
    <button class="drawer-item" data-page="profile" onclick="navigateFromDrawer('profile')">
      <span class="material-symbols-outlined">account_circle</span><span>个人中心</span>
    </button>
    <button class="drawer-item" data-page="settings" onclick="navigateFromDrawer('settings')">
      <span class="material-symbols-outlined">settings</span><span>设置</span>
    </button>
    <button class="drawer-item" data-page="docs" onclick="navigateFromDrawer('docs')">
      <span class="material-symbols-outlined">menu_book</span><span>文档中心</span>
    </button>
    <button class="drawer-item" data-page="admin" onclick="navigateFromDrawer('admin')">
      <span class="material-symbols-outlined">admin_panel_settings</span><span>后台管理</span>
    </button>
  </nav>
</aside>

<!-- Duration Dialog -->
<div class="md-dialog-overlay" id="duration-dialog">
  <div class="md-dialog">
    <h3 class="md-title-medium">选择授权时长</h3>
    <div class="duration-options">
      <label class="duration-option"><input type="radio" name="duration" value="1h" checked><span>1 小时</span></label>
      <label class="duration-option"><input type="radio" name="duration" value="1d"><span>1 天</span></label>
      <label class="duration-option"><input type="radio" name="duration" value="7d"><span>7 天</span></label>
      <label class="duration-option"><input type="radio" name="duration" value="30d"><span>30 天</span></label>
      <label class="duration-option"><input type="radio" name="duration" value="permanent"><span>永久</span></label>
    </div>
    <div class="md-dialog-actions">
      <button class="md-btn md-btn-text" onclick="closeDurationDialog()">取消</button>
      <button class="md-btn md-btn-filled" onclick="confirmApprove()">确认</button>
    </div>
  </div>
</div>

<div class="md-snackbar" id="snackbar"></div>

<!-- Avatar Editor Dialog -->
<div class="md-dialog-overlay" id="avatar-editor-dialog">
  <div class="md-dialog" style="max-width:500px;width:95%">
    <h3 class="md-title-medium">编辑头像</h3>
    <div class="avatar-editor-container">
      <canvas id="avatar-editor-canvas"></canvas>
    </div>
    <div class="avatar-editor-tools">
      <button class="md-btn md-btn-tonal" onclick="avatarEditorRotate(-90)" title="逆时针旋转">
        <span class="material-symbols-outlined" style="font-size:18px">rotate_left</span>
      </button>
      <button class="md-btn md-btn-tonal" onclick="avatarEditorRotate(90)" title="顺时针旋转">
        <span class="material-symbols-outlined" style="font-size:18px">rotate_right</span>
      </button>
      <button class="md-btn md-btn-tonal" onclick="avatarEditorZoom(1.2)" title="放大">
        <span class="material-symbols-outlined" style="font-size:18px">zoom_in</span>
      </button>
      <button class="md-btn md-btn-tonal" onclick="avatarEditorZoom(0.8)" title="缩小">
        <span class="material-symbols-outlined" style="font-size:18px">zoom_out</span>
      </button>
      <button class="md-btn md-btn-tonal" onclick="avatarEditorReset()" title="重置">
        <span class="material-symbols-outlined" style="font-size:18px">restart_alt</span>
      </button>
    </div>
    <p class="md-body-medium on-surface-variant" style="text-align:center;margin-top:8px">拖拽移动图片，圆形区域为最终裁剪范围</p>
    <div class="md-dialog-actions">
      <button class="md-btn md-btn-text" onclick="closeAvatarEditor()">取消</button>
      <button class="md-btn md-btn-filled" onclick="confirmAvatarEdit()">确认保存</button>
    </div>
  </div>
</div>

<!-- PLACEHOLDER_PAGES_CONTENT -->
<script>
const PRESETS=[
  {id:'breathe',name:'呼吸',icon:'air'},
  {id:'pulse',name:'脉冲',icon:'electric_bolt'},
  {id:'wave',name:'波浪',icon:'waves'},
  {id:'tap',name:'敲击',icon:'touch_app'},
  {id:'storm',name:'风暴',icon:'thunderstorm'}
];
let currentPage='devices';
let isTransitioning=false;
let isRegisterMode=false;
let snackTimer=null;
let devices=[];
let pendingApproveId=null;
let currentUser=null;
let refreshInterval=null;

function getToken(){return localStorage.getItem('dglab_token')}
function setToken(t){localStorage.setItem('dglab_token',t)}
function clearToken(){localStorage.removeItem('dglab_token')}

function showSnackbar(msg){
  const s=document.getElementById('snackbar');
  s.textContent=msg;s.classList.add('show');
  clearTimeout(snackTimer);
  snackTimer=setTimeout(()=>s.classList.remove('show'),3000);
}

async function api(method,path,body){
  const opts={method,headers:{'Content-Type':'application/json'}};
  const token=getToken();
  if(token)opts.headers['Authorization']='Bearer '+token;
  if(body)opts.body=JSON.stringify(body);
  try{
    const r=await fetch(path,opts);
    if(r.status===401){clearToken();history.pushState({page:'login'},'','/login');showAuthView('login');return null;}
    const data=await r.json();
    if(!r.ok){showSnackbar(data.error||'请求失败');return null;}
    return data;
  }catch(e){showSnackbar('网络错误');return null;}
}

// --- Auth ---
async function showAuthView(route){
  document.getElementById('auth-view').style.display='';
  document.getElementById('app-view').style.display='none';
  if(refreshInterval){clearInterval(refreshInterval);refreshInterval=null;}
  if(route==='register'){
    if(!isRegisterMode)toggleAuthMode(true);
  }else{
    if(isRegisterMode)toggleAuthMode(true);
  }
  // Load Turnstile config and init widget if enabled
  const tsConfig=await api('GET','/api/turnstile/config');
  if(tsConfig&&tsConfig.enabled&&tsConfig.site_key){
    turnstileSiteKey=tsConfig.site_key;
    await initTurnstileWidget();
  }else{
    turnstileSiteKey='';
    const container=document.getElementById('turnstile-widget');
    if(container){container.style.display='none';container.innerHTML='';}
  }
}
function showAppView(initialPage,extra){
  document.getElementById('auth-view').style.display='none';
  document.getElementById('app-view').style.display='';
  loadSettings();
  refreshInterval=setInterval(()=>{if(currentPage==='devices')loadDevices();},2000);
  if(initialPage&&initialPage!==currentPage){
    navigateTo(initialPage,false,extra||null);
  }else{
    loadDevices();
  }
}
function toggleAuthMode(skipPush){
  isRegisterMode=!isRegisterMode;
  document.getElementById('auth-title').textContent=isRegisterMode?'注册':'登录';
  document.getElementById('auth-subtitle').textContent=isRegisterMode?'创建账号以使用 CurrentCortex':'登录以使用 CurrentCortex';
  document.getElementById('auth-submit-btn').textContent=isRegisterMode?'注册':'登录';
  document.getElementById('auth-switch-text').textContent=isRegisterMode?'已有账号？':'还没有账号？';
  document.getElementById('auth-switch-link').textContent=isRegisterMode?'登录':'注册';
  document.getElementById('field-email').style.display=isRegisterMode?'':'none';
  document.getElementById('field-code').style.display=isRegisterMode?'':'none';
  if(isRegisterMode){
    document.getElementById('input-email').required=true;
    document.getElementById('input-code').required=true;
  }else{
    document.getElementById('input-email').required=false;
    document.getElementById('input-code').required=false;
  }
  if(!skipPush){
    history.pushState({page:isRegisterMode?'register':'login'},'',(isRegisterMode?'/register':'/login'));
  }
}
async function handleAuth(e){
  e.preventDefault();
  const username=document.getElementById('input-username').value.trim();
  const password=document.getElementById('input-password').value;
  // Turnstile verification
  let turnstileToken='';
  if(turnstileSiteKey){
    turnstileToken=getTurnstileToken();
    if(!turnstileToken){showSnackbar('请完成人机验证');return false;}
  }
  if(isRegisterMode){
    const email=document.getElementById('input-email').value.trim();
    const code=document.getElementById('input-code').value.trim();
    if(!email){showSnackbar('请输入邮箱地址');return false;}
    if(!code){showSnackbar('请输入验证码');return false;}
    const r=await api('POST','/api/auth/register-with-email',{username,email,password,code,turnstile_token:turnstileToken});
    if(r){showSnackbar('注册成功，请登录');resetTurnstileWidget();toggleAuthMode();}
  }else{
    const r=await api('POST','/api/auth/login',{username,password,turnstile_token:turnstileToken});
    if(r&&r.token){setToken(r.token);history.pushState({page:'devices'},'','/devices');showAppView('devices');}
    else{resetTurnstileWidget();}
  }
  return false;
}
let sendCodeCooldown=0;
let sendCodeTimer=null;

async function sendVerificationCode(){
  const email=document.getElementById('input-email').value.trim();
  if(!email){showSnackbar('请先输入邮箱地址');return;}
  // Basic email format check
  if(!/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email)){
    showSnackbar('邮箱格式不正确');return;
  }
  const btn=document.getElementById('send-code-btn');
  btn.disabled=true;
  const r=await api('POST','/api/auth/resend-verification',{email});
  if(r){
    showSnackbar('验证码已发送');
    sendCodeCooldown=60;
    btn.textContent=sendCodeCooldown+'s';
    sendCodeTimer=setInterval(()=>{
      sendCodeCooldown--;
      if(sendCodeCooldown<=0){
        clearInterval(sendCodeTimer);
        btn.textContent='发送验证码';
        btn.disabled=false;
      }else{
        btn.textContent=sendCodeCooldown+'s';
      }
    },1000);
  }else{
    btn.disabled=false;
  }
}
async function logout(){
  await api('POST','/api/auth/logout');
  clearToken();history.pushState({page:'login'},'','/login');showAuthView('login');
}

// --- Navigation ---
const APP_PAGES=['devices','discover','plaza','requests','chat','profile','settings','admin','docs'];
const SUB_PAGES=['post-detail','post-editor','user-profile'];

function navigate(page){
  navigateTo(page,true);
}
function navigateTo(page,pushState,extra){
  if(page===currentPage&&!extra)return;
  if(isTransitioning)return;
  isTransitioning=true;
  const oldEl=document.getElementById('page-'+currentPage);
  const newEl=document.getElementById('page-'+page);
  currentPage=page;
  const navPage=SUB_PAGES.includes(page)?'discover':page;
  document.querySelectorAll('.nav-rail-item,.nav-bottom-item').forEach(btn=>{
    btn.classList.toggle('active',btn.dataset.page===navPage);
  });
  document.querySelectorAll('.drawer-item').forEach(btn=>{
    btn.classList.toggle('active',btn.dataset.page===navPage);
  });
  // Hide all pages
  document.querySelectorAll('.page').forEach(p=>{p.style.display='none';p.classList.remove('active','fade-out');});
  newEl.style.display='block';newEl.classList.add('active');
  isTransitioning=false;
  // Show FAB only on discover list page
  const fab=document.getElementById('fab-new-post');
  if(fab)fab.style.display=(page==='discover')?'flex':'none';
  if(pushState){
    const url=extra&&extra.url?extra.url:'/'+page;
    history.pushState({page:page,extra:extra||null},'',url);
  }
  if(page==='devices')loadDevices();
  if(page==='discover')loadPosts();
  if(page==='plaza')loadPlaza();
  if(page==='requests')loadRequests();
  if(page==='chat')loadChatPage();
  if(page==='profile')loadProfile();
  if(page==='settings')loadSettings();
  if(page==='admin')loadAdminUsers();
  if(page==='docs')loadDocs();
  if(page==='post-detail'&&extra&&extra.postId)loadPostDetail(extra.postId);
  if(page==='post-editor')initEditor();
  if(page==='user-profile'&&extra&&extra.username)loadUserProfile(extra.username);
}

// --- Drawer ---
function toggleDrawer(){
  const drawer=document.getElementById('drawer');
  const overlay=document.getElementById('drawer-overlay');
  const isOpen=drawer.classList.contains('open');
  if(isOpen){closeDrawer();}else{openDrawer();}
}
function openDrawer(){
  document.getElementById('drawer').classList.add('open');
  document.getElementById('drawer-overlay').classList.add('open');
  document.body.classList.add('no-scroll');
}
function closeDrawer(){
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('drawer-overlay').classList.remove('open');
  document.body.classList.remove('no-scroll');
}
function navigateFromDrawer(page){
  closeDrawer();
  navigate(page);
}

// --- Routing ---
function getRouteFromPath(){
  const path=window.location.pathname.replace(/^\//,'').replace(/\/$/,'')||'';
  if(APP_PAGES.includes(path))return{view:'app',page:path};
  if(path==='register')return{view:'auth',page:'register'};
  if(path==='login')return{view:'auth',page:'login'};
  // Sub-routes
  if(path==='discover/new')return{view:'app',page:'post-editor',extra:{}};
  const discoverMatch=path.match(/^discover\/(.+)$/);
  if(discoverMatch)return{view:'app',page:'post-detail',extra:{postId:discoverMatch[1]}};
  const userMatch=path.match(/^user\/(.+)$/);
  if(userMatch)return{view:'app',page:'user-profile',extra:{username:decodeURIComponent(userMatch[1])}};
  return{view:'auto',page:'devices'};
}
window.addEventListener('popstate',function(e){
  const state=e.state;
  if(state&&state.page){
    const allPages=[...APP_PAGES,...SUB_PAGES];
    if(allPages.includes(state.page)){
      if(!getToken()){showAuthView('login');return;}
      document.getElementById('auth-view').style.display='none';
      document.getElementById('app-view').style.display='';
      navigateTo(state.page,false,state.extra||null);
    }else if(state.page==='login'||state.page==='register'){
      showAuthView(state.page);
    }
  }else{
    const route=getRouteFromPath();
    if(route.view==='app'){
      if(!getToken()){showAuthView('login');return;}
      navigateTo(route.page,false,route.extra||null);
    }else if(route.view==='auth'){
      showAuthView(route.page);
    }
  }
});

// --- Devices ---
async function loadDevices(){
  const r=await api('GET','/api/devices');
  if(!r)return;
  devices=r.devices;
  renderDevices();
}
function statusClass(s){
  if(s==='bound')return'status-bound';
  if(s==='connected'||s==='connecting')return'status-connected';
  return'status-disconnected';
}
function statusText(s){
  const m={bound:'已绑定',connected:'已连接',connecting:'连接中',disconnected:'未连接',error:'错误',reconnecting:'重连中'};
  return m[s]||s;
}
function renderDevices(){
  const list=document.getElementById('device-list');
  const empty=document.getElementById('no-devices');
  if(!devices.length){list.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  list.innerHTML=devices.map(d=>{
    const ownerTag=d.is_permitted?`<span class="owner-tag">来自 ${d.owner}</span>`:'';
    return `<div class="device-card">
      <div class="device-header">
        <span class="device-id">${d.user_id}${ownerTag}</span>
        <span class="status-badge ${statusClass(d.status)}">${statusText(d.status)}</span>
      </div>
      <div class="channel-section">
        <div class="channel-label"><span class="channel-name">A 通道</span><span>${d.strength_a} / ${d.limit_a}</span></div>
        <div class="slider-row">
          <input type="range" min="0" max="${d.limit_a}" value="${d.strength_a}" data-uid="${d.user_id}" data-ch="A" aria-label="A通道强度" oninput="this.parentElement.querySelector('.slider-value').textContent=this.value" onchange="setStrength(this)">
          <span class="slider-value">${d.strength_a}</span>
        </div>
      </div>
      <div class="channel-section">
        <div class="channel-label"><span class="channel-name">B 通道</span><span>${d.strength_b} / ${d.limit_b}</span></div>
        <div class="slider-row">
          <input type="range" min="0" max="${d.limit_b}" value="${d.strength_b}" data-uid="${d.user_id}" data-ch="B" aria-label="B通道强度" oninput="this.parentElement.querySelector('.slider-value').textContent=this.value" onchange="setStrength(this)">
          <span class="slider-value">${d.strength_b}</span>
        </div>
      </div>
      <div class="btn-row">
        ${PRESETS.map(p=>`<button class="md-btn md-btn-tonal" onclick="sendPulse('${d.user_id}','A','${p.id}')"><span class="material-symbols-outlined" style="font-size:18px">${p.icon}</span>${p.name} A</button><button class="md-btn md-btn-tonal" onclick="sendPulse('${d.user_id}','B','${p.id}')"><span class="material-symbols-outlined" style="font-size:18px">${p.icon}</span>${p.name} B</button>`).join('')}
        <button class="md-btn md-btn-error" onclick="stopDevice('${d.user_id}')"><span class="material-symbols-outlined" style="font-size:18px">stop_circle</span>停止全部</button>
      </div>
    </div>`;
  }).join('');
}
async function setStrength(el){
  const uid=el.dataset.uid,ch=el.dataset.ch,val=parseInt(el.value);
  const r=await api('POST','/api/device/'+uid+'/strength',{channel:ch,value:val});
  if(r)showSnackbar(r.message);
}
async function sendPulse(uid,ch,preset){
  const r=await api('POST','/api/device/'+uid+'/pulse',{channel:ch,preset:preset,duration:5});
  if(r)showSnackbar(r.message);
}
async function stopDevice(uid){
  const r=await api('POST','/api/device/'+uid+'/stop',{});
  if(r)showSnackbar(r.message);
}

// --- Plaza ---
async function loadPlaza(){
  const r=await api('GET','/api/plaza');
  if(!r)return;
  const list=document.getElementById('plaza-list');
  const empty=document.getElementById('no-plaza');
  if(!r.devices.length){list.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  list.innerHTML=r.devices.map(d=>`<div class="plaza-card">
    <div class="plaza-info">
      <div class="plaza-avatar"><span class="material-symbols-outlined">person</span></div>
      <div>
        <div class="md-title-medium">${d.username}</div>
        <div class="md-body-medium on-surface-variant"><span class="status-badge ${statusClass(d.status)}" style="margin-left:0">${statusText(d.status)}</span></div>
      </div>
    </div>
    <button class="md-btn md-btn-tonal" onclick="requestControl('${d.username}')">
      <span class="material-symbols-outlined" style="font-size:18px">send</span>申请控制
    </button>
  </div>`).join('');
}
async function requestControl(toUsername){
  const r=await api('POST','/api/plaza/request',{to_username:toUsername});
  if(r)showSnackbar('申请已发送');
}

// --- Requests ---
async function loadRequests(){
  const r=await api('GET','/api/requests/pending');
  if(!r)return;
  renderPending(r.pending);
  renderGranted(r.granted);
}
function timeAgo(ts){
  const diff=Date.now()/1000-ts;
  if(diff<60)return'刚刚';
  if(diff<3600)return Math.floor(diff/60)+'分钟前';
  if(diff<86400)return Math.floor(diff/3600)+'小时前';
  return Math.floor(diff/86400)+'天前';
}
function durationLabel(key){
  const m={'1h':'1小时','1d':'1天','7d':'7天','30d':'30天','permanent':'永久'};
  return m[key]||key;
}
function expiresLabel(expiresAt){
  if(!expiresAt)return'永久';
  const remaining=expiresAt-Date.now()/1000;
  if(remaining<=0)return'已过期';
  if(remaining<3600)return Math.floor(remaining/60)+'分钟后过期';
  if(remaining<86400)return Math.floor(remaining/3600)+'小时后过期';
  return Math.floor(remaining/86400)+'天后过期';
}
function renderPending(pending){
  const list=document.getElementById('pending-list');
  const empty=document.getElementById('no-pending');
  if(!pending.length){list.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  list.innerHTML=pending.map(r=>`<div class="request-card">
    <div class="request-header">
      <span class="md-title-medium">${r.from_username}</span>
      <span class="md-body-medium on-surface-variant">${timeAgo(r.created_at)}</span>
    </div>
    <div class="md-body-medium on-surface-variant">请求控制你的设备</div>
    <div class="request-actions">
      <button class="md-btn md-btn-filled" onclick="openApproveDialog('${r.request_id}')">通过</button>
      <button class="md-btn md-btn-outlined" onclick="rejectRequest('${r.request_id}')">拒绝</button>
    </div>
  </div>`).join('');
}
function renderGranted(granted){
  const list=document.getElementById('granted-list');
  const empty=document.getElementById('no-granted');
  if(!granted.length){list.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  list.innerHTML=granted.map(r=>`<div class="request-card">
    <div class="request-header">
      <span class="md-title-medium">${r.from_username}</span>
      <span class="md-body-medium on-surface-variant">${expiresLabel(r.expires_at)}</span>
    </div>
    <div class="md-body-medium on-surface-variant">授权时长: ${durationLabel(r.duration_key)}</div>
    <div class="request-actions">
      <button class="md-btn md-btn-error" onclick="revokePermission('${r.request_id}')">
        <span class="material-symbols-outlined" style="font-size:18px">block</span>撤销
      </button>
    </div>
  </div>`).join('');
}
function openApproveDialog(requestId){
  pendingApproveId=requestId;
  document.getElementById('duration-dialog').classList.add('show');
  document.body.classList.add('no-scroll');
}
function closeDurationDialog(){
  document.getElementById('duration-dialog').classList.remove('show');
  document.body.classList.remove('no-scroll');
  pendingApproveId=null;
}
async function confirmApprove(){
  if(!pendingApproveId)return;
  const duration=document.querySelector('input[name=duration]:checked').value;
  const r=await api('POST','/api/requests/'+pendingApproveId+'/approve',{duration});
  closeDurationDialog();
  if(r){showSnackbar('已通过申请');loadRequests();}
}
async function rejectRequest(requestId){
  const r=await api('POST','/api/requests/'+requestId+'/reject');
  if(r){showSnackbar('已拒绝申请');loadRequests();}
}
async function revokePermission(requestId){
  const r=await api('POST','/api/requests/'+requestId+'/revoke');
  if(r){showSnackbar('已撤销权限');loadRequests();}
}

// --- Settings ---
async function loadSettings(){
  const r=await api('GET','/api/auth/me');
  if(!r)return;
  currentUser=r;
  document.getElementById('settings-username').textContent=r.username;
  document.getElementById('settings-email').textContent=r.email||'-';
  document.getElementById('switch-public').checked=r.public_device;
  document.getElementById('switch-requests').checked=r.allow_requests;
  // Show admin nav if user is admin
  updateAdminNav();
}
function updateAdminNav(){
  // Admin nav is always visible; access control is handled by the API
}
async function saveSettings(){
  const publicDevice=document.getElementById('switch-public').checked;
  const allowRequests=document.getElementById('switch-requests').checked;
  await api('POST','/api/settings',{public_device:publicDevice,allow_requests:allowRequests});
}

// --- Profile ---
let avatarEditorState={img:null,rotation:0,scale:1,offsetX:0,offsetY:0,dragging:false,lastX:0,lastY:0};

async function loadProfile(){
  const r=await api('GET','/api/profile');
  if(!r)return;
  document.getElementById('input-nickname').value=r.nickname||'';
  document.getElementById('input-bio').value=r.bio||'';
  const genderRadios=document.querySelectorAll('input[name=gender]');
  genderRadios.forEach(radio=>{radio.checked=radio.value===(r.gender||'');});
  updateAvatarPreview(r.avatar);
}
function updateAvatarPreview(url){
  const container=document.getElementById('profile-avatar-preview');
  if(url){
    container.innerHTML=`<img src="${url}?t=${Date.now()}" onerror="this.parentElement.innerHTML='<span class=\\'material-symbols-outlined\\'>person</span>'" alt="avatar">`;
  }else{
    container.innerHTML='<span class="material-symbols-outlined">person</span>';
  }
}
async function saveProfile(){
  const nickname=document.getElementById('input-nickname').value.trim();
  const bio=document.getElementById('input-bio').value.trim();
  const genderEl=document.querySelector('input[name=gender]:checked');
  const gender=genderEl?genderEl.value:'';
  const avatar=currentUser?currentUser.avatar:'';
  const r=await api('POST','/api/profile',{nickname,gender,avatar,bio});
  if(r)showSnackbar(r.message);
}

// Avatar file selection
function onAvatarFileSelected(e){
  const file=e.target.files[0];
  if(!file)return;
  if(!file.type.match(/^image\/(png|jpeg|webp)$/)){showSnackbar('仅支持 JPG、PNG、WebP 格式');return;}
  if(file.size>5*1024*1024){showSnackbar('原始文件不能超过5MB');return;}
  const reader=new FileReader();
  reader.onload=function(ev){
    openAvatarEditor(ev.target.result);
  };
  reader.readAsDataURL(file);
  e.target.value='';
}

// Avatar Editor
function openAvatarEditor(dataUrl){
  const img=new Image();
  img.onload=function(){
    avatarEditorState={img,rotation:0,scale:1,offsetX:0,offsetY:0,dragging:false,lastX:0,lastY:0};
    document.getElementById('avatar-editor-dialog').classList.add('show');
    document.body.classList.add('no-scroll');
    setTimeout(()=>renderAvatarEditor(),50);
    setupEditorEvents();
  };
  img.src=dataUrl;
}
function closeAvatarEditor(){
  document.getElementById('avatar-editor-dialog').classList.remove('show');
  document.body.classList.remove('no-scroll');
  removeEditorEvents();
}
function renderAvatarEditor(){
  const canvas=document.getElementById('avatar-editor-canvas');
  const container=canvas.parentElement;
  canvas.width=container.clientWidth;
  canvas.height=container.clientHeight;
  const ctx=canvas.getContext('2d');
  const s=avatarEditorState;
  const cx=canvas.width/2;
  const cy=canvas.height/2;
  // Clear
  ctx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--md-sys-color-surface-container-highest').trim()||'#36343B';
  ctx.fillRect(0,0,canvas.width,canvas.height);
  // Draw image
  ctx.save();
  ctx.translate(cx+s.offsetX,cy+s.offsetY);
  ctx.rotate(s.rotation*Math.PI/180);
  ctx.scale(s.scale,s.scale);
  const aspect=s.img.width/s.img.height;
  let dw,dh;
  const fitSize=Math.min(canvas.width,canvas.height)*0.8;
  if(aspect>1){dw=fitSize;dh=fitSize/aspect;}
  else{dh=fitSize;dw=fitSize*aspect;}
  ctx.drawImage(s.img,-dw/2,-dh/2,dw,dh);
  ctx.restore();
  // Draw circular crop overlay
  ctx.save();
  const radius=Math.min(canvas.width,canvas.height)*0.38;
  ctx.fillStyle='rgba(0,0,0,0.55)';
  ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.globalCompositeOperation='destination-out';
  ctx.beginPath();
  ctx.arc(cx,cy,radius,0,Math.PI*2);
  ctx.fill();
  ctx.restore();
  // Draw circle border
  ctx.strokeStyle='rgba(208,188,255,0.7)';
  ctx.lineWidth=2;
  ctx.beginPath();
  ctx.arc(cx,cy,radius,0,Math.PI*2);
  ctx.stroke();
}
function avatarEditorRotate(deg){
  avatarEditorState.rotation=(avatarEditorState.rotation+deg)%360;
  renderAvatarEditor();
}
function avatarEditorZoom(factor){
  avatarEditorState.scale=Math.max(0.2,Math.min(5,avatarEditorState.scale*factor));
  renderAvatarEditor();
}
function avatarEditorReset(){
  avatarEditorState.rotation=0;
  avatarEditorState.scale=1;
  avatarEditorState.offsetX=0;
  avatarEditorState.offsetY=0;
  renderAvatarEditor();
}

// Drag to pan
function _editorPointerDown(e){
  avatarEditorState.dragging=true;
  avatarEditorState.lastX=e.clientX||e.touches[0].clientX;
  avatarEditorState.lastY=e.clientY||e.touches[0].clientY;
}
function _editorPointerMove(e){
  if(!avatarEditorState.dragging)return;
  const x=e.clientX||e.touches[0].clientX;
  const y=e.clientY||e.touches[0].clientY;
  avatarEditorState.offsetX+=x-avatarEditorState.lastX;
  avatarEditorState.offsetY+=y-avatarEditorState.lastY;
  avatarEditorState.lastX=x;
  avatarEditorState.lastY=y;
  renderAvatarEditor();
}
function _editorPointerUp(){avatarEditorState.dragging=false;}
function _editorWheel(e){
  e.preventDefault();
  const factor=e.deltaY<0?1.1:0.9;
  avatarEditorZoom(factor);
}
function setupEditorEvents(){
  const canvas=document.getElementById('avatar-editor-canvas');
  canvas.addEventListener('mousedown',_editorPointerDown);
  canvas.addEventListener('mousemove',_editorPointerMove);
  canvas.addEventListener('mouseup',_editorPointerUp);
  canvas.addEventListener('mouseleave',_editorPointerUp);
  canvas.addEventListener('touchstart',_editorPointerDown,{passive:true});
  canvas.addEventListener('touchmove',_editorPointerMove,{passive:true});
  canvas.addEventListener('touchend',_editorPointerUp);
  canvas.addEventListener('wheel',_editorWheel,{passive:false});
}
function removeEditorEvents(){
  const canvas=document.getElementById('avatar-editor-canvas');
  canvas.removeEventListener('mousedown',_editorPointerDown);
  canvas.removeEventListener('mousemove',_editorPointerMove);
  canvas.removeEventListener('mouseup',_editorPointerUp);
  canvas.removeEventListener('mouseleave',_editorPointerUp);
  canvas.removeEventListener('touchstart',_editorPointerDown);
  canvas.removeEventListener('touchmove',_editorPointerMove);
  canvas.removeEventListener('touchend',_editorPointerUp);
  canvas.removeEventListener('wheel',_editorWheel);
}

// Confirm and upload
async function confirmAvatarEdit(){
  const s=avatarEditorState;
  const canvas=document.getElementById('avatar-editor-canvas');
  const cx=canvas.width/2;
  const cy=canvas.height/2;
  const radius=Math.min(canvas.width,canvas.height)*0.38;
  // Render cropped circle to output canvas
  const outSize=256;
  const out=document.createElement('canvas');
  out.width=outSize;out.height=outSize;
  const octx=out.getContext('2d');
  // Clip to circle
  octx.beginPath();
  octx.arc(outSize/2,outSize/2,outSize/2,0,Math.PI*2);
  octx.clip();
  // Scale factor from display to output
  const sf=outSize/(radius*2);
  octx.translate(outSize/2,outSize/2);
  octx.scale(sf,sf);
  // Apply same transforms as editor relative to center
  octx.translate(s.offsetX,s.offsetY);
  octx.rotate(s.rotation*Math.PI/180);
  octx.scale(s.scale,s.scale);
  const aspect=s.img.width/s.img.height;
  const fitSize=Math.min(canvas.width,canvas.height)*0.8;
  let dw,dh;
  if(aspect>1){dw=fitSize;dh=fitSize/aspect;}
  else{dh=fitSize;dw=fitSize*aspect;}
  octx.drawImage(s.img,-dw/2,-dh/2,dw,dh);
  // Export as PNG data URL
  const dataUrl=out.toDataURL('image/png');
  // Upload
  const r=await api('POST','/api/avatar/upload',{image:dataUrl});
  if(r){
    showSnackbar(r.message);
    if(currentUser)currentUser.avatar=r.avatar;
    updateAvatarPreview(r.avatar);
    closeAvatarEditor();
  }
}

// --- Discover (Posts) ---
let currentPostSort='newest';
let searchDebounceTimer=null;

async function loadPosts(){
  const q=document.getElementById('discover-search-input').value.trim();
  const params=new URLSearchParams({sort:currentPostSort});
  if(q)params.set('q',q);
  const r=await api('GET','/api/posts?'+params.toString());
  if(!r)return;
  renderPosts(r.posts);
}

function renderPosts(posts){
  const list=document.getElementById('posts-list');
  const empty=document.getElementById('no-posts');
  if(!posts||!posts.length){list.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  list.innerHTML=posts.map(p=>{
    const avatarHtml=p.author_avatar
      ?`<img src="${p.author_avatar}" style="width:32px;height:32px;border-radius:50%;object-fit:cover">`
      :`<span class="material-symbols-outlined" style="font-size:20px">person</span>`;
    const nickname=p.author_nickname||p.author;
    return `<div class="post-card" onclick="navigateToPost('${p.post_id}')">
      <div class="post-card-title">${escapeHtml(p.title||'无标题')}</div>
      <div class="post-card-summary">${escapeHtml(p.summary||'')}</div>
      <div class="post-card-footer">
        <div class="post-card-author" onclick="event.stopPropagation();navigateToUser('${p.author}')">
          <div class="post-author-avatar">${avatarHtml}</div>
          <span>${escapeHtml(nickname)}</span>
        </div>
        <div class="post-card-meta">
          <span class="material-symbols-outlined" style="font-size:14px">visibility</span>${p.views||0}
          <span style="margin-left:8px">${timeAgo(p.created_at)}</span>
        </div>
      </div>
    </div>`;
  }).join('');
}

function escapeHtml(text){
  const d=document.createElement('div');
  d.textContent=text;
  return d.innerHTML;
}

function searchPostsDebounced(){
  if(searchDebounceTimer)clearTimeout(searchDebounceTimer);
  searchDebounceTimer=setTimeout(()=>loadPosts(),300);
}

function setPostSort(sort){
  currentPostSort=sort;
  document.querySelectorAll('.discover-sort button').forEach(btn=>{
    btn.classList.toggle('active',btn.dataset.sort===sort);
  });
  loadPosts();
}

function navigateToPost(postId){
  navigateTo('post-detail',true,{postId:postId,url:'/discover/'+postId});
}

function navigateToNewPost(){
  navigateTo('post-editor',true,{url:'/discover/new'});
}

function navigateToUser(username){
  navigateTo('user-profile',true,{username:username,url:'/user/'+encodeURIComponent(username)});
}

// --- Post Detail ---
async function loadPostDetail(postId){
  const container=document.getElementById('post-detail-content');
  container.innerHTML='<p class="on-surface-variant">加载中...</p>';
  const r=await api('GET','/api/posts/'+postId);
  if(!r||!r.post){container.innerHTML='<p class="on-surface-variant">帖子不存在或已被删除</p>';return;}
  const p=r.post;
  const avatarHtml=p.author_avatar
    ?`<img src="${p.author_avatar}" style="width:40px;height:40px;border-radius:50%;object-fit:cover">`
    :`<span class="material-symbols-outlined" style="font-size:24px">person</span>`;
  const nickname=p.author_nickname||p.author;
  const isMe=currentUser&&p.author===currentUser.username;
  const deleteBtn=isMe?`<button class="md-btn md-btn-text" onclick="deletePostFromDetail('${p.post_id}')" style="margin-left:auto"><span class="material-symbols-outlined" style="font-size:18px">delete</span>删除</button>`:'';
  const contentHtml=renderMarkdownContent(p.content||'');
  container.innerHTML=`
    <div class="post-detail-header">
      <h1 class="md-display-medium" style="font-size:1.6rem;margin-bottom:12px">${escapeHtml(p.title||'无标题')}</h1>
      <div class="post-detail-meta">
        <div class="post-card-author" onclick="navigateToUser('${p.author}')" style="cursor:pointer">
          <div class="post-author-avatar">${avatarHtml}</div>
          <span style="font-weight:500">${escapeHtml(nickname)}</span>
        </div>
        <span class="on-surface-variant" style="font-size:.85rem">${timeAgo(p.created_at)}</span>
        <span class="on-surface-variant" style="font-size:.85rem"><span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">visibility</span> ${p.views||0}</span>
        ${deleteBtn}
      </div>
    </div>
    <div class="docs-content post-detail-body">${contentHtml}</div>
  `;
}

async function deletePostFromDetail(postId){
  if(!confirm('确定要删除这篇帖子吗？'))return;
  const r=await api('POST','/api/posts/'+postId+'/delete');
  if(r){showSnackbar(r.message||'已删除');navigate('discover');}
}

// --- Post Editor ---
let editorMode='text';

function initEditor(){
  editorMode='text';
  document.getElementById('editor-title').value='';
  document.getElementById('editor-summary').value='';
  document.getElementById('editor-content').value='';
  document.getElementById('editor-preview').innerHTML='';
  document.getElementById('editor-preview').style.display='none';
  document.getElementById('editor-mode-text').classList.add('active');
  document.getElementById('editor-mode-md').classList.remove('active');
}

function setEditorMode(mode){
  editorMode=mode;
  document.getElementById('editor-mode-text').classList.toggle('active',mode==='text');
  document.getElementById('editor-mode-md').classList.toggle('active',mode==='markdown');
  const preview=document.getElementById('editor-preview');
  if(mode==='markdown'){
    preview.style.display='block';
    updateEditorPreview();
  }else{
    preview.style.display='none';
  }
}

function updateEditorPreview(){
  if(editorMode!=='markdown')return;
  const text=document.getElementById('editor-content').value;
  document.getElementById('editor-preview').innerHTML=renderMarkdownContent(text);
}

async function submitPost(){
  const title=document.getElementById('editor-title').value.trim();
  const summary=document.getElementById('editor-summary').value.trim();
  const content=document.getElementById('editor-content').value.trim();
  if(!title){showSnackbar('请输入标题');return;}
  if(!content){showSnackbar('请输入正文内容');return;}
  const r=await api('POST','/api/posts',{title,summary,content});
  if(r){showSnackbar(r.message||'发布成功');navigate('discover');}
}

// --- Markdown Renderer (shared) ---
function renderMarkdownContent(md){
  if(!md)return '';
  const lines=md.split('\n');
  let html='';
  let inCode=false;
  let inList=false;
  let listType='';
  let inBlockquote=false;

  for(let i=0;i<lines.length;i++){
    let line=lines[i];
    if(line.startsWith('\`\`\`')){
      if(inCode){html+='</code></pre>';inCode=false;}
      else{html+='<pre><code>';inCode=true;}
      continue;
    }
    if(inCode){html+=escapeHtml(line)+'\n';continue;}
    if(line.startsWith('> ')){
      if(!inBlockquote){html+='<blockquote>';inBlockquote=true;}
      html+='<p>'+inlineFormat(line.slice(2))+'</p>';continue;
    }else if(inBlockquote){html+='</blockquote>';inBlockquote=false;}
    const h3=line.match(/^### (.+)/);
    const h2=line.match(/^## (.+)/);
    const h1=line.match(/^# (.+)/);
    if(h3){if(inList){html+=listType==='ul'?'</ul>':'</ol>';inList=false;}html+='<h3>'+inlineFormat(h3[1])+'</h3>';continue;}
    if(h2){if(inList){html+=listType==='ul'?'</ul>':'</ol>';inList=false;}html+='<h2>'+inlineFormat(h2[1])+'</h2>';continue;}
    if(h1){if(inList){html+=listType==='ul'?'</ul>':'</ol>';inList=false;}html+='<h1>'+inlineFormat(h1[1])+'</h1>';continue;}
    if(line.match(/^---+$/)){if(inList){html+=listType==='ul'?'</ul>':'</ol>';inList=false;}html+='<hr>';continue;}
    const ulM=line.match(/^- (.+)/);
    const olM=line.match(/^\d+\. (.+)/);
    if(ulM){if(!inList||listType!=='ul'){if(inList)html+='</'+listType+'>';html+='<ul>';inList=true;listType='ul';}html+='<li>'+inlineFormat(ulM[1])+'</li>';continue;}
    if(olM){if(!inList||listType!=='ol'){if(inList)html+='</'+listType+'>';html+='<ol>';inList=true;listType='ol';}html+='<li>'+inlineFormat(olM[1])+'</li>';continue;}
    if(inList){html+=listType==='ul'?'</ul>':'</ol>';inList=false;}
    if(!line.trim())continue;
    html+='<p>'+inlineFormat(line)+'</p>';
  }
  if(inList)html+=listType==='ul'?'</ul>':'</ol>';
  if(inCode)html+='</code></pre>';
  if(inBlockquote)html+='</blockquote>';
  return html;
}

// --- User Profile ---
async function loadUserProfile(username){
  const container=document.getElementById('user-profile-content');
  container.innerHTML='<p class="on-surface-variant">加载中...</p>';
  const r=await api('GET','/api/user/'+encodeURIComponent(username));
  if(!r){container.innerHTML='<p class="on-surface-variant">用户不存在</p>';return;}
  const avatarHtml=r.avatar
    ?`<img src="${r.avatar}" style="width:80px;height:80px;border-radius:50%;object-fit:cover">`
    :`<div style="width:80px;height:80px;border-radius:50%;background:var(--md-sys-color-surface-variant);display:flex;align-items:center;justify-content:center"><span class="material-symbols-outlined" style="font-size:40px">person</span></div>`;
  const genderIcon=r.gender==='male'?'male':r.gender==='female'?'female':'';
  const genderHtml=genderIcon?`<span class="material-symbols-outlined" style="font-size:18px;color:var(--md-sys-color-primary)">${genderIcon}</span>`:'';
  container.innerHTML=`
    <div class="user-profile-card">
      <div class="user-profile-avatar">${avatarHtml}</div>
      <div class="user-profile-info">
        <h2 style="margin:0;font-size:1.4rem;display:flex;align-items:center;gap:8px">${escapeHtml(r.nickname||r.username)} ${genderHtml}</h2>
        <p class="on-surface-variant" style="margin:4px 0 0;font-size:.9rem">@${escapeHtml(r.username)}</p>
        ${r.bio?`<p style="margin:12px 0 0;font-size:.95rem">${escapeHtml(r.bio)}</p>`:''}
      </div>
    </div>
  `;
}

async function deletePost(postId){
  const r=await api('POST','/api/posts/'+postId+'/delete');
  if(r){showSnackbar(r.message);loadPosts();}
}

// --- Admin ---
let allAdminUsers=[];
async function loadAdminUsers(){
  const r=await api('GET','/api/admin/users');
  if(!r){
    // Non-admin users will get a 403 error handled by api(), show empty state
    const list=document.getElementById('admin-user-list');
    const empty=document.getElementById('no-admin-users');
    list.innerHTML='';
    empty.style.display='block';
    empty.innerHTML='<span class="material-symbols-outlined empty-icon">lock</span><p class="md-title-medium">无权访问</p><p class="md-body-medium on-surface-variant">仅管理员可以访问后台管理页面</p>';
    return;
  }
  allAdminUsers=r.users;
  renderAdminUsers(allAdminUsers);
  loadAdminConfigs();
}
function filterAdminUsers(){
  const q=document.getElementById('admin-search').value.trim().toLowerCase();
  if(!q){renderAdminUsers(allAdminUsers);return;}
  const filtered=allAdminUsers.filter(u=>u.username.toLowerCase().includes(q)||(u.email||'').toLowerCase().includes(q));
  renderAdminUsers(filtered);
}
function renderAdminUsers(users){
  const list=document.getElementById('admin-user-list');
  const empty=document.getElementById('no-admin-users');
  if(!users.length){list.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  list.innerHTML=users.map(u=>{
    const roleBadge=u.role==='admin'?'<span class="admin-role-badge admin-role-admin">管理员</span>':'<span class="admin-role-badge admin-role-user">普通用户</span>';
    const createdDate=new Date(u.created_at*1000).toLocaleDateString('zh-CN');
    return `<div class="admin-user-card">
      <div class="admin-user-info">
        <div class="admin-user-avatar"><span class="material-symbols-outlined">person</span></div>
        <div class="admin-user-details">
          <span class="admin-user-name">${u.username} ${roleBadge}</span>
          <span class="admin-user-meta">邮箱: ${u.email||'-'} | ${u.email_verified?'✓ 已验证':'✗ 未验证'} | 注册: ${createdDate}</span>
        </div>
      </div>
      <div class="admin-actions">
        <select class="admin-select" aria-label="设置${u.username}的角色" onchange="setUserRole('${u.username}',this.value)" ${u.username===currentUser.username?'disabled':''}>
          <option value="user" ${u.role==='user'?'selected':''}>普通用户</option>
          <option value="admin" ${u.role==='admin'?'selected':''}>管理员</option>
        </select>
      </div>
    </div>`;
  }).join('');
}
async function setUserRole(username,role){
  const r=await api('POST','/api/admin/users/'+encodeURIComponent(username)+'/role',{role});
  if(r){showSnackbar(r.message);loadAdminUsers();}
}

// --- SMTP Config ---
async function loadAdminConfigs(){
  await loadSmtpConfig();
  await loadTurnstileConfig();
}
async function loadSmtpConfig(){
  const r=await api('GET','/api/admin/smtp-config');
  if(!r)return;
  if(r.configured){
    document.getElementById('smtp-host').value=r.host||'';
    document.getElementById('smtp-port').value=r.port||587;
    document.getElementById('smtp-username').value=r.username||'';
    document.getElementById('smtp-encryption').value=r.encryption||'tls';
    document.getElementById('smtp-from-email').value=r.from_email||'';
    document.getElementById('smtp-password').value=r.has_password?'••••••••':'';
  }
}

function toggleSmtpPasswordVisibility(){
  const pw=document.getElementById('smtp-password');
  const icon=document.getElementById('smtp-pw-toggle-icon');
  if(pw.type==='password'){pw.type='text';icon.textContent='visibility_off';}
  else{pw.type='password';icon.textContent='visibility';}
}

async function testSmtpConnection(){
  const host=document.getElementById('smtp-host').value.trim();
  const port=parseInt(document.getElementById('smtp-port').value)||587;
  const username=document.getElementById('smtp-username').value.trim();
  const password=document.getElementById('smtp-password').value.trim();
  const encryption=document.getElementById('smtp-encryption').value;
  if(!host||!username){showSnackbar('请填写SMTP服务器和账号');return;}
  showSnackbar('正在测试连接...');
  const r=await api('POST','/api/admin/smtp-test',{host,port,username,password,encryption});
  if(r)showSnackbar('连接测试成功！');
}

async function saveSmtpConfig(){
  const host=document.getElementById('smtp-host').value.trim();
  const port=parseInt(document.getElementById('smtp-port').value)||587;
  const username=document.getElementById('smtp-username').value.trim();
  const password=document.getElementById('smtp-password').value.trim();
  const encryption=document.getElementById('smtp-encryption').value;
  const from_email=document.getElementById('smtp-from-email').value.trim();
  if(!host||!username){showSnackbar('请填写SMTP服务器和账号');return;}
  const r=await api('POST','/api/admin/smtp-config',{host,port,username,password,encryption,from_email});
  if(r)showSnackbar('SMTP配置已保存');
}

// --- Turnstile ---
let turnstileSiteKey='';
let turnstileWidgetId=null;

async function loadTurnstileConfig(){
  const r=await api('GET','/api/turnstile/config');
  if(!r)return;
  document.getElementById('turnstile-enabled').checked=r.enabled;
  document.getElementById('turnstile-site-key').value=r.site_key||'';
  turnstileSiteKey=r.site_key||'';
}

function toggleTurnstileEnabled(){
  const enabled=document.getElementById('turnstile-enabled').checked;
  document.getElementById('turnstile-site-key').disabled=!enabled;
  document.getElementById('turnstile-secret-key').disabled=!enabled;
}

function toggleTurnstileSecretVisibility(){
  const pw=document.getElementById('turnstile-secret-key');
  const icon=document.getElementById('turnstile-pw-toggle-icon');
  if(pw.type==='password'){pw.type='text';icon.textContent='visibility_off';}
  else{pw.type='password';icon.textContent='visibility';}
}

async function saveTurnstileConfig(){
  const site_key=document.getElementById('turnstile-site-key').value.trim();
  const secret_key=document.getElementById('turnstile-secret-key').value.trim();
  const enabled=document.getElementById('turnstile-enabled').checked;
  if(enabled&&(!site_key||!secret_key)){showSnackbar('启用时 Site Key 和 Secret Key 不能为空');return;}
  const r=await api('POST','/api/admin/turnstile-config',{site_key,secret_key,enabled});
  if(r){showSnackbar('Turnstile 配置已保存');turnstileSiteKey=site_key;}
}

async function initTurnstileWidget(){
  if(!turnstileSiteKey)return;
  const container=document.getElementById('turnstile-widget');
  if(!container)return;
  container.style.display='';
  // Load Cloudflare Turnstile script if not already loaded
  if(!window.turnstile){
    await new Promise((resolve,reject)=>{
      const s=document.createElement('script');
      s.src='https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      s.async=true;
      s.defer=true;
      s.onload=resolve;
      s.onerror=reject;
      document.head.appendChild(s);
    });
  }
  // Render widget
  if(turnstileWidgetId!==null){
    try{window.turnstile.remove(turnstileWidgetId);}catch(e){}
  }
  turnstileWidgetId=window.turnstile.render('#turnstile-widget',{
    sitekey:turnstileSiteKey,
    theme:'dark',
    callback:function(token){},
    'error-callback':function(){showSnackbar('人机验证加载失败，请刷新页面重试');}
  });
}

function getTurnstileToken(){
  if(!turnstileSiteKey||!window.turnstile)return '';
  return window.turnstile.getResponse(turnstileWidgetId)||'';
}

function resetTurnstileWidget(){
  if(turnstileWidgetId!==null&&window.turnstile){
    try{window.turnstile.reset(turnstileWidgetId);}catch(e){}
  }
}

// --- Docs ---
const DOCS_MD=`# DG-LAB 设备简介

## 什么是 DG-LAB

DG-LAB 是一款基于蓝牙通信的电刺激设备，支持通过手机 APP 或 WebSocket 协议进行远程控制。设备具有两个独立输出通道（A 通道和 B 通道），每个通道可独立设置强度（0-200）和波形。

## 设备特性

- **双通道输出**：A/B 两个独立通道，可分别控制
- **强度范围**：0-200 级可调
- **波形预设**：支持呼吸、脉冲、波浪、敲击、风暴等多种波形
- **远程控制**：通过 WebSocket 协议实现网络远程操控
- **安全机制**：设备端可设置强度上限，防止远程端超限操作
- **低功耗蓝牙**：采用 BLE 协议，续航持久

## 连接方式

设备通过 DG-LAB App 连接蓝牙后，App 会生成一个 WebSocket 服务地址。将该地址配置到本插件中即可实现远程控制。

### 连接流程

1. 打开 DG-LAB App，连接蓝牙设备
2. 进入 App 的"远程控制"功能
3. 选择"第三方接入"，获取 WebSocket 地址
4. 在聊天中使用 \`/dglab bind <地址>\` 绑定设备
5. 绑定成功后即可通过 WebUI 或指令控制

### 注意事项

> 请确保设备蓝牙连接稳定，且手机 App 保持前台运行。如果 App 被系统杀死，WebSocket 连接将断开。

## 技术参数

| 参数 | 说明 |
|------|------|
| 通道数 | 2（A/B） |
| 强度范围 | 0-200 |
| 通信协议 | WebSocket |
| 蓝牙版本 | BLE 4.2+ |
| 波形频率 | 10-1000Hz |
| 脉冲宽度 | 50-500μs |

---

# 插件功能介绍

## 概述

本插件为 AstrBot 提供 DG-LAB 设备的集成控制能力，将设备管理、远程控制、社交互动等功能整合到统一的 Web 界面中。

## 设备绑定与管理

- 通过聊天指令绑定设备到用户账号
- 支持多设备管理，每个用户可绑定一台设备
- 设备状态实时监控（已连接/已绑定/未连接/重连中）
- 自动重连机制，断线后自动尝试恢复连接

### 设备状态说明

| 状态 | 含义 |
|------|------|
| 已连接 | WebSocket 连接正常，可以控制 |
| 已绑定 | 设备已绑定但未连接 |
| 连接中 | 正在建立 WebSocket 连接 |
| 重连中 | 连接断开后正在自动重连 |
| 未连接 | 设备离线 |

## WebUI 控制面板

- 基于浏览器的可视化控制界面
- 支持实时调节 A/B 通道强度（滑块控制）
- 支持发送波形预设（呼吸、脉冲、波浪、敲击、风暴）
- 一键停止所有输出
- 响应式设计，支持桌面端和移动端

### 波形预设说明

| 预设 | 效果描述 |
|------|----------|
| 呼吸 | 缓慢渐强渐弱，节奏平稳 |
| 脉冲 | 短促有力的电击感 |
| 波浪 | 连续起伏的波动感 |
| 敲击 | 模拟轻拍的间断刺激 |
| 风暴 | 高强度随机变化 |

## 设备广场

- 用户可将设备公开到广场供他人查看
- 其他用户可申请控制权限
- 设备主人可审批/拒绝/撤销权限
- 支持设置授权时长（1小时/1天/7天/30天/永久）
- 授权到期自动回收权限

## 权限系统

- 基于用户角色的权限管理（普通用户/管理员）
- 设备级别的访问控制
- 申请-审批工作流
- 管理员可管理所有用户角色

### 权限层级

1. **管理员**：可管理用户、查看所有设备、修改系统设置
2. **普通用户**：可绑定设备、申请控制、发布动态
3. **被授权用户**：可在授权期内控制他人设备

## 社区功能

- 发现页面：用户可发布和浏览动态帖子
- 个人中心：管理个人资料、头像、昵称、签名
- 头像编辑：支持上传、裁剪、旋转、缩放

## 文档中心

- 内置完整使用文档
- 自动生成目录导航
- 支持关键词搜索和高亮

---

# 指令使用方法

## 设备绑定

\`\`\`
/dglab bind <WebSocket地址>
\`\`\`

将 DG-LAB 设备绑定到当前用户。WebSocket 地址从 DG-LAB App 中获取。

> 每个用户只能绑定一台设备。重复绑定会覆盖之前的绑定。

## 解除绑定

\`\`\`
/dglab unbind
\`\`\`

解除当前用户的设备绑定。解除后将无法通过指令或 WebUI 控制设备。

## 设置强度

\`\`\`
/dglab strength <通道> <强度值>
\`\`\`

- 通道：\`A\` 或 \`B\`
- 强度值：0-200 的整数

示例：\`/dglab strength A 50\`

> 实际最大强度受设备端限制。如果设备端设置了上限为 100，则即使发送 200 也只会生效到 100。

## 发送波形

\`\`\`
/dglab pulse <通道> <预设名> [持续秒数]
\`\`\`

- 通道：\`A\` 或 \`B\`
- 预设名：\`breathe\`（呼吸）、\`pulse\`（脉冲）、\`wave\`（波浪）、\`tap\`（敲击）、\`storm\`（风暴）
- 持续秒数：1-60，默认 5 秒

示例：\`/dglab pulse A breathe 10\`

### 波形参数

| 预设名 | 英文标识 | 默认时长 |
|--------|----------|----------|
| 呼吸 | breathe | 5s |
| 脉冲 | pulse | 5s |
| 波浪 | wave | 5s |
| 敲击 | tap | 5s |
| 风暴 | storm | 5s |

## 停止输出

\`\`\`
/dglab stop
\`\`\`

立即停止所有通道的输出，将 A/B 通道强度归零。

## 查看状态

\`\`\`
/dglab status
\`\`\`

查看当前设备的连接状态和通道强度信息，包括：
- 连接状态
- A 通道当前强度 / 上限
- B 通道当前强度 / 上限

## WebUI 访问

\`\`\`
/dglab webui
\`\`\`

获取 WebUI 控制面板的访问地址。返回的链接可在浏览器中打开。

## 设备广场

\`\`\`
/dglab plaza
\`\`\`

查看当前公开的设备列表。只有开启了"公开设备"选项的用户设备才会出现在广场中。

## 常见问题

### 绑定失败怎么办？

1. 确认 WebSocket 地址格式正确（以 \`ws://\` 或 \`wss://\` 开头）
2. 确认 DG-LAB App 处于前台运行状态
3. 确认手机网络正常，服务器可以访问到 App 提供的地址

### 设备显示"未连接"？

- 检查 App 是否被系统后台杀死
- 检查手机网络是否正常
- 尝试在 App 中重新生成 WebSocket 地址并重新绑定

### 强度设置不生效？

- 确认设备处于"已连接"状态
- 检查设备端是否设置了强度上限
- 确认通道名称正确（A 或 B，区分大小写）
`;

let docsRendered=false;
let docsHtmlCache='';
let docsTocCache=[];
let docsScrollObserver=null;

function loadDocs(){
  if(!docsRendered){
    renderDocs(DOCS_MD);
    docsRendered=true;
  }
  setupDocsScrollSpy();
}

function renderDocs(md){
  const lines=md.split('\n');
  let html='';
  let inCode=false;
  let inList=false;
  let listType='';
  let inBlockquote=false;
  let inTable=false;
  let tableHeaders=[];
  const toc=[];

  for(let i=0;i<lines.length;i++){
    let line=lines[i];

    // Code blocks
    if(line.startsWith('\`\`\`')){
      if(inCode){html+='</code></pre>';inCode=false;}
      else{html+='<pre><code>';inCode=true;}
      continue;
    }
    if(inCode){html+=escapeHtml(line)+'\n';continue;}

    // Table detection
    if(line.includes('|')&&line.trim().startsWith('|')){
      const cells=line.split('|').filter(c=>c.trim()!=='').map(c=>c.trim());
      if(!inTable){
        // Check if next line is separator
        if(i+1<lines.length&&lines[i+1].match(/^\|[\s\-:|]+\|$/)){
          inTable=true;
          tableHeaders=cells;
          html+='<table><thead><tr>';
          cells.forEach(c=>{html+='<th>'+inlineFormat(c)+'</th>';});
          html+='</tr></thead><tbody>';
          i++; // skip separator line
          continue;
        }
      }else{
        if(cells.length>0){
          html+='<tr>';
          cells.forEach(c=>{html+='<td>'+inlineFormat(c)+'</td>';});
          html+='</tr>';
          continue;
        }
      }
    }else if(inTable){
      html+='</tbody></table>';
      inTable=false;
    }

    // Blockquote
    if(line.startsWith('> ')){
      if(!inBlockquote){html+='<blockquote>';inBlockquote=true;}
      html+='<p>'+inlineFormat(line.slice(2))+'</p>';
      continue;
    }else if(inBlockquote){
      html+='</blockquote>';
      inBlockquote=false;
    }

    // Headings
    const h3Match=line.match(/^### (.+)/);
    const h2Match=line.match(/^## (.+)/);
    const h1Match=line.match(/^# (.+)/);
    if(h3Match){
      if(inList){html+=listType==='ul'?'</ul>':'</ol>';inList=false;}
      const id='doc-'+toc.length;
      toc.push({level:3,text:h3Match[1],id});
      html+='<h3 id="'+id+'">'+inlineFormat(h3Match[1])+'</h3>';continue;
    }
    if(h2Match){
      if(inList){html+=listType==='ul'?'</ul>':'</ol>';inList=false;}
      const id='doc-'+toc.length;
      toc.push({level:2,text:h2Match[1],id});
      html+='<h2 id="'+id+'">'+inlineFormat(h2Match[1])+'</h2>';continue;
    }
    if(h1Match){
      if(inList){html+=listType==='ul'?'</ul>':'</ol>';inList=false;}
      const id='doc-'+toc.length;
      toc.push({level:1,text:h1Match[1],id});
      html+='<h1 id="'+id+'">'+inlineFormat(h1Match[1])+'</h1>';continue;
    }

    // Horizontal rule
    if(line.match(/^---+$/)){
      if(inList){html+=listType==='ul'?'</ul>':'</ol>';inList=false;}
      html+='<hr style="border:none;border-top:1px solid var(--md-sys-color-outline-variant);margin:24px 0">';continue;
    }

    // List items
    const ulMatch=line.match(/^- (.+)/);
    const olMatch=line.match(/^\d+\. (.+)/);
    if(ulMatch){
      if(!inList||listType!=='ul'){if(inList)html+='</'+listType+'>';html+='<ul>';inList=true;listType='ul';}
      html+='<li>'+inlineFormat(ulMatch[1])+'</li>';continue;
    }
    if(olMatch){
      if(!inList||listType!=='ol'){if(inList)html+='</'+listType+'>';html+='<ol>';inList=true;listType='ol';}
      html+='<li>'+inlineFormat(olMatch[1])+'</li>';continue;
    }

    // Close list if not a list item
    if(inList){html+=listType==='ul'?'</ul>':'</ol>';inList=false;}

    // Empty line
    if(!line.trim()){continue;}

    // Paragraph
    html+='<p>'+inlineFormat(line)+'</p>';
  }
  if(inList)html+=listType==='ul'?'</ul>':'</ol>';
  if(inCode)html+='</code></pre>';
  if(inBlockquote)html+='</blockquote>';
  if(inTable)html+='</tbody></table>';

  docsHtmlCache=html;
  docsTocCache=toc;
  document.getElementById('docs-content').innerHTML=html;
  renderDocsToc(toc);
}

function inlineFormat(text){
  // Bold
  text=text.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  // Inline code
  text=text.replace(/\`([^\`]+)\`/g,'<code>$1</code>');
  return text;
}

function renderDocsToc(toc){
  const el=document.getElementById('docs-toc');
  if(!toc.length){el.innerHTML='';return;}
  let html='<div class="docs-toc-title">目录</div><ul>';
  toc.forEach(item=>{
    const cls=item.level===1?'toc-h1':item.level===2?'toc-h2':'toc-h3';
    html+='<li><a class="'+cls+'" data-doc-id="'+item.id+'" onclick="scrollToDoc(\''+item.id+'\')">'+item.text+'</a></li>';
  });
  html+='</ul>';
  el.innerHTML=html;
}

function scrollToDoc(id){
  const el=document.getElementById(id);
  if(el){
    const offset=72;
    const top=el.getBoundingClientRect().top+window.pageYOffset-offset;
    window.scrollTo({top:top,behavior:'smooth'});
  }
}

function setupDocsScrollSpy(){
  const headings=document.querySelectorAll('.docs-content h1[id],.docs-content h2[id],.docs-content h3[id]');
  if(!headings.length)return;

  if(docsScrollObserver){docsScrollObserver.disconnect();}

  docsScrollObserver=new IntersectionObserver(entries=>{
    entries.forEach(entry=>{
      if(entry.isIntersecting){
        const id=entry.target.id;
        document.querySelectorAll('.docs-toc a').forEach(a=>{
          a.classList.toggle('active',a.dataset.docId===id);
        });
      }
    });
  },{rootMargin:'-80px 0px -60% 0px',threshold:0});

  headings.forEach(h=>docsScrollObserver.observe(h));
}

function searchDocs(){
  const q=document.getElementById('docs-search').value.trim().toLowerCase();
  const content=document.getElementById('docs-content');
  const countEl=document.getElementById('docs-search-count');
  const clearBtn=document.getElementById('docs-search-clear');

  clearBtn.classList.toggle('show',q.length>0);

  if(!q){
    content.innerHTML=docsHtmlCache;
    countEl.textContent='';
    // Reset TOC highlights
    document.querySelectorAll('.docs-toc a').forEach(a=>a.classList.remove('has-match'));
    setupDocsScrollSpy();
    return;
  }

  // Highlight matches in content
  const regex=new RegExp('('+q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi');
  let matchCount=0;
  let highlighted=docsHtmlCache.replace(/>([^<]+)</g,(match,text)=>{
    const replaced=text.replace(regex,(m)=>{matchCount++;return '<mark>'+m+'</mark>';});
    return '>'+replaced+'<';
  });

  if(matchCount===0){
    content.innerHTML='<div class="docs-no-results"><span class="material-symbols-outlined" style="font-size:48px;display:block;margin-bottom:12px">search_off</span>未找到匹配"'+escapeHtml(q)+'"的内容</div>';
    countEl.textContent='';
  }else{
    content.innerHTML=highlighted;
    countEl.textContent=matchCount+' 处匹配';
  }

  // Highlight TOC items that have matching sections
  highlightTocMatches(q);
}

function highlightTocMatches(query){
  const regex=new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'i');
  document.querySelectorAll('.docs-toc a').forEach(a=>{
    const docId=a.dataset.docId;
    if(!docId){a.classList.remove('has-match');return;}
    // Check if the section content contains the query
    const heading=document.getElementById(docId);
    if(!heading){a.classList.remove('has-match');return;}
    // Get text content from heading to next heading
    let textContent=heading.textContent;
    let sibling=heading.nextElementSibling;
    while(sibling&&!sibling.matches('h1,h2,h3')){
      textContent+=' '+sibling.textContent;
      sibling=sibling.nextElementSibling;
    }
    a.classList.toggle('has-match',regex.test(textContent));
  });
}

function clearDocsSearch(){
  document.getElementById('docs-search').value='';
  searchDocs();
}

// --- Chat ---
let chatWs=null;
let chatCurrentConv=null;
let chatCurrentTab='conversations';
let chatConversations=[];
let chatFriends=[];
let chatGroups=[];
let chatMessages=[];
let chatLoadingMore=false;

function initChatWs(){
  if(chatWs&&chatWs.readyState<=1)return;
  const token=getToken();
  if(!token)return;
  const proto=location.protocol==='https:'?'wss:':'ws:';
  chatWs=new WebSocket(proto+'//'+location.host+'/ws/chat?token='+token);
  chatWs.onopen=function(){};
  chatWs.onmessage=function(e){
    try{
      const data=JSON.parse(e.data);
      if(data.type==='new_message'&&chatCurrentConv===data.conversation_id){
        chatMessages.unshift(data.message);
        renderChatMessages();
        // Mark as read
        api('POST','/api/chat/mark-read/'+data.conversation_id);
      }else if(data.type==='friend_request'||data.type==='friend_accepted'||data.type==='group_invite'){
        loadChatNotifications();
        loadChatConversations();
      }
    }catch(err){}
  };
  chatWs.onclose=function(){setTimeout(initChatWs,5000);};
  chatWs.onerror=function(){};
}

async function loadChatPage(){
  initChatWs();
  loadChatConversations();
  loadChatFriends();
  loadChatGroups();
  loadChatNotifications();
}

function switchChatTab(tab){
  chatCurrentTab=tab;
  document.querySelectorAll('.chat-tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===tab));
  document.querySelectorAll('.chat-tab-content').forEach(c=>c.style.display='none');
  document.getElementById('chat-tab-'+tab).style.display='';
}

async function loadChatConversations(){
  const r=await api('GET','/api/chat/conversations');
  if(!r)return;
  chatConversations=r.conversations;
  renderChatConversations();
}

function renderChatConversations(){
  const list=document.getElementById('chat-conversation-list');
  const empty=document.getElementById('no-conversations');
  if(!chatConversations.length){list.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  list.innerHTML=chatConversations.map(c=>{
    const isGroup=c.conv_type==='group';
    const name=isGroup?escapeHtml(c.name||'群组'):escapeHtml(c.other_nickname||c.other_user||'未知');
    const avatarHtml=isGroup
      ?`<span class="material-symbols-outlined">groups</span>`
      :(c.other_avatar?`<img src="${c.other_avatar}?t=${Date.now()}" onerror="this.outerHTML='<span class=\\'material-symbols-outlined\\'>person</span>'">`:`<span class="material-symbols-outlined">person</span>`);
    const lastMsg=c.last_message?formatChatMsgPreview(c.last_message):'';
    const timeStr=c.last_message?timeAgo(c.last_message.created_at):'';
    const unread=c.unread_count?`<span class="chat-unread-badge">${c.unread_count}</span>`:'';
    const active=chatCurrentConv===c.conversation_id?'active':'';
    return `<div class="chat-conv-item ${active}" onclick="openChatConversation('${c.conversation_id}')">
      <div class="chat-conv-avatar">${avatarHtml}</div>
      <div class="chat-conv-info"><div class="chat-conv-name">${name}</div><div class="chat-conv-last">${lastMsg}</div></div>
      <div class="chat-conv-meta"><span class="chat-conv-time">${timeStr}</span>${unread}</div>
    </div>`;
  }).join('');
}

function formatChatMsgPreview(msg){
  if(msg.msg_type==='text')return escapeHtml(msg.content).substring(0,40);
  if(msg.msg_type==='voice')return '[语音消息]';
  if(msg.msg_type==='file')return '[文件] '+escapeHtml(msg.file_name||'');
  return '[消息]';
}

async function openChatConversation(convId){
  chatCurrentConv=convId;
  const conv=chatConversations.find(c=>c.conversation_id===convId);
  // Update header
  const headerInfo=document.getElementById('chat-conv-header-info');
  if(conv){
    const isGroup=conv.conv_type==='group';
    const name=isGroup?conv.name:(conv.other_nickname||conv.other_user||'未知');
    const status=isGroup?`${conv.member_count||0} 成员`:'在线';
    headerInfo.innerHTML=`<div class="chat-conv-header-name">${escapeHtml(name)}</div><div class="chat-conv-header-status">${status}</div>`;
  }
  document.getElementById('chat-no-selection').style.display='none';
  document.getElementById('chat-conversation-view').style.display='flex';
  // Mark as read
  await api('POST','/api/chat/mark-read/'+convId);
  // Load messages
  chatMessages=[];
  await loadChatMessages(convId);
  renderChatConversations();
  // Mobile: show conversation view
  if(window.innerWidth<840){
    document.getElementById('chat-sidebar').style.display='none';
    document.getElementById('chat-back-btn').style.display='flex';
  }
}

function closeChatConversation(){
  chatCurrentConv=null;
  document.getElementById('chat-no-selection').style.display='flex';
  document.getElementById('chat-conversation-view').style.display='none';
  if(window.innerWidth<840){
    document.getElementById('chat-sidebar').style.display='flex';
    document.getElementById('chat-back-btn').style.display='none';
  }
}

async function loadChatMessages(convId,before){
  const params=before?`?limit=50&before=${before}`:'?limit=50';
  const r=await api('GET','/api/chat/messages/'+convId+params);
  if(!r)return;
  if(before){
    chatMessages=chatMessages.concat(r.messages);
  }else{
    chatMessages=r.messages;
  }
  renderChatMessages();
}

function renderChatMessages(){
  const container=document.getElementById('chat-messages');
  if(!chatMessages.length){
    container.innerHTML='<div style="text-align:center;padding:40px;color:var(--md-sys-color-on-surface-variant);font-size:.85rem">暂无消息</div>';
    return;
  }
  // Sort messages: oldest first for display
  const sorted=[...chatMessages].sort((a,b)=>a.created_at-b.created_at);
  container.innerHTML=sorted.map(m=>{
    const isSent=m.sender===currentUser.username;
    const cls=isSent?'sent':'received';
    const avatarHtml=isSent?'':`<div class="chat-msg-avatar"><span class="material-symbols-outlined">person</span></div>`;
    let contentHtml='';
    if(m.msg_type==='text'){
      contentHtml=formatChatText(m.content);
    }else if(m.msg_type==='voice'){
      contentHtml=`<div class="chat-msg-voice" onclick="playVoice(this,'${m.file_url||''}')">
        <span class="material-symbols-outlined" style="font-size:20px">play_circle</span>
        <div class="chat-msg-voice-bar">${Array(8).fill(0).map((_,i)=>`<span style="animation-delay:${i*0.1}s"></span>`).join('')}</div>
        <span class="chat-msg-voice-duration">${m.voice_duration||0}s</span>
      </div>`;
    }else if(m.msg_type==='file'){
      const isImage=/\\.(jpg|jpeg|png|gif|webp|svg)$/i.test(m.file_name||'');
      if(isImage){
        contentHtml=`<img class="chat-msg-image" src="${m.file_url||''}" onclick="viewChatImage(this.src)" loading="lazy" alt="${escapeHtml(m.file_name||'')}">`;
      }else{
        const icon=getFileIcon(m.file_name||'');
        contentHtml=`<div class="chat-msg-file"><span class="material-symbols-outlined chat-msg-file-icon">${icon}</span><div class="chat-msg-file-info"><span class="chat-msg-file-name">${escapeHtml(m.file_name||'文件')}</span><span class="chat-msg-file-size">${formatFileSize(m.file_size||0)}</span></div></div>`;
      }
    }
    const statusIcon=m.status==='read'?'done_all':m.status==='sent'?'done':'schedule';
    const statusHtml=isSent?`<span class="chat-msg-status"><span class="material-symbols-outlined" style="font-size:12px">${statusIcon}</span></span>`:'';
    return `<div class="chat-msg ${cls}">${avatarHtml}<div><div class="chat-msg-bubble">${contentHtml}</div><div class="chat-msg-time">${timeAgo(m.created_at)} ${statusHtml}</div></div></div>`;
  }).join('');
  // Scroll to bottom
  container.scrollTop=container.scrollHeight;
}

function formatChatText(text){
  if(!text)return '';
  let html=escapeHtml(text);
  // Bold: **text**
  html=html.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  // Italic: *text*
  html=html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g,'<em>$1</em>');
  // Links
  html=html.replace(/(https?:\/\/[^\s<]+)/g,'<a href="$1" target="_blank" rel="noopener">$1</a>');
  return html;
}

function getFileIcon(name){
  const ext=name.split('.').pop().toLowerCase();
  const icons={pdf:'picture_as_pdf',doc:'description',docx:'description',xls:'table_chart',xlsx:'table_chart',zip:'folder',rar:'folder',mp3:'audio_file',wav:'audio_file',mp4:'video_file',txt:'article'};
  return icons[ext]||'insert_drive_file';
}

function formatFileSize(bytes){
  if(bytes<1024)return bytes+' B';
  if(bytes<1024*1024)return (bytes/1024).toFixed(1)+' KB';
  return (bytes/(1024*1024)).toFixed(1)+' MB';
}

function handleChatInputKey(e){
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChatMessage();}
}

function autoResizeChatInput(){
  const ta=document.getElementById('chat-input');
  ta.style.height='auto';
  ta.style.height=Math.min(ta.scrollHeight,120)+'px';
}

async function sendChatMessage(){
  if(!chatCurrentConv)return;
  const input=document.getElementById('chat-input');
  const text=input.value.trim();
  if(!text)return;
  input.value='';
  input.style.height='auto';
  await api('POST','/api/chat/messages',{conversation_id:chatCurrentConv,msg_type:'text',content:text});
  await loadChatMessages(chatCurrentConv);
  loadChatConversations();
}

async function triggerFileUpload(){
  document.getElementById('chat-file-input').click();
}

async function onChatFileSelected(e){
  if(!chatCurrentConv)return;
  const files=e.target.files;
  if(!files.length)return;
  for(const file of files){
    const reader=new FileReader();
    reader.onload=async function(ev){
      const base64=ev.target.result;
      const r=await api('POST','/api/chat/upload-file',{file_data:base64,file_name:file.name});
      if(r){
        const isImage=/\\.(jpg|jpeg|png|gif|webp|svg)$/i.test(file.name);
        await api('POST','/api/chat/messages',{
          conversation_id:chatCurrentConv,
          msg_type:'file',
          content:isImage?'[图片]':file.name,
          file_url:r.file_url,
          file_name:file.name,
          file_size:r.file_size
        });
        await loadChatMessages(chatCurrentConv);
        loadChatConversations();
      }
    };
    reader.readAsDataURL(file);
  }
  e.target.value='';
}

let voiceMediaRecorder=null;
let voiceChunks=[];

async function startVoiceRecording(){
  try{
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    voiceChunks=[];
    voiceMediaRecorder=new MediaRecorder(stream);
    voiceMediaRecorder.ondataavailable=e=>{if(e.data.size>0)voiceChunks.push(e.data);};
    voiceMediaRecorder.onstop=async()=>{
      stream.getTracks().forEach(t=>t.stop());
      const blob=new Blob(voiceChunks,{type:'audio/webm'});
      const reader=new FileReader();
      reader.onload=async ev=>{
        const base64=ev.target.result;
        const r=await api('POST','/api/chat/upload-file',{file_data:base64,file_name:'voice.webm'});
        if(r){
          // Calculate duration (rough estimate)
          const duration=Math.max(1,Math.round(blob.size/8000));
          await api('POST','/api/chat/messages',{
            conversation_id:chatCurrentConv,
            msg_type:'voice',
            content:'[语音消息]',
            file_url:r.file_url,
            file_name:'voice.webm',
            file_size:r.file_size,
            voice_duration:duration
          });
          await loadChatMessages(chatCurrentConv);
          loadChatConversations();
        }
      };
      reader.readAsDataURL(blob);
    };
    voiceMediaRecorder.start();
    isRecording=true;
    document.getElementById('chat-voice-btn').classList.add('recording');
  }catch(err){
    showSnackbar('无法访问麦克风');
  }
}

function stopVoiceRecording(){
  if(voiceMediaRecorder&&isRecording){
    voiceMediaRecorder.stop();
    isRecording=false;
    document.getElementById('chat-voice-btn').classList.remove('recording');
  }
}

function playVoice(el,url){
  if(!url)return;
  const audio=new Audio(url);
  audio.play().catch(()=>showSnackbar('播放失败'));
}

function viewChatImage(src){
  // Simple image viewer overlay
  const overlay=document.createElement('div');
  overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.9);z-index:9999;display:flex;align-items:center;justify-content:center;cursor:pointer';
  overlay.onclick=()=>overlay.remove();
  const img=document.createElement('img');
  img.src=src;
  img.style.cssText='max-width:90vw;max-height:90vh;object-fit:contain';
  overlay.appendChild(img);
  // Download button
  const dl=document.createElement('a');
  dl.href=src;dl.download='';dl.style.cssText='position:absolute;bottom:20px;right:20px;color:white;cursor:pointer';
  dl.innerHTML='<span class="material-symbols-outlined" style="font-size:28px">download</span>';
  overlay.appendChild(dl);
  document.body.appendChild(overlay);
}

async function loadChatFriends(){
  const r=await api('GET','/api/chat/friends');
  if(!r)return;
  chatFriends=r.friends;
  renderChatFriends();
}

function renderChatFriends(){
  const list=document.getElementById('chat-friend-list');
  const empty=document.getElementById('no-friends');
  if(!chatFriends.length){list.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  list.innerHTML=chatFriends.map(f=>{
    const avatarHtml=f.avatar?`<img src="${f.avatar}?t=${Date.now()}" onerror="this.outerHTML='<span class=\\'material-symbols-outlined\\'>person</span>'">`:`<span class="material-symbols-outlined">person</span>`;
    return `<div class="chat-friend-item" onclick="openChatWithFriend('${f.username}','${f.conversation_id||''}')">
      <div class="chat-conv-avatar">${avatarHtml}</div>
      <div class="chat-conv-info"><div class="chat-conv-name">${escapeHtml(f.nickname||f.username)}</div></div>
      <button class="md-btn md-btn-text" onclick="event.stopPropagation();removeChatFriend('${f.username}')" style="padding:4px 8px"><span class="material-symbols-outlined" style="font-size:18px">person_remove</span></button>
    </div>`;
  }).join('');
}

async function openChatWithFriend(username,convId){
  if(convId){
    openChatConversation(convId);
  }else{
    // Find or create conversation
    const conv=chatConversations.find(c=>c.conv_type==='private'&&c.other_user===username);
    if(conv){
      openChatConversation(conv.conversation_id);
    }else{
      // Create conversation via friend list
      const r=await api('POST','/api/chat/friend-request',{to_user:username});
      showSnackbar('请先添加好友');
    }
  }
}

async function removeChatFriend(username){
  if(!confirm('确定要删除好友 '+username+' 吗？'))return;
  await api('POST','/api/chat/remove-friend',{username});
  loadChatFriends();
  loadChatConversations();
}

async function loadChatGroups(){
  // Groups are conversations with conv_type==='group'
  chatGroups=chatConversations.filter(c=>c.conv_type==='group');
  renderChatGroups();
}

function renderChatGroups(){
  const list=document.getElementById('chat-group-list');
  const empty=document.getElementById('no-groups');
  if(!chatGroups.length){list.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  list.innerHTML=chatGroups.map(g=>{
    return `<div class="chat-conv-item" onclick="openChatConversation('${g.conversation_id}')">
      <div class="chat-conv-avatar"><span class="material-symbols-outlined">groups</span></div>
      <div class="chat-conv-info"><div class="chat-conv-name">${escapeHtml(g.name||'群组')}</div><div class="chat-conv-last">${g.member_count||0} 成员</div></div>
    </div>`;
  }).join('');
}

async function searchChatUsers(){
  const q=document.getElementById('chat-search-users').value.trim();
  const results=document.getElementById('chat-search-results');
  if(!q){results.style.display='none';return;}
  const r=await api('GET','/api/chat/search-users?q='+encodeURIComponent(q));
  if(!r||!r.users.length){results.style.display='none';return;}
  results.style.display='block';
  results.innerHTML=r.users.map(u=>{
    const avatarHtml=u.avatar?`<img src="${u.avatar}?t=${Date.now()}" onerror="this.outerHTML='<span class=\\'material-symbols-outlined\\'>person</span>'">`:`<span class="material-symbols-outlined">person</span>`;
    const emailHidden=u.email?u.email.replace(/(.{2})(.*)(@.*)/,'$1***$3'):'';
    const isFriend=chatFriends.some(f=>f.username===u.username);
    const addBtn=isFriend?'<span class="md-body-medium" style="color:var(--md-sys-color-primary);font-size:.75rem">已好友</span>'
      :`<button class="md-btn md-btn-tonal" style="padding:4px 10px;font-size:.75rem" onclick="addChatFriend('${u.username}')"><span class="material-symbols-outlined" style="font-size:14px">person_add</span>添加</button>`;
    return `<div class="chat-search-result">
      <div class="chat-conv-avatar">${avatarHtml}</div>
      <div class="chat-search-result-info"><div class="chat-search-result-name">${escapeHtml(u.nickname||u.username)}</div><div class="chat-search-result-email">${emailHidden}</div></div>
      ${addBtn}
    </div>`;
  }).join('');
}

async function addChatFriend(username){
  const r=await api('POST','/api/chat/friend-request',{to_user:username});
  if(r)showSnackbar('好友请求已发送');
}

async function loadChatNotifications(){
  const r1=await api('GET','/api/chat/friend-requests');
  const r2=await api('GET','/api/chat/group-invites');
  const notif=document.getElementById('chat-notifications');
  const friendReqs=r1?r1.requests:[];
  const groupInvs=r2?r2.invites:[];
  if(!friendReqs.length&&!groupInvs.length){notif.style.display='none';return;}
  notif.style.display='block';
  let html='';
  friendReqs.forEach(r=>{
    html+=`<div class="chat-notif-item"><span>${escapeHtml(r.from_nickname||r.from_user)} 请求添加好友</span>
      <button class="md-btn md-btn-filled" style="padding:4px 8px;font-size:.7rem" onclick="acceptFriendReq('${r.request_id}')">接受</button>
      <button class="md-btn md-btn-outlined" style="padding:4px 8px;font-size:.7rem" onclick="rejectFriendReq('${r.request_id}')">拒绝</button></div>`;
  });
  groupInvs.forEach(inv=>{
    html+=`<div class="chat-notif-item"><span>${escapeHtml(inv.from_nickname||inv.from_user)} 邀请你加入 ${escapeHtml(inv.group_name||'群组')}</span>
      <button class="md-btn md-btn-filled" style="padding:4px 8px;font-size:.7rem" onclick="acceptGroupInv('${inv.invite_id}')">接受</button>
      <button class="md-btn md-btn-outlined" style="padding:4px 8px;font-size:.7rem" onclick="rejectGroupInv('${inv.invite_id}')">拒绝</button></div>`;
  });
  document.getElementById('chat-friend-requests').innerHTML=html;
}

async function acceptFriendReq(id){
  await api('POST','/api/chat/friend-request/'+id+'/accept');
  loadChatNotifications();loadChatFriends();loadChatConversations();
}
async function rejectFriendReq(id){
  await api('POST','/api/chat/friend-request/'+id+'/reject');
  loadChatNotifications();
}
async function acceptGroupInv(id){
  await api('POST','/api/chat/group-invite/'+id+'/accept');
  loadChatNotifications();loadChatConversations();loadChatGroups();
}
async function rejectGroupInv(id){
  await api('POST','/api/chat/group-invite/'+id+'/reject');
  loadChatNotifications();
}

function showCreateGroupDialog(){
  const overlay=document.createElement('div');
  overlay.className='md-dialog-overlay show';
  overlay.id='create-group-dialog';
  overlay.innerHTML=`<div class="md-dialog" style="max-width:440px;width:95%">
    <h3 class="md-title-medium">创建群组</h3>
    <div class="md-text-field" style="margin-top:16px"><input type="text" id="new-group-name" placeholder=" " maxlength="30"><label for="new-group-name">群组名称</label></div>
    <div class="md-text-field" style="margin-top:12px"><input type="text" id="new-group-desc" placeholder=" " maxlength="200"><label for="new-group-desc">群组描述</label></div>
    <div class="md-dialog-actions">
      <button class="md-btn md-btn-text" onclick="document.getElementById('create-group-dialog').remove()">取消</button>
      <button class="md-btn md-btn-filled" onclick="createChatGroup()">创建</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
}

async function createChatGroup(){
  const name=document.getElementById('new-group-name').value.trim();
  const desc=document.getElementById('new-group-desc').value.trim();
  if(!name){showSnackbar('请输入群组名称');return;}
  const r=await api('POST','/api/chat/create-group',{name,description:desc});
  if(r){
    showSnackbar('群组创建成功');
    document.getElementById('create-group-dialog').remove();
    loadChatConversations();
    loadChatGroups();
  }
}

async function showConvInfoDialog(){
  if(!chatCurrentConv)return;
  const conv=chatConversations.find(c=>c.conversation_id===chatCurrentConv);
  if(!conv)return;
  const isGroup=conv.conv_type==='group';
  const overlay=document.createElement('div');
  overlay.className='md-dialog-overlay show';
  overlay.id='conv-info-dialog';
  let html=`<div class="md-dialog" style="max-width:440px;width:95%;max-height:80vh;overflow-y:auto">
    <h3 class="md-title-medium">${isGroup?'群组信息':'会话信息'}</h3>`;
  if(isGroup){
    html+=`<div style="margin-top:12px"><p class="md-body-medium">名称: ${escapeHtml(conv.name||'')}</p>
      <p class="md-body-medium on-surface-variant">描述: ${escapeHtml(conv.description||'无')}</p></div>
      <h4 class="md-title-small" style="margin:16px 0 8px">成员</h4>
      <div id="conv-members-list">加载中...</div>
      <div style="margin-top:12px">
        <div class="chat-search-bar" style="margin-bottom:8px">
          <span class="material-symbols-outlined" style="font-size:18px;color:var(--md-sys-color-on-surface-variant)">search</span>
          <label for="invite-user-search" class="sr-only">搜索用户邀请加入</label>
          <input type="text" id="invite-user-search" placeholder="搜索用户邀请加入..." oninput="searchInviteUser()">
        </div>
        <div id="invite-search-results"></div>
      </div>
      <div class="md-dialog-actions" style="flex-direction:column;gap:8px">
        <button class="md-btn md-btn-error" style="width:100%" onclick="leaveChatGroup('${chatCurrentConv}')"><span class="material-symbols-outlined" style="font-size:18px">logout</span>退出群组</button>
        <button class="md-btn md-btn-text" style="width:100%" onclick="document.getElementById('conv-info-dialog').remove()">关闭</button>
      </div>`;
  }else{
    html+=`<p class="md-body-medium" style="margin-top:12px">与 ${escapeHtml(conv.other_nickname||conv.other_user||'未知')} 的对话</p>
      <div class="md-dialog-actions">
        <button class="md-btn md-btn-text" onclick="document.getElementById('conv-info-dialog').remove()">关闭</button>
      </div>`;
  }
  html+=`</div>`;
  overlay.innerHTML=html;
  document.body.appendChild(overlay);
  if(isGroup){
    const r=await api('GET','/api/chat/group-members/'+chatCurrentConv);
    const list=document.getElementById('conv-members-list');
    if(r&&r.members){
      list.innerHTML=r.members.map(m=>{
        const roleIcon=m.role==='owner'?'👑':m.role==='admin'?'⭐':'';
        return `<div class="chat-friend-item" style="padding:6px 8px">
          <div class="chat-conv-avatar" style="width:28px;height:28px"><span class="material-symbols-outlined" style="font-size:14px">person</span></div>
          <span style="font-size:.85rem">${roleIcon} ${escapeHtml(m.nickname||m.username)}</span>
          ${m.role!=='owner'&&conv.creator===currentUser.username?`<button class="md-btn md-btn-text" style="padding:2px 6px;font-size:.7rem;margin-left:auto" onclick="removeGroupMember('${chatCurrentConv}','${m.username}')">移除</button>`:''}
        </div>`;
      }).join('');
    }
  }
}

async function searchInviteUser(){
  const q=document.getElementById('invite-user-search').value.trim();
  const results=document.getElementById('invite-search-results');
  if(!q){results.innerHTML='';return;}
  const r=await api('GET','/api/chat/search-users?q='+encodeURIComponent(q));
  if(!r||!r.users.length){results.innerHTML='<p class="md-body-medium on-surface-variant" style="padding:8px;font-size:.8rem">未找到用户</p>';return;}
  results.innerHTML=r.users.map(u=>`<div class="chat-search-result" style="padding:6px 8px">
    <span style="font-size:.85rem">${escapeHtml(u.nickname||u.username)}</span>
    <button class="md-btn md-btn-tonal" style="padding:4px 8px;font-size:.7rem;margin-left:auto" onclick="inviteUserToGroup('${chatCurrentConv}','${u.username}')">邀请</button>
  </div>`).join('');
}

async function inviteUserToGroup(groupId,username){
  const r=await api('POST','/api/chat/invite-to-group',{group_id:groupId,username});
  if(r)showSnackbar('邀请已发送');
}

async function removeGroupMember(groupId,username){
  if(!confirm('确定要移除 '+username+' 吗？'))return;
  await api('POST','/api/chat/remove-group-member',{group_id:groupId,username});
  showConvInfoDialog();
}

async function leaveChatGroup(groupId){
  if(!confirm('确定要退出该群组吗？'))return;
  await api('POST','/api/chat/leave-group',{group_id:groupId});
  document.getElementById('conv-info-dialog').remove();
  closeChatConversation();
  loadChatConversations();loadChatGroups();
}

// --- Init ---
window.addEventListener('load',function(){
  setTimeout(function(){
    const overlay=document.getElementById('loading-overlay');
    overlay.classList.add('fade-out');
    overlay.addEventListener('transitionend',function(){overlay.style.display='none';},{once:true});
  },300);
  const route=getRouteFromPath();
  if(getToken()){
    api('GET','/api/auth/me').then(r=>{
       if(r){
        currentUser=r;
        updateAdminNav();
        const targetPage=(route.view==='app')?route.page:'devices';
        const extra=route.extra||null;
        const url=extra&&extra.postId?'/discover/'+extra.postId:extra&&extra.username?'/user/'+extra.username:targetPage==='post-editor'?'/discover/new':'/'+targetPage;
        history.replaceState({page:targetPage,extra:extra},'',url);
        showAppView(targetPage,extra);
      }else{
        history.replaceState({page:'login'},'','/login');
        showAuthView('login');
      }
    });
  }else{
    const authPage=(route.page==='register')?'register':'login';
    history.replaceState({page:authPage},'','/'+authPage);
    showAuthView(authPage);
  }
});
</script>
</body>
</html>"""
