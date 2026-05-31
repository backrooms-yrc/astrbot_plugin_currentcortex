"""DG-LAB WebUI 控制界面

提供基于浏览器的设备控制面板，通过 aiohttp.web 实现 HTTP 服务器。
包含用户认证、设备隔离、权限控制功能。
"""

from typing import Optional
from dataclasses import asdict

from aiohttp import web

from astrbot.api import logger

from .dglab_connection_pool import DeviceConnectionPool, ConnectionStatus
from .dglab_device_store import DeviceStore
from .dglab_commands import WAVE_PRESETS
from .dglab_user_store import UserStore
from .dglab_permission_store import PermissionStore


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
            r.add_post("/api/auth/register", self._handle_register)
            r.add_post("/api/auth/login", self._handle_login)
            r.add_post("/api/auth/logout", self._handle_logout)
            r.add_get("/api/auth/me", self._handle_me)
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

            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self._host, self._port)
            await self._site.start()
            logger.info(f"[DGLab WebUI] 已启动: http://{self._host}:{self._port}")
        except OSError as e:
            logger.error(f"[DGLab WebUI] 启动失败（端口 {self._port} 可能被占用）: {e}")
        except Exception as e:
            logger.error(f"[DGLab WebUI] 启动失败: {e}")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        logger.info("[DGLab WebUI] 已停止")

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

    async def _handle_register(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求体"}, status=400)
        username = body.get("username", "").strip()
        phone = body.get("phone", "").strip()
        qq = body.get("qq", "").strip()
        password = body.get("password", "")
        if not username or not phone or not qq or not password:
            return web.json_response({"error": "所有字段均为必填"}, status=400)
        if len(username) < 2 or len(username) > 20:
            return web.json_response({"error": "用户名长度需在2-20字符之间"}, status=400)
        if len(password) < 6:
            return web.json_response({"error": "密码长度不能少于6位"}, status=400)
        ok, msg = self._user_store.register(username, phone, qq, password)
        if not ok:
            return web.json_response({"error": msg}, status=409)
        return web.json_response({"ok": True, "message": msg})

    async def _handle_login(self, request: web.Request) -> web.Response:
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
        resp.set_cookie("token", token, max_age=7*24*3600, httponly=True, samesite="Lax")
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
        return web.json_response({
            "username": user.username,
            "qq": user.qq,
            "phone": user.phone,
            "public_device": user.public_device,
            "allow_requests": user.allow_requests,
        })

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
                my_devices.append({
                    "user_id": user_id,
                    "server_url": b.server_url,
                    "status": status_info["status"] if status_info else "disconnected",
                    "is_bound": status_info["is_bound"] if status_info else False,
                    "strength_a": feedback["strength_a"] if feedback else 0,
                    "strength_b": feedback["strength_b"] if feedback else 0,
                    "limit_a": feedback["limit_a"] if feedback else 200,
                    "limit_b": feedback["limit_b"] if feedback else 200,
                })

        permitted = self._perm_store.get_my_permissions(username)
        for perm in permitted:
            target_qq = perm.to_qq
            if target_qq in bindings and target_qq != user.qq:
                b = bindings[target_qq]
                status_info = self._pool.get_user_status_info(target_qq)
                feedback = self._pool.get_strength_feedback(target_qq)
                my_devices.append({
                    "user_id": target_qq,
                    "server_url": b.server_url,
                    "status": status_info["status"] if status_info else "disconnected",
                    "is_bound": status_info["is_bound"] if status_info else False,
                    "strength_a": feedback["strength_a"] if feedback else 0,
                    "strength_b": feedback["strength_b"] if feedback else 0,
                    "limit_a": feedback["limit_a"] if feedback else 200,
                    "limit_b": feedback["limit_b"] if feedback else 200,
                    "owner": perm.to_username,
                    "is_permitted": True,
                })

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
            result = await self._pool.send_strength_command(user_id, channel_num, 2, value)
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
            result = await self._pool.send_pulse_command(user_id, channel, pulse_data, duration)
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
                plaza_devices.append({
                    "username": pu["username"],
                    "qq": qq,
                    "status": status_info["status"] if status_info else "disconnected",
                })
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
        return web.json_response({
            "pending": [asdict(r) for r in pending],
            "granted": [asdict(r) for r in granted],
        })

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
        return web.json_response({
            "public_device": user.public_device,
            "allow_requests": user.allow_requests,
        })

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

    async def _handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=INDEX_HTML, content_type="text/html")


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DG-LAB WebUI</title>
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
.main-content{flex:1;overflow-y:auto;padding:24px;padding-bottom:100px}
.page{display:none;opacity:0;transform:translateY(8px)}
.page.active{display:block;animation:pageFadeIn .3s cubic-bezier(0.2,0,0,1) forwards}
.page.fade-out{display:block;animation:pageFadeOut .15s cubic-bezier(0.2,0,0,1) forwards}
@keyframes pageFadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes pageFadeOut{from{opacity:1;transform:translateY(0)}to{opacity:0;transform:translateY(-8px)}}
.page-header{margin-bottom:32px}
.page-header h1{margin-bottom:8px}
.md-card{border-radius:var(--md-sys-shape-corner-medium);padding:24px;margin-bottom:16px}
.md-card-filled{background:var(--md-sys-color-surface-container-high)}
.md-card-outlined{background:var(--md-sys-color-surface-container-low);border:1px solid var(--md-sys-color-outline-variant)}
/* PLACEHOLDER_CSS_2 */
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
.md-dialog-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center;z-index:300}
.md-dialog-overlay.show{display:flex}
.md-dialog{background:var(--md-sys-color-surface-container-high);border-radius:var(--md-sys-shape-corner-extra-large);padding:24px;width:90%;max-width:360px}
.md-dialog h3{margin-bottom:16px}
.md-dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:24px}
.duration-options{display:flex;flex-direction:column;gap:8px}
.duration-option{display:flex;align-items:center;gap:12px;padding:12px;border-radius:var(--md-sys-shape-corner-medium);cursor:pointer;transition:background .2s}
.duration-option:hover{background:var(--md-sys-color-surface-container-highest)}
.duration-option input[type=radio]{accent-color:var(--md-sys-color-primary);width:20px;height:20px}
.section-title{margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid var(--md-sys-color-outline-variant)}
/* Responsive */
@media(min-width:840px){
  .nav-rail{display:flex}
  .nav-bottom{display:none}
  .main-content{padding:40px 48px;padding-bottom:40px}
  .md-snackbar{bottom:32px}
  .page-header h1{font-size:2.8rem}
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
        <p id="auth-subtitle">登录以控制你的 DG-LAB 设备</p>
      </div>
      <form id="auth-form" onsubmit="return handleAuth(event)">
        <div class="md-text-field" id="field-username">
          <input type="text" id="input-username" placeholder=" " required autocomplete="username">
          <label for="input-username">用户名</label>
        </div>
        <div class="md-text-field" id="field-phone" style="display:none">
          <input type="tel" id="input-phone" placeholder=" " autocomplete="tel">
          <label for="input-phone">手机号</label>
        </div>
        <div class="md-text-field" id="field-qq" style="display:none">
          <input type="text" id="input-qq" placeholder=" " autocomplete="off">
          <label for="input-qq">QQ号</label>
        </div>
        <div class="md-text-field">
          <input type="password" id="input-password" placeholder=" " required autocomplete="current-password">
          <label for="input-password">密码</label>
        </div>
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
    <nav class="nav-rail" aria-label="主导航">
      <div class="nav-rail-header">
        <span class="material-symbols-outlined nav-rail-logo">electric_bolt</span>
      </div>
      <div class="nav-rail-items">
        <button class="nav-rail-item active" data-page="devices" onclick="navigate('devices')">
          <span class="material-symbols-outlined">devices</span>
          <span class="nav-label">设备</span>
        </button>
        <button class="nav-rail-item" data-page="plaza" onclick="navigate('plaza')">
          <span class="material-symbols-outlined">explore</span>
          <span class="nav-label">广场</span>
        </button>
        <button class="nav-rail-item" data-page="requests" onclick="navigate('requests')">
          <span class="material-symbols-outlined">assignment</span>
          <span class="nav-label">申请</span>
        </button>
        <button class="nav-rail-item" data-page="settings" onclick="navigate('settings')">
          <span class="material-symbols-outlined">settings</span>
          <span class="nav-label">设置</span>
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
            <div class="settings-label"><span class="md-body-large">QQ号</span></div>
            <span class="md-body-large on-surface-variant" id="settings-qq">-</span>
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
    </main>
    <nav class="nav-bottom" aria-label="主导航">
      <button class="nav-bottom-item active" data-page="devices" onclick="navigate('devices')">
        <span class="material-symbols-outlined">devices</span>
        <span class="nav-label">设备</span>
      </button>
      <button class="nav-bottom-item" data-page="plaza" onclick="navigate('plaza')">
        <span class="material-symbols-outlined">explore</span>
        <span class="nav-label">广场</span>
      </button>
      <button class="nav-bottom-item" data-page="requests" onclick="navigate('requests')">
        <span class="material-symbols-outlined">assignment</span>
        <span class="nav-label">申请</span>
      </button>
      <button class="nav-bottom-item" data-page="settings" onclick="navigate('settings')">
        <span class="material-symbols-outlined">settings</span>
        <span class="nav-label">设置</span>
      </button>
    </nav>
  </div>
</div>

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
function showAuthView(route){
  document.getElementById('auth-view').style.display='';
  document.getElementById('app-view').style.display='none';
  if(refreshInterval){clearInterval(refreshInterval);refreshInterval=null;}
  if(route==='register'){
    if(!isRegisterMode)toggleAuthMode(true);
  }else{
    if(isRegisterMode)toggleAuthMode(true);
  }
}
function showAppView(initialPage){
  document.getElementById('auth-view').style.display='none';
  document.getElementById('app-view').style.display='';
  loadSettings();
  refreshInterval=setInterval(()=>{if(currentPage==='devices')loadDevices();},2000);
  if(initialPage&&initialPage!==currentPage){
    navigateTo(initialPage,false);
  }else{
    loadDevices();
  }
}
function toggleAuthMode(skipPush){
  isRegisterMode=!isRegisterMode;
  document.getElementById('auth-title').textContent=isRegisterMode?'注册':'登录';
  document.getElementById('auth-subtitle').textContent=isRegisterMode?'创建账号以使用 DG-LAB WebUI':'登录以控制你的 DG-LAB 设备';
  document.getElementById('auth-submit-btn').textContent=isRegisterMode?'注册':'登录';
  document.getElementById('auth-switch-text').textContent=isRegisterMode?'已有账号？':'还没有账号？';
  document.getElementById('auth-switch-link').textContent=isRegisterMode?'登录':'注册';
  document.getElementById('field-phone').style.display=isRegisterMode?'':'none';
  document.getElementById('field-qq').style.display=isRegisterMode?'':'none';
  if(isRegisterMode){
    document.getElementById('input-phone').required=true;
    document.getElementById('input-qq').required=true;
  }else{
    document.getElementById('input-phone').required=false;
    document.getElementById('input-qq').required=false;
  }
  if(!skipPush){
    history.pushState({page:isRegisterMode?'register':'login'},'',(isRegisterMode?'/register':'/login'));
  }
}
async function handleAuth(e){
  e.preventDefault();
  const username=document.getElementById('input-username').value.trim();
  const password=document.getElementById('input-password').value;
  if(isRegisterMode){
    const phone=document.getElementById('input-phone').value.trim();
    const qq=document.getElementById('input-qq').value.trim();
    const r=await api('POST','/api/auth/register',{username,phone,qq,password});
    if(r){showSnackbar('注册成功，请登录');toggleAuthMode();}
  }else{
    const r=await api('POST','/api/auth/login',{username,password});
    if(r&&r.token){setToken(r.token);history.pushState({page:'devices'},'','/devices');showAppView('devices');}
  }
  return false;
}
async function logout(){
  await api('POST','/api/auth/logout');
  clearToken();history.pushState({page:'login'},'','/login');showAuthView('login');
}

// --- Navigation ---
const APP_PAGES=['devices','plaza','requests','settings'];

function navigate(page){
  navigateTo(page,true);
}
function navigateTo(page,pushState){
  if(page===currentPage||isTransitioning)return;
  isTransitioning=true;
  const oldPage=document.getElementById('page-'+currentPage);
  const newPage=document.getElementById('page-'+page);
  currentPage=page;
  document.querySelectorAll('.nav-rail-item,.nav-bottom-item').forEach(btn=>{
    btn.classList.toggle('active',btn.dataset.page===page);
  });
  oldPage.classList.remove('active');oldPage.classList.add('fade-out');
  setTimeout(()=>{
    oldPage.classList.remove('fade-out');oldPage.style.display='none';
    newPage.style.display='block';newPage.classList.add('active');
    isTransitioning=false;
  },150);
  if(pushState)history.pushState({page:page},'','/'+page);
  if(page==='devices')loadDevices();
  if(page==='plaza')loadPlaza();
  if(page==='requests')loadRequests();
  if(page==='settings')loadSettings();
}

// --- Routing ---
function getRouteFromPath(){
  const path=window.location.pathname.replace(/^\//,'').replace(/\/$/,'')||'';
  if(APP_PAGES.includes(path))return{view:'app',page:path};
  if(path==='register')return{view:'auth',page:'register'};
  if(path==='login')return{view:'auth',page:'login'};
  return{view:'auto',page:'devices'};
}
window.addEventListener('popstate',function(e){
  const state=e.state;
  if(state&&state.page){
    if(APP_PAGES.includes(state.page)){
      if(!getToken()){showAuthView('login');return;}
      document.getElementById('auth-view').style.display='none';
      document.getElementById('app-view').style.display='';
      navigateTo(state.page,false);
    }else if(state.page==='login'||state.page==='register'){
      showAuthView(state.page);
    }
  }else{
    const route=getRouteFromPath();
    if(route.view==='app'){
      if(!getToken()){showAuthView('login');return;}
      navigateTo(route.page,false);
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
          <input type="range" min="0" max="${d.limit_a}" value="${d.strength_a}" data-uid="${d.user_id}" data-ch="A" oninput="this.parentElement.querySelector('.slider-value').textContent=this.value" onchange="setStrength(this)">
          <span class="slider-value">${d.strength_a}</span>
        </div>
      </div>
      <div class="channel-section">
        <div class="channel-label"><span class="channel-name">B 通道</span><span>${d.strength_b} / ${d.limit_b}</span></div>
        <div class="slider-row">
          <input type="range" min="0" max="${d.limit_b}" value="${d.strength_b}" data-uid="${d.user_id}" data-ch="B" oninput="this.parentElement.querySelector('.slider-value').textContent=this.value" onchange="setStrength(this)">
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
}
function closeDurationDialog(){
  document.getElementById('duration-dialog').classList.remove('show');
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
  document.getElementById('settings-qq').textContent=r.qq;
  document.getElementById('switch-public').checked=r.public_device;
  document.getElementById('switch-requests').checked=r.allow_requests;
}
async function saveSettings(){
  const publicDevice=document.getElementById('switch-public').checked;
  const allowRequests=document.getElementById('switch-requests').checked;
  await api('POST','/api/settings',{public_device:publicDevice,allow_requests:allowRequests});
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
        const targetPage=(route.view==='app')?route.page:'devices';
        history.replaceState({page:targetPage},'','/'+targetPage);
        showAppView(targetPage);
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
