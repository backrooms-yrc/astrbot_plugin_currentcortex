"""CurrentCortex 邮箱验证模块 - SMTP配置/验证码生成与发送"""

import json
import os
import random
import smtplib
import socket
import string
import threading
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Optional
from dataclasses import dataclass, asdict

from astrbot.api import logger


@dataclass
class SMTPConfig:
    """SMTP服务器配置"""

    host: str
    port: int
    username: str
    password: str
    encryption: str  # "none" / "tls" / "ssl"
    from_email: str


@dataclass
class VerificationCode:
    """邮箱验证码"""

    email: str
    code: str
    created_at: float
    expires_at: float
    used: bool = False


class EmailStore:
    """线程安全的邮箱验证码持久化存储与SMTP发送

    存储路径:
      data/dglab_smtp_config.json - SMTP配置（单个对象）
      data/dglab_verification_codes.json - 验证码（key: "email:code"）
    """

    def __init__(self, data_dir: str = "data"):
        self._data_dir = data_dir
        self._smtp_path = os.path.join(data_dir, "dglab_smtp_config.json")
        self._codes_path = os.path.join(data_dir, "dglab_verification_codes.json")
        self._lock = threading.Lock()
        self._smtp_config: Optional[SMTPConfig] = None
        self._codes: Dict[str, VerificationCode] = {}
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self):
        os.makedirs(self._data_dir, exist_ok=True)

    def _load(self):
        # 加载SMTP配置
        if os.path.exists(self._smtp_path):
            try:
                with open(self._smtp_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    try:
                        self._smtp_config = SMTPConfig(**data)
                        logger.info("[DGLab Email] 已加载SMTP配置")
                    except Exception as e:
                        logger.error(f"[DGLab Email] SMTP配置解析失败: {e}")
            except Exception as e:
                logger.error(f"[DGLab Email] 加载SMTP配置失败: {e}")

        # 加载验证码
        if os.path.exists(self._codes_path):
            try:
                with open(self._codes_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    with self._lock:
                        for key, cdata in data.items():
                            if isinstance(cdata, dict):
                                try:
                                    self._codes[key] = VerificationCode(**cdata)
                                except Exception as e:
                                    logger.error(
                                        f"[DGLab Email] 加载验证码 {key} 失败: {e}"
                                    )
                logger.info(f"[DGLab Email] 已加载 {len(self._codes)} 条验证码记录")
            except Exception as e:
                logger.error(f"[DGLab Email] 加载验证码数据失败: {e}")

    def _save_smtp(self):
        try:
            with self._lock:
                data = asdict(self._smtp_config) if self._smtp_config else {}
            temp = self._smtp_path + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, self._smtp_path)
        except Exception as e:
            logger.error(f"[DGLab Email] 保存SMTP配置失败: {e}")

    def _save_codes(self):
        try:
            with self._lock:
                data = {key: asdict(code) for key, code in self._codes.items()}
            temp = self._codes_path + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, self._codes_path)
        except Exception as e:
            logger.error(f"[DGLab Email] 保存验证码数据失败: {e}")

    # ── SMTP 配置 ──────────────────────────────────────────

    def get_config(self) -> Optional[SMTPConfig]:
        """加载并返回SMTP配置，未配置则返回None"""
        with self._lock:
            return self._smtp_config

    def save_config(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        encryption: str,
        from_email: str,
    ) -> SMTPConfig:
        """保存SMTP配置，校验端口和加密方式后持久化"""
        if port not in (25, 465, 587):
            raise ValueError(f"不支持的SMTP端口: {port}，仅支持 25/465/587")
        if encryption not in ("none", "tls", "ssl"):
            raise ValueError(f"不支持的加密方式: {encryption}，仅支持 none/tls/ssl")

        # from_email 为空时使用 username 作为发件人
        if not from_email:
            from_email = username

        config = SMTPConfig(
            host=host,
            port=port,
            username=username,
            password=password,
            encryption=encryption,
            from_email=from_email,
        )
        with self._lock:
            self._smtp_config = config
        self._save_smtp()
        logger.info(f"[DGLab Email] SMTP配置已保存: {host}:{port} ({encryption})")
        return config

    def test_connection(
        self, host: str, port: int, username: str, password: str, encryption: str
    ) -> tuple:
        """测试SMTP连接，不保存配置。返回 (success, message)"""
        server = None
        try:
            logger.info(f"[DGLab Email] 正在测试SMTP连接: {host}:{port} ({encryption})")

            if encryption == "ssl":
                server = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server = smtplib.SMTP(host, port, timeout=15)

            # 开启调试日志
            server.set_debuglevel(0)

            # 发送 EHLO（某些服务器要求在 STARTTLS 前先 EHLO）
            server.ehlo()

            if encryption == "tls":
                server.starttls()
                server.ehlo()  # STARTTLS 后需要再次 EHLO

            # 登录验证
            server.login(username, password)

            # 验证发件人地址
            server.noop()  # 简单的 NOOP 确认连接正常

            server.quit()
            logger.info(f"[DGLab Email] SMTP连接测试成功: {host}:{port}")
            return True, "连接成功，认证通过"

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"[DGLab Email] SMTP认证失败: {e}")
            smtp_code = getattr(e, "smtp_code", "")
            smtp_error = getattr(e, "smtp_error", b"").decode("utf-8", errors="replace")
            return False, f"认证失败 (代码:{smtp_code}): {smtp_error}"
        except smtplib.SMTPConnectError as e:
            logger.error(f"[DGLab Email] SMTP连接失败: {e}")
            return False, f"无法连接到SMTP服务器 {host}:{port}，请检查地址和端口"
        except smtplib.SMTPServerDisconnected as e:
            logger.error(f"[DGLab Email] SMTP服务器断开连接: {e}")
            return False, f"服务器断开连接，可能是加密方式不匹配（尝试切换 TLS/SSL）"
        except smtplib.SMTPHeloError as e:
            logger.error(f"[DGLab Email] SMTP HELO/EHLO 失败: {e}")
            return False, f"HELO/EHLO 握手失败: {e}"
        except smtplib.SMTPNotSupportedError as e:
            logger.error(f"[DGLab Email] SMTP不支持此操作: {e}")
            return False, f"服务器不支持此操作: {e}"
        except smtplib.SMTPException as e:
            logger.error(f"[DGLab Email] SMTP错误: {e}")
            return False, f"SMTP错误: {e}"
        except ConnectionRefusedError:
            logger.error(f"[DGLab Email] SMTP连接被拒绝: {host}:{port}")
            return False, f"连接被拒绝 ({host}:{port})，请检查主机地址和端口号是否正确"
        except ConnectionResetError:
            logger.error(f"[DGLab Email] SMTP连接被重置: {host}:{port}")
            return False, f"连接被重置，可能是加密方式不匹配或防火墙阻止"
        except socket.timeout:
            logger.error(f"[DGLab Email] SMTP连接超时: {host}:{port}")
            return (
                False,
                f"连接超时 ({host}:{port})，请检查服务器地址是否正确或网络是否畅通",
            )
        except socket.gaierror as e:
            logger.error(f"[DGLab Email] SMTP域名解析失败: {host} - {e}")
            return False, f"无法解析主机名 '{host}'，请检查地址是否正确"
        except OSError as e:
            logger.error(f"[DGLab Email] SMTP网络错误: {e}")
            return False, f"网络错误: {e}"
        except Exception as e:
            logger.error(f"[DGLab Email] SMTP测试异常: {type(e).__name__}: {e}")
            return False, f"连接失败 ({type(e).__name__}): {e}"
        finally:
            if server:
                try:
                    server.close()
                except Exception:
                    pass

    # ── 邮件发送 ────────────────────────────────────────────

    def send_verification_email(self, to_email: str, code: str) -> tuple:
        """发送验证码邮件，返回 (success, message)"""
        with self._lock:
            config = self._smtp_config

        if config is None:
            logger.warning("[DGLab Email] 尝试发送邮件但SMTP未配置")
            return False, "SMTP未配置，请联系管理员配置邮件服务"

        # 确定发件人地址
        from_addr = config.from_email or config.username

        html_body = self._build_email_html(code)
        text_body = self._build_email_text(code)

        server = None
        try:
            logger.info(f"[DGLab Email] 正在发送验证码邮件至: {to_email}")

            msg = MIMEMultipart("alternative")
            msg["Subject"] = "CurrentCortex 邮箱验证码"
            msg["From"] = from_addr
            msg["To"] = to_email
            msg["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
            # 添加纯文本和HTML两个版本
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            if config.encryption == "ssl":
                server = smtplib.SMTP_SSL(config.host, config.port, timeout=20)
            else:
                server = smtplib.SMTP(config.host, config.port, timeout=20)

            server.ehlo()

            if config.encryption == "tls":
                server.starttls()
                server.ehlo()

            server.login(config.username, config.password)

            # 发送邮件
            refused = server.sendmail(from_addr, [to_email], msg.as_string())

            if refused:
                logger.warning(f"[DGLab Email] 部分收件人被拒绝: {refused}")
                return False, f"收件人被拒绝: {refused}"

            server.quit()
            logger.info(f"[DGLab Email] 验证码邮件发送成功: {to_email}")
            return True, "邮件发送成功"

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"[DGLab Email] 发送邮件认证失败: {e}")
            smtp_error = getattr(e, "smtp_error", b"").decode("utf-8", errors="replace")
            return False, f"SMTP认证失败: {smtp_error}"
        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"[DGLab Email] 收件人被拒绝: {e}")
            return False, f"收件人地址被拒绝，请检查邮箱地址是否正确"
        except smtplib.SMTPSenderRefused as e:
            logger.error(f"[DGLab Email] 发件人被拒绝: {e}")
            return False, f"发件人地址被拒绝，请检查发件人邮箱配置"
        except smtplib.SMTPDataError as e:
            logger.error(f"[DGLab Email] 邮件数据错误: {e}")
            return False, f"邮件内容被拒绝: {e}"
        except smtplib.SMTPServerDisconnected as e:
            logger.error(f"[DGLab Email] 发送邮件时服务器断开: {e}")
            return False, f"发送过程中服务器断开连接，可能是加密方式不匹配"
        except smtplib.SMTPException as e:
            logger.error(f"[DGLab Email] 发送邮件失败: {e}")
            return False, f"发送失败: {e}"
        except socket.timeout:
            logger.error(f"[DGLab Email] 发送邮件超时: {to_email}")
            return False, f"发送超时，请检查网络连接或SMTP服务器状态"
        except ConnectionRefusedError:
            logger.error(f"[DGLab Email] SMTP连接被拒绝: {config.host}:{config.port}")
            return False, f"SMTP服务器拒绝连接，请检查配置"
        except socket.gaierror as e:
            logger.error(f"[DGLab Email] SMTP域名解析失败: {config.host} - {e}")
            return False, f"无法解析SMTP服务器地址，请检查配置"
        except Exception as e:
            logger.error(f"[DGLab Email] 发送邮件异常: {type(e).__name__}: {e}")
            return False, f"发送失败 ({type(e).__name__}): {e}"
        finally:
            if server:
                try:
                    server.close()
                except Exception:
                    pass

    @staticmethod
    def _build_email_text(code: str) -> str:
        """生成验证码邮件的纯文本内容"""
        return f"""CurrentCortex 邮箱验证码

您好，

您正在验证邮箱地址，请使用以下验证码完成操作：

验证码：{code}

有效期：24 小时

安全提示：请勿将验证码透露给任何人，CurrentCortex 不会主动向您索要验证码。

此邮件由 CurrentCortex 系统自动发送，请勿直接回复。
如果您没有进行此操作，请忽略此邮件。"""

    @staticmethod
    def _build_email_html(code: str) -> str:
        """生成验证码邮件的HTML内容（Material Design 3 暗色主题风格）"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CurrentCortex 邮箱验证码</title>
</head>
<body style="margin:0;padding:0;background-color:#1a1a2e;font-family:'Segoe UI','Roboto','Helvetica Neue',Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#1a1a2e;min-height:100vh;">
<tr>
<td align="center" style="padding:40px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">
<!-- Header -->
<tr>
<td align="center" style="padding-bottom:32px;">
<h1 style="margin:0;color:#bb86fc;font-size:28px;font-weight:600;letter-spacing:1px;">CurrentCortex</h1>
<p style="margin:8px 0 0;color:#9e9e9e;font-size:14px;">邮箱验证服务</p>
</td>
</tr>
<!-- Card -->
<tr>
<td style="background-color:#2d2d44;border-radius:16px;padding:40px 32px;">
<p style="margin:0 0 8px;color:#e0e0e0;font-size:16px;line-height:1.6;">您好，</p>
<p style="margin:0 0 28px;color:#b0b0b0;font-size:14px;line-height:1.6;">您正在验证邮箱地址，请使用以下验证码完成操作：</p>
<!-- Code Box -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr>
<td align="center" style="background-color:#3700b3;border-radius:12px;padding:24px 16px;">
<span style="font-size:36px;font-weight:700;color:#ffffff;letter-spacing:8px;font-family:'Courier New',monospace;">{code}</span>
</td>
</tr>
</table>
<!-- Info -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;">
<tr>
<td style="padding:16px;background-color:#1a1a2e;border-radius:8px;border-left:3px solid #bb86fc;">
<p style="margin:0 0 8px;color:#e0e0e0;font-size:13px;line-height:1.5;">
<strong style="color:#bb86fc;">有效期：</strong>24 小时
</p>
<p style="margin:0;color:#e0e0e0;font-size:13px;line-height:1.5;">
<strong style="color:#bb86fc;">安全提示：</strong>请勿将验证码透露给任何人，CurrentCortex 不会主动向您索要验证码。
</p>
</td>
</tr>
</table>
</td>
</tr>
<!-- Footer -->
<tr>
<td align="center" style="padding-top:24px;">
<p style="margin:0;color:#757575;font-size:12px;line-height:1.6;">此邮件由 CurrentCortex 系统自动发送，请勿直接回复。</p>
<p style="margin:8px 0 0;color:#757575;font-size:12px;">如果您没有进行此操作，请忽略此邮件。</p>
</td>
</tr>
</table>
</td>
</tr>
</table>
</body>
</html>"""

    # ── 验证码管理 ──────────────────────────────────────────

    def generate_code(self, email: str) -> str:
        """生成6位数字验证码，24小时有效，使该邮箱之前的未使用验证码失效"""
        code = "".join(random.choices(string.digits, k=6))
        now = time.time()

        with self._lock:
            # 使该邮箱之前未使用的验证码失效
            for key, vc in self._codes.items():
                if vc.email == email and not vc.used:
                    vc.used = True

            vc = VerificationCode(
                email=email,
                code=code,
                created_at=now,
                expires_at=now + 24 * 3600,
                used=False,
            )
            key = f"{email}:{code}"
            self._codes[key] = vc

        self._save_codes()
        logger.info(f"[DGLab Email] 已生成验证码: {email}")
        return code

    def verify_code(self, email: str, code: str) -> tuple:
        """验证验证码，返回 (success, message)"""
        key = f"{email}:{code}"
        now = time.time()

        with self._lock:
            vc = self._codes.get(key)

        if vc is None:
            return False, "验证码不存在"

        if vc.used:
            return False, "验证码已使用"

        if now > vc.expires_at:
            return False, "验证码已过期"

        with self._lock:
            vc.used = True

        self._save_codes()
        logger.info(f"[DGLab Email] 验证码验证成功: {email}")
        return True, "验证成功"

    def can_resend(self, email: str) -> tuple:
        """检查是否可以重新发送验证码（60秒冷却），返回 (can_resend, remaining_seconds)"""
        now = time.time()

        with self._lock:
            latest_created = 0.0
            for vc in self._codes.values():
                if vc.email == email and not vc.used:
                    if vc.created_at > latest_created:
                        latest_created = vc.created_at

        if latest_created == 0.0:
            return True, 0

        elapsed = now - latest_created
        if elapsed < 60:
            remaining = int(60 - elapsed)
            return False, remaining

        return True, 0

    def cleanup_expired(self) -> None:
        """清理已过期的验证码"""
        now = time.time()
        with self._lock:
            expired_keys = [
                key for key, vc in self._codes.items() if now > vc.expires_at
            ]
            for key in expired_keys:
                del self._codes[key]

        if expired_keys:
            self._save_codes()
            logger.info(f"[DGLab Email] 已清理 {len(expired_keys)} 条过期验证码")
