"""CurrentCortex 插件 Page 后端 API。

所有路由以 ``/cc/`` 为前缀，通过 ``plugin.context.register_web_api`` 注册。
Page 前端（pages/cc-dashboard）通过 ``window.AstrBotPluginPage`` 调用。

约定：
- 所有 handler 返回 ``json_response({...})``；异常统一 ``error_response``。
- 配置写入走白名单（仅 ``_conf_schema.json`` 中存在的 key）。
- 写配置后自动 ``save_config_async`` + ``star_manager.reload`` 热重载。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, List

from astrbot.api import logger
from astrbot.api.web import error_response, json_response, request


# ----------------------------------------------------------------------- #
# 配置 schema 与白名单
# ----------------------------------------------------------------------- #

_CONFIG_SCHEMA: Dict[str, Dict[str, Any]] = {}
_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_conf_schema.json"
)


def _load_schema() -> Dict[str, Dict[str, Any]]:
    """惰性加载 _conf_schema.json，结果带类型/默认值/选项等元数据。"""
    global _CONFIG_SCHEMA
    if _CONFIG_SCHEMA:
        return _CONFIG_SCHEMA
    try:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            _CONFIG_SCHEMA = json.load(f)
    except Exception as e:
        logger.warning(f"[Pages] 加载 _conf_schema.json 失败: {e}")
        _CONFIG_SCHEMA = {}
    return _CONFIG_SCHEMA


# 配置 key 分组（前端「设置」页用，key 必须存在于 schema）
_CONFIG_GROUPS: List[Dict[str, Any]] = [
    {
        "key": "basic",
        "title": "基础",
        "icon": "settings",
        "items": ["llm_tools_enable"],
    },
    {
        "key": "pixiv",
        "title": "Pixiv 图片",
        "icon": "image",
        "items": [
            "default_r18",
            "default_num",
            "default_size",
            "image_proxy",
            "exclude_ai",
            "request_timeout",
        ],
    },
    {
        "key": "music",
        "title": "网易云/酷狗 点歌",
        "icon": "music",
        "items": [
            "music_file_max_bytes",
            "music_cooldown",
            "music_default_source",
        ],
    },
    {
        "key": "leiz",
        "title": "LeiZ API 密钥",
        "icon": "key",
        "items": ["leiz_api_key"],
    },
    {
        "key": "coyote",
        "title": "DG-LAB（郊狼）",
        "icon": "bolt",
        "items": [
            "dglab_server_url",
            "dglab_heartbeat_interval",
            "dglab_auto_connect",
            "dglab_webui_enabled",
            "dglab_webui_host",
            "dglab_webui_port",
        ],
    },
    {
        "key": "cross_group",
        "title": "跨群聊记忆",
        "icon": "share",
        "items": [
            "cross_group_enable",
            "cross_group_max_cnt",
            "cross_group_inject_cnt",
        ],
    },
    {
        "key": "group_switch",
        "title": "按群聊开关",
        "icon": "switch",
        "items": ["group_switch_enable", "group_switch_admin_only"],
    },
    {
        "key": "reply_seg",
        "title": "分段回复",
        "icon": "scissors",
        "items": [
            "reply_seg_enable",
            "reply_seg_only_llm",
            "reply_seg_mention",
            "reply_seg_mode",
            "reply_seg_llm_provider_id",
            "reply_seg_llm_density",
            "reply_seg_llm_max_segments",
            "reply_seg_llm_min_chars",
            "reply_seg_llm_timeout",
            "reply_seg_llm_max_tokens",
            "reply_seg_split_symbols",
            "reply_seg_split_words",
            "reply_seg_merge_threshold",
            "reply_seg_min_length",
            "reply_seg_max_length",
            "reply_seg_delay_range",
        ],
    },
]


# ----------------------------------------------------------------------- #
# 工具方法
# ----------------------------------------------------------------------- #


def _meta_from_schema(key: str) -> Dict[str, Any]:
    """从 schema 抽取 type/description/default/options/hint。"""
    schema = _load_schema().get(key, {})
    return {
        "key": key,
        "type": schema.get("type", "string"),
        "default": schema.get("default"),
        "options": schema.get("options"),
        "hint": schema.get("hint", ""),
        "description": schema.get("description", ""),
    }


def _coerce(key: str, raw: Any) -> Any:
    """根据 schema 类型把字符串/前端表单值转为正确的 Python 类型。"""
    schema = _load_schema().get(key, {})
    typ = schema.get("type", "string")
    if raw is None:
        return schema.get("default")
    try:
        if typ == "bool":
            if isinstance(raw, bool):
                return raw
            return str(raw).strip().lower() in ("1", "true", "yes", "on")
        if typ == "int":
            return int(raw)
        if typ == "float":
            return float(raw)
        if typ == "string":
            return str(raw)
    except Exception:
        return schema.get("default")
    return raw


async def _save_and_reload(plugin, payload: Dict[str, Any]) -> Dict[str, Any]:
    """白名单过滤 + 类型转换 + 写盘 + 热重载。

    返回 ``{changed: [...], reloaded: bool}``。
    """
    schema = _load_schema()
    changed: List[str] = []
    for key, raw in payload.items():
        if key not in schema:
            continue
        # 跳过未变化的值
        try:
            current = plugin.config.get(key)
        except Exception:
            current = None
        new_val = _coerce(key, raw)
        if current == new_val:
            continue
        plugin.config[key] = new_val
        changed.append(key)
    if not changed:
        return {"changed": [], "reloaded": False}
    # 写盘
    save = getattr(plugin.config, "save_config_async", None)
    if save is None:
        save = getattr(plugin.config, "save_config", None)
    if save is not None:
        try:
            res = save()
            if hasattr(res, "__await__"):
                await res
        except Exception as e:
            logger.warning(f"[Pages] save_config 失败: {e}")
    # 热重载插件
    reloaded = False
    try:
        star_manager = getattr(plugin.context, "star_manager", None)
        if star_manager is not None and hasattr(star_manager, "reload"):
            plugin_name = getattr(plugin, "name", None) or "astrbot_plugin_currentcortex"
            try:
                await star_manager.reload(plugin_name)
                reloaded = True
            except TypeError:
                # 兼容旧签名 reload() 无参
                await star_manager.reload()
                reloaded = True
    except Exception as e:
        logger.warning(f"[Pages] star_manager.reload 失败: {e}")
    return {"changed": changed, "reloaded": reloaded}


# ----------------------------------------------------------------------- #
# Handler：仪表板
# ----------------------------------------------------------------------- #


async def page_status(plugin):
    """仪表板聚合状态：版本 / 运行时长 / 设备 / 用户 / 平台等。"""
    try:
        # 元数据
        metadata = {}
        meta_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "metadata.yaml"
        )
        try:
            import yaml  # type: ignore
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = yaml.safe_load(f) or {}
        except Exception:
            # fallback：手取 version/name
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    txt = f.read()
                import re as _re
                m = _re.search(r"^version:\s*(.+)$", txt, _re.M)
                if m:
                    metadata["version"] = m.group(1).strip()
                m = _re.search(r"^name:\s*(.+)$", txt, _re.M)
                if m:
                    metadata["name"] = m.group(1).strip()
                m = _re.search(r"^author:\s*(.+)$", txt, _re.M)
                if m:
                    metadata["author"] = m.group(1).strip()
            except Exception:
                metadata = {}

        # 设备数
        device_count = 0
        try:
            device_store = getattr(plugin, "_device_store", None)
            if device_store is not None and hasattr(device_store, "count"):
                device_count = int(device_store.count() or 0)
        except Exception:
            pass

        # 活跃连接
        active_conn = 0
        error_count = 0
        try:
            pool = getattr(plugin, "_connection_pool", None)
            if pool is not None:
                if hasattr(pool, "get_active_count"):
                    active_conn = int(pool.get_active_count() or 0)
                if hasattr(pool, "error_count"):
                    error_count = int(pool.error_count or 0)
        except Exception:
            pass

        # 用户数
        user_count = 0
        try:
            user_store = getattr(plugin, "_user_store", None)
            if user_store is not None:
                if hasattr(user_store, "count_all_users"):
                    user_count = int(user_store.count_all_users() or 0)
                elif hasattr(user_store, "list_users"):
                    user_count = len(user_store.list_users() or [])
        except Exception:
            pass

        # 配置开关状态
        cfg = {}
        for key in [
            "llm_tools_enable",
            "dglab_webui_enabled",
            "dglab_auto_connect",
            "cross_group_enable",
            "group_switch_enable",
            "reply_seg_enable",
        ]:
            try:
                cfg[key] = bool(plugin.config.get(key, False))
            except Exception:
                cfg[key] = False

        started_at = float(getattr(plugin, "_started_at", time.time()))
        uptime_sec = int(time.time() - started_at)

        return json_response(
            {
                "metadata": metadata,
                "started_at": started_at,
                "uptime_sec": uptime_sec,
                "device_count": device_count,
                "active_connections": active_conn,
                "error_count": error_count,
                "user_count": user_count,
                "feature_flags": cfg,
            }
        )
    except Exception as e:
        logger.error(f"[Pages] /cc/status 失败: {e}", exc_info=True)
        return error_response(f"状态获取失败: {e}", status_code=500)


# ----------------------------------------------------------------------- #
# Handler：配置读写
# ----------------------------------------------------------------------- #


async def page_get_config(plugin):
    """读取分组后的配置 schema + 当前值。"""
    try:
        schema = _load_schema()
        groups: List[Dict[str, Any]] = []
        for g in _CONFIG_GROUPS:
            items = []
            for k in g["items"]:
                if k not in schema:
                    continue
                meta = _meta_from_schema(k)
                try:
                    meta["value"] = plugin.config.get(k)
                except Exception:
                    meta["value"] = meta.get("default")
                items.append(meta)
            if items:
                groups.append({"key": g["key"], "title": g["title"], "icon": g["icon"], "items": items})
        return json_response({"groups": groups})
    except Exception as e:
        logger.error(f"[Pages] /cc/config GET 失败: {e}", exc_info=True)
        return error_response(f"读取配置失败: {e}", status_code=500)


async def page_save_config(plugin):
    """保存配置并触发热重载。body: {key: value, ...}。"""
    try:
        payload = await request.json(default={}) or {}
        if not isinstance(payload, dict):
            return error_response("请求体必须是 JSON 对象", status_code=400)
        result = await _save_and_reload(plugin, payload)
        return json_response(
            {
                "ok": True,
                "changed": result["changed"],
                "reloaded": result["reloaded"],
                "message": "已保存" + ("并热重载" if result["reloaded"] else ""),
            }
        )
    except Exception as e:
        logger.error(f"[Pages] /cc/config POST 失败: {e}", exc_info=True)
        return error_response(f"保存配置失败: {e}", status_code=500)


# ----------------------------------------------------------------------- #
# Handler：郊狼（CCDG WebUI）
# ----------------------------------------------------------------------- #


async def page_coyote_info(plugin):
    """返回郊狼 WebUI 当前状态：是否启用 / host / port / 进程 / 连接数。"""
    try:
        webui = getattr(plugin, "_dglab_webui", None)
        running = bool(webui is not None and webui._site is not None)
        host = str(plugin.config.get("dglab_webui_host", "127.0.0.1"))
        port = int(plugin.config.get("dglab_webui_port", 9178))
        enabled = bool(plugin.config.get("dglab_webui_enabled", False))
        is_public = host in ("0.0.0.0", "::")
        local_url = f"http://{'localhost' if host in ('0.0.0.0', '127.0.0.1') else host}:{port}"
        return json_response(
            {
                "enabled": enabled,
                "running": running,
                "host": host,
                "port": port,
                "is_public": is_public,
                "local_url": local_url,
            }
        )
    except Exception as e:
        logger.error(f"[Pages] /cc/coyote/info 失败: {e}", exc_info=True)
        return error_response(f"获取郊狼状态失败: {e}", status_code=500)


async def page_coyote_public_ip(plugin):
    """主动探测本机公网 IPv4。"""
    try:
        ip = await plugin.get_public_ip()
        return json_response({"ip": ip})
    except Exception as e:
        logger.error(f"[Pages] /cc/coyote/public_ip 失败: {e}", exc_info=True)
        return error_response(f"获取公网 IP 失败: {e}", status_code=500)


async def page_coyote_enable(plugin):
    """启用 CCDG WebUI 总开关。

    仅打开 WebUI，监听地址保持当前配置（默认 127.0.0.1，只本机可访问，
    不视为暴露公网）。
    """
    try:
        payload = await request.json(default={}) or {}
        port = int(payload.get("port") or plugin.config.get("dglab_webui_port", 9178))
        host = str(payload.get("host") or plugin.config.get("dglab_webui_host", "127.0.0.1"))
        result = await _save_and_reload(
            plugin,
            {"dglab_webui_enabled": True, "dglab_webui_host": host, "dglab_webui_port": port},
        )
        is_public = host in ("0.0.0.0", "::")
        return json_response(
            {
                "ok": True,
                "changed": result["changed"],
                "reloaded": result["reloaded"],
                "host": host,
                "port": port,
                "is_public": is_public,
                "local_url": f"http://{'localhost' if host in ('0.0.0.0', '127.0.0.1') else host}:{port}",
                "message": "已启用（监听 127.0.0.1，仅本机可访问）" if not is_public else f"已启用（监听 {host}，公网可访问！）",
            }
        )
    except Exception as e:
        logger.error(f"[Pages] /cc/coyote/enable 失败: {e}", exc_info=True)
        return error_response(f"启用郊狼 WebUI 失败: {e}", status_code=500)


async def page_coyote_disable(plugin):
    """关闭 CCDG WebUI 总开关。

    关闭时把监听地址一并恢复为 127.0.0.1，避免残留 0.0.0.0 暴露配置；
    同时收回暴露开关可能留下的 ufw 端口放行（尽力而为，失败仅记日志）。
    """
    try:
        port = int(plugin.config.get("dglab_webui_port", 9178))
        result = await _save_and_reload(
            plugin,
            {"dglab_webui_enabled": False, "dglab_webui_host": "127.0.0.1"},
        )
        fw = await _relay_ufw_allow(port, allow=False)
        if not fw["changed"] and "可达" not in fw["note"]:
            logger.warning("[Pages] WebUI 端口 %s ufw 规则收回失败: %s", port, fw["note"])
        return json_response(
            {
                "ok": True,
                "changed": result["changed"],
                "reloaded": result["reloaded"],
                "fw": fw,
                "message": "已关闭 CCDG WebUI",
            }
        )
    except Exception as e:
        logger.error(f"[Pages] /cc/coyote/disable 失败: {e}", exc_info=True)
        return error_response(f"关闭郊狼 WebUI 失败: {e}", status_code=500)


async def page_coyote_expose(plugin):
    """暴露公网开关：打开后监听 0.0.0.0，自动 ufw 放行端口，探测公网 IP 返回链接。

    若 WebUI 尚未启用，会一并自动启用（因为暴露的前提是 WebUI 在运行）。
    防火墙放行复用中转服务器暴露开关逻辑：先放行并以 `ufw status` 实际查询
    校验生效，失败则不落配置、显式报错（避免开关显示已开、实际端口未放行）。
    需请求体携带 ``confirm=true``（前端二次确认）。
    """
    try:
        payload = await request.json(default={}) or {}
        if not payload.get("confirm"):
            return error_response(
                "暴露公网有安全风险，需经前端二次确认（confirm=true）",
                status_code=400,
            )
        port = int(payload.get("port") or plugin.config.get("dglab_webui_port", 9178))
        host = str(payload.get("host") or "0.0.0.0")
        # 先放行防火墙：失败时不改配置，前端开关保持关闭状态
        fw = await _relay_ufw_allow(port, allow=True, comment=WEBUI_UFW_COMMENT)
        if not fw["changed"] and "可达" not in fw["note"]:
            logger.error("[Pages] WebUI 端口 %s 放行失败: %s", port, fw["note"])
            return error_response(f"放行端口 {port} 失败: {fw['note']}", status_code=500)
        result = await _save_and_reload(
            plugin,
            {
                "dglab_webui_enabled": True,
                "dglab_webui_host": host,
                "dglab_webui_port": port,
            },
        )
        ip = await plugin.get_public_ip()
        if host in ("0.0.0.0", "::"):
            logger.warning(
                "[Pages] ⚠️ 郊狼 WebUI 已暴露公网（%s:%s，ufw 已放行）！"
                "请确保已配置反代 + 鉴权。",
                host,
                port,
            )
        url = f"http://{ip}:{port}"
        return json_response(
            {
                "ok": True,
                "changed": result["changed"],
                "reloaded": result["reloaded"],
                "ip": ip,
                "host": host,
                "port": port,
                "url": url,
                "fw": fw,
                "warning": "已暴露公网，请务必配置反向代理与访问控制！"
                + (f"（{fw['note']}）" if fw["note"] else ""),
            }
        )
    except Exception as e:
        logger.error(f"[Pages] /cc/coyote/expose 失败: {e}", exc_info=True)
        return error_response(f"暴露公网失败: {e}", status_code=500)


async def page_coyote_unexpose(plugin):
    """关闭暴露公网开关：监听恢复 127.0.0.1 并收回 ufw 端口放行，WebUI 总开关状态保留。

    先恢复监听地址（立即切断公网入口），再删除防火墙规则；规则删除失败不
    阻断关闭操作（监听已回本机，端口不再对外响应），仅在回执中提示。
    """
    try:
        payload = await request.json(default={}) or {}
        port = int(payload.get("port") or plugin.config.get("dglab_webui_port", 9178))
        result = await _save_and_reload(
            plugin,
            {"dglab_webui_host": "127.0.0.1"},
        )
        fw = await _relay_ufw_allow(port, allow=False)
        fw_note = ""
        if not fw["changed"] and "可达" not in fw["note"]:
            logger.warning("[Pages] WebUI 端口 %s ufw 规则收回失败: %s", port, fw["note"])
            fw_note = fw["note"]
        return json_response(
            {
                "ok": True,
                "changed": result["changed"],
                "reloaded": result["reloaded"],
                "fw": fw,
                "message": "已取消公网暴露，恢复本机监听"
                + (f"；但防火墙规则收回失败: {fw_note}" if fw_note else ""),
            }
        )
    except Exception as e:
        logger.error(f"[Pages] /cc/coyote/unexpose 失败: {e}", exc_info=True)
        return error_response(f"取消公网暴露失败: {e}", status_code=500)


# ----------------------------------------------------------------------- #
# Handler：中转服务器一键部署（v3/v4）
# ----------------------------------------------------------------------- #

# 官方服务端监听地址写死为全接口,「本机/公网」可达性完全由防火墙控制:
# 未放行 = 仅本机(127.0.0.1)可达;ufw allow = 公网可达。
RELAY_REPO = "https://github.com/dungeonlab-open/dglab-websocket-server"
RELAY_BASE_DIR = "/root/dglab-relay"
RELAY_PORTS = {"v3": 9999, "v4": 9998}
# 检测候选 unit:一键部署用 dglab-relay-*,同时接管历史手工部署(dglab-v3/v4)
RELAY_UNIT_CANDIDATES = {
    "v3": ("dglab-relay-v3", "dglab-v3"),
    "v4": ("dglab-relay-v4", "dglab-v4"),
}
RELAY_BUN_PATH = "/root/.bun/bin/bun"
RELAY_UNIT_DIR = "/etc/systemd/system"
RELAY_UFW_COMMENT = "CurrentCortex-DGLab-relay"
WEBUI_UFW_COMMENT = "CurrentCortex-DGLab-webui"


def _relay_dir(version: str) -> str:
    return os.path.join(RELAY_BASE_DIR, version)


def _render_relay_env(version: str) -> str:
    """渲染指定版本中转服务器的 .env 内容(纯函数,便于测试)。"""
    lines = [
        f"# CurrentCortex 一键部署生成 (DG-LAB {version.upper()} relay)",
        f"PORT={RELAY_PORTS[version]}",
        "IDLE_TIMEOUT=300000",
        "PREFIX=/",
        "LOG_LEVEL=info",
        "VERBOSE=false",
    ]
    if version == "v3":
        lines.insert(2, "HEARTBEAT_INTERVAL=60000")
        lines += ["DEFAULT_PUNISHMENT_TIME=1", "DEFAULT_PUNISHMENT_DURATION=5"]
    else:
        lines.insert(2, "HEARTBEAT_INTERVAL=30000")
    return "\n".join(lines) + "\n"


def _render_relay_unit(version: str) -> str:
    """渲染 systemd 单元内容(纯函数,便于测试)。"""
    return (
        "[Unit]\n"
        f"Description=DG-LAB WebSocket {version.upper()} Relay Server (deployed by CurrentCortex)\n"
        f"Documentation={RELAY_REPO}\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={_relay_dir(version)}\n"
        'Environment="PATH=/root/.bun/bin:/usr/local/bin:/usr/bin:/bin"\n'
        f"ExecStart={RELAY_BUN_PATH} run {version}-server.ts\n"
        "Restart=on-failure\n"
        "RestartSec=3\n"
        "NoNewPrivileges=true\n"
        "PrivateTmp=true\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def _parse_ufw_status(text: str, port: int) -> bool:
    """从 `ufw status` 输出判断端口是否被放行(纯函数,便于测试)。

    兼容两种格式:
      9998/tcp                   ALLOW IN    Anywhere
      9998/tcp (CurrentCortex)   ALLOW IN    Anywhere
    """
    prefix = f"{port}/"
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or ":" in stripped[:12]:  # 跳过 "Status: active" 等头行
            continue
        fields = stripped.split()
        if fields and fields[0].startswith(prefix) and "ALLOW" in stripped.upper():
            return True
    return False


async def _run_cmd(
    cmd: List[str],
    timeout: float = 30.0,
    cwd: str = None,
    env: Dict[str, str] = None,
):
    """执行外部命令,返回 (rc, stdout, stderr)。超时自动 kill。

    env 缺省时继承当前进程环境;传入时整体替换(需包含 PATH 等必要变量)。
    """
    import asyncio
    import shutil as _shutil

    if _shutil.which(cmd[0]) is None and not os.path.isabs(cmd[0]):
        return 127, "", f"{cmd[0]}: command not found"
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        return 1, "", repr(e)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return 124, "", f"timeout after {timeout}s"
    return (
        proc.returncode or 0,
        out.decode("utf-8", "replace").strip(),
        err.decode("utf-8", "replace").strip(),
    )


def _relay_deploy_env() -> Dict[str, str]:
    """构建部署子进程环境:补齐 HOME/USER/BUN_INSTALL,并把 bun 目录放进 PATH。

    AstrBot 常由 systemd/容器以精简环境启动(无 HOME),而 bun 官方安装脚本
    以 `set -u` 运行并引用 $HOME,会报 "HOME: unbound variable"。中转部署的
    路径与 systemd 单元都硬编码 root,故 HOME 固定为 /root。
    """
    bun_bin_dir = os.path.dirname(RELAY_BUN_PATH)
    env = dict(os.environ)
    env.setdefault("HOME", "/root")
    env.setdefault("USER", "root")
    env["BUN_INSTALL"] = os.path.dirname(bun_bin_dir)
    env["PATH"] = (
        bun_bin_dir
        + ":"
        + env.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    )
    return env


def _relay_find_unit(version: str) -> str:
    """返回已存在的 unit 名(不含 .service 后缀),不存在返回空串。"""
    for name in RELAY_UNIT_CANDIDATES.get(version, ()):
        if os.path.exists(os.path.join(RELAY_UNIT_DIR, f"{name}.service")):
            return name
    return ""


def _relay_port_listening(port: int) -> bool:
    import socket as _socket

    try:
        s = _socket.socket()
        s.settimeout(0.5)
        ok = s.connect_ex(("127.0.0.1", port)) == 0
        s.close()
        return ok
    except Exception:
        return False


async def _relay_ufw_state() -> Dict[str, Any]:
    """探测防火墙状态: {available, active}。"""
    import shutil as _shutil

    if _shutil.which("ufw") is None:
        return {"available": False, "active": False}
    rc, out, _ = await _run_cmd(["ufw", "status"], timeout=10)
    active = "active" in out.splitlines()[0].lower() if out else False
    return {"available": True, "active": bool(active and "inactive" not in out.lower())}


async def _relay_ufw_allow(port: int, allow: bool, comment: str = RELAY_UFW_COMMENT) -> Dict[str, Any]:
    """放行/收回端口。返回 {changed, note};changed=True 仅代表规则已实际生效。"""
    state = await _relay_ufw_state()
    if not state["available"]:
        return {"changed": False, "note": "未安装 ufw,无防火墙拦截,端口本就对外可达"}
    if not state["active"]:
        return {"changed": False, "note": "ufw 未启用,端口本就对外可达"}
    if allow:
        rc, out, err = await _run_cmd(
            ["ufw", "allow", f"{port}/tcp", "comment", comment], timeout=15
        )
    else:
        rc, out, err = await _run_cmd(["ufw", "delete", "allow", f"{port}/tcp"], timeout=15)
    if rc != 0:
        logger.warning("[Relay] ufw %s %s/tcp 失败 rc=%s: %s", "allow" if allow else "delete", port, rc, (err or out)[:200])
        return {"changed": False, "note": f"ufw 操作失败(rc={rc}): {(err or out)[:200]}"}
    # 关键:命令成功 ≠ 规则生效,以 ufw status 实际查询结果为准
    allowed_now = await _relay_ufw_allowed(port)
    if allow and not allowed_now:
        logger.warning("[Relay] ufw allow 返回成功但规则未出现(端口 %s)", port)
        return {"changed": False, "note": "ufw allow 已执行但规则未生效,请手动检查 `ufw status`"}
    if (not allow) and allowed_now and state["active"]:
        return {"changed": False, "note": "ufw delete 已执行但规则仍存在,请手动检查 `ufw status`"}
    return {"changed": True, "note": ""}


async def _relay_ufw_allowed(port: int) -> bool:
    state = await _relay_ufw_state()
    if not state["available"] or not state["active"]:
        return True  # 无防火墙 = 外部可达
    rc, out, _ = await _run_cmd(["ufw", "status"], timeout=10)
    return _parse_ufw_status(out, port)


async def _relay_commit(dir_path: str) -> str:
    if not os.path.isdir(os.path.join(dir_path, ".git")):
        return ""
    rc, out, _ = await _run_cmd(
        ["git", "-C", dir_path, "rev-parse", "--short", "HEAD"], timeout=10
    )
    return out if rc == 0 else ""


async def _relay_version_state(version: str) -> Dict[str, Any]:
    """检测单个版本的部署状态(全部为事实检测,不依赖配置)。"""
    port = RELAY_PORTS[version]
    unit = _relay_find_unit(version)
    running = False
    if unit:
        rc, _, _ = await _run_cmd(["systemctl", "is-active", unit, "--quiet"], timeout=10)
        running = rc == 0
    listening = _relay_port_listening(port)
    deployed = bool(unit) or listening
    exposed = await _relay_ufw_allowed(port) if deployed else False
    commit = ""
    for d in (_relay_dir(version), "/root/dglab-websocket-server"):
        if os.path.isdir(d):
            commit = await _relay_commit(d)
            if commit:
                break
    return {
        "deployed": deployed,
        "running": running or listening,
        "managed": unit.startswith("dglab-relay-"),
        "unit": unit,
        "port": port,
        "exposed": exposed,
        "commit": commit,
        "local_url": f"ws://127.0.0.1:{port}" if deployed else "",
    }


async def _relay_selfcheck(version: str) -> str:
    """部署自检:连接本机端口等待协议首帧。返回空串表示通过,否则为错误描述。"""
    import websockets as _ws

    port = RELAY_PORTS[version]
    expect = "hello" if version == "v4" else "bind"
    try:
        async with _ws.connect(f"ws://127.0.0.1:{port}", open_timeout=5) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            frame = json.loads(raw)
            if isinstance(frame, dict) and frame.get("type") == expect:
                return ""
            return f"首帧类型异常: {frame.get('type')!r} (期望 {expect!r})"
    except Exception as e:
        return f"自检连接失败: {e}"


async def _relay_deploy_version(version: str) -> Dict[str, Any]:
    """一键部署指定版本。返回 {ok, steps: [...], message}。"""
    import shutil as _shutil

    steps: List[str] = []

    def step(msg: str):
        steps.append(msg)
        logger.info(f"[Relay] {version} 部署: {msg}")

    # 前置:已部署则拒绝
    state = await _relay_version_state(version)
    if state["deployed"]:
        return {
            "ok": False,
            "steps": steps,
            "message": f"{version.upper()} 中转已部署(unit={state['unit'] or '端口占用'},请先卸载再重新部署)",
        }

    # 前置:git
    if _shutil.which("git") is None:
        return {"ok": False, "steps": steps, "message": "系统未安装 git,无法克隆官方仓库"}
    step("git 就绪")

    # bun:缺失则自动安装(显式注入 HOME 等环境变量,避免精简环境下安装脚本报
    # "HOME: unbound variable")
    bun = RELAY_BUN_PATH if os.path.exists(RELAY_BUN_PATH) else _shutil.which("bun")
    deploy_env = _relay_deploy_env()
    if not bun:
        step("bun 未安装,开始自动安装(约 10~30s)")
        rc, out, err = await _run_cmd(
            ["bash", "-c", "curl -fsSL https://bun.sh/install | bash"],
            timeout=180,
            env=deploy_env,
        )
        if rc != 0 or not os.path.exists(RELAY_BUN_PATH):
            return {
                "ok": False,
                "steps": steps,
                "message": f"bun 安装失败: {err[:300] or out[:300]}",
            }
        bun = RELAY_BUN_PATH
        step("bun 安装完成")
    else:
        step(f"bun 就绪 ({bun})")

    # 克隆/复用源码
    target = _relay_dir(version)
    if os.path.isdir(os.path.join(target, ".git")):
        step("复用已有源码目录")
    else:
        if os.path.isdir(target):
            # 目录存在但不是仓库(残留),清掉重来
            import shutil as _rm

            _rm.rmtree(target, ignore_errors=True)
        step("克隆官方仓库(约 5~20s)")
        rc, out, err = await _run_cmd(
            ["git", "clone", "--depth", "1", RELAY_REPO, target], timeout=120
        )
        if rc != 0:
            return {"ok": False, "steps": steps, "message": f"克隆失败: {err[:300]}"}
        step("克隆完成")

    # .env
    env_path = os.path.join(target, ".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(_render_relay_env(version))
    step(f"写入 .env (PORT={RELAY_PORTS[version]})")

    # 依赖(用解析出的绝对路径,插件自身 PATH 不含 bun 目录)
    step("安装依赖 (bun install)")
    rc, out, err = await _run_cmd([bun, "install"], cwd=target, timeout=120, env=deploy_env)
    if rc != 0:
        return {"ok": False, "steps": steps, "message": f"bun install 失败: {err[:300]}"}

    # systemd 单元
    unit_name = f"dglab-relay-{version}"
    unit_path = os.path.join(RELAY_UNIT_DIR, f"{unit_name}.service")
    try:
        with open(unit_path, "w", encoding="utf-8") as f:
            f.write(_render_relay_unit(version))
    except PermissionError:
        return {
            "ok": False,
            "steps": steps,
            "message": (
                f"无权限写入 {unit_path}。AstrBot 服务若启用了 ProtectSystem 只读保护,"
                "需添加 systemd 覆盖(ReadWritePaths=/etc/ufw /etc/systemd/system)后重启 AstrBot"
            ),
        }
    step(f"写入 systemd 单元 {unit_name}.service")

    rc, out, err = await _run_cmd(["systemctl", "daemon-reload"], timeout=30)
    if rc != 0:
        return {"ok": False, "steps": steps, "message": f"daemon-reload 失败: {err[:200]}"}
    rc, out, err = await _run_cmd(
        ["systemctl", "enable", "--now", unit_name], timeout=30
    )
    if rc != 0:
        return {"ok": False, "steps": steps, "message": f"服务启动失败: {err[:300]}"}
    step("服务已启动 (enable --now)")

    # 自检
    await asyncio.sleep(1)
    err_msg = await _relay_selfcheck(version)
    if err_msg:
        return {
            "ok": False,
            "steps": steps,
            "message": f"服务已启动但自检未通过: {err_msg}(可查看 journalctl -u {unit_name})",
        }
    step("自检通过(协议首帧正常)")

    # 不放行防火墙:暴露由开关控制(默认关闭 = 仅本机可达)
    step("完成(未放行防火墙,如需公网访问请打开「暴露公网」开关)")
    return {"ok": True, "steps": steps, "message": f"{version.upper()} 中转部署成功"}


async def _relay_uninstall_version(version: str) -> Dict[str, Any]:
    """卸载:停服务 + 删单元 + 收回防火墙放行。保留源码目录便于重装。"""
    steps: List[str] = []
    unit = _relay_find_unit(version)
    port = RELAY_PORTS[version]
    if not unit and not _relay_port_listening(port):
        return {"ok": False, "steps": steps, "message": f"{version.upper()} 未部署"}

    if unit:
        await _run_cmd(["systemctl", "disable", "--now", unit], timeout=30)
        steps.append(f"停止服务 {unit}")
        try:
            os.remove(os.path.join(RELAY_UNIT_DIR, f"{unit}.service"))
        except OSError:
            pass
        await _run_cmd(["systemctl", "daemon-reload"], timeout=30)
        await _run_cmd(["systemctl", "reset-failed", unit], timeout=10)
        steps.append("删除 systemd 单元")
    else:
        steps.append(f"端口 {port} 被无 systemd 服务的进程占用,请手动处理")

    fw = await _relay_ufw_allow(port, allow=False)
    if fw["changed"]:
        steps.append(f"收回防火墙 {port}/tcp 放行")
    return {
        "ok": True,
        "steps": steps,
        "message": f"{version.upper()} 已卸载(源码目录 {_relay_dir(version)} 保留,重装秒级)",
    }


async def page_relay_status(plugin):
    """GET /cc/coyote/relay — 中转服务器部署状态(v3/v4 独立检测)。"""
    try:
        import shutil as _shutil

        ufw = await _relay_ufw_state()
        env = {
            "bun": os.path.exists(RELAY_BUN_PATH) or bool(_shutil.which("bun")),
            "git": bool(_shutil.which("git")),
            "ufw": ufw,
        }
        return json_response(
            {
                "env": env,
                "v3": await _relay_version_state("v3"),
                "v4": await _relay_version_state("v4"),
            }
        )
    except Exception as e:
        logger.error(f"[Pages] /cc/coyote/relay 失败: {e}", exc_info=True)
        return error_response(f"获取中转状态失败: {e}", status_code=500)


async def page_relay_deploy(plugin):
    """POST /cc/coyote/relay/deploy {version, confirm} — 一键部署 v3/v4 中转。

    属系统级操作（可能安装 Bun、克隆官方仓库、创建 systemd 服务并设自启），
    在框架层管理员鉴权之外，还要求请求体 ``confirm`` 与版本号一致（前端确认
    面板键入），防止误触或绕过确认界面直接调用。
    """
    try:
        payload = await request.json(default={}) or {}
        version = str(payload.get("version", "")).lower()
        if version not in RELAY_PORTS:
            return error_response("version 必须是 v3 或 v4", status_code=400)
        if str(payload.get("confirm", "")).strip().lower() != version:
            return error_response(
                "部署为系统级操作，需键入确认：请在确认面板输入版本号（如 v3）后重试",
                status_code=400,
            )
        result = await asyncio.wait_for(
            _relay_deploy_version(version), timeout=300
        )
        state = await _relay_version_state(version)
        return json_response({**result, "state": state})
    except asyncio.TimeoutError:
        return error_response("部署超时(>300s),请查看插件日志排查", status_code=500)
    except Exception as e:
        logger.error(f"[Pages] relay/deploy 失败: {e}", exc_info=True)
        return error_response(f"部署失败: {e}", status_code=500)


async def page_relay_uninstall(plugin):
    """POST /cc/coyote/relay/uninstall {version, confirm} — 卸载中转（需二次确认）。"""
    try:
        payload = await request.json(default={}) or {}
        version = str(payload.get("version", "")).lower()
        if version not in RELAY_PORTS:
            return error_response("version 必须是 v3 或 v4", status_code=400)
        if not payload.get("confirm"):
            return error_response(
                "卸载会停止并删除 systemd 服务，需经前端二次确认（confirm=true）",
                status_code=400,
            )
        result = await _relay_uninstall_version(version)
        state = await _relay_version_state(version)
        return json_response({**result, "state": state})
    except Exception as e:
        logger.error(f"[Pages] relay/uninstall 失败: {e}", exc_info=True)
        return error_response(f"卸载失败: {e}", status_code=500)


async def page_relay_expose(plugin):
    """POST /cc/coyote/relay/expose {version, confirm} — 放行端口 + 探测公网地址（需二次确认）。"""
    try:
        payload = await request.json(default={}) or {}
        version = str(payload.get("version", "")).lower()
        if version not in RELAY_PORTS:
            return error_response("version 必须是 v3 或 v4", status_code=400)
        if not payload.get("confirm"):
            return error_response(
                "放行端口会把服务暴露到公网，需经前端二次确认（confirm=true）",
                status_code=400,
            )
        port = RELAY_PORTS[version]
        state = await _relay_version_state(version)
        if not state["deployed"]:
            return error_response(f"{version.upper()} 未部署,请先部署", status_code=400)

        fw = await _relay_ufw_allow(port, allow=True)
        if not fw["changed"]:
            # ufw 未实际生效时必须显式报错,否则前端会误认为已放行
            # (changed=False 可能是"无防火墙本就可达",也可能是执行失败,以 note 区分)
            if "可达" in fw["note"]:
                pass  # 无防火墙场景:端口本就对外可达,视为已暴露
            else:
                logger.error("[Relay] %s 端口 %s 放行失败: %s", version.upper(), port, fw["note"])
                return error_response(
                    f"放行端口 {port} 失败: {fw['note']}", status_code=500
                )
        ip = await plugin.get_public_ip()
        public_url = f"ws://{ip}:{port}"
        logger.warning(
            "[Relay] ⚠️ %s 中转端口 %s 已放行公网(%s)!DG-LAB APP 可直连,请知悉风险。",
            version.upper(),
            port,
            public_url,
        )
        return json_response(
            {
                "ok": True,
                "version": version,
                "port": port,
                "fw": fw,
                "ip": ip,
                "local_url": f"ws://127.0.0.1:{port}",
                "public_url": public_url,
                "warning": "已放行公网,任何知道地址的 DG-LAB APP 都可尝试接入该中转!",
            }
        )
    except Exception as e:
        logger.error(f"[Pages] relay/expose 失败: {e}", exc_info=True)
        return error_response(f"暴露公网失败: {e}", status_code=500)


async def page_relay_unexpose(plugin):
    """POST /cc/coyote/relay/unexpose {version} — 收回端口放行,回到仅本机可达。"""
    try:
        payload = await request.json(default={}) or {}
        version = str(payload.get("version", "")).lower()
        if version not in RELAY_PORTS:
            return error_response("version 必须是 v3 或 v4", status_code=400)
        port = RELAY_PORTS[version]
        fw = await _relay_ufw_allow(port, allow=False)
        if not fw["changed"] and "可达" not in fw["note"]:
            logger.error("[Relay] %s 端口 %s 收回失败: %s", version.upper(), port, fw["note"])
            return error_response(
                f"收回端口 {port} 失败: {fw['note']}", status_code=500
            )
        return json_response(
            {
                "ok": True,
                "version": version,
                "port": port,
                "fw": fw,
                "local_url": f"ws://127.0.0.1:{port}",
                "message": "已收回公网放行,恢复仅本机可达"
                if fw["changed"]
                else (fw["note"] or "未检测到放行规则"),
            }
        )
    except Exception as e:
        logger.error(f"[Pages] relay/unexpose 失败: {e}", exc_info=True)
        return error_response(f"取消暴露失败: {e}", status_code=500)


# ----------------------------------------------------------------------- #
# Handler：帮助中心
# ----------------------------------------------------------------------- #


_HELP_DOCS: List[Dict[str, Any]] = [
    {
        "category": "快速开始",
        "items": [
            {
                "q": "如何获取 Pixiv 图片？",
                "a": "发送 /pixiv（默认配置），或 /pixiv tag=风景 r18=0 num=3。也可 /femboy 获取随机男娘图。",
            },
            {
                "q": "如何点歌？",
                "a": "发送 /点歌 关键词 或 /music 关键词。默认走 auto 音源（网易云→酷狗）；/音源 可切换。",
            },
            {
                "q": "如何解析小红书 / B站 / 抖音链接？",
                "a": "发送 /解析 <URL>，或直接 /xhs <URL>、/bilibili <URL>。自动识别链接中的视频/图文。",
            },
        ],
    },
    {
        "category": "郊狼 DG-LAB",
        "items": [
            {
                "q": "如何绑定郊狼设备？",
                "a": "1. 设置 dglab_server_url（如 ws://192.168.1.100:9999）并开启 dglab_auto_connect；"
                     "2. /dglab bind，或在群聊里给机器人发 /dglab bind；"
                     "3. 用郊狼 APP「APP 局域网连接」扫描 QR 码绑定。",
            },
            {
                "q": "CCDG WebUI 是什么？",
                "a": "浏览器端的远程控制面板：在网页里调节波形/强度/查看设备状态。默认关闭，需在设置页打开总开关后访问。",
            },
            {
                "q": "开启公网暴露有什么风险？",
                "a": "打开暴露开关后，插件会监听 0.0.0.0 并自动在系统防火墙（ufw）放行对应端口，"
                     "任何人都能访问 WebUI 的注册/登录/设备接口。"
                     "必须前面挂反代 + 鉴权（推荐 Cloudflare Zero Trust、Caddy + BasicAuth、Nginx + IP 白名单）。"
                     "关闭开关会自动恢复 127.0.0.1 并收回防火墙放行，"
                     "但具体安全由用户自己负责。",
            },
        ],
    },
    {
        "category": "分段回复",
        "items": [
            {
                "q": "分段回复和 AstrBot 框架的分段冲突吗？",
                "a": "会。本插件的 reply_seg_enable 与框架 platform_settings.segmented_reply 二选一，"
                     "同时开会导致重复分段。",
            },
            {
                "q": "llm 模式很慢怎么办？",
                "a": "缩短原文长度、增加 reply_seg_llm_min_chars、选更快的 reply_seg_llm_provider_id、"
                     "或切换到 punct 模式（零额外消耗）。",
            },
            {
                "q": "如何自定义切分词？",
                "a": "修改 reply_seg_split_words（空格分隔多个词），词保留在段尾。建议只放多字符词。",
            },
        ],
    },
    {
        "category": "跨群聊记忆",
        "items": [
            {
                "q": "跨群聊记忆会把其他群的内容发给 LLM 吗？",
                "a": "是。开启 cross_group_enable 后，所有群聊共享记忆并注入 LLM 上下文。"
                     "请评估是否符合隐私预期。",
            },
            {
                "q": "如何限制记忆长度？",
                "a": "cross_group_max_cnt 控制总条数（建议 200~1000）；"
                     "cross_group_inject_cnt 控制每次注入条数（建议 10~50）。",
            },
        ],
    },
    {
        "category": "故障排查",
        "items": [
            {
                "q": "保存配置后插件无变化？",
                "a": "本页保存会自动调 star_manager.reload() 热重载。若仍然无效，"
                     "请检查 AstrBot 控制台日志是否有 reload 失败提示。",
            },
            {
                "q": "郊狼开关打开但仪表板仍显示「未运行」？",
                "a": "热重载需要 1~3 秒，请等待后刷新；如仍未运行，检查 dglab_webui_port 是否被占用。",
            },
            {
                "q": "无法访问公网链接？",
                "a": "公网 IP 探测依赖 api.ipify.org。如该服务不可达，本插件会回落到本机出口 IP，"
                     "但若机器本身无公网 IP（如 NAT 后），需自行配置 DDNS / 内网穿透（frp、Cloudflare Tunnel 等）。",
            },
        ],
    },
]


async def page_help(plugin):
    """返回帮助文档（Q&A + 命令速查）。"""
    try:
        return json_response({"docs": _HELP_DOCS})
    except Exception as e:
        logger.error(f"[Pages] /cc/help 失败: {e}", exc_info=True)
        return error_response(f"加载帮助失败: {e}", status_code=500)


# ----------------------------------------------------------------------- #
# 注册入口
# ----------------------------------------------------------------------- #


def _make_handler(fn, plugin):
    """把 handler 绑定到插件实例。

    AstrBot 框架以 ``view_handler(**path_values)`` 形式调用注册的 handler
    （路由无动态参数时 path_values 为空），故这里用闭包把 ``plugin`` 绑定进去，
    handler 本体签名保持 ``async def fn(plugin)``。
    """

    async def _wrapper(**kwargs):
        return await fn(plugin, **kwargs)

    return _wrapper


def register_routes(plugin) -> None:
    """注册全部 Page API 路由。重复调用幂等（AstrBot 会原地替换）。

    注意：路由必须包含插件名前缀（如 /astrbot_plugin_currentcortex/cc/status），
    因为前端 bridge 调用 ``apiGet("cc/status")`` 时，实际请求路径为
    ``/api/v1/plugins/extensions/<插件名>/cc/status``。
    """
    prefix = getattr(plugin, "name", None) or "astrbot_plugin_currentcortex"
    routes = [
        (f"/{prefix}/cc/status", page_status, ["GET"], "仪表板状态"),
        (f"/{prefix}/cc/config", page_get_config, ["GET"], "读取插件配置"),
        (f"/{prefix}/cc/config", page_save_config, ["POST"], "保存插件配置（热重载）"),
        (f"/{prefix}/cc/coyote/info", page_coyote_info, ["GET"], "郊狼 WebUI 状态"),
        (f"/{prefix}/cc/coyote/public_ip", page_coyote_public_ip, ["GET"], "探测本机公网 IP"),
        (f"/{prefix}/cc/coyote/enable", page_coyote_enable, ["POST"], "启用郊狼 WebUI"),
        (f"/{prefix}/cc/coyote/disable", page_coyote_disable, ["POST"], "关闭郊狼 WebUI"),
        (f"/{prefix}/cc/coyote/expose", page_coyote_expose, ["POST"], "暴露郊狼 WebUI 公网"),
        (f"/{prefix}/cc/coyote/unexpose", page_coyote_unexpose, ["POST"], "取消郊狼 WebUI 公网暴露"),
        (f"/{prefix}/cc/coyote/relay", page_relay_status, ["GET"], "中转服务器部署状态(v3/v4)"),
        (f"/{prefix}/cc/coyote/relay/deploy", page_relay_deploy, ["POST"], "一键部署中转服务器(v3/v4,需键入版本号确认)"),
        (f"/{prefix}/cc/coyote/relay/uninstall", page_relay_uninstall, ["POST"], "卸载中转服务器(需二次确认)"),
        (f"/{prefix}/cc/coyote/relay/expose", page_relay_expose, ["POST"], "中转服务器暴露公网(放行端口,需二次确认)"),
        (f"/{prefix}/cc/coyote/relay/unexpose", page_relay_unexpose, ["POST"], "中转服务器取消公网暴露"),
        (f"/{prefix}/cc/help", page_help, ["GET"], "帮助中心文档"),
    ]
    for route, handler, methods, desc in routes:
        try:
            plugin.context.register_web_api(
                route, _make_handler(handler, plugin), methods, desc
            )
            logger.debug(f"[Pages] 注册 {methods} {route}")
        except Exception as e:
            logger.warning(f"[Pages] 注册 {route} 失败: {e}")
    logger.info(f"[Pages] 已注册 {len(routes)} 个 Page API 路由")
