"""DG-LAB WebUI 控制界面

提供基于浏览器的设备控制面板，通过 aiohttp.web 实现 HTTP 服务器。
"""

from typing import Optional

from aiohttp import web

from astrbot.api import logger

from .dglab_connection_pool import DeviceConnectionPool, ConnectionStatus
from .dglab_device_store import DeviceStore
from .dglab_commands import WAVE_PRESETS


class DGLabWebUI:
    def __init__(
        self,
        connection_pool: DeviceConnectionPool,
        device_store: DeviceStore,
        host: str = "0.0.0.0",
        port: int = 9800,
    ):
        self._pool = connection_pool
        self._store = device_store
        self._host = host
        self._port = port
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    async def start(self):
        self._app = web.Application()
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/api/devices", self._handle_list_devices)
        self._app.router.add_get("/api/device/{user_id}/status", self._handle_device_status)
        self._app.router.add_post("/api/device/{user_id}/strength", self._handle_set_strength)
        self._app.router.add_post("/api/device/{user_id}/pulse", self._handle_send_pulse)
        self._app.router.add_post("/api/device/{user_id}/stop", self._handle_stop)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        logger.info(f"[DGLab WebUI] 已启动: http://{self._host}:{self._port}")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        logger.info("[DGLab WebUI] 已停止")

    # --- API Handlers ---

    async def _handle_list_devices(self, request: web.Request) -> web.Response:
        bindings = self._store.list_all_bindings()
        devices = []
        for user_id, b in bindings.items():
            status_info = self._pool.get_user_status_info(user_id)
            feedback = self._pool.get_strength_feedback(user_id)
            devices.append({
                "user_id": user_id,
                "server_url": b.server_url,
                "status": status_info["status"] if status_info else "disconnected",
                "is_bound": status_info["is_bound"] if status_info else False,
                "strength_a": feedback["strength_a"] if feedback else 0,
                "strength_b": feedback["strength_b"] if feedback else 0,
                "limit_a": feedback["limit_a"] if feedback else 200,
                "limit_b": feedback["limit_b"] if feedback else 200,
            })
        return web.json_response({"devices": devices})

    async def _handle_device_status(self, request: web.Request) -> web.Response:
        user_id = request.match_info["user_id"]
        status_info = self._pool.get_user_status_info(user_id)
        feedback = self._pool.get_strength_feedback(user_id)
        if not status_info:
            return web.json_response({"error": "设备未连接"}, status=404)
        result = {**status_info}
        if feedback:
            result.update(feedback)
        return web.json_response(result)

    async def _handle_set_strength(self, request: web.Request) -> web.Response:
        user_id = request.match_info["user_id"]
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
        user_id = request.match_info["user_id"]
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
        user_id = request.match_info["user_id"]
        try:
            result = await self._pool.stop_all(user_id)
            return web.json_response({"ok": True, "message": result})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    # --- HTML Page ---

    async def _handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=INDEX_HTML, content_type="text/html")


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DG-LAB WebUI</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh;padding:20px}
.container{max-width:800px;margin:0 auto}
h1{text-align:center;color:#7c4dff;margin-bottom:24px;font-size:1.8em}
.device-card{background:#16213e;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #0f3460}
.device-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.device-id{font-weight:600;font-size:1.1em;color:#e94560}
.status-badge{padding:4px 10px;border-radius:12px;font-size:0.8em;font-weight:500}
.status-bound{background:#1b5e20;color:#a5d6a7}
.status-connected{background:#e65100;color:#ffcc80}
.status-disconnected{background:#424242;color:#9e9e9e}
.channel-section{margin-bottom:14px}
.channel-label{font-size:0.9em;color:#90caf9;margin-bottom:6px;display:flex;justify-content:space-between}
.slider-row{display:flex;align-items:center;gap:10px}
.slider-row input[type=range]{flex:1;accent-color:#7c4dff;height:6px}
.slider-value{min-width:40px;text-align:right;font-variant-numeric:tabular-nums}
.btn-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.btn{padding:8px 14px;border:none;border-radius:8px;cursor:pointer;font-size:0.85em;font-weight:500;transition:opacity .2s}
.btn:hover{opacity:0.85}
.btn:active{transform:scale(0.96)}
.btn-preset{background:#1a237e;color:#9fa8da}
.btn-stop{background:#b71c1c;color:#ffcdd2}
.btn-channel{background:#004d40;color:#80cbc4;font-size:0.75em;padding:6px 10px}
.empty-state{text-align:center;padding:60px 20px;color:#666}
.empty-state .hint{margin-top:8px;font-size:0.9em;color:#555}
.toast{position:fixed;bottom:20px;right:20px;background:#333;color:#fff;padding:12px 20px;border-radius:8px;opacity:0;transition:opacity .3s;pointer-events:none;z-index:999}
.toast.show{opacity:1}
</style>
</head>
<body>
<div class="container">
<h1>DG-LAB WebUI</h1>
<div id="device-list"></div>
<div id="no-devices" class="empty-state" style="display:none;">
  <p>暂无已绑定设备</p>
  <p class="hint">请通过聊天命令 /dglab bind 绑定设备</p>
</div>
</div>
<div id="toast" class="toast"></div>
<script>
const PRESETS = [
  {id:'breathe',name:'呼吸'},{id:'pulse',name:'脉冲'},
  {id:'wave',name:'波浪'},{id:'tap',name:'敲击'},{id:'storm',name:'风暴'}
];
let devices = [];
let toastTimer = null;

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2500);
}

async function api(method, path, body) {
  const opts = {method, headers:{'Content-Type':'application/json'}};
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  const data = await r.json();
  if (!r.ok) { showToast(data.error || '请求失败'); return null; }
  return data;
}

function statusClass(s) {
  if (s === 'bound') return 'status-bound';
  if (s === 'connected' || s === 'connecting') return 'status-connected';
  return 'status-disconnected';
}
function statusText(s) {
  const m = {bound:'已绑定',connected:'已连接',connecting:'连接中',disconnected:'未连接',error:'错误',reconnecting:'重连中'};
  return m[s] || s;
}

function renderDevices() {
  const list = document.getElementById('device-list');
  const empty = document.getElementById('no-devices');
  if (!devices.length) { list.innerHTML=''; empty.style.display='block'; return; }
  empty.style.display='none';
  list.innerHTML = devices.map(d => `
    <div class="device-card" data-uid="${d.user_id}">
      <div class="device-header">
        <span class="device-id">${d.user_id}</span>
        <span class="status-badge ${statusClass(d.status)}">${statusText(d.status)}</span>
      </div>
      <div class="channel-section">
        <div class="channel-label"><span>A 通道</span><span>${d.strength_a} / ${d.limit_a}</span></div>
        <div class="slider-row">
          <input type="range" min="0" max="${d.limit_a}" value="${d.strength_a}" data-uid="${d.user_id}" data-ch="A" oninput="this.nextElementSibling.textContent=this.value" onchange="setStrength(this)">
          <span class="slider-value">${d.strength_a}</span>
        </div>
      </div>
      <div class="channel-section">
        <div class="channel-label"><span>B 通道</span><span>${d.strength_b} / ${d.limit_b}</span></div>
        <div class="slider-row">
          <input type="range" min="0" max="${d.limit_b}" value="${d.strength_b}" data-uid="${d.user_id}" data-ch="B" oninput="this.nextElementSibling.textContent=this.value" onchange="setStrength(this)">
          <span class="slider-value">${d.strength_b}</span>
        </div>
      </div>
      <div class="btn-row">
        ${PRESETS.map(p => `
          <button class="btn btn-preset" onclick="sendPulse('${d.user_id}','A','${p.id}')">${p.name} A</button>
          <button class="btn btn-preset" onclick="sendPulse('${d.user_id}','B','${p.id}')">${p.name} B</button>
        `).join('')}
        <button class="btn btn-stop" onclick="stopDevice('${d.user_id}')">停止全部</button>
      </div>
    </div>
  `).join('');
}

async function setStrength(el) {
  const uid = el.dataset.uid, ch = el.dataset.ch, val = parseInt(el.value);
  const r = await api('POST', '/api/device/'+uid+'/strength', {channel:ch, value:val});
  if (r) showToast(r.message);
}

async function sendPulse(uid, ch, preset) {
  const r = await api('POST', '/api/device/'+uid+'/pulse', {channel:ch, preset:preset, duration:5});
  if (r) showToast(r.message);
}

async function stopDevice(uid) {
  const r = await api('POST', '/api/device/'+uid+'/stop', {});
  if (r) showToast(r.message);
}

async function refresh() {
  const r = await api('GET', '/api/devices');
  if (r) { devices = r.devices; renderDevices(); }
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>"""
