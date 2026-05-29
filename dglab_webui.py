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
<script>
(function(){
  const GOOGLE_FONT='https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap';
  const GOOGLE_ICON='https://fonts.googleapis.com/icon?family=Material+Symbols+Outlined';
  const MIRROR_FONT='https://fonts.loli.net/css2?family=Roboto:wght@400;500;700&display=swap';
  const MIRROR_ICON='https://fonts.loli.net/icon?family=Material+Symbols+Outlined';
  const TIMEOUT=3000;
  function loadCSS(href){
    const l=document.createElement('link');l.rel='stylesheet';l.href=href;
    document.head.appendChild(l);return l;
  }
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
<style>
:root {
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

/* Typography */
.md-display-medium{font-size:2.25rem;font-weight:400;line-height:2.75rem;letter-spacing:0}
.md-title-medium{font-size:1rem;font-weight:500;line-height:1.5rem;letter-spacing:.15px}
.md-body-large{font-size:1rem;font-weight:400;line-height:1.5rem;letter-spacing:.5px}
.md-body-medium{font-size:.875rem;font-weight:400;line-height:1.25rem;letter-spacing:.25px}
.md-label-large{font-size:.875rem;font-weight:500;line-height:1.25rem;letter-spacing:.1px}
.on-surface-variant{color:var(--md-sys-color-on-surface-variant)}

/* App Layout */
.app-layout{display:flex;height:100vh;width:100vw;overflow:hidden}

/* Navigation Rail (Desktop) */
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

/* Bottom Navigation (Mobile) */
.nav-bottom{display:flex;justify-content:space-around;align-items:center;height:80px;background:var(--md-sys-color-surface-container);border-top:1px solid var(--md-sys-color-outline-variant);position:fixed;bottom:0;left:0;right:0;z-index:100}
.nav-bottom-item{display:flex;flex-direction:column;align-items:center;gap:4px;border:none;background:none;cursor:pointer;color:var(--md-sys-color-on-surface-variant);padding:12px 0;min-width:64px;transition:color .2s}
.nav-bottom-item .material-symbols-outlined{width:64px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:16px;transition:background .2s}
.nav-bottom-item .nav-label{font-size:12px;font-weight:500}
.nav-bottom-item.active{color:var(--md-sys-color-on-surface)}
.nav-bottom-item.active .material-symbols-outlined{background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container);font-variation-settings:'FILL' 1}

/* Main Content */
.main-content{flex:1;overflow-y:auto;padding:24px;padding-bottom:100px}
.page{display:none}
.page.active{display:block}
.page-header{margin-bottom:32px}
.page-header h1{margin-bottom:8px}

/* Cards */
.md-card{border-radius:var(--md-sys-shape-corner-medium);padding:24px;margin-bottom:16px}
.md-card-filled{background:var(--md-sys-color-surface-container-high)}
.md-card-outlined{background:var(--md-sys-color-surface-container-low);border:1px solid var(--md-sys-color-outline-variant)}

/* Welcome Page */
.welcome-cards{display:grid;grid-template-columns:1fr;gap:16px}
.welcome-cards .card-icon{font-size:32px;color:var(--md-sys-color-primary);margin-bottom:12px}
.welcome-cards h3{margin-bottom:8px}

/* Device Cards */
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

/* Buttons */
.btn-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.md-btn{padding:10px 16px;border:none;border-radius:20px;cursor:pointer;font-size:.875rem;font-weight:500;letter-spacing:.1px;transition:all .2s;display:inline-flex;align-items:center;gap:6px}
.md-btn:hover{box-shadow:0 1px 3px rgba(0,0,0,.3)}
.md-btn:active{transform:scale(0.97)}
.md-btn-tonal{background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container)}
.md-btn-error{background:var(--md-sys-color-error-container);color:var(--md-sys-color-on-error-container)}
.md-btn-filled{background:var(--md-sys-color-primary);color:var(--md-sys-color-on-primary)}

/* Empty State */
.empty-state{text-align:center;padding:80px 24px}
.empty-icon{font-size:48px;color:var(--md-sys-color-on-surface-variant);margin-bottom:16px}
.empty-state .md-title-medium{margin-bottom:8px}

/* Help Page */
.help-content{max-width:640px}
.help-section{margin-bottom:16px}
.help-section h3{margin-bottom:12px;color:var(--md-sys-color-on-surface)}
.help-steps{padding-left:20px;line-height:2}
.help-steps code,.help-commands code{background:var(--md-sys-color-surface-container-highest);padding:2px 8px;border-radius:4px;font-family:'Roboto Mono',monospace;font-size:.8rem}
.help-presets{display:flex;flex-direction:column;gap:8px}
.help-preset-item{color:var(--md-sys-color-on-surface-variant);line-height:1.6}
.help-commands{display:flex;flex-direction:column;gap:8px;line-height:1.8}

/* Snackbar */
.md-snackbar{position:fixed;bottom:96px;left:50%;transform:translateX(-50%);background:var(--md-sys-color-inverse-surface);color:var(--md-sys-color-inverse-on-surface);padding:14px 24px;border-radius:var(--md-sys-shape-corner-medium);font-size:.875rem;opacity:0;transition:opacity .3s,bottom .3s;pointer-events:none;z-index:200;max-width:90vw;text-align:center;box-shadow:0 3px 5px rgba(0,0,0,.2)}
.md-snackbar.show{opacity:1}

/* Loading Overlay */
.loading-overlay{position:fixed;inset:0;background:var(--md-sys-color-surface);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:9999;transition:opacity .4s cubic-bezier(0.2,0,0,1)}
.loading-overlay.fade-out{opacity:0;pointer-events:none}
.md-circular-progress{width:48px;height:48px;animation:rotate 1.4s linear infinite}
.md-circular-progress circle{stroke:var(--md-sys-color-primary);stroke-width:4;fill:none;stroke-linecap:round;stroke-dasharray:90,150;stroke-dashoffset:0;animation:dash 1.4s ease-in-out infinite}
@keyframes rotate{to{transform:rotate(360deg)}}
@keyframes dash{0%{stroke-dasharray:1,150;stroke-dashoffset:0}50%{stroke-dasharray:90,150;stroke-dashoffset:-35}100%{stroke-dasharray:90,150;stroke-dashoffset:-124}}
.loading-text{margin-top:16px;color:var(--md-sys-color-on-surface-variant);font-size:.875rem}

/* Page Transitions (MD3 Fade Through) */
.page{display:none;opacity:0;transform:translateY(8px)}
.page.active{display:block;animation:pageFadeIn .3s cubic-bezier(0.2,0,0,1) forwards}
.page.fade-out{display:block;animation:pageFadeOut .15s cubic-bezier(0.2,0,0,1) forwards}
@keyframes pageFadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes pageFadeOut{from{opacity:1;transform:translateY(0)}to{opacity:0;transform:translateY(-8px)}}

/* Nav indicator transition */
.nav-rail-item .material-symbols-outlined,.nav-bottom-item .material-symbols-outlined{transition:background .25s cubic-bezier(0.2,0,0,1),color .25s cubic-bezier(0.2,0,0,1)}

/* Responsive: Desktop (>=840px) */
@media(min-width:840px){
  .nav-rail{display:flex}
  .nav-bottom{display:none}
  .main-content{padding:40px 48px;padding-bottom:40px}
  .md-snackbar{bottom:32px}
  .welcome-cards{grid-template-columns:repeat(3,1fr)}
  .page-header h1{font-size:2.8rem}
}
</style>
</head>
<body>
<!-- Loading Overlay -->
<div class="loading-overlay" id="loading-overlay">
  <svg class="md-circular-progress" viewBox="0 0 48 48">
    <circle cx="24" cy="24" r="20"></circle>
  </svg>
  <span class="loading-text">正在加载...</span>
</div>

<div class="app-layout">
  <!-- Desktop Navigation Rail -->
  <nav class="nav-rail" aria-label="主导航">
    <div class="nav-rail-header">
      <span class="material-symbols-outlined nav-rail-logo">electric_bolt</span>
    </div>
    <div class="nav-rail-items">
      <button class="nav-rail-item active" data-page="welcome" onclick="navigate('welcome')">
        <span class="material-symbols-outlined">home</span>
        <span class="nav-label">欢迎</span>
      </button>
      <button class="nav-rail-item" data-page="devices" onclick="navigate('devices')">
        <span class="material-symbols-outlined">devices</span>
        <span class="nav-label">设备</span>
      </button>
      <button class="nav-rail-item" data-page="help" onclick="navigate('help')">
        <span class="material-symbols-outlined">help</span>
        <span class="nav-label">帮助</span>
      </button>
    </div>
  </nav>

  <!-- Main Content -->
  <main class="main-content">
    <!-- Page: Welcome -->
    <section class="page page-welcome active" id="page-welcome">
      <div class="page-header">
        <h1 class="md-display-medium">DG-LAB 控制面板</h1>
        <p class="md-body-large on-surface-variant">通过浏览器远程控制你的 DG-LAB 设备</p>
      </div>
      <div class="welcome-cards">
        <div class="md-card md-card-filled">
          <span class="material-symbols-outlined card-icon">link</span>
          <h3 class="md-title-medium">连接设备</h3>
          <p class="md-body-medium on-surface-variant">通过聊天命令 /dglab bind 绑定设备后，即可在此控制</p>
        </div>
        <div class="md-card md-card-filled">
          <span class="material-symbols-outlined card-icon">tune</span>
          <h3 class="md-title-medium">强度控制</h3>
          <p class="md-body-medium on-surface-variant">实时调节 A/B 通道强度，精确控制 0-200 级别</p>
        </div>
        <div class="md-card md-card-filled">
          <span class="material-symbols-outlined card-icon">waves</span>
          <h3 class="md-title-medium">波形预设</h3>
          <p class="md-body-medium on-surface-variant">内置呼吸、脉冲、波浪等多种波形模式</p>
        </div>
      </div>
    </section>

    <!-- Page: Devices -->
    <section class="page page-devices" id="page-devices">
      <div class="page-header">
        <h1 class="md-display-medium">设备控制</h1>
        <p class="md-body-large on-surface-variant">管理和控制已绑定的设备</p>
      </div>
      <div id="device-list"></div>
      <div id="no-devices" class="empty-state" style="display:none;">
        <span class="material-symbols-outlined empty-icon">devices_off</span>
        <p class="md-title-medium">暂无已绑定设备</p>
        <p class="md-body-medium on-surface-variant">请通过聊天命令 /dglab bind 绑定设备</p>
      </div>
    </section>

    <!-- Page: Help -->
    <section class="page page-help" id="page-help">
      <div class="page-header">
        <h1 class="md-display-medium">使用帮助</h1>
        <p class="md-body-large on-surface-variant">了解如何使用 DG-LAB WebUI</p>
      </div>
      <div class="help-content">
        <div class="md-card md-card-outlined help-section">
          <h3 class="md-title-medium">快速开始</h3>
          <ol class="help-steps md-body-medium">
            <li>在聊天中发送 <code>/dglab bind</code> 命令</li>
            <li>使用 DG-LAB APP 扫描生成的二维码</li>
            <li>绑定成功后，在「设备」页面即可看到设备</li>
            <li>通过滑块和按钮控制设备输出</li>
          </ol>
        </div>
        <div class="md-card md-card-outlined help-section">
          <h3 class="md-title-medium">通道控制</h3>
          <p class="md-body-medium on-surface-variant">每个设备有 A、B 两个独立通道，可分别设置强度（0-200）和波形。拖动滑块即时调节强度，松开后发送指令。</p>
        </div>
        <div class="md-card md-card-outlined help-section">
          <h3 class="md-title-medium">波形预设</h3>
          <div class="help-presets">
            <div class="help-preset-item"><strong>呼吸</strong> — 缓慢渐强渐弱</div>
            <div class="help-preset-item"><strong>脉冲</strong> — 快速间歇脉冲</div>
            <div class="help-preset-item"><strong>波浪</strong> — 连续波浪起伏</div>
            <div class="help-preset-item"><strong>敲击</strong> — 短促有力的单次敲击</div>
            <div class="help-preset-item"><strong>风暴</strong> — 高频持续输出</div>
          </div>
        </div>
        <div class="md-card md-card-outlined help-section">
          <h3 class="md-title-medium">聊天命令参考</h3>
          <div class="help-commands md-body-medium">
            <div><code>/dglab bind [server]</code> — 绑定设备</div>
            <div><code>/dglab unbind</code> — 解绑设备</div>
            <div><code>/dglab strength A 100</code> — 设置A通道强度</div>
            <div><code>/dglab pulse A breathe 5</code> — 发送波形</div>
            <div><code>/dglab stop</code> — 停止所有输出</div>
            <div><code>/dglab status</code> — 查看设备状态</div>
          </div>
        </div>
      </div>
    </section>
  </main>

  <!-- Mobile Bottom Navigation -->
  <nav class="nav-bottom" aria-label="主导航">
    <button class="nav-bottom-item active" data-page="welcome" onclick="navigate('welcome')">
      <span class="material-symbols-outlined">home</span>
      <span class="nav-label">欢迎</span>
    </button>
    <button class="nav-bottom-item" data-page="devices" onclick="navigate('devices')">
      <span class="material-symbols-outlined">devices</span>
      <span class="nav-label">设备</span>
    </button>
    <button class="nav-bottom-item" data-page="help" onclick="navigate('help')">
      <span class="material-symbols-outlined">help</span>
      <span class="nav-label">帮助</span>
    </button>
  </nav>
</div>

<!-- Snackbar -->
<div class="md-snackbar" id="snackbar"></div>

<script>
const PRESETS = [
  {id:'breathe',name:'呼吸',icon:'air'},
  {id:'pulse',name:'脉冲',icon:'electric_bolt'},
  {id:'wave',name:'波浪',icon:'waves'},
  {id:'tap',name:'敲击',icon:'touch_app'},
  {id:'storm',name:'风暴',icon:'thunderstorm'}
];
let devices = [];
let snackTimer = null;
let currentPage = 'welcome';
let isTransitioning = false;

// --- Loading Overlay ---
window.addEventListener('load', function() {
  setTimeout(function() {
    const overlay = document.getElementById('loading-overlay');
    overlay.classList.add('fade-out');
    overlay.addEventListener('transitionend', function() {
      overlay.style.display = 'none';
    }, {once: true});
  }, 300);
});

function showSnackbar(msg) {
  const s = document.getElementById('snackbar');
  s.textContent = msg;
  s.classList.add('show');
  clearTimeout(snackTimer);
  snackTimer = setTimeout(() => s.classList.remove('show'), 3000);
}

async function api(method, path, body) {
  const opts = {method, headers:{'Content-Type':'application/json'}};
  if (body) opts.body = JSON.stringify(body);
  try {
    const r = await fetch(path, opts);
    const data = await r.json();
    if (!r.ok) { showSnackbar(data.error || '请求失败'); return null; }
    return data;
  } catch(e) { return null; }
}

// --- Page Navigation with MD3 Fade Through ---
function navigate(page) {
  if (page === currentPage || isTransitioning) return;
  isTransitioning = true;

  const oldPage = document.getElementById('page-' + currentPage);
  const newPage = document.getElementById('page-' + page);
  currentPage = page;

  // Update nav indicators immediately
  document.querySelectorAll('.nav-rail-item, .nav-bottom-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.page === page);
  });

  // Phase 1: Fade out old page (150ms)
  oldPage.classList.remove('active');
  oldPage.classList.add('fade-out');

  setTimeout(() => {
    oldPage.classList.remove('fade-out');
    oldPage.style.display = 'none';
    // Phase 2: Fade in new page (300ms)
    newPage.style.display = 'block';
    newPage.classList.add('active');
    isTransitioning = false;
  }, 150);

  if (page === 'devices') refresh();
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
    <div class="device-card">
      <div class="device-header">
        <span class="device-id">${d.user_id}</span>
        <span class="status-badge ${statusClass(d.status)}">${statusText(d.status)}</span>
      </div>
      <div class="channel-section">
        <div class="channel-label">
          <span class="channel-name">A 通道</span>
          <span>${d.strength_a} / ${d.limit_a}</span>
        </div>
        <div class="slider-row">
          <input type="range" min="0" max="${d.limit_a}" value="${d.strength_a}"
            data-uid="${d.user_id}" data-ch="A"
            oninput="this.parentElement.querySelector('.slider-value').textContent=this.value"
            onchange="setStrength(this)">
          <span class="slider-value">${d.strength_a}</span>
        </div>
      </div>
      <div class="channel-section">
        <div class="channel-label">
          <span class="channel-name">B 通道</span>
          <span>${d.strength_b} / ${d.limit_b}</span>
        </div>
        <div class="slider-row">
          <input type="range" min="0" max="${d.limit_b}" value="${d.strength_b}"
            data-uid="${d.user_id}" data-ch="B"
            oninput="this.parentElement.querySelector('.slider-value').textContent=this.value"
            onchange="setStrength(this)">
          <span class="slider-value">${d.strength_b}</span>
        </div>
      </div>
      <div class="btn-row">
        ${PRESETS.map(p => `
          <button class="md-btn md-btn-tonal" onclick="sendPulse('${d.user_id}','A','${p.id}')">
            <span class="material-symbols-outlined" style="font-size:18px">${p.icon}</span>${p.name} A
          </button>
          <button class="md-btn md-btn-tonal" onclick="sendPulse('${d.user_id}','B','${p.id}')">
            <span class="material-symbols-outlined" style="font-size:18px">${p.icon}</span>${p.name} B
          </button>
        `).join('')}
        <button class="md-btn md-btn-error" onclick="stopDevice('${d.user_id}')">
          <span class="material-symbols-outlined" style="font-size:18px">stop_circle</span>停止全部
        </button>
      </div>
    </div>
  `).join('');
}

async function setStrength(el) {
  const uid = el.dataset.uid, ch = el.dataset.ch, val = parseInt(el.value);
  const r = await api('POST', '/api/device/'+uid+'/strength', {channel:ch, value:val});
  if (r) showSnackbar(r.message);
}

async function sendPulse(uid, ch, preset) {
  const r = await api('POST', '/api/device/'+uid+'/pulse', {channel:ch, preset:preset, duration:5});
  if (r) showSnackbar(r.message);
}

async function stopDevice(uid) {
  const r = await api('POST', '/api/device/'+uid+'/stop', {});
  if (r) showSnackbar(r.message);
}

async function refresh() {
  const r = await api('GET', '/api/devices');
  if (r) { devices = r.devices; renderDevices(); }
}

refresh();
setInterval(() => { if (currentPage === 'devices') refresh(); }, 2000);
</script>
</body>
</html>"""
