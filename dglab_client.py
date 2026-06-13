"""DG-LAB Socket V2 WebSocket 客户端封装。

协议参考: https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE
报文统一为: {type, clientId, targetId, message}
类型: bind / msg / break / error / heartbeat

本模块作为 "第三方终端" 一侧实现:
  1. 连接到中转 WebSocket 服务器, 拿到服务器分配的 clientId (bind, targetId 为空)
  2. 生成给 APP 扫描的二维码内容
  3. APP 扫码绑定后, 服务器再次下发 bind (200) -> 双方互填 clientId/targetId
  4. 之后通过前端协议格式发送指令 (type:1/2/3/4/clientMsg), 由服务器转换为 APP 协议转发

重要: 前端(第三方终端)必须使用前端协议格式发送消息, 中转服务器会将其转换为
APP 可识别的 type:"msg" 格式。直接发送 type:"msg" 会被服务器忽略, APP 无法收到。

前端协议格式:
  - 强度减少: type=1, channel=1|2, message="set channel"
  - 强度增加: type=2, channel=1|2, message="set channel"
  - 强度设置: type=3, channel=1|2, strength=0-200, message="set channel"
  - 直接转发: type=4, message="APP指令" (如 clear-1)
  - 波形发送: type="clientMsg", channel="A"|"B", time=秒数, message="通道:波形JSON"
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

from astrbot.api import logger

QR_PREFIX = "https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#"
DEFAULT_HEARTBEAT_INTERVAL = 60.0


@dataclass
class DGLabState:
    server_url: str = ""  # 形如 ws://host:port  (不含 clientId 路径)
    client_id: str = ""  # 服务器或本地分配的终端 ID
    target_id: str = ""  # APP 端 ID, 绑定后填充
    bound: bool = False
    connected: bool = False
    last_error: str = ""
    on_message: Optional[Callable[[dict], Awaitable[None]]] = field(
        default=None, repr=False
    )

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
    async def connect(
        self, server_url: str, client_id: Optional[str] = None
    ) -> DGLabState:
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

    async def send_strength(self, channel: int, mode: int, value: int) -> None:
        """发送强度控制指令（使用前端协议格式）。

        前端协议:
          mode=0(减少), value=1 → type=1, 服务器转换为 strength-{channel}+0+1
          mode=1(增加), value=1 → type=2, 服务器转换为 strength-{channel}+1+1
          mode=2(设置)          → type=3, 服务器转换为 strength-{channel}+2+{value}
          其他情况              → type=4, 直接转发 strength-{channel}+{mode}+{value}

        Args:
            channel: 1=A通道, 2=B通道
            mode: 0=减少, 1=增加, 2=设置值
            value: 强度值 (0-200)
        """
        if not self.state.bound or not self.state.target_id:
            raise RuntimeError("尚未与 APP 绑定, 无法发送强度指令")
        if not self._ws:
            raise RuntimeError("WebSocket 未连接")
        if not (1 <= channel <= 2):
            raise ValueError("通道必须是 1(A) 或 2(B)")
        if not (0 <= mode <= 2):
            raise ValueError("模式必须是 0(减少)、1(增加) 或 2(设置)")
        if not (0 <= value <= 200):
            raise ValueError("强度值必须在 0-200 范围内")

        # 根据模式选择合适的前端协议类型
        if mode == 2:
            # 设置强度: type=3, 包含 strength 字段
            payload = {
                "type": 3,
                "channel": channel,
                "strength": value,
                "message": "set channel",
                "clientId": self.state.client_id,
                "targetId": self.state.target_id,
            }
            logger.info(
                f"[DGLab] 发送强度设置指令: type=3, channel={channel}, "
                f"strength={value}, targetId={self.state.target_id[:8]}..."
            )
        elif mode in (0, 1) and value == 1:
            # 增加/减少1: 使用 type=1/2 (协议原生支持)
            type_num = mode + 1  # 0→1(减少), 1→2(增加)
            payload = {
                "type": type_num,
                "channel": channel,
                "message": "set channel",
                "clientId": self.state.client_id,
                "targetId": self.state.target_id,
            }
            mode_name = "减少" if mode == 0 else "增加"
            logger.info(
                f"[DGLab] 发送强度{mode_name}指令: type={type_num}, channel={channel}, "
                f"targetId={self.state.target_id[:8]}..."
            )
        else:
            # 自定义步进增加/减少: 使用 type=4 直接转发
            command = f"strength-{channel}+{mode}+{value}"
            payload = {
                "type": 4,
                "message": command,
                "clientId": self.state.client_id,
                "targetId": self.state.target_id,
            }
            mode_name = "减少" if mode == 0 else "增加"
            logger.info(
                f"[DGLab] 发送强度{mode_name}指令(直接转发): type=4, "
                f"command={command}, targetId={self.state.target_id[:8]}..."
            )

        await self._ws.send(json.dumps(payload, ensure_ascii=False))

    async def send_pulse(self, channel: str, message: str, duration: int = 5) -> None:
        """发送波形数据（使用前端协议 clientMsg 格式，由服务器管理定时发送）。

        前端协议:
          type="clientMsg", channel="A"|"B", time=秒数,
          message="{channel}:{波形HEX数组JSON}",
          服务器会加上 pulse- 前缀后按频率定时发送给 APP

        Args:
            channel: "A" 或 "B"
            message: 波形HEX数据的JSON数组字符串
            duration: 持续时长（秒）
        """
        if not self.state.bound or not self.state.target_id:
            raise RuntimeError("尚未与 APP 绑定, 无法发送波形")
        if not self._ws:
            raise RuntimeError("WebSocket 未连接")
        if channel not in ("A", "B"):
            raise ValueError("通道必须是 A 或 B")

        frames = json.loads(message)
        if not frames:
            raise ValueError("波形数据不能为空")

        # 前端协议: type="clientMsg"
        # message 格式: "通道:波形JSON数组"
        pulse_message = f"{channel}:{json.dumps(frames, ensure_ascii=False)}"

        if len(pulse_message) > 1950:
            raise ValueError(f"波形数据过长 ({len(pulse_message)} > 1950), 请减少帧数")

        payload = {
            "type": "clientMsg",
            "channel": channel,
            "time": duration,
            "message": pulse_message,
            "clientId": self.state.client_id,
            "targetId": self.state.target_id,
        }

        logger.info(
            f"[DGLab] 发送波形指令: channel={channel}, duration={duration}s, "
            f"frames={len(frames)}, targetId={self.state.target_id[:8]}..."
        )
        await self._ws.send(json.dumps(payload, ensure_ascii=False))

    async def send_direct(self, message: str) -> None:
        """直接转发 APP 指令（使用前端协议 type=4 格式）。

        服务器会将 message 字段原样作为 type:"msg" 转发给 APP。
        适用于 clear-1, clear-2 等直接指令。

        Args:
            message: APP 协议格式的指令字符串 (如 "clear-1")
        """
        if not self.state.bound or not self.state.target_id:
            raise RuntimeError("尚未与 APP 绑定, 无法发送指令")
        if not self._ws:
            raise RuntimeError("WebSocket 未连接")
        if len(message) > 1950:
            raise ValueError("message 长度不能超过 1950")

        payload = {
            "type": 4,
            "message": message,
            "clientId": self.state.client_id,
            "targetId": self.state.target_id,
        }

        logger.info(
            f"[DGLab] 发送直接转发指令: message={message}, "
            f"targetId={self.state.target_id[:8]}..."
        )
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
