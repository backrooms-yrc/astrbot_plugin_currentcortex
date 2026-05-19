"""DG-LAB Socket V2 WebSocket 客户端封装。

协议参考: https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE
报文统一为: {type, clientId, targetId, message}
类型: bind / msg / break / error / heartbeat

本模块作为 "第三方终端" 一侧实现:
  1. 连接到中转 WebSocket 服务器, 拿到服务器分配的 clientId (bind, targetId 为空)
  2. 生成给 APP 扫描的二维码内容
  3. APP 扫码绑定后, 服务器再次下发 bind (200) -> 双方互填 clientId/targetId
  4. 之后可通过 send_message() 透传字符串形式的指令到 APP (例如强度/波形)

注意: 本模块仅负责 WebSocket 通道的可靠传输, 不解析具体郊狼指令字符串。
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

try:  # 延迟依赖, 未安装时给出友好提示
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore
    WebSocketClientProtocol = object  # type: ignore

QR_PREFIX = "https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#"
DEFAULT_HEARTBEAT_INTERVAL = 60.0


@dataclass
class DGLabState:
    server_url: str = ""          # 形如 ws://host:port  (不含 clientId 路径)
    client_id: str = ""            # 服务器或本地分配的终端 ID
    target_id: str = ""            # APP 端 ID, 绑定后填充
    bound: bool = False
    connected: bool = False
    last_error: str = ""
    on_message: Optional[Callable[[dict], Awaitable[None]]] = field(default=None, repr=False)

    @property
    def qr_content(self) -> str:
        if not self.server_url or not self.client_id:
            return ""
        base = self.server_url.rstrip("/")
        return f"{QR_PREFIX}{base}/{self.client_id}"


class DGLabClient:
    """线程安全 (单事件循环) 的 DG-LAB Socket V2 客户端。"""

    def __init__(self, heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL):
        self.state = DGLabState()
        self.heartbeat_interval = heartbeat_interval
        self._ws: Optional[WebSocketClientProtocol] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._hb_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._server_ack = asyncio.Event()

    # ---------- 连接管理 ----------
    async def connect(self, server_url: str, client_id: Optional[str] = None) -> DGLabState:
        """连接到中转服务器。

        server_url: ws://host:port 或 wss://host:port (不要带 clientId 路径)
        client_id : 可选, 自带 clientId 复用; 否则使用 uuid4 生成 (服务器也可能改写)
        """
        if websockets is None:
            raise RuntimeError("未安装 websockets 库, 请先 `pip install websockets`. ")
        await self.close()
        cid = client_id or str(uuid.uuid4())
        url = server_url.rstrip("/") + "/" + cid
        self._ws = await websockets.connect(url, max_size=2 * 1024 * 1024)
        self.state.server_url = server_url.rstrip("/")
        self.state.client_id = cid
        self.state.target_id = ""
        self.state.bound = False
        self.state.connected = True
        self.state.last_error = ""
        self._server_ack.clear()
        # 启动后台任务
        self._recv_task = asyncio.create_task(self._recv_loop())
        self._hb_task = asyncio.create_task(self._heartbeat_loop())
        # 等待服务器首个 bind 报文 (包含真实 clientId), 最多 5s
        try:
            await asyncio.wait_for(self._wait_until_first_bind(), timeout=5.0)
        except asyncio.TimeoutError:
            self.state.last_error = "等待服务器分配 clientId 超时"
        return self.state

    async def _wait_until_first_bind(self):
        # 等待服务器下发首个 bind 报文确认 clientId 已注册
        await self._server_ack.wait()

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

            if self._ws is not None:
                try:
                    await self._ws.close()
                except Exception:
                    pass
            self._ws = None
            self.state.connected = False
            self.state.bound = False

    # ---------- 收发 ----------
    async def _send_envelope(self, type_, message: str, target_id: str = "") -> None:
        if not self._ws:
            raise RuntimeError("WebSocket 未连接")
        payload = {
            "type": type_,
            "clientId": self.state.client_id,
            "targetId": target_id or self.state.target_id,
            "message": message,
        }
        await self._ws.send(json.dumps(payload, ensure_ascii=False))

    async def send_message(self, message: str) -> None:
        """向已绑定的 APP 透传 message 字符串 (例如强度/波形指令)。"""
        if not self.state.bound or not self.state.target_id:
            raise RuntimeError("尚未与 APP 绑定, 无法发送 msg")
        if len(message) > 1950:
            raise ValueError("message 长度不能超过 1950")
        await self._send_envelope(4, message)

    async def send_pulse(self, channel: str, message: str, duration: int = 5) -> None:
        """通过 clientMsg 类型发送波形数据（服务端管理队列和发送频率）。"""
        if not self.state.bound or not self.state.target_id:
            raise RuntimeError("尚未与 APP 绑定, 无法发送波形")
        if not self._ws:
            raise RuntimeError("WebSocket 未连接")
        payload = {
            "type": "clientMsg",
            "clientId": self.state.client_id,
            "targetId": self.state.target_id,
            "channel": channel,
            "time": duration,
            "message": message,
        }
        await self._ws.send(json.dumps(payload, ensure_ascii=False))

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
                await self._handle_packet(data)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.state.last_error = f"recv_loop: {e!r}"
        finally:
            self.state.connected = False
            self.state.bound = False

    async def _handle_packet(self, data: dict):
        t = data.get("type")
        msg = str(data.get("message", ""))
        cid = data.get("clientId", "")
        tid = data.get("targetId", "")
        if t == "bind":
            if cid:
                self.state.client_id = cid
            if msg == "targetId":
                # 服务器确认 clientId 已注册, 等待 APP 扫码
                self.state.target_id = ""
                self.state.bound = False
                self._server_ack.set()
            elif msg == "200":
                self.state.target_id = tid
                self.state.bound = True
            elif msg in ("400", "401"):
                self.state.bound = False
                self.state.last_error = f"bind {msg}"
        elif t == "break":
            self.state.bound = False
            self.state.target_id = ""
            self.state.last_error = f"break {msg}"
        elif t == "error":
            self.state.last_error = f"error {msg}"
        # heartbeat / msg 交给上层回调
        if self.state.on_message:
            try:
                await self.state.on_message(data)
            except Exception:
                pass

    async def _heartbeat_loop(self):
        """定期发送心跳，连接断开或被取消时退出。"""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                # 连接已断开则退出
                if not self.state.connected:
                    break
                try:
                    await self._send_envelope("heartbeat", "200")
                except Exception as e:
                    self.state.last_error = f"heartbeat: {e!r}"
                    break
        except asyncio.CancelledError:
            pass

