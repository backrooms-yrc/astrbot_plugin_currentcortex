"""Pages 中转服务器(一键部署)纯函数单元测试。

覆盖: .env 渲染、systemd 单元渲染、ufw status 解析、unit 检测、
CCDG WebUI 暴露公网开关的 ufw 放行/收回行为。

运行方式: python3 test_relay_pages.py
"""

import asyncio
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class MockLogger:
    def info(self, *a, **k):
        pass

    def debug(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class _Stub:
    logger = MockLogger()


# stub astrbot.api / astrbot.api.web(_pages_api 顶层依赖)
astrbot = type(sys)("astrbot")
api = type(sys)("astrbot.api")
api.logger = MockLogger()
web = type(sys)("astrbot.api.web")
web.error_response = lambda *a, **k: None
web.json_response = lambda *a, **k: None
web.request = type("R", (), {"json": staticmethod(lambda **k: None)})()
astrbot.api = api
api.web = web
sys.modules.update({"astrbot": astrbot, "astrbot.api": api, "astrbot.api.web": web})

import _pages_api as P  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {('- ' + str(detail)) if detail else ''}")


def test_env_render():
    print("\n📄 .env 渲染")
    v3 = P._render_relay_env("v3")
    check("v3 端口 9999", "PORT=9999" in v3, v3)
    check("v3 心跳 60000", "HEARTBEAT_INTERVAL=60000" in v3)
    check("v3 波形参数", "DEFAULT_PUNISHMENT_TIME=1" in v3 and "DEFAULT_PUNISHMENT_DURATION=5" in v3)
    v4 = P._render_relay_env("v4")
    check("v4 端口 9998", "PORT=9998" in v4, v4)
    check("v4 心跳 30000", "HEARTBEAT_INTERVAL=30000" in v4)
    check("v4 无波形参数", "DEFAULT_PUNISHMENT" not in v4)
    check("公共项", "PREFIX=/" in v4 and "LOG_LEVEL=info" in v4)


def test_deploy_env():
    print("\n🌱 部署子进程环境")
    # 模拟 AstrBot 精简环境(无 HOME/USER/PATH)
    with patch.dict(os.environ, {}, clear=True):
        env = P._relay_deploy_env()
    check("HOME 已补齐", bool(env.get("HOME")), env)
    check("USER 已补齐", bool(env.get("USER")), env)
    check("BUN_INSTALL 指向 /root/.bun", env.get("BUN_INSTALL") == "/root/.bun", env)
    check("PATH 含 bun 目录", env.get("PATH", "").startswith("/root/.bun/bin:"), env)


def test_unit_render():
    print("\n⚙️ systemd 单元渲染")
    for v in ("v3", "v4"):
        unit = P._render_relay_unit(v)
        check(f"{v} 执行对应 server.ts", f"ExecStart={P.RELAY_BUN_PATH} run {v}-server.ts" in unit)
        check(f"{v} 工作目录", f"WorkingDirectory={P._relay_dir(v)}" in unit)
        check(f"{v} 自启与重启", "WantedBy=multi-user.target" in unit and "Restart=on-failure" in unit)
        check(f"{v} PATH 含 bun", "/root/.bun/bin" in unit)


def test_ufw_parse():
    print("\n🧱 ufw status 解析")
    sample = (
        "Status: active\n"
        "To                         Action      From\n"
        "--                         ------      ----\n"
        "22/tcp                     ALLOW IN    Anywhere\n"
        "9998/tcp                   ALLOW IN    Anywhere\n"
        "9998/tcp (v6)              ALLOW IN    Anywhere (v6)\n"
        "8080/tcp (PyMineCore)      ALLOW IN    Anywhere\n"
    )
    check("放行端口命中", P._parse_ufw_status(sample, 9998))
    check("带注释命中", P._parse_ufw_status(sample, 8080))
    check("未放行端口不命中", not P._parse_ufw_status(sample, 9999))
    check("头行不误判", not P._parse_ufw_status("Status: active\nTo Action From\n", 9999))
    check(
        "前缀防误判(999 不等于 9998)",
        not P._parse_ufw_status("999/tcp    ALLOW IN    Anywhere\n", 9998),
    )
    check("空输出不命中", not P._parse_ufw_status("", 9998))


def test_find_unit():
    print("\n🔎 unit 存在性检测")
    with tempfile.TemporaryDirectory() as td:
        old = P.RELAY_UNIT_DIR
        P.RELAY_UNIT_DIR = td
        try:
            check("无 unit", P._relay_find_unit("v3") == "")
            with open(os.path.join(td, "dglab-v4.service"), "w") as f:
                f.write(P._render_relay_unit("v4"))
            check("接管旧名 dglab-v4", P._relay_find_unit("v4") == "dglab-v4")
            with open(os.path.join(td, "dglab-relay-v4.service"), "w") as f:
                f.write(P._render_relay_unit("v4"))
            check("新名优先于旧名", P._relay_find_unit("v4") == "dglab-relay-v4")
            check("v3 不受影响", P._relay_find_unit("v3") == "")
        finally:
            P.RELAY_UNIT_DIR = old


class FakePlugin:
    def __init__(self):
        self.config = {
            "dglab_webui_enabled": False,
            "dglab_webui_host": "127.0.0.1",
            "dglab_webui_port": 9178,
        }

    async def get_public_ip(self):
        return "1.2.3.4"


def _make_ufw(result):
    """构造可记录调用的 _relay_ufw_allow 替身。"""

    async def fake(port, allow, comment=P.RELAY_UFW_COMMENT):
        fake.calls.append((port, allow, comment))
        return result

    fake.calls = []
    return fake


def test_webui_expose_ufw():
    print("\n🌐 WebUI 暴露公网 ufw 集成")

    async def run():
        plugin = FakePlugin()
        saved = []
        json_calls = []

        async def fake_save(p, payload):
            saved.append(dict(payload))
            return {"changed": list(payload.keys()), "reloaded": True}

        def _json(payload, *a, **k):
            json_calls.append(payload)
            return payload

        def _error(message, *a, **k):
            return {"error": message}

        with patch.object(P, "json_response", _json), patch.object(
            P, "error_response", _error
        ), patch.object(P, "_save_and_reload", fake_save):
            # 1) 放行成功 → 落配置 + 返回公网地址
            fake_ok = _make_ufw({"changed": True, "note": ""})

            async def _json_payload(default=None):
                return {}

            with patch.object(P, "_relay_ufw_allow", fake_ok):
                P.request.json = _json_payload
                res = await P.page_coyote_expose(plugin)
            check("放行成功返回 ok", res.get("ok") is True, res)
            check(
                "已保存 0.0.0.0 监听",
                bool(saved) and saved[-1]["dglab_webui_host"] == "0.0.0.0",
                saved,
            )
            check(
                "放行带 WebUI 注释",
                bool(fake_ok.calls) and fake_ok.calls[-1][2] == P.WEBUI_UFW_COMMENT,
                fake_ok.calls,
            )
            check("返回公网链接", res.get("url") == "http://1.2.3.4:9178", res)

            # 2) 放行失败(非可达) → 显式报错且不落配置
            saved.clear()
            fake_fail = _make_ufw({"changed": False, "note": "ufw 操作失败(rc=1): boom"})
            with patch.object(P, "_relay_ufw_allow", fake_fail):
                res = await P.page_coyote_expose(plugin)
            check("放行失败返回错误", isinstance(res, dict) and "boom" in res.get("error", ""), res)
            check("失败不落配置", not saved, saved)

            # 3) 无防火墙(可达) → 照常暴露并提示
            saved.clear()
            fake_nofw = _make_ufw(
                {"changed": False, "note": "未安装 ufw,无防火墙拦截,端口本就对外可达"}
            )
            with patch.object(P, "_relay_ufw_allow", fake_nofw):
                res = await P.page_coyote_expose(plugin)
            check("无防火墙仍可暴露", res.get("ok") is True and bool(saved), res)
            check("warning 带无防火墙提示", "无防火墙拦截" in res.get("warning", ""), res)

            # 4) unexpose: 恢复本机监听;删除失败时消息带提示
            saved.clear()
            fake_del_fail = _make_ufw({"changed": False, "note": "ufw 操作失败(rc=1): boom"})
            with patch.object(P, "_relay_ufw_allow", fake_del_fail):
                res = await P.page_coyote_unexpose(plugin)
            check(
                "unexpose 恢复本机监听",
                bool(saved) and saved[-1]["dglab_webui_host"] == "127.0.0.1",
                saved,
            )
            check("删除失败消息带提示", "收回失败" in res.get("message", ""), res)

            # 5) disable 也会收回防火墙放行
            fake_del = _make_ufw({"changed": True, "note": ""})
            with patch.object(P, "_relay_ufw_allow", fake_del):
                res = await P.page_coyote_disable(plugin)
            check(
                "disable 关闭并收回放行",
                bool(fake_del.calls) and fake_del.calls[-1][1] is False,
                fake_del.calls,
            )
            check("disable 返回 ok", res.get("ok") is True, res)

    asyncio.run(run())


def main():
    print("=" * 60)
    print("🧪 Pages 中转服务器一键部署 · 纯函数测试")
    print("=" * 60)
    test_env_render()
    test_deploy_env()
    test_unit_render()
    test_ufw_parse()
    test_find_unit()
    test_webui_expose_ufw()
    print("\n" + "=" * 60)
    print(f"📊 总计: {PASS}/{PASS + FAIL} 通过")
    return FAIL == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
