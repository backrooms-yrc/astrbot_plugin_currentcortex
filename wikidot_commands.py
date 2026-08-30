"""Wikidot 命令处理器：把聊天命令映射为 WikidotClient 调用。

命令入口 ``/wikidot``（别名 ``/wd``、``/维基``），本类负责剥离命令前缀、
子命令分发、权限门禁与错误转译。权限规则：

- 写操作（编辑页面 / 管理站点）永远要求会话管理员（event.is_admin()）；
- 读操作（源码 / 成员 / 设置查看等）受 wikidot_admin_only 配置控制
  （默认开启，即所有命令都需要管理员）。

子命令风格与 dglab_commands.py 一致：中文主名 + 英文别名，dispatch 到
``_cmd_*`` 异步方法（返回 str 或 List[str]）。
"""

import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger

from .wikidot_client import (
    WikidotClient,
    WikidotError,
    to_unix_name,
)

# 源码等长文本的输出截断（字符）
_OUTPUT_LIMIT = 1500

_WRITE_DENIED = "⛔ 仅管理员可执行 Wikidot 写操作"
_READ_DENIED = "⛔ 该命令当前仅管理员可用（ wikidot_admin_only 开启中）"

CONFIRM_WORDS = ("确认", "confirm", "yes")
OVERWRITE_WORDS = ("覆盖", "overwrite")

_GENERAL_FIELD_ALIASES = {
    "名称": "name", "name": "name",
    "副标题": "subtitle", "subtitle": "subtitle",
    "语言": "language", "language": "language",
    "描述": "description", "description": "description",
    "默认页": "default_page", "default_page": "default_page",
    "欢迎页": "welcome_page", "welcome_page": "welcome_page",
}

_POLICY_FIELD_ALIASES = {
    "隐私": "privacy", "privacy": "privacy",
    "申请": "by_apply", "by_apply": "by_apply",
    "域名": "by_domain", "by_domain": "by_domain",
    "密码访问": "by_password", "by_password": "by_password",
    "访问密码": "password", "password": "password",
    "落地页": "landingPage", "landingPage": "landingPage", "landing_page": "landingPage",
}

_KV_RE = re.compile(r'([\w\u4e00-\u9fff]+)=("([^"]*)"|\S+)')


def parse_kv(args: str) -> Dict[str, str]:
    """解析 ``key=value`` 参数序列，value 支持双引号包裹（可含空格）。"""
    result: Dict[str, str] = {}
    for m in _KV_RE.finditer(args or ""):
        value = m.group(3) if m.group(3) is not None else m.group(2)
        result[m.group(1)] = value
    return result


def _truncate(text: str, limit: int = _OUTPUT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（已截断，共 {len(text)} 字符）"


def _fmt_ts(ts: Optional[float]) -> str:
    if not ts:
        return "未知"
    return time.strftime("%Y-%m-%d", time.localtime(ts))


class WikidotCommandHandler:
    """Wikidot 子命令处理器。"""

    def __init__(self, client: WikidotClient, admin_only: bool = True) -> None:
        self._client = client
        self._admin_only = bool(admin_only)

    # ------------------------------------------------------------------ #
    # 入口与分发
    # ------------------------------------------------------------------ #
    async def handle_command(
        self, event: AstrMessageEvent, message: str
    ) -> AsyncGenerator[Any, None]:
        try:
            command, args = self._parse_command(message)
            if command == "help":
                yield event.plain_result(self.HELP_TEXT)
                return
            if not self._client.configured():
                yield event.plain_result(self._not_configured_text())
                return

            handler, need_admin = self._resolve(command)
            if handler is None:
                yield event.plain_result(
                    f"❌ 未知的 Wikidot 子命令: {command}\n"
                    f"💡 发送 /wikidot 帮助 查看用法"
                )
                return
            if need_admin and not self._is_admin(event):
                yield event.plain_result(_WRITE_DENIED)
                return
            if not need_admin and self._admin_only and not self._is_admin(event):
                yield event.plain_result(_READ_DENIED)
                return

            logger.info(f"[Wikidot] 子命令: {command} args={args[:80]}")
            result = await handler(args, event)
            if isinstance(result, list):
                for item in result:
                    yield event.plain_result(item)
            elif result:
                yield event.plain_result(result)
        except WikidotError as e:
            yield event.plain_result(self._fmt_error(e))
        except ValueError as e:
            yield event.plain_result(f"❌ 参数错误: {e}\n💡 发送 /wikidot 帮助 查看用法")
        except Exception as e:
            logger.error(f"[Wikidot] 命令处理异常: {e}", exc_info=True)
            yield event.plain_result(
                f"❌ Wikidot 操作失败: {e}\n💡 发送 /wikidot 帮助 查看用法"
            )

    def _parse_command(self, message: str) -> Tuple[str, str]:
        """剥离 ``/wikidot`` 前缀，返回 (子命令, 余下参数)。"""
        cleaned = re.sub(
            r"^[/!！]\s*(wikidot|wd|维基)\s*", "", message.strip(),
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(wikidot|wd|维基)\s*", "", cleaned.strip(), flags=re.IGNORECASE
        ).strip()
        if not cleaned or cleaned.lower() in ("help", "-h", "--help", "帮助"):
            return "help", ""
        parts = cleaned.split(None, 1)
        return parts[0].lower(), parts[1].strip() if len(parts) > 1 else ""

    def _resolve(self, command: str):
        """返回 (handler, 是否写操作)；未知命令返回 (None, False)。"""
        table: Dict[str, Tuple[Any, bool]] = {
            # 通用
            "status": (self._cmd_status, False),
            "状态": (self._cmd_status, False),
            "登录": (self._cmd_login, True),
            "login": (self._cmd_login, True),
            # 页面 - 读
            "source": (self._cmd_source, False),
            "src": (self._cmd_source, False),
            "源码": (self._cmd_source, False),
            "info": (self._cmd_info, False),
            "信息": (self._cmd_info, False),
            # 页面 - 写
            "write": (self._cmd_write, True),
            "save": (self._cmd_write, True),
            "写入": (self._cmd_write, True),
            "append": (self._cmd_append, True),
            "追加": (self._cmd_append, True),
            "tags": (self._cmd_tags, True),
            "标签": (self._cmd_tags, True),
            "rename": (self._cmd_rename, True),
            "重命名": (self._cmd_rename, True),
            "parent": (self._cmd_parent, True),
            "父页": (self._cmd_parent, True),
            "delete": (self._cmd_delete, True),
            "del": (self._cmd_delete, True),
            "删除": (self._cmd_delete, True),
            # 成员
            "members": (self._cmd_members, False),
            "member": (self._cmd_members, False),
            "成员": (self._cmd_members, False),
            "remove": (self._cmd_remove_member, True),
            "移除": (self._cmd_remove_member, True),
            "移除成员": (self._cmd_remove_member, True),
            "踢出": (self._cmd_remove_member, True),
            "kick": (self._cmd_remove_member, True),
            "ban": (self._cmd_ban, True),
            "封禁": (self._cmd_ban, True),
            "unban": (self._cmd_unban, True),
            "解封": (self._cmd_unban, True),
            # 站点设置
            "settings": (self._cmd_settings, False),
            "设置": (self._cmd_settings, False),
            "policy": (self._cmd_policy, False),
            "访问策略": (self._cmd_policy, False),
            "nav": (self._cmd_nav, False),
            "navigation": (self._cmd_nav, False),
            "导航": (self._cmd_nav, False),
            "license": (self._cmd_license, False),
            "许可证": (self._cmd_license, False),
            "许可": (self._cmd_license, False),
            "template": (self._cmd_template, False),
            "模板": (self._cmd_template, False),
            "theme": (self._cmd_theme, False),
            "appearance": (self._cmd_theme, False),
            "外观": (self._cmd_theme, False),
            "主题": (self._cmd_theme, False),
            # 论坛
            "forum": (self._cmd_forum, False),
            "论坛": (self._cmd_forum, False),
            # 邀请 / 申请
            "invite": (self._cmd_invite, False),
            "邀请": (self._cmd_invite, False),
            "邀请开关": (self._cmd_invite_switch, True),
            "applications": (self._cmd_applications, False),
            "apps": (self._cmd_applications, False),
            "申请": (self._cmd_applications, False),
        }
        return table.get(command, (None, False))

    # ------------------------------------------------------------------ #
    # 权限与错误
    # ------------------------------------------------------------------ #
    @staticmethod
    def _is_admin(event: AstrMessageEvent) -> bool:
        try:
            return bool(event.is_admin())
        except Exception:
            return False

    @staticmethod
    def _fmt_error(e: WikidotError) -> str:
        prefix = {
            WikidotError.KIND_AUTH: "🔑 Wikidot 登录/会话问题",
            WikidotError.KIND_PERMISSION: "⛔",
            WikidotError.KIND_NO_PAGE: "📄",
            WikidotError.KIND_LOCKED: "🔒",
            WikidotError.KIND_FORM: "📝",
            WikidotError.KIND_RATE_LIMITED: "⏳",
            WikidotError.KIND_TIMEOUT: "⏱",
            WikidotError.KIND_NETWORK: "🌐",
            WikidotError.KIND_API: "❌",
        }.get(e.kind, "❌")
        return f"{prefix} {e}"

    def _not_configured_text(self) -> str:
        return (
            "⚠️ Wikidot 功能尚未配置\n"
            "💡 请在插件配置（WebUI 设置页或配置面板）填写：\n"
            "　• wikidot_site（站点名，如 scp-wiki-cn）\n"
            "　• wikidot_username / wikidot_password（Wikidot 账号）"
        )

    async def _resolve_user_id(self, username: str) -> Tuple[int, str]:
        """用户名 -> (user_id, 显示名)；数字直接当 ID，否则查用户页，
        再兜底翻成员列表。找不到抛 ValueError。"""
        if username.isdigit():
            return int(username), f"#{username}"
        try:
            resolved = await self._client.resolve_user(username)
        except WikidotError:
            resolved = None
        if resolved is not None:
            return resolved
        members, _ = await self._client.list_members(page=1)
        unix = to_unix_name(username)
        for member in members:
            if member.get("unix_name") == unix:
                return int(member["user_id"]), member.get("name") or username
        try:
            members_all = await self._client.list_all_members()
        except WikidotError:
            members_all = []
        for member in members_all:
            if member.get("unix_name") == unix:
                return int(member["user_id"]), member.get("name") or username
        raise ValueError(f"未找到 Wikidot 用户「{username}」")

    # ------------------------------------------------------------------ #
    # 通用
    # ------------------------------------------------------------------ #
    async def _cmd_status(self, args: str, event: AstrMessageEvent) -> str:
        c = self._client
        lines = [
            "📊 Wikidot 状态",
            f"　站点: {c.site or '（未配置）'}.wikidot.com",
            f"　账号: {c.username or '（未配置）'}",
            f"　配置完整: {'✅' if c.configured() else '❌'}",
            f"　读写均需管理员: {'是' if self._admin_only else '仅写操作需要'}",
        ]
        return "\n".join(lines)

    async def _cmd_login(self, args: str, event: AstrMessageEvent) -> str:
        session_id = await self._client.login(force=True)
        return f"✅ 已登录 {self._client.username}@{self._client.site}（会话已刷新）" if session_id else "❌ 登录失败"

    # ------------------------------------------------------------------ #
    # 页面
    # ------------------------------------------------------------------ #
    async def _cmd_source(self, args: str, event: AstrMessageEvent) -> str:
        page = args.split()[0] if args.split() else ""
        if not page:
            return "❌ 用法: /wikidot 源码 <页面名>\n例: /wikidot 源码 start"
        source = await self._client.get_source(page)
        if not source:
            return f"📄 页面 {page} 是空页面（无源码）"
        return f"📄 {page} 的源码：\n{_truncate(source)}"

    async def _cmd_info(self, args: str, event: AstrMessageEvent) -> str:
        page = args.split()[0] if args.split() else ""
        if not page:
            return "❌ 用法: /wikidot 信息 <页面名>"
        info = await self._client.get_page_info(page)
        if not info.get("exists"):
            return f"📄 页面 {page} 不存在"
        tags = "、".join(info.get("tags") or []) or "（无）"
        return (
            f"📄 页面信息\n"
            f"　名称: {page}\n"
            f"　标题: {info.get('title') or '（无）'}\n"
            f"　page_id: {info.get('page_id')}\n"
            f"　标签: {tags}"
        )

    async def _cmd_write(self, args: str, event: AstrMessageEvent) -> str:
        """写入页面：``写入 <页> :: 标题 :: 内容``，覆盖已有页面需尾缀「覆盖」。"""
        confirm = False
        stripped = args.strip()
        for word in OVERWRITE_WORDS:
            token = f" {word}"
            if stripped.endswith(token):
                confirm = True
                stripped = stripped[: -len(token)].rstrip()
        parts = [p.strip() for p in stripped.split("::")]
        if len(parts) < 2 or not parts[0]:
            return (
                "❌ 用法: /wikidot 写入 <页面> :: 标题 :: 内容\n"
                "　（标题可省略: /wikidot 写入 <页面> :: 内容）\n"
                "　覆盖已存在页面需在末尾加「 覆盖」"
            )
        page = parts[0].split()[0] if parts[0].split() else ""
        title = parts[1] if len(parts) >= 3 else ""
        content = parts[-1] if len(parts) >= 3 else parts[1]
        if len(parts) == 2:
            title, content = "", parts[1]
        if not page or not content:
            return "❌ 页面名与内容不能为空"
        info = await self._client.get_page_info(page)
        if info.get("exists") and not confirm:
            current = ""
            try:
                current = await self._client.get_source(page)
            except WikidotError:
                pass
            preview = _truncate(current, 200)
            return (
                f"⚠️ 页面 {page} 已存在，本次未写入。\n"
                f"　当前源码开头: {preview or '（空）'}\n"
                f"💡 确认覆盖请在命令末尾加「 覆盖」"
            )
        await self._client.save_page(
            page, content,
            title=title or None,
            comment=f"via AstrBot by {event.get_sender_name() or 'admin'}",
        )
        action = "覆盖" if info.get("exists") else "新建"
        return f"✅ 已{action}页面 {page}"

    async def _cmd_append(self, args: str, event: AstrMessageEvent) -> str:
        parts = args.strip().split(None, 1)
        if len(parts) < 2 or not parts[1].strip():
            return "❌ 用法: /wikidot 追加 <页面> <内容>"
        page, content = parts[0], parts[1].strip()
        await self._client.append_page(
            page, content,
            comment=f"append via AstrBot by {event.get_sender_name() or 'admin'}",
        )
        return f"✅ 已追加内容到 {page}"

    async def _cmd_tags(self, args: str, event: AstrMessageEvent) -> str:
        parts = args.strip().split(None, 1)
        if len(parts) < 2:
            return "❌ 用法: /wikidot 标签 <页面> <标签1> [标签2 ...]（空格分隔，整组覆盖）"
        page = parts[0]
        tags = [t for t in re.split(r"[\s,，]+", parts[1]) if t]
        await self._client.save_tags(page, tags)
        return f"✅ 已把 {page} 的标签设为: {' '.join(tags) or '（清空）'}"

    async def _cmd_rename(self, args: str, event: AstrMessageEvent) -> str:
        parts = args.split()
        if len(parts) == 2:
            return (
                f"⚠️ 即将把 {parts[0]} 重命名为 {parts[1]}。\n"
                f"💡 确认执行请补上尾缀: /wikidot 重命名 {parts[0]} {parts[1]} 确认"
            )
        if len(parts) != 3 or parts[2] not in CONFIRM_WORDS:
            return "❌ 用法: /wikidot 重命名 <旧页面> <新页面> 确认"
        old, new = parts[0], parts[1]
        await self._client.rename_page(old, new)
        return f"✅ 已重命名 {old} → {new}"

    async def _cmd_parent(self, args: str, event: AstrMessageEvent) -> str:
        parts = args.split()
        if len(parts) != 2:
            return "❌ 用法: /wikidot 父页 <页面> <父页面|无>"
        page, parent = parts
        await self._client.set_parent(page, None if parent in ("无", "none") else parent)
        return f"✅ 已设置 {page} 的父页面为 {parent}"

    async def _cmd_delete(self, args: str, event: AstrMessageEvent) -> str:
        parts = args.split()
        if len(parts) == 1 and parts[0]:
            info = await self._client.get_page_info(parts[0])
            if not info.get("exists"):
                return f"📄 页面 {parts[0]} 不存在"
            return (
                f"⚠️ 即将删除页面 {parts[0]}（标题: {info.get('title') or '无'}）。\n"
                f"💡 确认删除请执行: /wikidot 删除 {parts[0]} 确认"
            )
        if len(parts) != 2 or parts[1] not in CONFIRM_WORDS:
            return "❌ 用法: /wikidot 删除 <页面> 确认"
        await self._client.delete_page(parts[0])
        return f"🗑️ 已删除页面 {parts[0]}"

    # ------------------------------------------------------------------ #
    # 成员
    # ------------------------------------------------------------------ #
    async def _cmd_members(self, args: str, event: AstrMessageEvent) -> str:
        group = ""
        page_no = 1
        for token in args.split():
            if token in ("管理员", "admins"):
                group = "admins"
            elif token in ("版主", "moderators"):
                group = "moderators"
            elif token.isdigit():
                page_no = max(1, int(token))
        members, last_page = await self._client.list_members(group=group, page=page_no)
        if not members:
            return f"📄 第 {page_no} 页没有成员数据"
        group_label = {"": "全部成员", "admins": "管理员", "moderators": "版主"}[group]
        lines = [f"👥 {group_label}（第 {page_no}/{max(last_page, 1)} 页，共本页 {len(members)} 人）"]
        for m in members[:40]:
            lines.append(f"　• {m['name']}（{m['unix_name']}，加入于 {_fmt_ts(m.get('joined_ts'))}）")
        if len(members) > 40:
            lines.append(f"　…仅显示前 40 人，翻页: /wikidot 成员 {page_no + 1}")
        return "\n".join(lines)

    async def _cmd_remove_member(self, args: str, event: AstrMessageEvent) -> str:
        parts = args.split()
        ban = False
        if parts and parts[-1] in ("封禁", "ban"):
            ban = True
            parts = parts[:-1]
        if len(parts) != 1:
            return "❌ 用法: /wikidot 移除成员 <用户名> [封禁]"
        user_id, name = await self._resolve_user_id(parts[0])
        await self._client.remove_member(user_id, ban=ban)
        suffix = "（并同时封禁）" if ban else ""
        return f"✅ 已移除成员 {name}{suffix}"

    async def _cmd_ban(self, args: str, event: AstrMessageEvent) -> str:
        parts = args.strip().split(None, 1)
        if not parts:
            return "❌ 用法: /wikidot 封禁 <用户名> [原因]"
        reason = parts[1].strip() if len(parts) > 1 else ""
        user_id, name = await self._resolve_user_id(parts[0])
        await self._client.block_user(user_id, reason=reason)
        return f"✅ 已封禁 {name}" + (f"（原因: {reason}）" if reason else "")

    async def _cmd_unban(self, args: str, event: AstrMessageEvent) -> str:
        if not args.strip():
            return "❌ 用法: /wikidot 解封 <用户名>"
        user_id, name = await self._resolve_user_id(args.split()[0])
        await self._client.unblock_user(user_id)
        return f"✅ 已解封 {name}"

    # ------------------------------------------------------------------ #
    # 站点设置
    # ------------------------------------------------------------------ #
    async def _cmd_settings(self, args: str, event: AstrMessageEvent) -> str:
        kv = parse_kv(args)
        if not kv:
            settings = await self._client.get_general_settings()
            labels = {
                "name": "名称", "subtitle": "副标题", "language": "语言",
                "description": "描述", "default_page": "默认页",
                "welcome_page": "欢迎页",
            }
            lines = ["⚙️ 站点常规设置"]
            for key in ("name", "subtitle", "language", "description",
                        "default_page", "welcome_page"):
                lines.append(f"　{labels[key]}: {settings.get(key) or '（空）'}")
            lines.append("💡 修改: /wikidot 设置 名称=新名称 描述=\"一段 描述\"")
            return "\n".join(lines)
        updates: Dict[str, str] = {}
        for key, value in kv.items():
            field = _GENERAL_FIELD_ALIASES.get(key.lower()) or \
                _GENERAL_FIELD_ALIASES.get(key)
            if not field:
                raise ValueError(f"未知设置字段「{key}」，可用: 名称/副标题/语言/描述/默认页/欢迎页")
            updates[field] = value
        merged = await self._client.save_general_settings(updates)
        return f"✅ 已保存站点设置（名称: {merged.get('name')}）"

    async def _cmd_policy(self, args: str, event: AstrMessageEvent) -> str:
        kv = parse_kv(args)
        if not kv:
            policy = await self._client.get_access_policy()
            privacy_label = {
                "open": "公开（任何人可加入/浏览）",
                "closed": "封闭（仅受邀请）",
                "private": "私密（仅成员可浏览）",
            }.get(policy["privacy"], policy["privacy"])
            lines = [
                "🔐 站点访问策略",
                f"　隐私等级: {policy['privacy']} — {privacy_label}",
                f"　需申请加入: {'是' if policy['by_apply'] else '否'}",
                f"　按域名限制: {'是' if policy['by_domain'] else '否'}",
                f"　密码访问: {'是' if policy['by_password'] else '否'}"
                + (f"（密码已设置）" if policy["password"] else ""),
                f"　落地页: {policy['landingPage'] or '（默认）'}",
                "💡 修改: /wikidot 访问策略 privacy=closed 申请=on",
            ]
            return "\n".join(lines)
        updates: Dict[str, Any] = {}
        for key, value in kv.items():
            field = _POLICY_FIELD_ALIASES.get(key) or _POLICY_FIELD_ALIASES.get(key.lower())
            if not field:
                raise ValueError(f"未知策略字段「{key}」，可用: 隐私/申请/域名/密码访问/访问密码/落地页")
            if field in ("by_apply", "by_domain", "by_password"):
                updates[field] = value.lower() in ("on", "true", "1", "开", "yes")
            else:
                updates[field] = value
        merged = await self._client.save_access_policy(updates)
        return f"✅ 已保存访问策略（privacy={merged.get('privacy')}）"

    async def _cmd_nav(self, args: str, event: AstrMessageEvent) -> str:
        kv = parse_kv(args)
        use_default = bool(args.split()) and args.split()[0] in ("默认", "default")
        if use_default:
            await self._client.save_navigation(use_default=True)
            return "✅ 已恢复默认导航"
        if not kv:
            fields = await self._client.get_navigation()
            lines = ["🧭 站点导航元素"]
            for label, key in (("顶栏", "top_bar_page_name"), ("侧栏", "side_bar_page_name")):
                value = fields.get(key) or fields.get(key.replace("_page", ""))
                lines.append(f"　{label}: {value or '（默认）'}")
            lines.append("💡 修改: /wikidot 导航 顶栏=nav:top 侧栏=nav:side / 恢复默认: /wikidot 导航 默认")
            return "\n".join(lines)
        top = kv.get("顶栏") or kv.get("top") or kv.get("top_bar_page_name")
        side = kv.get("侧栏") or kv.get("side") or kv.get("side_bar_page_name")
        if top is None and side is None:
            raise ValueError("请提供 顶栏=页面 或 侧栏=页面（留空值表示清除该项）")
        await self._client.save_navigation(top=top, side=side)
        return "✅ 已保存导航设置"

    async def _cmd_license(self, args: str, event: AstrMessageEvent) -> str:
        kv = parse_kv(args)
        if not kv:
            license_info = await self._client.get_license()
            current = license_info.get("license_id") or "（未知）"
            lines = [f"📄 站点许可证: {current}"]
            options = license_info.get("options") or []
            if options:
                shown = [f"{v or '（默认）'}: {label}" for v, label in options[:10]]
                lines.append("　可选: " + "；".join(shown))
            lines.append('💡 修改: /wikidot 许可证 id=cc-by-sa-3.0 / other="自定义文本" / 默认')
            return "\n".join(lines)
        if "默认" in args or "default" in args.lower():
            await self._client.set_license(use_default=True)
            return "✅ 已恢复默认许可证"
        license_id = kv.get("id") or kv.get("许可证")
        other = kv.get("other") or kv.get("自定义")
        await self._client.set_license(license_id=license_id, other=other)
        return f"✅ 已设置许可证: {license_id or other}"

    async def _cmd_template(self, args: str, event: AstrMessageEvent) -> str:
        if not args.strip():
            info = await self._client.get_templates()
            lines = [f"📐 默认页面模板: {info.get('template_id') or '（无）'}"]
            for value, label in (info.get("options") or [])[:15]:
                mark = " ←" if value == info.get("template_id") else ""
                lines.append(f"　• {value or '（无）'}: {label}{mark}")
            lines.append("💡 修改: /wikidot 模板 <id> / /wikidot 模板 无")
            return "\n".join(lines)
        value = args.split()[0]
        await self._client.set_template(None if value in ("无", "none") else value)
        return f"✅ 已设置默认模板: {value}"

    async def _cmd_theme(self, args: str, event: AstrMessageEvent) -> str:
        if not args.strip():
            fields = await self._client.get_appearance()
            lines = ["🎨 站点外观（主题）设置"]
            for key in sorted(fields):
                lines.append(f"　{key}: {fields[key]}")
            lines.append("💡 修改: /wikidot 外观 <theme_id> / 恢复默认: /wikidot 外观 默认")
            return "\n".join(lines)
        value = args.split()[0]
        if value in ("默认", "default"):
            await self._client.set_appearance(use_default=True)
            return "✅ 已恢复默认主题"
        await self._client.set_appearance(theme_id=value)
        return f"✅ 已切换主题: {value}"

    # ------------------------------------------------------------------ #
    # 论坛
    # ------------------------------------------------------------------ #
    async def _cmd_forum(self, args: str, event: AstrMessageEvent) -> str:
        """论坛管理（嵌套子命令）。"""
        if not args.strip():
            layout = await self._client.get_forum_layout()
            nesting = layout.get("default_nesting")
            lines = ["💬 论坛版块结构" + (f"（默认嵌套 {nesting} 级）" if nesting is not None else "")]
            groups = layout.get("groups") or []
            if not groups:
                lines.append("　（论坛未启用或没有任何版块组）")
            for g in groups:
                vis = "" if g.get("visible", True) else "（隐藏）"
                lines.append(f"　▸ {g['name']}{vis}" + (f" — {g['description']}" if g.get("description") else ""))
                for c in g.get("categories", []):
                    lines.append(f"　　　• {c['name']}" + (f" — {c['description']}" if c.get("description") else ""))
            lines.append(
                "💡 子命令: 论坛 激活 | 论坛 嵌套 <0-10> | 论坛 加组 <名> [描述] | "
                "论坛 删组 <名> 确认 | 论坛 加版块 <组> <名> [描述] | 论坛 删版块 <名> 确认"
            )
            return "\n".join(lines)

        parts = args.split(None, 1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if sub in ("激活", "activate"):
            if not self._is_admin(event):
                return _WRITE_DENIED
            await self._client.activate_forum()
            return "✅ 论坛已激活"
        if sub in ("嵌套", "nesting"):
            if not self._is_admin(event):
                return _WRITE_DENIED
            if not rest.split() or not rest.split()[0].isdigit():
                return "❌ 用法: /wikidot 论坛 嵌套 <0-10>"
            await self._client.set_forum_nesting(int(rest.split()[0]))
            return f"✅ 已设置论坛默认嵌套深度为 {rest.split()[0]}"
        if sub in ("加组", "addgroup"):
            if not self._is_admin(event):
                return _WRITE_DENIED
            return await self._forum_add_group(rest)
        if sub in ("删组", "delgroup"):
            if not self._is_admin(event):
                return _WRITE_DENIED
            return await self._forum_del_group(rest)
        if sub in ("加版块", "addcategory", "addcat"):
            if not self._is_admin(event):
                return _WRITE_DENIED
            return await self._forum_add_category(rest)
        if sub in ("删版块", "delcategory", "delcat"):
            if not self._is_admin(event):
                return _WRITE_DENIED
            return await self._forum_del_category(rest)
        return (
            f"❌ 未知的论坛子命令: {sub}\n"
            f"💡 可用: 激活 / 嵌套 / 加组 / 删组 / 加版块 / 删版块"
        )

    async def _forum_add_group(self, rest: str) -> str:
        parts = rest.split(None, 1)
        if not parts:
            return "❌ 用法: /wikidot 论坛 加组 <组名> [描述]"
        layout = await self._client.get_forum_layout()
        groups = layout["groups"]
        if any(g["name"] == parts[0] for g in groups):
            raise ValueError(f"版块组「{parts[0]}」已存在")
        groups.append({
            "name": parts[0],
            "description": parts[1].strip() if len(parts) > 1 else "",
            "visible": True,
            "categories": [],
        })
        await self._client.save_forum_layout(groups)
        return f"✅ 已添加版块组「{parts[0]}」"

    async def _forum_del_group(self, rest: str) -> str:
        parts = rest.split()
        if len(parts) == 1:
            return f"⚠️ 将删除版块组「{parts[0]}」及其全部版块。\n💡 确认: /wikidot 论坛 删组 {parts[0]} 确认"
        if len(parts) != 2 or parts[1] not in CONFIRM_WORDS:
            return "❌ 用法: /wikidot 论坛 删组 <组名> 确认"
        name = parts[0]
        layout = await self._client.get_forum_layout()
        groups = layout["groups"]
        target = next((g for g in groups if g["name"] == name), None)
        if target is None:
            raise ValueError(f"版块组「{name}」不存在")
        deleted_groups = [target["group_id"]] if target.get("group_id") else []
        deleted_cats = [
            c.get("category_id") for c in target.get("categories", [])
            if c.get("category_id")
        ]
        await self._client.save_forum_layout(
            [g for g in groups if g["name"] != name],
            deleted_group_ids=deleted_groups,
            deleted_category_ids=deleted_cats,
        )
        return f"🗑️ 已删除版块组「{name}」"

    async def _forum_add_category(self, rest: str) -> str:
        parts = rest.split(None, 2)
        if len(parts) < 2:
            return "❌ 用法: /wikidot 论坛 加版块 <组名> <版块名> [描述]"
        group_name, cat_name = parts[0], parts[1]
        description = parts[2].strip() if len(parts) > 2 else ""
        layout = await self._client.get_forum_layout()
        groups = layout["groups"]
        target = next((g for g in groups if g["name"] == group_name), None)
        if target is None:
            raise ValueError(f"版块组「{group_name}」不存在")
        if any(c["name"] == cat_name for c in target["categories"]):
            raise ValueError(f"版块「{cat_name}」已存在于该组")
        target["categories"].append({
            "name": cat_name, "description": description, "max_nest_level": None,
        })
        await self._client.save_forum_layout(groups)
        return f"✅ 已在「{group_name}」下添加版块「{cat_name}」"

    async def _forum_del_category(self, rest: str) -> str:
        parts = rest.split()
        if len(parts) == 1:
            return f"⚠️ 将删除版块「{parts[0]}」。\n💡 确认: /wikidot 论坛 删版块 {parts[0]} 确认"
        if len(parts) != 2 or parts[1] not in CONFIRM_WORDS:
            return "❌ 用法: /wikidot 论坛 删版块 <版块名> 确认"
        name = parts[0]
        layout = await self._client.get_forum_layout()
        groups = layout["groups"]
        found_group = None
        for g in groups:
            if any(c["name"] == name for c in g["categories"]):
                found_group = g
                break
        if found_group is None:
            raise ValueError(f"版块「{name}」不存在")
        deleted_cats = [
            c.get("category_id") for c in found_group["categories"]
            if c["name"] == name and c.get("category_id")
        ]
        found_group["categories"] = [
            c for c in found_group["categories"] if c["name"] != name
        ]
        await self._client.save_forum_layout(
            groups, deleted_category_ids=deleted_cats
        )
        return f"🗑️ 已删除版块「{name}」"

    # ------------------------------------------------------------------ #
    # 邀请与申请
    # ------------------------------------------------------------------ #
    async def _cmd_invite(self, args: str, event: AstrMessageEvent) -> str:
        """邀请用户加入站点；``邀请 邮箱 <地址> [说明]`` 走邮件邀请（需管理员）。"""
        if not args.strip():
            return "❌ 用法: /wikidot 邀请 <用户名> [附言]　或　/wikidot 邀请 邮箱 <地址> [说明]"
        if args.split()[0] in ("邮箱", "email", "mail"):
            if not self._is_admin(event):
                return _WRITE_DENIED
            parts = args.split(None, 2)
            if len(parts) < 2 or "@" not in parts[1]:
                return "❌ 用法: /wikidot 邀请 邮箱 <邮箱地址> [说明]"
            message = parts[2].strip() if len(parts) > 2 else ""
            await self._client.send_email_invitation(parts[1], message=message)
            return f"✅ 已向 {parts[1]} 发送邮件邀请"
        parts = args.split(None, 1)
        text = parts[1].strip() if len(parts) > 1 else ""
        user_id, name = await self._resolve_user_id(parts[0])
        await self._client.invite_user(user_id, text=text)
        return f"✅ 已邀请 {name} 加入站点"

    async def _cmd_invite_switch(self, args: str, event: AstrMessageEvent) -> str:
        token = args.split()[0] if args.split() else ""
        if token in ("开", "on", "true", "1"):
            await self._client.set_let_users_invite(True)
            return "✅ 已允许站点成员邀请他人加入"
        if token in ("关", "off", "false", "0"):
            await self._client.set_let_users_invite(False)
            return "✅ 已禁止站点成员邀请他人加入"
        return "❌ 用法: /wikidot 邀请开关 <开|关>"

    async def _cmd_applications(self, args: str, event: AstrMessageEvent) -> str:
        if not args.strip():
            applications = await self._client.list_applications()
            if not applications:
                return "📄 当前没有待处理的加入申请"
            lines = ["📋 待处理的加入申请"]
            for app in applications:
                lines.append(
                    f"　• {app['name']}（unix: {app['unix_name']}）\n"
                    f"　　　留言: {app.get('text') or '（无）'}"
                )
            lines.append("💡 处理: /wikidot 申请 <用户名> 同意|拒绝")
            return "\n".join(lines)
        parts = args.split()
        if len(parts) != 2 or parts[1] not in ("同意", "accept", "拒绝", "decline"):
            return "❌ 用法: /wikidot 申请 <用户名> 同意|拒绝"
        accept = parts[1] in ("同意", "accept")
        if not self._is_admin(event):
            return _WRITE_DENIED
        user_id, name = await self._resolve_user_id(parts[0])
        await self._client.process_application(user_id, accept=accept)
        return f"✅ 已{'同意' if accept else '拒绝'} {name} 的加入申请"

    # ------------------------------------------------------------------ #
    # LLM 工具实现（main.py 里以 @filter.llm_tool 薄壳调用）
    # ------------------------------------------------------------------ #
    async def tool_get_page(self, fullname: str) -> str:
        """LLM 工具：获取页面源码与元信息。"""
        info = await self._client.get_page_info(fullname)
        if not info.get("exists"):
            return f"页面 {fullname} 不存在"
        try:
            source = await self._client.get_source(fullname)
        except WikidotError as e:
            source = f"（源码获取失败: {e}）"
        return (
            f"页面 {fullname}（标题: {info.get('title') or '无'}，"
            f"标签: {' '.join(info.get('tags') or []) or '无'}）源码:\n"
            f"{_truncate(source, 4000)}"
        )

    async def tool_save_page(
        self, event: AstrMessageEvent, fullname: str, source: str,
        comment: str = "",
    ) -> str:
        """LLM 工具：保存页面（管理员）。"""
        if not self._is_admin(event):
            return "仅管理员可通过 AI 保存 Wikidot 页面"
        await self._client.save_page(
            fullname, source, comment=comment or "edit via AstrBot LLM tool"
        )
        return f"已保存页面 {fullname}"

    async def tool_append_page(
        self, event: AstrMessageEvent, fullname: str, text: str,
        comment: str = "",
    ) -> str:
        """LLM 工具：向页面追加内容（管理员）。"""
        if not self._is_admin(event):
            return "仅管理员可通过 AI 追加 Wikidot 页面内容"
        await self._client.append_page(
            fullname, text, comment=comment or "append via AstrBot LLM tool"
        )
        return f"已向页面 {fullname} 追加内容"

    async def tool_list_members(self) -> str:
        """LLM 工具：成员列表。"""
        members, last_page = await self._client.list_members(page=1)
        if not members:
            return "站点没有成员数据"
        lines = [f"成员（第 1/{max(last_page, 1)} 页）:"]
        for m in members[:50]:
            lines.append(f"- {m['name']}（unix: {m['unix_name']}，加入于 {_fmt_ts(m.get('joined_ts'))}）")
        return "\n".join(lines)

    async def tool_forum_layout(self) -> str:
        """LLM 工具：论坛结构。"""
        layout = await self._client.get_forum_layout()
        lines = []
        for g in layout.get("groups") or []:
            lines.append(f"组: {g['name']}")
            for c in g.get("categories", []):
                lines.append(f"  - 版块: {c['name']}")
        return "\n".join(lines) or "论坛未启用或没有版块"

    async def tool_site_settings(self) -> str:
        """LLM 工具：站点常规设置。"""
        settings = await self._client.get_general_settings()
        return "\n".join(f"{k}: {v}" for k, v in settings.items())

    HELP_TEXT = """📖 Wikidot 命令帮助（前缀 /wikidot、/wd、/维基 均可）

【页面】
　源码 <页> — 查看页面 wikitext
　信息 <页> — 页面标题/ID/标签
　写入 <页> :: 标题 :: 内容 — 新建/覆盖页面（覆盖已有页需末尾加「 覆盖」）
　追加 <页> <内容> — 追加到页面末尾
　标签 <页> <标签…> — 整组覆盖标签
　重命名 <旧> <新> 确认
　父页 <页> <父页|无>
　删除 <页> 确认

【成员】
　成员 [页码] / 成员 管理员 / 成员 版主
　移除成员 <用户> [封禁]
　封禁 <用户> [原因] / 解封 <用户>

【站点设置】
　设置 [字段=值…]（名称/副标题/语言/描述/默认页/欢迎页）
　访问策略 [隐私=open|closed|private 申请=on|off …]
　导航 [顶栏=页 侧栏=页|默认]
　许可证 [id=…|other=…|默认]
　模板 [id|无] / 外观 [id|默认]

【论坛】
　论坛 — 查看结构
　论坛 激活 / 论坛 嵌套 <0-10>
　论坛 加组 <组> [描述] / 论坛 删组 <组> 确认
　论坛 加版块 <组> <版块> [描述] / 论坛 删版块 <版块> 确认

【邀请/申请】
　邀请 <用户> [附言]
　邀请 邮箱 <地址> [说明]
　邀请开关 <开|关>
　申请 [列表] / 申请 <用户> 同意|拒绝

【其他】
　状态 — 配置与登录概览　　登录 — 强制重新登录（管理员）
　帮助 — 本帮助

⚠️ 所有写操作仅管理员可用；站点与账号在插件配置中填写。"""
