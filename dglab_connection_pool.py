"""DG-LAB 设备连接池与状态管理系统

功能:
- 多用户并发连接管理
- 连接复用与生命周期管理
- 自动重连机制
- 操作隔离与队列
- 超时控制与异常恢复
"""

import asyncio
import json
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from astrbot.api import logger

from .dglab_client import DGLabClient, DGLabState
from .dglab_device_store import DeviceStore, DeviceBinding


class ConnectionStatus(Enum):
    """连接状态枚举"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"  # 已连接服务器，等待APP绑定
    BOUND = "bound"  # 已与APP绑定，可通信
    ERROR = "error"  # 错误状态
    RECONNECTING = "reconnecting"


@dataclass
class ConnectionInfo:
    """连接信息"""

    user_id: str
    client: DGLabClient
    status: ConnectionStatus
    created_at: float  # 创建时间戳
    last_used_at: float  # 最后使用时间戳
    error_count: int = 0  # 连续错误次数
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    reconnect_task: Optional[asyncio.Task] = None
    # APP 回传的实时强度/上限数据
    strength_a: int = 0
    strength_b: int = 0
    limit_a: int = 200
    limit_b: int = 200
    last_feedback_button: int = -1  # 最近一次反馈按钮角标 (0-9)
    last_feedback_time: Optional[float] = None


class DeviceConnectionPool:
    """DG-LAB设备连接池
    特性:
    1. 每个用户维护独立连接，实现操作隔离
    2. 连接复用：相同server_url+client_id的连接可复用
    3. 自动心跳保活
    4. 异常自动重连（指数退避）
    5. 空闲连接清理（防止资源泄漏）
    6. 超时保护（防止长时间阻塞）
    """

    def __init__(
        self,
        device_store: DeviceStore,
        max_connections: int = 50,
        idle_timeout: int = 300,
        max_reconnect_attempts: int = 3,
        operation_timeout: float = 10.0,
    ):
        self._store = device_store
        self._max_connections = max_connections
        self._idle_timeout = idle_timeout  # 空闲超时（秒）
        self._max_reconnect_attempts = max_reconnect_attempts
        self._operation_timeout = operation_timeout

        self._connections: Dict[str, ConnectionInfo] = {}
        self._global_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """启动连接池（启动后台清理任务）"""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("[DGLab] 连接池已启动")

    async def stop(self):
        """停止连接池（关闭所有连接）"""
        self._running = False

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except (asyncio.CancelledError, Exception):
                pass
            self._cleanup_task = None

        # 获取所有用户ID的快照再逐个关闭，避免迭代时修改字典
        async with self._global_lock:
            user_ids = list(self._connections.keys())

        for user_id in user_ids:
            await self._close_connection(user_id)

        logger.info("[DGLab] 连接池已停止，所有连接已关闭")

    async def get_or_create_connection(
        self,
        user_id: str,
        server_url: str,
        client_id: Optional[str] = None,
        heartbeat_interval: float = 60.0,
    ) -> Tuple[DGLabClient, ConnectionStatus]:
        """获取或创建用户连接（带超时保护）"""
        async with self._global_lock:
            if user_id in self._connections:
                conn_info = self._connections[user_id]
                conn_info.last_used_at = time.time()

                # 如果已有连接指向不同的服务器，关闭旧连接重建
                existing_url = conn_info.client.state.server_url
                if existing_url and existing_url != server_url.rstrip("/"):
                    logger.info(
                        f"[DGLab] 用户 {user_id} 服务器地址变更 "
                        f"({existing_url} -> {server_url})，重建连接"
                    )
                    await self._close_connection_unlocked(user_id)
                elif conn_info.status in (
                    ConnectionStatus.BOUND,
                    ConnectionStatus.CONNECTED,
                    ConnectionStatus.CONNECTING,
                ):
                    return conn_info.client, conn_info.status
                else:
                    # ERROR / DISCONNECTED / RECONNECTING -> 关闭旧连接再重建
                    await self._close_connection_unlocked(user_id)

            if len(self._connections) >= self._max_connections:
                raise RuntimeError(
                    f"连接池已达上限 ({self._max_connections})，请稍后重试"
                )

            client = DGLabClient(heartbeat_interval=heartbeat_interval)
            conn_info = ConnectionInfo(
                user_id=user_id,
                client=client,
                status=ConnectionStatus.CONNECTING,
                created_at=time.time(),
                last_used_at=time.time(),
            )
            self._connections[user_id] = conn_info

        try:
            state = await asyncio.wait_for(
                client.connect(server_url, client_id), timeout=self._operation_timeout
            )

            conn_info.status = (
                ConnectionStatus.BOUND if state.bound else ConnectionStatus.CONNECTED
            )

            if state.bound:
                self._store.update_last_active(user_id)

            client.state.on_message = self._make_state_sync_callback(user_id, conn_info)

            logger.info(
                f"[DGLab] 用户 {user_id} 连接成功 (status={conn_info.status.value})"
            )
            return client, conn_info.status

        except Exception as e:
            conn_info.status = ConnectionStatus.ERROR
            conn_info.error_count += 1
            logger.error(f"[DGLab] 用户 {user_id} 连接失败: {e}")
            raise

    def _make_state_sync_callback(self, user_id: str, conn_info: "ConnectionInfo"):
        """创建状态同步回调，将客户端事件同步到连接池和持久化存储"""

        async def _on_message(data: dict):
            pkt_type = data.get("type")
            msg = str(data.get("message", ""))
            tid = data.get("targetId", "")

            if pkt_type == "bind" and msg == "200":
                conn_info.status = ConnectionStatus.BOUND
                conn_info.last_used_at = time.time()
                self._store.update_target_id(user_id, tid)
                self._store.update_last_active(user_id)
                logger.info(
                    f"[DGLab] 用户 {user_id} APP已扫码绑定成功 (target={tid[:8]}...)"
                )

            elif pkt_type == "break":
                conn_info.status = ConnectionStatus.CONNECTED
                self._store.update_target_id(user_id, "")
                logger.info(f"[DGLab] 用户 {user_id} APP已断开连接")

            elif pkt_type == "error":
                conn_info.error_count += 1
                logger.warning(f"[DGLab] 用户 {user_id} 收到错误: {msg}")

            elif pkt_type == "msg":
                logger.debug(f"[DGLab] 用户 {user_id} 收到APP消息: {msg[:100]}")
                self._parse_app_message(conn_info, msg)

        return _on_message

    def _parse_app_message(self, conn_info: "ConnectionInfo", msg: str):
        """解析 APP 回传的 msg 消息（强度回传、反馈按钮等）"""
        if msg.startswith("strength-"):
            # 格式: strength-A强度+B强度+A上限+B上限
            parts = msg[len("strength-") :].split("+")
            if len(parts) == 4:
                try:
                    conn_info.strength_a = int(parts[0])
                    conn_info.strength_b = int(parts[1])
                    conn_info.limit_a = int(parts[2])
                    conn_info.limit_b = int(parts[3])
                except ValueError:
                    pass
        elif msg.startswith("feedback-"):
            try:
                btn = int(msg[len("feedback-") :])
                conn_info.last_feedback_button = btn
                conn_info.last_feedback_time = time.time()
            except ValueError:
                pass

    async def execute_with_retry(
        self,
        user_id: str,
        operation: callable,
        max_retries: int = 2,
    ):
        """带重试的操作执行（自动处理断线重连）"""
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                conn_info = self._connections.get(user_id)
                if not conn_info:
                    raise RuntimeError(f"用户 {user_id} 未建立连接")

                if conn_info.status != ConnectionStatus.BOUND:
                    if attempt < max_retries:
                        logger.warning(
                            f"[DGLab] 用户 {user_id} 未绑定，尝试重新连接..."
                        )
                        await self._reconnect_user(user_id)
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    else:
                        raise RuntimeError("设备未绑定或已离线，请重新扫码绑定")

                async with conn_info.lock:
                    result = await asyncio.wait_for(
                        operation(conn_info.client), timeout=self._operation_timeout
                    )

                    conn_info.last_used_at = time.time()
                    conn_info.error_count = 0
                    return result

            except asyncio.TimeoutError:
                last_error = f"操作超时 ({self._operation_timeout}s)"
                logger.warning(
                    f"[DGLab] 用户 {user_id} 操作超时 (attempt {attempt + 1}/{max_retries + 1})"
                )

            except Exception as e:
                last_error = str(e)
                logger.error(
                    f"[DGLab] 用户 {user_id} 操作失败 (attempt {attempt + 1}): {e}"
                )

                if "尚未与 APP 绑定" in str(e) or "WebSocket 未连接" in str(e):
                    if conn_info:
                        conn_info.status = ConnectionStatus.ERROR
                    if attempt < max_retries:
                        await self._reconnect_user(user_id)
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue

        raise RuntimeError(f"操作失败（已重试{max_retries + 1}次）: {last_error}")

    async def send_strength_command(
        self,
        user_id: str,
        channel: int,
        mode: int,
        value: int,
    ) -> str:
        """发送强度控制命令（使用前端协议格式 type=1/2/3）

        Args:
            channel: 1=A通道, 2=B通道
            mode: 0=减少, 1=增加, 2=设置值
            value: 强度值 (0-200)

        Returns:
            命令执行结果描述
        """
        if not (1 <= channel <= 2):
            raise ValueError("通道参数错误，必须是 1(A通道) 或 2(B通道)")
        if not (0 <= mode <= 2):
            raise ValueError("模式参数错误，必须是 0(减少)、1(增加) 或 2(设置)")
        if not (0 <= value <= 200):
            raise ValueError("强度值必须在 0-200 范围内")

        channel_name = {1: "A", 2: "B"}.get(channel, f"未知通道({channel})")
        logger.info(
            f"[DGLab] 准备发送强度指令: user={user_id}, channel={channel_name}, "
            f"mode={mode}, value={value}"
        )

        async def _send(client: DGLabClient):
            await client.send_strength(channel, mode, value)

        await self.execute_with_retry(user_id, _send)

        mode_desc = {0: "减少", 1: "增加", 2: "设置"}.get(mode, f"未知模式({mode})")

        if mode == 2:
            return f"✅ 已将{channel_name}通道强度设置为 {value}"
        elif mode == 1:
            return f"✅ 已将{channel_name}通道强度增加 {value}"
        else:
            return f"✅ 已将{channel_name}通道强度减少 {value}"

    async def send_pulse_command(
        self,
        user_id: str,
        channel: str,
        pulse_data: list,
        duration: int = 5,
    ) -> str:
        """发送波形数据（使用前端协议 clientMsg 格式，由服务器管理定时发送）

        Args:
            channel: "A" 或 "B"
            pulse_data: 波形HEX数据列表（每条8字节HEX，代表100ms）
            duration: 持续发送时长（秒）
        """
        if channel not in ("A", "B"):
            raise ValueError("通道必须是 A 或 B")
        if not pulse_data:
            raise ValueError("波形数据不能为空")
        if len(pulse_data) > 100:
            raise ValueError("波形数据过长（最大100条）")

        logger.info(
            f"[DGLab] 准备发送波形指令: user={user_id}, channel={channel}, "
            f"frames={len(pulse_data)}, duration={duration}s"
        )

        pulse_json = json.dumps(pulse_data, ensure_ascii=False)

        async def _send(client: DGLabClient):
            await client.send_pulse(channel, pulse_json, duration)

        await self.execute_with_retry(user_id, _send)
        return f"✅ 已向{channel}通道发送波形数据（持续{duration}秒）"

    async def clear_channel(self, user_id: str, channel: int) -> str:
        """清空指定通道波形队列（使用前端协议 type=4 直接转发）"""
        if not (1 <= channel <= 2):
            raise ValueError("通道参数错误")

        command = f"clear-{channel}"
        channel_name = {1: "A", 2: "B"}.get(channel, f"未知通道({channel})")

        logger.info(
            f"[DGLab] 准备发送清空指令: user={user_id}, channel={channel_name}, cmd={command}"
        )

        async def _send(client: DGLabClient):
            await client.send_direct(command)

        await self.execute_with_retry(user_id, _send)
        return f"✅ 已清空{channel_name}通道波形队列"

    async def stop_all(self, user_id: str) -> str:
        """停止所有输出（将双通道强度设为0并清空波形队列）"""
        results = []
        for ch in [1, 2]:
            channel_name = {1: "A", 2: "B"}[ch]
            try:
                # 先将强度设为0（使用前端协议 type=3）
                logger.info(f"[DGLab] 停止{channel_name}通道: 设置强度为0")

                async def _send_strength(client: DGLabClient, _ch=ch):
                    await client.send_strength(_ch, 2, 0)

                await self.execute_with_retry(user_id, _send_strength)

                # 再清空波形队列（使用前端协议 type=4）
                clear_cmd = f"clear-{ch}"

                async def _send_clear(client: DGLabClient, cmd=clear_cmd):
                    await client.send_direct(cmd)

                await self.execute_with_retry(user_id, _send_clear)

                results.append(f"✅ 已停止{channel_name}通道输出")
            except Exception as e:
                logger.error(f"[DGLab] 停止{channel_name}通道失败: {e}")
                results.append(f"❌ 停止{channel_name}通道失败: {e}")

        return "\n".join(results) if results else "⚠️ 无活跃通道"

    async def close_user_connection(self, user_id: str) -> bool:
        """关闭用户连接"""
        return await self._close_connection(user_id)

    def get_connection_status(self, user_id: str) -> Optional[ConnectionStatus]:
        """获取用户连接状态"""
        conn_info = self._connections.get(user_id)
        return conn_info.status if conn_info else None

    def get_active_count(self) -> int:
        """获取活跃连接数"""
        return sum(
            1
            for c in self._connections.values()
            if c.status in (ConnectionStatus.CONNECTED, ConnectionStatus.BOUND)
        )

    def get_user_status_info(self, user_id: str) -> Optional[dict]:
        """获取用户详细状态信息"""
        conn_info = self._connections.get(user_id)
        if not conn_info:
            return None

        return {
            "status": conn_info.status.value,
            "connected_seconds": int(time.time() - conn_info.created_at),
            "idle_seconds": int(time.time() - conn_info.last_used_at),
            "error_count": conn_info.error_count,
            "is_bound": conn_info.status == ConnectionStatus.BOUND,
        }

    def get_strength_feedback(self, user_id: str) -> Optional[dict]:
        """获取 APP 回传的实时强度和上限数据"""
        conn_info = self._connections.get(user_id)
        if not conn_info:
            return None

        return {
            "strength_a": conn_info.strength_a,
            "strength_b": conn_info.strength_b,
            "limit_a": conn_info.limit_a,
            "limit_b": conn_info.limit_b,
            "last_feedback_button": conn_info.last_feedback_button,
            "last_feedback_time": conn_info.last_feedback_time,
        }

    async def _reconnect_user(self, user_id: str):
        """尝试重新连接用户"""
        binding = self._store.get_binding(user_id)
        if not binding:
            logger.warning(f"[DGLab] 无法重连用户 {user_id}: 无绑定记录")
            return

        await self._close_connection(user_id)

        try:
            _, status = await self.get_or_create_connection(
                user_id=user_id,
                server_url=binding.server_url,
                client_id=binding.client_id,
            )
            logger.info(f"[DGLab] 用户 {user_id} 重连成功 (status={status.value})")
        except Exception as e:
            logger.error(f"[DGLab] 用户 {user_id} 重连失败: {e}")

    async def _close_connection(self, user_id: str) -> bool:
        """关闭指定用户连接（线程安全）"""
        async with self._global_lock:
            return await self._close_connection_unlocked(user_id)

    async def _close_connection_unlocked(self, user_id: str) -> bool:
        """关闭指定用户连接（调用方必须持有 _global_lock）"""
        conn_info = self._connections.pop(user_id, None)
        if not conn_info:
            return False

        if conn_info.reconnect_task and not conn_info.reconnect_task.done():
            conn_info.reconnect_task.cancel()
            try:
                await conn_info.reconnect_task
            except (asyncio.CancelledError, Exception):
                pass

        try:
            await conn_info.client.close()
        except Exception as e:
            logger.warning(f"[DGLab] 关闭连接异常: {e}")

        logger.info(f"[DGLab] 已关闭用户 {user_id} 的连接")
        return True

    async def _cleanup_loop(self):
        """定期清理空闲连接"""
        try:
            while self._running:
                await asyncio.sleep(60)

                now = time.time()
                to_close = []

                async with self._global_lock:
                    for user_id, conn_info in self._connections.items():
                        idle_time = now - conn_info.last_used_at

                        if idle_time > self._idle_timeout:
                            to_close.append(user_id)
                            logger.info(
                                f"[DGLab] 检测到空闲连接: user={user_id}, "
                                f"idle={idle_time:.0f}s > {self._idle_timeout}s"
                            )

                    # 在持有锁的情况下直接关闭，避免释放锁后再获取导致死锁
                    for user_id in to_close:
                        await self._close_connection_unlocked(user_id)
        except asyncio.CancelledError:
            pass
