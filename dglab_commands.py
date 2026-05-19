"""DG-LAB 设备管理命令处理器

提供完整的设备管理命令集:
- /dglab bind [server_url]    - 绑定设备（生成二维码）
- /dglab unbind              - 解绑当前设备
- /dglab strength <A|B> <0-200> - 设置通道强度
- /dglab up/down <A|B> [step]  - 增加/减少强度
- /dglab pulse <A|B> <preset> [sec] - 发送波形
- /dglab stop [A|B]           - 停止指定/所有通道
- /dglab clear <A|B>          - 清空波形队列
- /dglab feedback             - 查看设备实时强度反馈
- /dglab status               - 查看绑定状态和连接状态
- /dglab info                 - 查看详细设备信息
- /dglab help                 - 显示帮助信息
"""

import re
import os
import asyncio
import time
import tempfile
from typing import Optional, Tuple, List, Union
from datetime import datetime

import qrcode

from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger

from .dglab_device_store import DeviceBinding


class DGLabCommandError(Exception):
    """DG-LAB命令错误"""
    def __init__(self, message: str, suggestion: str = ""):
        super().__init__(message)
        self.suggestion = suggestion


# 预设波形数据（每条8字节HEX，代表100ms脉冲）
WAVE_PRESETS = {
    "breathe": {
        "name": "呼吸",
        "description": "缓慢渐强渐弱",
        "data": [
            "0A0A0A0A14141414", "0A0A0A0A1E1E1E1E", "0A0A0A0A28282828",
            "0A0A0A0A32323232", "0A0A0A0A3C3C3C3C", "0A0A0A0A46464646",
            "0A0A0A0A50505050", "0A0A0A0A5A5A5A5A", "0A0A0A0A64646464",
            "0A0A0A0A5A5A5A5A", "0A0A0A0A50505050", "0A0A0A0A46464646",
            "0A0A0A0A3C3C3C3C", "0A0A0A0A32323232", "0A0A0A0A28282828",
            "0A0A0A0A1E1E1E1E", "0A0A0A0A14141414", "0A0A0A0A0A0A0A0A",
        ],
    },
    "pulse": {
        "name": "脉冲",
        "description": "快速间歇脉冲",
        "data": [
            "0A0A0A0A64646464", "0A0A0A0A64646464", "0A0A0A0A64646464",
            "0A0A0A0A00000000", "0A0A0A0A00000000", "0A0A0A0A00000000",
            "0A0A0A0A64646464", "0A0A0A0A64646464", "0A0A0A0A64646464",
            "0A0A0A0A00000000", "0A0A0A0A00000000", "0A0A0A0A00000000",
        ],
    },
    "wave": {
        "name": "波浪",
        "description": "连续波浪起伏",
        "data": [
            "0A0A0A0A14141414", "0A0A0A0A28282828", "0A0A0A0A3C3C3C3C",
            "0A0A0A0A50505050", "0A0A0A0A64646464", "0A0A0A0A64646464",
            "0A0A0A0A50505050", "0A0A0A0A3C3C3C3C", "0A0A0A0A28282828",
            "0A0A0A0A14141414",
        ],
    },
    "tap": {
        "name": "敲击",
        "description": "短促有力的单次敲击",
        "data": [
            "0A0A0A0A64646464", "0A0A0A0A00000000", "0A0A0A0A00000000",
            "0A0A0A0A00000000", "0A0A0A0A00000000",
        ],
    },
    "storm": {
        "name": "风暴",
        "description": "高频持续输出",
        "data": [
            "0505050564646464", "0505050564646464", "0505050564646464",
            "0505050564646464", "0505050564646464", "0505050564646464",
            "0505050564646464", "0505050564646464", "0505050564646464",
            "0505050564646464",
        ],
    },
}


class DGLabCommandHandler:
    """DG-LAB命令处理器
    
    职责:
    1. 解析用户输入的命令参数
    2. 参数合法性校验
    3. 调用底层连接池执行操作
    4. 格式化返回结果
    5. 统一异常处理
    """
    
    HELP_TEXT = """🔌 DG-LAB 设备管理 使用说明

📌 设备绑定管理
  /dglab bind [服务器地址]   绑定设备（显示二维码）
                            例: /dglab bind ws://192.168.1.100:9999
  /dglab unbind             解绑当前设备

📌 强度控制 (范围: 0-200)
  /dglab strength <A|B> <值>  设置通道强度
                            例: /dglab strength A 50
  /dglab up <A|B> [步进]     增加强度（默认+5）
                            例: /dglab up A 10
  /dglab down <A|B> [步进]    减少强度（默认-5）
                            例: /dglab down B

📌 波形控制
  /dglab pulse <A|B> <预设名> [秒数]  发送波形（默认5秒）
                            例: /dglab pulse A breathe 10
  /dglab pulse <A|B> <HEX数据> [秒数] 发送自定义波形
                            例: /dglab pulse B 0A0A0A0A64646464
  可用预设: breathe(呼吸), pulse(脉冲), wave(波浪), tap(敲击), storm(风暴)

📌 电击启停
  /dglab shock <A|B> [强度] [波形] [秒数]  开始电击
                            例: /dglab shock A 30 breathe 10
                            默认: 强度20, 波形pulse, 持续5秒
  /dglab stop [A|B]          停止电击（不指定则停止全部）
  /dglab clear <A|B>         清空波形队列

📌 状态与反馈
  /dglab status              查看绑定和连接状态
  /dglab info                查看详细设备信息
  /dglab feedback            查看设备实时强度和反馈

📌 权限管理
  /dglab permission          查看权限隔离状态
  /dglab permission off      关闭隔离（允许他人操控你的设备）
  /dglab permission on       开启隔离（仅本人可控，默认）

⚠️ 注意事项
  • 强度值范围: 0-200，请根据个人耐受度调整
  • A/B通道分别对应不同的脉冲输出
  • 绑定后可保持长时间在线，超时自动断开
  • 操控他人设备: /dglab strength @用户ID A 50
  • 如遇问题发送 /dglab help 查看帮助

💡 提示: 默认开启权限隔离，仅本人可控制自己的设备
   使用 /dglab permission off 可允许他人操控"""
    
    def __init__(self, connection_pool, device_store, default_server_url: str = ""):
        self._pool = connection_pool
        self._store = device_store
        self._default_server_url = default_server_url
    
    async def handle_command(self, event: AstrMessageEvent, message: str):
        """处理DG-LAB命令（统一入口）"""
        user_id = self._extract_user_id(event)
        user_name = event.get_sender_name()
        
        try:
            command, args = self._parse_command(message)
            logger.info(f"[DGLab] 收到命令: {command} from {user_name}({user_id})")
            
            if command == "help":
                yield event.plain_result(self.HELP_TEXT)
                return
            
            result = await self._dispatch_command(command, args, user_id, user_name, event)
            
            if isinstance(result, list):
                for item in result:
                    yield item
            else:
                yield event.plain_result(result)
                
        except DGLabCommandError as e:
            error_msg = f"❌ {str(e)}"
            if e.suggestion:
                error_msg += f"\n💡 {e.suggestion}"
            error_msg += "\n💡 发送 /dglab help 查看帮助"
            yield event.plain_result(error_msg)
            
        except Exception as e:
            logger.error(f"[DGLab] 命令执行异常: {e}", exc_info=True)
            yield event.plain_result(
                f"❌ 操作失败: {str(e)}\n"
                f"💡 请稍后重试或联系管理员\n"
                f"💡 发送 /dglab help 查看帮助"
            )
    
    def _parse_command(self, message: str) -> Tuple[str, str]:
        """解析命令和参数"""
        cleaned = re.sub(r'^[/!！]\s*dglab\s*', '', message.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'^dglab\s*', '', cleaned.strip(), flags=re.IGNORECASE)
        cleaned = cleaned.strip()
        
        if not cleaned or cleaned.lower() in ('help', '-h', '--help', '帮助'):
            return "help", ""
        
        parts = cleaned.split(None, 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        return command, args
    
    async def _dispatch_command(
        self,
        command: str,
        args: str,
        user_id: str,
        user_name: str,
        event: AstrMessageEvent,
    ) -> Union[str, List]:
        """分发命令到对应的处理方法"""
        
        handlers = {
            "bind": self._cmd_bind,
            "unbind": self._cmd_unbind,
            "permission": self._cmd_permission,
            "perm": self._cmd_permission,
            "shared": self._cmd_permission,
            "strength": self._cmd_strength,
            "set": self._cmd_strength,
            "up": self._cmd_strength_up,
            "down": self._cmd_strength_down,
            "+": self._cmd_strength_up,
            "-": self._cmd_strength_down,
            "shock": self._cmd_shock,
            "start": self._cmd_shock,
            "fire": self._cmd_shock,
            "stop": self._cmd_stop,
            "clear": self._cmd_clear,
            "pulse": self._cmd_pulse,
            "wave": self._cmd_pulse,
            "feedback": self._cmd_feedback,
            "status": self._cmd_status,
            "info": self._cmd_info,
            "state": self._cmd_status,
        }
        
        handler = handlers.get(command)
        if not handler:
            raise DGLabCommandError(
                f"未知命令: {command}",
                suggestion="可用命令: bind, unbind, strength, up, down, shock, stop, clear, pulse, feedback, status, help"
            )
        
        return await handler(args, user_id, user_name, event)
    
    async def _cmd_bind(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """绑定设备命令"""
        server_url = args.strip() if args.strip() else None
        user_specified_url = bool(server_url)
        
        if not server_url:
            binding = self._store.get_binding(user_id)
            if binding and binding.server_url:
                server_url = binding.server_url
                logger.info(f"[DGLab] 使用上次绑定的服务器地址: {server_url}")
            elif self._default_server_url:
                server_url = self._default_server_url
                logger.info(f"[DGLab] 使用配置文件默认服务器地址: {server_url}")
            else:
                raise DGLabCommandError(
                    "未指定服务器地址",
                    suggestion="用法: /dglab bind ws://服务器地址:端口"
                )
        
        if not re.match(r'^wss?://[\w\.-]+(:\d+)?(/.*)?$', server_url):
            raise DGLabCommandError(
                "服务器地址格式错误",
                suggestion="正确格式: ws://host:port 或 wss://host:port（端口可省略）"
            )
        
        existing_binding = self._store.get_binding(user_id)
        if existing_binding:
            await self._pool.close_user_connection(user_id)
            logger.info(f"[DGLab] 用户 {user_id} 重新绑定，关闭旧连接")
        
        try:
            client, status = await self._pool.get_or_create_connection(
                user_id=user_id,
                server_url=server_url,
            )
        except DGLabCommandError:
            raise
        except Exception as e:
            raise DGLabCommandError(f"连接失败: {str(e)}", suggestion="请检查服务器地址是否正确")

        state = client.state

        if state.last_error:
            raise DGLabCommandError(
                f"服务器未确认连接: {state.last_error}",
                suggestion="请检查服务器是否正常运行"
            )

        qr_content = state.qr_content

        if not qr_content:
            raise DGLabCommandError("生成二维码失败", suggestion="请检查服务器是否正常运行")

        now = datetime.now().isoformat()
        binding = DeviceBinding(
            user_id=user_id,
            client_id=state.client_id,
            target_id="",
            server_url=server_url,
            bound_time=now,
            last_active=now,
            nickname=user_name,
        )
        self._store.set_binding(binding)

        qr_img_path = self._generate_qr_image(qr_content, user_id)

        response_parts = [
            f"🔗 DG-LAB 设备绑定",
            f"",
            f"👤 用户: {user_name}",
        ]
        if user_specified_url:
            response_parts.append(f"🖥️  服务器: {server_url}")
        response_parts += [
            f"🆔 客户端ID: {state.client_id[:8]}...",
            f"",
            f"📱 请使用 DG-LAB APP 扫描下方二维码完成绑定",
            f"⏳ 等待APP扫码绑定中...",
            f"💡 扫码后使用 /dglab status 确认连接状态",
        ]

        return [
            event.plain_result("\n".join(response_parts)),
            event.image_result(qr_img_path),
        ]
    
    def _generate_qr_image(self, qr_content: str, user_id: str) -> str:
        """将二维码内容生成为图片文件，返回文件路径"""
        qr_dir = os.path.join("data", "dglab_qrcodes")
        os.makedirs(qr_dir, exist_ok=True)
        
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_content)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        file_path = os.path.join(qr_dir, f"qr_{user_id}.png")
        img.save(file_path)
        logger.info(f"[DGLab] 二维码图片已生成: {file_path}")
        
        return os.path.abspath(file_path)
    
    async def _cmd_permission(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """权限隔离开关: /dglab permission [on|off]"""
        binding = self._store.get_binding(user_id)
        if not binding:
            raise DGLabCommandError("当前未绑定设备", suggestion="请先使用 /dglab bind 绑定设备")
        
        arg = args.strip().lower()
        
        if arg in ("off", "open", "开", "关闭隔离", "0"):
            self._store.set_shared(user_id, True)
            return (
                "🔓 权限隔离已关闭\n"
                f"👤 用户: {user_name}\n"
                "📢 现在其他用户可以操控你的设备\n"
                "💡 使用 /dglab permission on 重新开启隔离"
            )
        elif arg in ("on", "close", "关", "开启隔离", "1"):
            self._store.set_shared(user_id, False)
            return (
                "🔒 权限隔离已开启\n"
                f"👤 用户: {user_name}\n"
                "🛡️ 仅你本人可以操控你的设备"
            )
        else:
            # 无参数时显示当前状态
            status = "🔓 关闭（他人可操控）" if binding.shared else "🔒 开启（仅本人可控）"
            return (
                f"🛡️ 权限隔离状态\n"
                f"\n"
                f"👤 用户: {user_name}\n"
                f"📋 当前状态: {status}\n"
                f"\n"
                f"💡 用法:\n"
                f"  /dglab permission off  关闭隔离（允许他人操控）\n"
                f"  /dglab permission on   开启隔离（仅本人可控）"
            )
    
    async def _cmd_unbind(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """解绑设备命令"""
        binding = self._store.get_binding(user_id)
        if not binding:
            raise DGLabCommandError("当前未绑定任何设备", suggestion="无需解绑")
        
        await self._pool.close_user_connection(user_id)
        self._store.remove_binding(user_id)
        
        return (
            f"✅ 设备解绑成功\n"
            f"👤 用户: {user_name}\n"
            f"🕐 解绑时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"💡 可随时使用 /dglab bind 重新绑定"
        )
    
    async def _cmd_strength(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """设置强度命令: /dglab strength [@user] <A|B> <0-200>"""
        target_id, remaining = self._resolve_target(args, user_id)
        channel, value = self._parse_strength_args(remaining)
        
        result = await self._pool.send_strength_command(
            user_id=target_id,
            channel=channel,
            mode=2,
            value=value,
        )
        
        return result
    
    async def _cmd_strength_up(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """增加强度命令: /dglab up [@user] <A|B> [step]"""
        target_id, remaining = self._resolve_target(args, user_id)
        channel, step = self._parse_strength_adjust_args(remaining, default_step=5)
        
        result = await self._pool.send_strength_command(
            user_id=target_id,
            channel=channel,
            mode=1,
            value=step,
        )
        
        return result
    
    async def _cmd_strength_down(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """减少强度命令: /dglab down [@user] <A|B> [step]"""
        target_id, remaining = self._resolve_target(args, user_id)
        channel, step = self._parse_strength_adjust_args(remaining, default_step=5)
        
        result = await self._pool.send_strength_command(
            user_id=target_id,
            channel=channel,
            mode=0,
            value=step,
        )
        
        return result

    async def _cmd_shock(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """开始电击: /dglab shock [@user] <A|B> [强度] [波形预设] [秒数]"""
        target_id, remaining = self._resolve_target(args, user_id)
        parts = remaining.strip().split()

        if len(parts) < 1:
            preset_list = ", ".join(WAVE_PRESETS.keys())
            raise DGLabCommandError(
                "参数不足",
                suggestion=f"用法: /dglab shock <A|B> [强度0-200] [波形预设] [秒数]\n可用预设: {preset_list}"
            )

        channel_str = parts[0].upper()
        channel = self._parse_channel(channel_str)
        channel_letter = {1: "A", 2: "B"}[channel]

        # 默认值
        strength = 20
        preset_name_key = "pulse"
        duration = 5

        # 解析可选参数
        idx = 1
        if idx < len(parts):
            try:
                strength = int(parts[idx])
                if not (0 <= strength <= 200):
                    raise DGLabCommandError("强度值超出范围", suggestion="强度值范围: 0-200")
                idx += 1
            except ValueError:
                pass

        if idx < len(parts) and parts[idx].lower() in WAVE_PRESETS:
            preset_name_key = parts[idx].lower()
            idx += 1

        if idx < len(parts):
            try:
                duration = int(parts[idx])
                if not (1 <= duration <= 30):
                    raise DGLabCommandError("持续时间超出范围", suggestion="持续时间范围: 1-30 秒")
            except ValueError:
                raise DGLabCommandError(f"持续时间必须是数字: {parts[idx]}", suggestion="持续时间范围: 1-30 秒")

        pulse_data = WAVE_PRESETS[preset_name_key]["data"]
        preset_display = WAVE_PRESETS[preset_name_key]["name"]

        # 设置强度
        await self._pool.send_strength_command(
            user_id=target_id, channel=channel, mode=2, value=strength,
        )
        # 发送波形
        await self._pool.send_pulse_command(
            user_id=target_id, channel=channel_letter,
            pulse_data=pulse_data, duration=duration,
        )

        return (
            f"⚡ 已启动{channel_letter}通道电击\n"
            f"📋 强度: {strength} | 波形: {preset_display} | 持续: {duration}秒\n"
            f"💡 使用 /dglab stop {channel_letter} 停止输出"
        )

    async def _cmd_stop(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """停止输出命令: /dglab stop [@user] [A|B]"""
        target_id, remaining = self._resolve_target(args, user_id)
        channel_str = remaining.strip().upper()

        if not channel_str:
            result = await self._pool.stop_all(target_id)
            return f"🛑 已停止所有输出\n{result}"

        channel = self._parse_channel(channel_str)
        await self._pool.send_strength_command(user_id=target_id, channel=channel, mode=2, value=0)
        await self._pool.clear_channel(target_id, channel)
        channel_name = {1: "A", 2: "B"}[channel]
        return f"🛑 已停止{channel_name}通道输出（强度归零 + 清空波形）"
    
    async def _cmd_clear(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """清空波形队列: /dglab clear [@user] <A|B>"""
        target_id, remaining = self._resolve_target(args, user_id)
        channel_str = remaining.strip().upper()
        if not channel_str:
            raise DGLabCommandError("必须指定通道", suggestion="用法: /dglab clear A 或 /dglab clear B")

        channel = self._parse_channel(channel_str)
        result = await self._pool.clear_channel(target_id, channel)
        return result

    async def _cmd_pulse(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """发送波形: /dglab pulse [@user] <A|B> <预设名|HEX数据> [持续秒数]"""
        target_id, remaining = self._resolve_target(args, user_id)
        parts = remaining.strip().split()

        if len(parts) < 2:
            preset_list = "\n".join(
                f"  • {key} — {info['name']}（{info['description']}）"
                for key, info in WAVE_PRESETS.items()
            )
            raise DGLabCommandError(
                "参数不足",
                suggestion=f"用法: /dglab pulse <A|B> <预设名> [秒数]\n可用预设:\n{preset_list}"
            )

        channel_str = parts[0].upper()
        channel = self._parse_channel(channel_str)
        channel_letter = {1: "A", 2: "B"}[channel]

        preset_or_hex = parts[1].lower()
        duration = 5

        if len(parts) >= 3:
            try:
                duration = int(parts[2])
                if not (1 <= duration <= 30):
                    raise DGLabCommandError("持续时间超出范围", suggestion="持续时间范围: 1-30 秒")
            except ValueError:
                raise DGLabCommandError(f"持续时间必须是数字: {parts[2]}", suggestion="持续时间范围: 1-30 秒")

        if preset_or_hex in WAVE_PRESETS:
            pulse_data = WAVE_PRESETS[preset_or_hex]["data"]
            preset_name = WAVE_PRESETS[preset_or_hex]["name"]
        else:
            # 尝试作为逗号分隔的HEX数据解析
            hex_parts = preset_or_hex.split(",")
            for h in hex_parts:
                if len(h) != 16 or not all(c in "0123456789abcdefABCDEF" for c in h):
                    raise DGLabCommandError(
                        f"无效的波形数据或预设名: {preset_or_hex}",
                        suggestion=f"可用预设: {', '.join(WAVE_PRESETS.keys())}\n或提供16位HEX数据（逗号分隔多条）"
                    )
            pulse_data = hex_parts
            preset_name = "自定义"

        result = await self._pool.send_pulse_command(
            user_id=target_id,
            channel=channel_letter,
            pulse_data=pulse_data,
            duration=duration,
        )
        return f"{result}\n📋 波形: {preset_name} | 通道: {channel_letter} | 持续: {duration}秒"

    async def _cmd_feedback(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """查看设备实时反馈: /dglab feedback [@user]"""
        target_id, _ = self._resolve_target(args, user_id)

        feedback = self._pool.get_strength_feedback(target_id)
        if not feedback:
            raise DGLabCommandError("无法获取设备反馈", suggestion="请确认设备已绑定且在线")

        parts = [
            "📡 DG-LAB 设备实时反馈",
            "",
            f"⚡ A通道强度: {feedback['strength_a']} / {feedback['limit_a']}",
            f"⚡ B通道强度: {feedback['strength_b']} / {feedback['limit_b']}",
        ]

        if feedback["last_feedback_button"] >= 0 and feedback["last_feedback_time"]:
            btn = feedback["last_feedback_button"]
            ch = "A" if btn < 5 else "B"
            btn_idx = (btn % 5) + 1
            elapsed = int(time.time() - feedback["last_feedback_time"])
            parts.extend([
                "",
                f"🔘 最近反馈按钮: {ch}通道 第{btn_idx}个（{elapsed}秒前）",
            ])

        return "\n".join(parts)
    
    async def _cmd_status(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """查看状态命令"""
        binding = self._store.get_binding(user_id)
        conn_status = self._pool.get_connection_status(user_id)
        status_info = self._pool.get_user_status_info(user_id)
        
        parts = ["📊 DG-LAB 设备状态"]
        
        if binding:
            bound_time = datetime.fromisoformat(binding.bound_time).strftime("%Y-%m-%d %H:%M")
            last_active = datetime.fromisoformat(binding.last_active).strftime("%Y-%m-%d %H:%M:%S")
            
            parts.extend([
                "",
                f"🔗 绑定状态: {'✅ 已绑定' if binding.target_id else '⏳ 等待扫码'}",
                f"🖥️  服务器: {binding.server_url}",
                f"🆔 客户端ID: {binding.client_id[:12]}...",
                f"🕐 绑定时间: {bound_time}",
                f"🔄 最后活跃: {last_active}",
            ])
            
            if conn_status:
                status_emoji = {
                    "connected": "🟡",
                    "bound": "🟢",
                    "error": "🔴",
                    "disconnected": "⚫",
                }.get(conn_status.value, "❓")
                
                parts.append(f"📡 连接状态: {status_emoji} {conn_status.value}")
                
                if status_info:
                    parts.append(f"⏱️  连接时长: {status_info.get('connected_seconds', 0)}秒")
                    parts.append(f"😴 空闲时长: {status_info.get('idle_seconds', 0)}秒")
        else:
            parts.extend([
                "",
                "❌ 未绑定设备",
                "",
                "💡 使用 /dglab bind <服务器地址> 进行绑定",
            ])
        
        active_count = self._pool.get_active_count()
        parts.append(f"\n📈 系统活跃连接数: {active_count}")
        
        return "\n".join(parts)
    
    async def _cmd_info(self, args: str, user_id: str, user_name: str, event: AstrMessageEvent) -> str:
        """查看详细信息命令"""
        binding = self._store.get_binding(user_id)
        status_info = self._pool.get_user_status_info(user_id)
        
        if not binding and not status_info:
            raise DGLabCommandError("无设备信息", suggestion="请先使用 /dglab bind 绑定设备")
        
        parts = ["🔍 DG-LAB 详细信息", ""]
        
        if binding:
            parts.extend([
                f"=== 绑定信息 ===",
                f"用户ID: {binding.user_id}",
                f"昵称: {binding.nickname or '未设置'}",
                f"客户端ID: {binding.client_id}",
                f"目标ID: {binding.target_id or '(等待绑定)'}",
                f"服务器: {binding.server_url}",
                f"绑定时间: {binding.bound_time}",
                f"最后活跃: {binding.last_active}",
                "",
            ])
        
        if status_info:
            parts.extend([
                f"=== 连接信息 ===",
                f"状态: {status_info.get('status', '未知')}",
                f"已绑定: {'是' if status_info.get('is_bound', False) else '否'}",
                f"连接时长: {status_info.get('connected_seconds', 0)}秒 ({status_info.get('connected_seconds', 0) // 60}分钟)",
                f"空闲时长: {status_info.get('idle_seconds', 0)}秒",
                f"错误次数: {status_info.get('error_count', 0)}",
            ])
        
        return "\n".join(parts)
    
    def _resolve_target(self, args: str, caller_id: str) -> tuple:
        """解析操控目标用户，返回 (target_user_id, remaining_args)。
        
        如果 args 以 @user_id 开头，则尝试操控该用户的设备（需权限检查）。
        否则操控自己的设备。
        """
        stripped = args.strip()
        target_id = caller_id
        remaining = stripped
        
        # 检查是否指定了目标用户: @user_id 参数
        if stripped.startswith("@"):
            parts = stripped.split(None, 1)
            target_id = parts[0][1:]  # 去掉 @ 前缀
            remaining = parts[1] if len(parts) > 1 else ""
        
        if target_id == caller_id:
            # 操控自己的设备，无需权限检查
            binding = self._store.get_binding(caller_id)
            if not binding:
                raise DGLabCommandError("你尚未绑定设备", suggestion="请先使用 /dglab bind 绑定设备")
            return target_id, remaining
        
        # 操控他人设备，检查权限
        binding = self._store.get_binding(target_id)
        if not binding:
            raise DGLabCommandError(
                f"目标用户 {target_id} 未绑定设备",
                suggestion="该用户需要先绑定设备"
            )
        if not binding.shared:
            raise DGLabCommandError(
                "权限不足，该用户已开启权限隔离",
                suggestion="目标用户需先执行 /dglab permission off 允许他人操控"
            )
        return target_id, remaining
    
    def _extract_user_id(self, event: AstrMessageEvent) -> str:
        """提取用户唯一标识"""
        try:
            return str(event.get_sender_id())
        except Exception:
            return f"unknown_{id(event)}"
    
    def _parse_channel(self, channel_str: str) -> int:
        """解析通道参数"""
        channel_str = channel_str.upper().strip()
        if channel_str == "A":
            return 1
        elif channel_str == "B":
            return 2
        else:
            raise DGLabCommandError(
                f"无效通道: {channel_str}",
                suggestion="通道必须是 A 或 B"
            )
    
    def _parse_strength_args(self, args: str) -> Tuple[int, int]:
        """解析强度设置参数: <A|B> <0-200>"""
        parts = args.strip().split()
        if len(parts) < 2:
            raise DGLabCommandError(
                "参数不足",
                suggestion="用法: /dglab strength <A|B> <0-200>"
            )
        
        channel = self._parse_channel(parts[0])
        
        try:
            value = int(parts[1])
        except ValueError:
            raise DGLabCommandError(
                f"强度值必须是数字: {parts[1]}",
                suggestion="强度值范围: 0-200"
            )
        
        if not (0 <= value <= 200):
            raise DGLabCommandError(
                f"强度值超出范围: {value}",
                suggestion="强度值必须在 0-200 之间"
            )
        
        return channel, value
    
    def _parse_strength_adjust_args(self, args: str, default_step: int = 5) -> Tuple[int, int]:
        """解析强度调整参数: <A|B> [step]"""
        parts = args.strip().split()
        if len(parts) < 1:
            raise DGLabCommandError(
                "参数不足",
                suggestion=f"用法: /dglab up/down <A|B> [步进值，默认{default_step}]"
            )
        
        channel = self._parse_channel(parts[0])
        
        step = default_step
        if len(parts) >= 2:
            try:
                step = int(parts[1])
                if not (1 <= step <= 200):
                    raise DGLabCommandError(
                        f"步进值超出范围: {step}",
                        suggestion="步进值范围: 1-200"
                    )
            except ValueError:
                raise DGLabCommandError(
                    f"步进值必须是数字: {parts[1]}",
                    suggestion="步进值范围: 1-200"
                )
        
        return channel, step
