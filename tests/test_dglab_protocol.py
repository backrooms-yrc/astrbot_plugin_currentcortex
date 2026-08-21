"""DG-LAB 协议客户端集成测试（V3 / V4 / 旧 V2 兼容）。

使用本地 mock 中转服务器（按官方 dungeonlab-open/dglab-websocket-server 的
v3-server.ts / v4-server.ts 行为实现）对 DGLabClient 做端到端验证。

覆盖:
1. 协议自动识别（bind → v3, hello → v4, 路径前缀回退）
2. V3 控制端裸连 + 服务端分配 clientId + 二维码内容
3. V3 绑定流程 / 强度(设置·多步增减) / 通道清理 / 波形
4. issue #3 回归: error 帧不得误判为绑定成功
5. V4 hello / client_attached / devices.get 设备发现
6. V4 强度(绝对·相对·归零·未知强度兜底) / 波形补帧 / 任务清理
7. V4 事件合成(strength 回传 / feedback / 断开)
8. 旧 V2 服务器兼容(忽略路径 + type4 原样转发)

运行方式: python3 test_dglab_protocol.py
"""

import asyncio
import json
import sys
import os
import uuid
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dglab"))


class MockLogger:
    def info(self, msg, *a, **k):
        pass

    def debug(self, msg, *a, **k):
        pass

    def warning(self, msg, *a, **k):
        pass

    def error(self, msg, *a, **k):
        pass


class MockAstrBotAPI:
    logger = MockLogger()


sys.modules["astrbot"] = type(sys)("astrbot")
sys.modules["astrbot.api"] = MockAstrBotAPI()

import websockets  # noqa: E402

from dglab_client import DGLabClient  # noqa: E402

PASS = 0
FAIL = 0


async def wait_received(mock, count, timeout=2.0):
    """等待 mock 服务端收到至少 count 条控制端报文。

    mock 可为 MockV3Server/MockV4Server(取 .received)或普通列表。
    """
    buf = mock.received if hasattr(mock, "received") else mock
    deadline = asyncio.get_event_loop().time() + timeout
    while len(buf) < count:
        if asyncio.get_event_loop().time() > deadline:
            return False
        await asyncio.sleep(0.02)
    return True


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {('- ' + str(detail)) if detail else ''}")


# ---------------------------------------------------------------- Mock V3 服务端


class MockV3Server:
    """按 v3-server.ts 行为实现的 mock 中转(控制端 1:1 APP)。"""

    def __init__(self):
        self.connections = {}  # clientId -> ws
        self.paired = {}  # controllerId -> appId
        self.received = []  # 控制端发来的报文
        self.path_clients = {}  # path targetId -> ws (APP 直连)

    async def handler(self, ws):
        path = ws.request.path if ws.request else "/"
        target_id = path.lstrip("/").strip() or None
        cid = str(uuid.uuid4())

        if target_id:
            # APP 直连: 携带控制端 ID 的路径
            self.path_clients[target_id] = ws
            await ws.send(json.dumps({"type": "bind", "clientId": str(uuid.uuid4()), "targetId": "", "message": "targetId"}))
            controller = self.connections.get(target_id)
            if controller:
                bind200 = {"type": "bind", "clientId": target_id, "targetId": cid, "message": "200"}
                await controller.send(json.dumps(bind200))
                await ws.send(json.dumps(bind200))
            return

        # 控制端: 裸连根路径, 分配 clientId
        self.connections[cid] = ws
        await ws.send(json.dumps({"type": "bind", "clientId": cid, "targetId": "", "message": "targetId"}))
        try:
            async for raw in ws:
                data = json.loads(raw)
                data["_from"] = "controller"
                self.received.append(data)
                app_id = self.paired.get(cid)
                app_ws = self.path_clients.get(app_id) if app_id else None
                if data.get("type") == "bind" and data.get("message") == "targetId":
                    self.paired[cid] = data.get("targetId")
        finally:
            self.connections.pop(cid, None)


# ---------------------------------------------------------------- Mock V4 服务端


class MockV4Server:
    """按 v4-server.ts 行为实现的 mock 中转(透传 + RPC 应答)。"""

    def __init__(self, prefix="/"):
        self.prefix = prefix
        self.received = []  # 控制端发来的 message/ping 帧
        self.controller_ws = None
        self.controller_id = ""
        self.next_id = 0

    def _new_id(self):
        self.next_id += 1
        return f"cid{self.next_id:04d}"

    async def handler(self, ws):
        path = ws.request.path if ws.request else "/"
        if path != self.prefix:
            await ws.close(code=3001, reason="not_found")
            return
        cid = self._new_id()
        await ws.send(json.dumps({"type": "hello", "clientId": cid}))
        self.controller_ws = ws
        self.controller_id = cid
        try:
            async for raw in ws:
                data = json.loads(raw)
                if data.get("type") == "ping":
                    await ws.send(json.dumps({"type": "pong", "ts": 1}))
                    continue
                if data.get("type") != "message":
                    continue
                self.received.append(data)
                payload = data.get("data") or {}
                await self._handle_rpc(ws, payload)
        finally:
            if self.controller_ws is ws:
                self.controller_ws = None

    async def _handle_rpc(self, ws, payload):
        method = payload.get("m")
        req_id = payload.get("reqId")
        if method == "devices.get":
            await ws.send(
                json.dumps(
                    {
                        "type": "message",
                        "clientId": self.controller_id,
                        "data": {
                            "t": "resp",
                            "reqId": req_id,
                            "result": {
                                "devices": [
                                    {"slotId": "slot-a", "name": "郊狼3.0", "type": "COYOTE_030"}
                                ]
                            },
                        },
                    }
                )
            )
        elif method in ("device.op", "device.op.clear"):
            await ws.send(
                json.dumps(
                    {
                        "type": "message",
                        "clientId": self.controller_id,
                        "data": {"t": "resp", "reqId": req_id, "result": {}},
                    }
                )
            )

    async def simulate_app_attach(self):
        """模拟 APP 被控方接入 + 设备快照上报。"""
        await self.controller_ws.send(
            json.dumps({"type": "client_attached", "clientId": "app-0001"})
        )
        await self.controller_ws.send(
            json.dumps(
                {
                    "type": "message",
                    "clientId": "app-0001",
                    "data": {
                        "t": "ev",
                        "ev": "devices.snapshot",
                        "devices": [
                            {"slotId": "slot-a", "name": "郊狼3.0", "type": "COYOTE_030"}
                        ],
                    },
                }
            )
        )

    async def simulate_event(self, payload):
        await self.controller_ws.send(
            json.dumps({"type": "message", "clientId": "app-0001", "data": payload})
        )


# ---------------------------------------------------------------- 测试用例


async def test_v3_flow():
    print("\n📡 V3 协议流程")
    mock = MockV3Server()
    server = await websockets.serve(mock.handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        client = DGLabClient()
        state = await client.connect(f"ws://127.0.0.1:{port}")
        check("自动识别为 v3", state.protocol == "v3", state.protocol)
        check("clientId 由服务端分配", bool(state.client_id))
        qr = state.qr_content
        check(
            "二维码为 V3 格式",
            qr == f"https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#ws://127.0.0.1:{port}/{state.client_id}",
            qr,
        )

        # APP 扫码: 直连 /{clientId}
        app_ws = await websockets.connect(f"ws://127.0.0.1:{port}/{state.client_id}")
        await asyncio.sleep(0.2)
        check("APP 扫码后判定绑定成功", state.bound, state.last_error)

        # 强度设置 (mode=2)
        n = len(mock.received)
        await client.send_strength(1, 2, 50)
        await wait_received(mock, n + 1)
        msg = mock.received[-1]
        check("强度设置走 type=3", msg.get("type") == 3 and msg.get("strength") == 50, msg)

        # 多步增加 (mode=1, value=5) → 5 条 type=2
        before = len(mock.received)
        await client.send_strength(2, 1, 5)
        await wait_received(mock, before + 5)
        steps = mock.received[before:]
        check(
            "多步增加拆分为 5 条 type=2",
            len(steps) == 5 and all(m.get("type") == 2 and m.get("channel") == 2 for m in steps),
            steps,
        )

        # 多步减少 (mode=0, value=3) → 3 条 type=1
        before = len(mock.received)
        await client.send_strength(1, 0, 3)
        await wait_received(mock, before + 3)
        steps = mock.received[before:]
        check(
            "多步减少拆分为 3 条 type=1",
            len(steps) == 3 and all(m.get("type") == 1 for m in steps),
            steps,
        )

        # 通道清理: channel 字段必须正确(V3 依据 channel 而非 message)
        n = len(mock.received)
        await client.send_direct("clear-2")
        await wait_received(mock, n + 1)
        msg = mock.received[-1]
        check(
            "清理指令携带正确 channel",
            msg.get("type") == 4 and msg.get("channel") == 2 and msg.get("message") == "clear-2",
            msg,
        )

        # 波形
        n = len(mock.received)
        await client.send_pulse("A", json.dumps(["0A0A0A0A64646464"]), 5)
        await wait_received(mock, n + 1)
        msg = mock.received[-1]
        check(
            "波形走 clientMsg",
            msg.get("type") == "clientMsg" and msg.get("channel") == "A"
            and msg.get("message") == 'A:["0A0A0A0A64646464"]',
            msg,
        )

        await app_ws.close()
        await client.close()
    finally:
        server.close()
        await server.wait_closed()


async def test_v3_error_no_false_bind():
    print("\n🛡️ issue #3 回归: error 帧不误判绑定")
    mock = MockV3Server()
    server = await websockets.serve(mock.handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        client = DGLabClient()
        state = await client.connect(f"ws://127.0.0.1:{port}")
        # 模拟 V3 服务端对非法连接的拒绝帧(携带 targetId)
        controller_ws = list(mock.connections.values())[0]
        await controller_ws.send(
            json.dumps({"type": "error", "clientId": state.client_id, "targetId": "0e9105d3", "message": "4001"})
        )
        await asyncio.sleep(0.2)
        check("error 帧未误判为绑定", not state.bound, f"bound={state.bound}")
        check("last_error 记录错误码", "4001" in state.last_error, state.last_error)

        # 随后仍可通过正常 bind/200 绑定
        app_ws = await websockets.connect(f"ws://127.0.0.1:{port}/{state.client_id}")
        await asyncio.sleep(0.2)
        check("正常扫码绑定不受影响", state.bound)
        await app_ws.close()
        await client.close()
    finally:
        server.close()
        await server.wait_closed()


async def test_v2_compat():
    print("\n📜 旧 V2 中转兼容(忽略路径 + type4 原样转发)")
    received = []

    async def handler(ws):
        # 旧 v2: 无论路径一律分配 ID 并下发 bind/targetId
        cid = str(uuid.uuid4())
        await ws.send(json.dumps({"type": "bind", "clientId": cid, "targetId": "", "message": "targetId"}))
        try:
            async for raw in ws:
                received.append(json.loads(raw))
        except Exception:
            pass

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        client = DGLabClient()
        state = await client.connect(f"ws://127.0.0.1:{port}/whatever-path")
        check("v2 服务器识别为 v3 兼容路径", state.protocol == "v3", state.protocol)

        # 模拟绑定后发指令
        state.bound = True
        state.target_id = "app-x"
        await client.send_direct("clear-1")
        await wait_received(received, 1)
        msg = received[-1]
        check(
            "v2 收到的 message 原样为 clear-1(且带 channel 字段无碍)",
            msg.get("type") == 4 and msg.get("message") == "clear-1",
            msg,
        )
        await client.send_strength(1, 2, 30)
        await wait_received(received, 2)
        msg = received[-1]
        check("v2 强度设置 type=3 正常", msg.get("type") == 3 and msg.get("strength") == 30, msg)
        await client.close()
    finally:
        server.close()
        await server.wait_closed()


async def test_v4_flow():
    print("\n🚀 V4 协议流程")
    mock = MockV4Server()
    server = await websockets.serve(mock.handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        client = DGLabClient()
        events = []

        async def on_message(data):
            events.append(data)

        state = await client.connect(f"ws://127.0.0.1:{port}", protocol="auto")
        check("自动识别为 v4", state.protocol == "v4", state.protocol)
        check("clientId 来自 hello", bool(state.client_id))
        from urllib.parse import quote

        expected_qr = (
            "https://dungeon-lab.cn/s/?v=1&action=socket&url="
            + quote(f"ws://127.0.0.1:{port}?tid={state.client_id}", safe="")
        )
        check("二维码为 V4 格式", state.qr_content == expected_qr, state.qr_content)

        client.state.on_message = on_message
        await mock.simulate_app_attach()
        await asyncio.sleep(0.3)
        check("client_attached 后判定绑定", state.bound and state.target_id == "app-0001")
        check("设备发现选中 slot-a", state.slot_id == "slot-a", state.slot_id)
        check("合成 bind/200 事件回调", any(e.get("type") == "bind" and e.get("message") == "200" for e in events))

        # 上报强度快照
        await mock.simulate_event(
            {"t": "ev", "ev": "slots.patch", "slots": [{"slotId": "slot-a", "props": {"strength": {"A": 30, "B": 0}}}]}
        )
        await asyncio.sleep(0.2)
        check(
            "强度回传合成为 strength 消息",
            any(
                e.get("type") == "msg" and e.get("message") == "strength-30+0+200+200"
                for e in events
            ),
            [e for e in events if e.get("type") == "msg"],
        )

        def last_op():
            ops = [m for m in mock.received if (m.get("data") or {}).get("m") == "device.op"]
            return ops[-1]["data"]["data"] if ops else None

        # 绝对强度: 30 -> 80, 应换算 delta=50
        await client.send_strength(1, 2, 80)
        op = last_op()
        check(
            "绝对强度换算 AddIntensity delta=50",
            op and op.get("t") == 3 and op.get("c") == 0 and op.get("v") == 50,
            op,
        )

        # 相对增加
        await client.send_strength(2, 1, 5)
        op = last_op()
        check(
            "相对增加 AddIntensity v=+5",
            op and op.get("t") == 3 and op.get("c") == 1 and op.get("v") == 5,
            op,
        )

        # 相对减少
        await client.send_strength(2, 0, 3)
        op = last_op()
        check("相对减少 AddIntensity v=-3", op and op.get("t") == 3 and op.get("v") == -3, op)

        # 归零 → SetIntensity t=7 v=0
        await client.send_strength(1, 2, 0)
        op = last_op()
        check("归零 SetIntensity t=7 v=0", op and op.get("t") == 7 and op.get("v") == 0, op)

        # 波形: 1 帧 × 5 秒 → 补齐 50 帧, d=5000
        await client.send_pulse("B", json.dumps(["0A0A0A0A64646464"]), 5)
        await asyncio.sleep(0.3)
        ops = [m for m in mock.received if (m.get("data") or {}).get("m") == "device.op"]
        op = ops[-1]["data"]["data"]
        check(
            "波形 AppendPulseData 补帧至50/时长5000ms",
            op.get("t") == 0 and op.get("c") == 1 and len(op.get("v", [])) == 50 and op.get("d") == 5000,
            {k: v for k, v in op.items() if k != "v"},
        )

        # 通道清理 → device.op.clear
        await client.send_direct("clear-1")
        clears = [m for m in mock.received if (m.get("data") or {}).get("m") == "device.op.clear"]
        check(
            "清理映射 device.op.clear",
            clears and clears[-1]["data"]["data"] == {"s": "slot-a", "c": 0},
            clears[-1]["data"]["data"] if clears else None,
        )

        # 自定义动作 → feedback 合成
        await mock.simulate_event({"t": "ev", "ev": "custom.action", "action": 7})
        await asyncio.sleep(0.2)
        check(
            "custom.action 合成 feedback-7",
            any(e.get("type") == "msg" and e.get("message") == "feedback-7" for e in events),
        )

        # APP 断开
        await mock.controller_ws.send(json.dumps({"type": "client_disconnected", "clientId": "app-0001"}))
        await asyncio.sleep(0.2)
        check("client_disconnected 后解绑", not state.bound and not state.target_id)
        check(
            "断开合成 break 事件",
            any(e.get("type") == "break" and e.get("message") == "209" for e in events),
        )

        # 未绑定时发送指令应报错
        try:
            await client.send_strength(1, 2, 10)
            check("解绑后发送指令被拒绝", False)
        except RuntimeError:
            check("解绑后发送指令被拒绝", True)

        await client.close()
    finally:
        server.close()
        await server.wait_closed()


async def test_v4_unknown_strength_fallback():
    print("\n🧩 V4 未知强度时绝对设置的兜底")
    mock = MockV4Server()
    server = await websockets.serve(mock.handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        client = DGLabClient()
        state = await client.connect(f"ws://127.0.0.1:{port}", protocol="auto")
        await mock.simulate_app_attach()
        await asyncio.sleep(0.3)
        # 不上报任何强度 → 未知
        await client.send_strength(1, 2, 60)
        ops = [m for m in mock.received if (m.get("data") or {}).get("m") == "device.op"]
        op = ops[-1]["data"]["data"]
        check(
            "未知强度退化为 SetTempIntensity",
            op.get("t") == 4 and op.get("v") == 60 and "d" not in op,
            op,
        )
        await client.close()
    finally:
        server.close()
        await server.wait_closed()


async def test_v4_prefix_fallback():
    print("\n🔀 auto 模式: V4 路径前缀回退")
    mock = MockV4Server(prefix="/v4")
    server = await websockets.serve(mock.handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        client = DGLabClient()
        # 配置带 /v4 前缀: 根路径尝试会被关闭, 应回退到带前缀地址
        state = await client.connect(f"ws://127.0.0.1:{port}/v4")
        check("回退后识别为 v4", state.protocol == "v4", state.protocol)
        check("server_url 保留前缀", state.server_url.endswith("/v4"), state.server_url)
        check("二维码包含前缀与 tid", f"%2Fv4%3Ftid%3D{state.client_id}" in state.qr_content, state.qr_content)
        await client.close()
    finally:
        server.close()
        await server.wait_closed()


async def main():
    print("=" * 60)
    print("🧪 DG-LAB 协议客户端测试 (V3 / V4 / V2 兼容)")
    print("=" * 60)
    await test_v3_flow()
    await test_v3_error_no_false_bind()
    await test_v2_compat()
    await test_v4_flow()
    await test_v4_unknown_strength_fallback()
    await test_v4_prefix_fallback()

    print("\n" + "=" * 60)
    print(f"📊 总计: {PASS}/{PASS + FAIL} 通过")
    if FAIL:
        print(f"⚠️  {FAIL} 个测试失败")
    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
