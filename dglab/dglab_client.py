"""DG-LAB Socket WebSocket 客户端封装（V3 / V4 / 旧 V2 兼容）。

协议参考:
  - V3/V4: https://github.com/dungeonlab-open/dglab-websocket-server
  - SDK 参考: https://github.com/dungeonlab-open/dglab-kit (含 Python 版 dglab-kit-python)
  - 旧 V2: https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE (已移除, 仅作兼容)

官方中转服务器现已只提供 v3-server (端口 9999) 与 v4-server (端口 9998),
本模块按"控制端(第三方终端)"一侧实现, 连接时自动识别协议版本:

  V3 (兼容旧 V2):
    1. 控制端裸连根路径 ws://host:port (V2/V3 服务端均忽略路径中的自选 ID,
       早期实现把自生成 clientId 拼进路径, V3 会把路径误解析为 targetId,
       导致被当成 APP 端拒绝 —— 即 issue #3 的根因)
    2. 服务端下发首个 bind 报文分配 clientId, 控制端以此生成二维码
    3. APP 扫码后连接 ws://host:port/{clientId}, 服务端向双方下发 bind/"200"
    4. 强度/波形经 type 1/2/3/4/clientMsg 由服务端转换为 APP 协议转发
       (注意: V3 中 type 4 不再是原始指令透传, message 含 "clear" 即清通道,
        否则按 channel+strength 设置强度; 旧 V2 服务器则原样转发 message)

  V4:
    1. 控制端连接 ws://host:port (可选 PREFIX 路径), 服务端返回 hello 分配 clientId
    2. 二维码为 https://dungeon-lab.cn/s/?v=1&action=socket&url={ws?tid=clientId},
       需 DG-LAB 4 APP 扫码; APP 接入后控制端收到 client_attached
    3. 通过 message 帧透传 RPC (t:req/resp/ev):
       devices.get 设备发现 / device.op 强度与波形任务 / device.op.clear 清理
    4. V4 透传层不解析设备指令, APP 上报经 devices.snapshot / devices.patch /
       slots.patch / custom.action 事件同步设备与强度状态

前端协议格式(V2/V3):
  - 强度减少: type=1, channel=1|2, message="set channel"
  - 强度增加: type=2, channel=1|2, message="set channel"
  - 强度设置: type=3, channel=1|2, strength=0-200, message="set channel"
  - 通道清理: type=4, channel=1|2, message="clear" (V3) / "clear-N" (V2 原样转发, V3 亦兼容)
  - 波形发送: type="clientMsg", channel="A"|"B", time=秒数, message="通道:波形JSON"
"""

from __future__ import annotations

import asyncio
import itertools
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

try:  # 延迟依赖, 未安装时给出友好提示
    import websockets
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore

from astrbot.api import logger

QR_PREFIX = "https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#"
V4_QR_PREFIX = "https://dungeon-lab.cn/s/?v=1&action=socket&url="
DEFAULT_HEARTBEAT_INTERVAL = 60.0
FIRST_FRAME_TIMEOUT = 5.0

# V4 device.op 动作类型 (见 dglab-kit V4ActionType)
V4_OP_APPEND_PULSE = 0
V4_OP_ADD_INTENSITY = 3
V4_OP_SET_TEMP_INTENSITY = 4
V4_OP_SET_INTENSITY = 7

V4_RESPONSE_TIMEOUT = 8.0
V4_MAX_PULSE_FRAMES = 1000


def _strip_to_root(url: str) -> str:
    """去掉 URL 的路径与查询部分, 仅保留 scheme://host:port (V3 控制端必须裸连)。"""
    idx = url.find("://")
    if idx < 0:
        return url.rstrip("/")
    rest = url[idx + 3:]
    for sep in ("/", "?", "#"):
        rest = rest.split(sep, 1)[0]
    return url[: idx + 3] + rest


@dataclass
class DGLabState:
    server_url: str = ""  # 实际连接成功的中转服务器地址(不含 clientId)
    client_id: str = ""  # 服务器分配的终端 ID
    target_id: str = ""  # APP 端 ID, 绑定后填充
    bound: bool = False
    connected: bool = False
    last_error: str = ""
    protocol: str = ""  # 识别出的协议: "v3"(含旧 v2 兼容路径) / "v4"
    on_message: Optional[Any] = field(default=None, repr=False)
    # V4: 当前被控 APP 上报的设备列表与选中设备
    slot_id: str = ""
    slot_name: str = ""

    @property
    def qr_content(self) -> str:
        if not self.server_url or not self.client_id:
            return ""
        base = self.server_url.rstrip("/")
        if self.protocol == "v4":
            # V4 二维码: 需 DG-LAB 4 APP 扫码, ws 地址需整体 URL 编码
            ws_url = f"{base}?tid={self.client_id}"
            return f"{V4_QR_PREFIX}{quote(ws_url, safe='')}"
        return f"{QR_PREFIX}{base}/{self.client_id}"


class DGLabClient:
    """单事件循环安全的 DG-LAB Socket 客户端(V3/V4 自动识别, 兼容旧 V2)。"""

    def __init__(self, heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL):
        self.state = DGLabState()
        self.heartbeat_interval = heartbeat_interval
        self._ws: Optional[Any] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._hb_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._server_ack = asyncio.Event()
        self._first_frame: Optional[asyncio.Future] = None
        # V4 RPC 状态
        self._v4_req_ids = itertools.count(1)
        self._v4_pending: Dict[Tuple[str, str], asyncio.Future] = {}
        self._v4_devices: list = []  # 被控方上报的设备描述列表
        self._v4_strength: Dict[str, Optional[int]] = {"A": None, "B": None}
        self._v4_limit: Dict[str, Optional[int]] = {"A": None, "B": None}
        self._v4_props_refreshed = False  # 本次绑定周期内是否已主动刷新过设备属性

    # ---------- 连接管理 ----------

    async def connect(
        self,
        server_url: str,
        client_id: Optional[str] = None,
        protocol: str = "auto",
    ) -> DGLabState:
        """连接中转服务器, 自动识别协议版本。

        server_url: ws://host:port 或 wss://host:port (V4 可含路径前缀如 /v4)
        client_id : 忽略 —— V2/V3/V4 服务端均会在连接后分配 clientId
        protocol  : "auto"(默认, 自动识别) / "v3" / "v4"
        """
        if websockets is None:
            raise RuntimeError("未安装 websockets 库, 请先 `pip install websockets`. ")
        await self.close()

        configured = server_url.rstrip("/")
        root = _strip_to_root(configured)
        # auto: 先按 V3 裸连根路径(旧 V2 同样忽略路径), 失败再按配置的原样地址
        # 重试(覆盖 V4 配置了 PREFIX 路径前缀的场景)
        if protocol == "v3":
            candidates = [root]
        elif protocol == "v4":
            candidates = [configured]
        else:
            candidates = [root] if root == configured else [root, configured]

        last_error = ""
        for url in candidates:
            try:
                detected = await self._connect_and_detect(url)
            except Exception as e:
                last_error = str(e) or repr(e)
                logger.info(
                    f"[DGLab] 连接 {url} 失败({last_error}), "
                    f"{'尝试下一个地址' if url != candidates[-1] else '已无备选地址'}"
                )
                continue
            self.state.server_url = url
            self.state.protocol = detected
            self.state.connected = True
            self.state.last_error = ""
            # 启动后台任务
            self._recv_task = asyncio.create_task(self._recv_loop())
            self._hb_task = asyncio.create_task(self._heartbeat_loop())
            logger.info(
                f"[DGLab] 已连接中转服务器 {url} (协议={detected.upper()}, "
                f"clientId={self.state.client_id[:8]}...)"
            )
            return self.state

        self.state.connected = False
        self.state.last_error = last_error or "无法建立 WebSocket 连接"
        raise RuntimeError(self.state.last_error)

    async def _connect_and_detect(self, url: str) -> str:
        """建立连接并等待首个报文, 依据报文类型识别协议。返回 "v3"/"v4"。"""
        ws = await websockets.connect(url, max_size=2 * 1024 * 1024, open_timeout=8)
        try:
            first_raw = await asyncio.wait_for(ws.recv(), timeout=FIRST_FRAME_TIMEOUT)
            frame = json.loads(first_raw)
            if not isinstance(frame, dict):
                raise ValueError("首个报文不是 JSON 对象")
            ftype = frame.get("type")
            if ftype == "hello":
                cid = str(frame.get("clientId", ""))
                if not cid:
                    raise ValueError("hello 报文缺少 clientId")
                self.state.client_id = cid
                self.state.target_id = ""
                self.state.bound = False
                self._server_ack.set()
                self._ws = ws
                return "v4"
            if ftype == "bind":
                cid = str(frame.get("clientId", ""))
                self.state.client_id = cid or str(uuid.uuid4())
                self.state.target_id = ""
                self.state.bound = False
                self._server_ack.set()
                self._ws = ws
                return "v3"
            raise ValueError(f"无法识别的首个报文类型: {ftype!r}")
        except Exception:
            try:
                await ws.close()
            except Exception:
                pass
            raise

    async def close(self):
        """关闭连接并清理所有后台任务。"""
        async with self._lock:
            tasks_to_cancel = []
            for t in (self._recv_task, self._hb_task):
                if t and not t.done():
                    t.cancel()
                    tasks_to_cancel.append(t)
            self._recv_task = self._hb_task = None

            # 等待任务真正结束，避免资源泄漏
            for t in tasks_to_cancel:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

            self._reject_v4_pending(RuntimeError("WebSocket 已断开"))

            if self._ws is not None:
                try:
                    await self._ws.close()
                except Exception:
                    pass
            self._ws = None
            self.state.connected = False
            self.state.bound = False
            self.state.slot_id = ""
            self._v4_devices = []

    # ---------- 收发公共 ----------

    async def _send_json(self, payload: dict) -> None:
        if not self._ws:
            raise RuntimeError("WebSocket 未连接")
        await self._ws.send(json.dumps(payload, ensure_ascii=False))

    async def _send_envelope(self, type_, message: str, target_id: str = "") -> None:
        payload = {
            "type": type_,
            "clientId": self.state.client_id,
            "targetId": target_id or self.state.target_id,
            "message": message,
        }
        await self._send_json(payload)

    def _require_bound(self) -> None:
        if not self.state.bound or not self.state.target_id:
            raise RuntimeError("尚未与 APP 绑定, 无法发送指令")

    # ---------- 指令: 强度 ----------

    async def send_strength(self, channel: int, mode: int, value: int) -> None:
        """发送强度控制指令。

        Args:
            channel: 1=A通道, 2=B通道
            mode: 0=减少, 1=增加, 2=设置值
            value: 强度值 (0-200)
        """
        self._require_bound()
        if not self._ws:
            raise RuntimeError("WebSocket 未连接")
        if not (1 <= channel <= 2):
            raise ValueError("通道必须是 1(A) 或 2(B)")
        if not (0 <= mode <= 2):
            raise ValueError("模式必须是 0(减少)、1(增加) 或 2(设置)")
        if not (0 <= value <= 200):
            raise ValueError("强度值必须在 0-200 范围内")

        if self.state.protocol == "v4":
            await self._v4_send_strength(channel, mode, value)
            return

        # ---- V3 / 旧 V2 ----
        if mode == 2:
            # 设置强度: type=3, V2/V3 语义一致
            await self._send_json(
                {
                    "type": 3,
                    "channel": channel,
                    "strength": value,
                    "message": "set channel",
                    "clientId": self.state.client_id,
                    "targetId": self.state.target_id,
                }
            )
            logger.info(
                f"[DGLab] 发送强度设置指令: type=3, channel={channel}, "
                f"strength={value}, targetId={self.state.target_id[:8]}..."
            )
            return

        if value == 1:
            # 增减 1: type=1/2 协议原生支持
            await self._send_v3_step(channel, mode)
            return

        # 多步增减: V3 的 type=4 不再透传原始 strength-N+mode+val 指令
        # (会被误当作"设置强度"且 strength 缺省为 0, 相当危险),
        # 改为按官方 SDK(dglab-kit)方式拆成多条 type=1/2 报文, V2/V3 均兼容
        for _ in range(value):
            await self._send_v3_step(channel, mode)

    async def _send_v3_step(self, channel: int, mode: int) -> None:
        type_num = mode + 1  # 0→1(减少), 1→2(增加)
        await self._send_json(
            {
                "type": type_num,
                "channel": channel,
                "message": "set channel",
                "clientId": self.state.client_id,
                "targetId": self.state.target_id,
            }
        )

    # ---------- 指令: 波形 ----------

    async def send_pulse(self, channel: str, message: str, duration: int = 5) -> None:
        """发送波形数据。

        Args:
            channel: "A" 或 "B"
            message: 波形HEX数据的JSON数组字符串 (每帧8字节HEX, 代表100ms)
            duration: 持续时长（秒）
        """
        self._require_bound()
        if not self._ws:
            raise RuntimeError("WebSocket 未连接")
        if channel not in ("A", "B"):
            raise ValueError("通道必须是 A 或 B")

        frames = json.loads(message)
        if not frames:
            raise ValueError("波形数据不能为空")

        if self.state.protocol == "v4":
            await self._v4_send_pulse(channel, frames, duration)
            return

        # V3: type="clientMsg", 服务端负责按频率循环补帧定时发送
        pulse_message = f"{channel}:{json.dumps(frames, ensure_ascii=False)}"
        if len(pulse_message) > 1950:
            raise ValueError(f"波形数据过长 ({len(pulse_message)} > 1950), 请减少帧数")

        await self._send_json(
            {
                "type": "clientMsg",
                "channel": channel,
                "time": duration,
                "message": pulse_message,
                "clientId": self.state.client_id,
                "targetId": self.state.target_id,
            }
        )
        logger.info(
            f"[DGLab] 发送波形指令: channel={channel}, duration={duration}s, "
            f"frames={len(frames)}, targetId={self.state.target_id[:8]}..."
        )

    # ---------- 指令: 通道清理 / 直接转发 ----------

    async def send_direct(self, message: str) -> None:
        """清空通道波形队列等指令。

        V2: type=4 原样转发 message 给 APP (如 "clear-1")
        V3: type=4 按 channel 字段清理通道, message 含 "clear" 即可
        V4: 映射为 device.op.clear RPC
        """
        self._require_bound()
        if not self._ws:
            raise RuntimeError("WebSocket 未连接")
        if len(message) > 1950:
            raise ValueError("message 长度不能超过 1950")

        channel = 1
        if message.startswith("clear-"):
            try:
                channel = int(message[len("clear-"):])
            except ValueError:
                channel = 1
        if not (1 <= channel <= 2):
            channel = 1

        if self.state.protocol == "v4":
            await self._v4_clear_channel(channel)
            return

        # channel 字段对 V3 是清理目标通道的依据(缺失会默认 A 通道),
        # 旧 V2 服务器会忽略多余字段并原样转发 message
        await self._send_json(
            {
                "type": 4,
                "channel": channel,
                "message": message,
                "clientId": self.state.client_id,
                "targetId": self.state.target_id,
            }
        )
        logger.info(
            f"[DGLab] 发送通道清理指令: message={message}, channel={channel}, "
            f"targetId={self.state.target_id[:8]}..."
        )

    # ---------- 接收循环 ----------

    async def _recv_loop(self):
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                try:
                    if self.state.protocol == "v4":
                        await self._handle_v4_packet(data)
                    else:
                        await self._handle_v3_packet(data)
                except Exception as e:
                    logger.debug(f"[DGLab] 处理报文异常: {e!r}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.state.last_error = f"recv_loop: {e!r}"
        finally:
            self.state.connected = False
            self.state.bound = False
            self._reject_v4_pending(RuntimeError("WebSocket 已断开"))

    async def _emit(self, data: dict) -> None:
        """将报文(或合成报文)交给上层回调。"""
        if self.state.on_message:
            try:
                await self.state.on_message(data)
            except Exception:
                pass

    # ---------- V3 / 旧 V2 报文处理 ----------

    async def _handle_v3_packet(self, data: dict):
        t = data.get("type")
        msg = str(data.get("message", ""))
        cid = data.get("clientId", "")
        tid = data.get("targetId", "")

        if t == "bind":
            if cid and msg == "targetId":
                # 服务端确认 clientId 注册(重连/覆盖场景下可能再次下发)
                self.state.client_id = cid
                self._server_ack.set()
                return
            if msg == "200":
                self._mark_bound(tid, via="bind/200")
            elif msg in ("400", "401"):
                self.state.bound = False
                self.state.last_error = f"bind {msg}"
        elif t == "break":
            self.state.bound = False
            self.state.target_id = ""
            self.state.last_error = f"break {msg}"
        elif t == "error":
            # 注意: 错误帧携带的 targetId 不可作为绑定凭证
            # (issue #3: V3 服务器对非法连接下发 error/4001 时带 targetId,
            #  旧版误判为绑定成功)
            self.state.last_error = f"error {msg}"
        elif t == "notify":
            # V3 波形发送完毕/覆盖通知, 仅记录
            logger.debug(f"[DGLab] 服务端通知: {msg}")
        elif t == "heartbeat":
            # 兼容性关键: 部分(非完全符合协议文档的)中转服务器在 APP 扫码
            # 配对成功后不下发 bind/"200", 而是通过已填充 targetId 的心跳
            # 隐式告知绑定关系
            if tid:
                self._mark_bound(tid, via="heartbeat")
        elif t == "msg" and tid and not self.state.bound:
            # APP 回传消息带 targetId 同样可作为绑定凭证的二次确认
            self._mark_bound(tid, via="msg")

        await self._emit(data)

    def _mark_bound(self, target_id: str, via: str = "") -> None:
        """记录绑定成功状态。"""
        if not target_id:
            return
        was_unbound = not self.state.bound
        self.state.target_id = target_id
        self.state.bound = True
        self.state.last_error = ""
        if was_unbound:
            logger.info(
                f"[DGLab] 检测到 APP 绑定 (via {via}), "
                f"targetId={target_id[:8]}..."
            )

    # ---------- V4 报文处理 ----------

    async def _handle_v4_packet(self, data: dict):
        t = data.get("type")

        if t == "hello":
            # 连接阶段已处理过 hello, 忽略重复帧
            return
        if t == "client_attached":
            app_id = str(data.get("clientId", ""))
            if not app_id:
                return
            self.state.target_id = app_id
            self.state.bound = True
            self.state.last_error = ""
            self._v4_devices = []
            self.state.slot_id = ""
            self._v4_props_refreshed = False
            logger.info(
                f"[DGLab] 检测到 APP 绑定 (via client_attached), "
                f"targetId={app_id[:8]}..."
            )
            await self._emit(
                {"type": "bind", "targetId": app_id, "message": "200"}
            )
            # 后台拉取设备列表(不阻塞接收循环)
            asyncio.get_running_loop().create_task(self._v4_refresh_devices())
            return
        if t == "client_disconnected":
            app_id = str(data.get("clientId", ""))
            self.state.bound = False
            self.state.target_id = ""
            self.state.slot_id = ""
            self._v4_devices = []
            self._v4_strength = {"A": None, "B": None}
            self._v4_limit = {"A": None, "B": None}
            self._reject_v4_pending(RuntimeError("被控方已断开"), client_id=app_id)
            logger.info(f"[DGLab] APP 已断开 (client_disconnected), targetId={app_id[:8]}...")
            await self._emit({"type": "break", "targetId": app_id, "message": "209"})
            return
        if t == "idle_timeout":
            self.state.last_error = "控制方空闲超时(5分钟内无 APP 接入)"
            return
        if t == "error":
            code = str(data.get("code", "")) or str(data.get("message", ""))
            self.state.last_error = f"error {code}"
            await self._emit({"type": "error", "message": code})
            return
        if t in ("heartbeat", "pong"):
            return
        if t != "message":
            return

        # message 帧: 应用层负载在 data 字段
        payload = data.get("data")
        if not isinstance(payload, dict):
            return

        if payload.get("t") == "resp":
            req_id = str(payload.get("reqId") or payload.get("requestId") or "")
            key = (self.state.target_id, req_id)
            future = self._v4_pending.pop(key, None)
            if future is not None and not future.done():
                err = payload.get("error")
                if err:
                    future.set_exception(RuntimeError(f"V4 指令执行失败: {err}"))
                else:
                    future.set_result(payload.get("result"))
            return

        if payload.get("t") == "ev":
            await self._handle_v4_event(payload)

    async def _handle_v4_event(self, payload: dict):
        ev = payload.get("ev")

        if ev in ("devices.snapshot", "devices.patch"):
            if ev == "devices.snapshot":
                devices = payload.get("devices")
                self._v4_devices = list(devices) if isinstance(devices, list) else []
            else:
                added = payload.get("added")
                if isinstance(added, list):
                    self._v4_devices.extend(d for d in added if isinstance(d, dict))
                removed = payload.get("removed")
                if isinstance(removed, list):
                    self._v4_devices = [
                        d
                        for d in self._v4_devices
                        if d.get("slotId") not in removed
                    ]
            self._pick_v4_slot()
            return

        if ev == "slots.patch":
            slots = payload.get("slots")
            if not isinstance(slots, list):
                return
            strength_changed = False
            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                if self.state.slot_id and slot.get("slotId") != self.state.slot_id:
                    continue
                props = slot.get("props")
                if not isinstance(props, dict):
                    continue
                strength_changed |= self._v4_apply_strength_props(props)
            if strength_changed:
                # 合成 V3 风格强度回传, 供连接池/WebUI 复用现有解析逻辑
                await self._emit(
                    {
                        "type": "msg",
                        "targetId": self.state.target_id,
                        "message": (
                            f"strength-{self._v4_strength['A'] or 0}"
                            f"+{self._v4_strength['B'] or 0}"
                            f"+{self._v4_limit['A'] or 200}"
                            f"+{self._v4_limit['B'] or 200}"
                        ),
                    }
                )
            return

        if ev == "custom.action":
            action = payload.get("action")
            if isinstance(action, int) and 0 <= action <= 9:
                await self._emit(
                    {
                        "type": "msg",
                        "targetId": self.state.target_id,
                        "message": f"feedback-{action}",
                    }
                )
            return

    def _v4_apply_strength_props(self, props: dict) -> bool:
        """从设备属性中提取通道强度/上限(结构以 APP 实现为准, 容错解析)。

        返回是否有强度更新。
        """
        changed = False
        for key, store in (("strength", self._v4_strength), ("softLimit", self._v4_limit)):
            value = props.get(key)
            if isinstance(value, dict):
                for ch, idx in (("A", "A"), ("a", "A"), ("0", "A"), ("B", "B"), ("b", "B"), ("1", "B")):
                    if isinstance(value.get(idx), (int, float)):
                        if store.get(ch) != int(value[idx]):
                            store[ch] = int(value[idx])
                            changed = True
            elif isinstance(value, (int, float)) and key == "strength":
                # 单值无法区分通道, 仅在双通道均未知时无法使用, 跳过
                pass
        return changed

    def _pick_v4_slot(self):
        """从被控方上报的设备中选择控制目标(优先真实连接设备的插槽)。"""
        if not self._v4_devices:
            self.state.slot_id = ""
            self.state.slot_name = ""
            return
        chosen = None
        for device in self._v4_devices:
            if not isinstance(device, dict) or not device.get("slotId"):
                continue
            slot_state = device.get("slotState")
            if isinstance(slot_state, dict) and slot_state.get("hasDevice"):
                chosen = device
                break
        if chosen is None:
            chosen = next(
                (d for d in self._v4_devices if isinstance(d, dict) and d.get("slotId")),
                None,
            )
        if chosen is not None:
            self.state.slot_id = str(chosen["slotId"])
            self.state.slot_name = str(chosen.get("name", ""))
            logger.debug(
                f"[DGLab] V4 选中设备: slot={self.state.slot_id} "
                f"name={self.state.slot_name}"
            )

    # ---------- V4 RPC ----------

    def _v4_next_req_id(self) -> str:
        return f"cc-{next(self._v4_req_ids)}"

    async def _v4_request(
        self, method: str, op_data: Optional[dict] = None, timeout: float = V4_RESPONSE_TIMEOUT
    ) -> Any:
        """发送 V4 RPC 请求并等待响应。"""
        if not self.state.target_id:
            raise RuntimeError("尚未与 APP 绑定, 无法发送指令")
        req_id = self._v4_next_req_id()
        payload = {"t": "req", "reqId": req_id, "m": method}
        if op_data is not None:
            payload["data"] = op_data
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._v4_pending[(self.state.target_id, req_id)] = future
        try:
            await self._send_json(
                {"type": "message", "clientId": self.state.target_id, "data": payload}
            )
        except Exception:
            self._v4_pending.pop((self.state.target_id, req_id), None)
            raise
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._v4_pending.pop((self.state.target_id, req_id), None)
            raise RuntimeError(f"V4 指令 {method} 等待响应超时")

    def _v4_request_fire_and_forget(
        self, method: str, op_data: Optional[dict] = None, timeout: float = 60.0
    ) -> None:
        """发送 V4 RPC 请求但不等待响应(用于波形等长耗时任务), 失败仅记日志。"""
        req_id = self._v4_next_req_id()
        payload = {"t": "req", "reqId": req_id, "m": method}
        if op_data is not None:
            payload["data"] = op_data

        async def _runner():
            if not self.state.target_id:
                return
            key = (self.state.target_id, req_id)
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            self._v4_pending[key] = future
            try:
                await self._send_json(
                    {"type": "message", "clientId": self.state.target_id, "data": payload}
                )
            except Exception as e:
                self._v4_pending.pop(key, None)
                logger.warning(f"[DGLab] V4 任务 {method} 发送失败: {e}")
                return
            try:
                await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError:
                self._v4_pending.pop(key, None)
                logger.warning(f"[DGLab] V4 任务 {method} 等待响应超时")
            except Exception as e:
                logger.warning(f"[DGLab] V4 任务 {method} 执行失败: {e}")

        asyncio.get_running_loop().create_task(_runner())

    def _reject_v4_pending(self, error: Exception, client_id: str = ""):
        for key, future in list(self._v4_pending.items()):
            if client_id and key[0] != client_id:
                continue
            self._v4_pending.pop(key, None)
            if not future.done():
                future.set_exception(error)
                # 取出异常避免 "never retrieved" 告警
                future.exception()

    async def _v4_refresh_devices(self):
        """向被控方请求设备列表(带容错, 失败不影响主流程)。"""
        self._v4_props_refreshed = True
        try:
            result = await self._v4_request("devices.get", timeout=3.0)
        except Exception as e:
            logger.debug(f"[DGLab] V4 devices.get 失败: {e}")
            return
        if isinstance(result, dict) and isinstance(result.get("devices"), list):
            self._v4_devices = list(result["devices"])
            self._pick_v4_slot()
            # 设备快照可能携带 props 强度/上限, 一并解析
            for device in self._v4_devices:
                if (
                    isinstance(device, dict)
                    and device.get("slotId") == self.state.slot_id
                    and isinstance(device.get("props"), dict)
                ):
                    self._v4_apply_strength_props(device["props"])
                    break
            logger.info(
                f"[DGLab] V4 被控方设备列表: "
                f"{[d.get('slotId') for d in self._v4_devices if isinstance(d, dict)]}"
            )

    async def _v4_ensure_slot(self) -> str:
        if self.state.slot_id:
            return self.state.slot_id
        if not self._v4_devices:
            await self._v4_refresh_devices()
        self._pick_v4_slot()
        if not self.state.slot_id:
            raise RuntimeError("被控方未上报可用设备(slotId), 请确认 APP 已连接设备")
        return self.state.slot_id

    # ---------- V4 指令实现 ----------

    async def _v4_send_strength(self, channel: int, mode: int, value: int):
        slot = await self._v4_ensure_slot()
        c = channel - 1  # 1/2 → 0/1
        ch_key = "A" if channel == 1 else "B"

        if mode == 2 and value == 0:
            # 归零: SetIntensity 仅接受 0
            await self._v4_request(
                "device.op",
                {"s": slot, "t": V4_OP_SET_INTENSITY, "c": c, "v": 0},
            )
            self._v4_strength[ch_key] = 0
            logger.info(f"[DGLab] V4 强度归零: slot={slot}, channel={ch_key}")
            return

        if mode in (0, 1):
            # 相对增减: AddIntensity 支持负值
            delta = value if mode == 1 else -value
            await self._v4_request(
                "device.op", {"s": slot, "t": V4_OP_ADD_INTENSITY, "c": c, "v": delta}
            )
            cur = self._v4_strength[ch_key]
            if cur is not None:
                self._v4_strength[ch_key] = max(0, min(200, cur + delta))
            mode_name = "增加" if mode == 1 else "减少"
            logger.info(
                f"[DGLab] V4 强度{mode_name}: slot={slot}, channel={ch_key}, delta={delta}"
            )
            return

        # 绝对强度设置: SetIntensity 仅支持 0, 需按当前强度换算增量
        cur = self._v4_strength[ch_key]
        if cur is None and not self._v4_props_refreshed:
            # 每个绑定周期最多主动刷新一次设备属性快照, 避免命令重试时反复等待
            await self._v4_refresh_devices()
            cur = self._v4_strength[ch_key]
        if cur is not None:
            delta = value - cur
            if delta == 0:
                logger.info(f"[DGLab] V4 强度已是 {value}, 无需调整")
                return
            await self._v4_request(
                "device.op",
                {"s": slot, "t": V4_OP_ADD_INTENSITY, "c": c, "v": delta},
            )
            self._v4_strength[ch_key] = value
            logger.info(
                f"[DGLab] V4 强度设置: slot={slot}, channel={ch_key}, "
                f"{cur} -> {value} (delta={delta})"
            )
        else:
            # 被控方未上报当前强度, 退化为临时强度任务(不设持续时间即长期生效)
            await self._v4_request(
                "device.op",
                {"s": slot, "t": V4_OP_SET_TEMP_INTENSITY, "c": c, "v": value},
            )
            logger.info(
                f"[DGLab] V4 强度设置(临时强度兜底): slot={slot}, "
                f"channel={ch_key}, value={value}"
            )

    async def _v4_send_pulse(self, channel: str, frames: list, duration: int):
        slot = await self._v4_ensure_slot()
        c = 0 if channel == "A" else 1
        # V3 服务端会把波形帧循环补齐到 time 时长, V4 由控制端自行补帧
        total = min(duration * 10, V4_MAX_PULSE_FRAMES)
        if total < 1:
            total = 1
        expanded = [frames[i % len(frames)] for i in range(total)]
        # device.op 为任务式 RPC, 波形任务持续期间不返回响应, 后台等待即可
        self._v4_request_fire_and_forget(
            "device.op",
            {
                "s": slot,
                "t": V4_OP_APPEND_PULSE,
                "c": c,
                "d": duration * 1000,
                "im": True,
                "v": expanded,
            },
            timeout=duration + 10.0,
        )
        logger.info(
            f"[DGLab] V4 发送波形指令: slot={slot}, channel={channel}, "
            f"duration={duration}s, frames={len(expanded)}"
        )

    async def _v4_clear_channel(self, channel: int):
        slot = await self._v4_ensure_slot()
        await self._v4_request(
            "device.op.clear", {"s": slot, "c": channel - 1}
        )
        logger.info(f"[DGLab] V4 清理通道任务: slot={slot}, channel={'AB'[channel - 1]}")

    # ---------- 心跳 ----------

    async def _heartbeat_loop(self):
        """定期发送心跳，连接断开或被取消时退出。

        - V3/V2: 心跳需携带完整四字段(未绑定时 targetId 为空会被 V3 服务端
          判为 403 错误帧), 因此仅在绑定成功后发送
        - V4: 发送应用层 {"type":"ping"} 探测(服务端回 pong), 与绑定无关
        """
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                if not self.state.connected:
                    break
                try:
                    if self.state.protocol == "v4":
                        await self._send_json({"type": "ping"})
                    elif self.state.bound and self.state.target_id:
                        await self._send_envelope("heartbeat", "200")
                except Exception as e:
                    self.state.last_error = f"heartbeat: {e!r}"
                    break
        except asyncio.CancelledError:
            pass
