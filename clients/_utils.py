"""通用辅助函数。

供 main.py 及各 API 客户端模块复用。
"""
import os


def _format_api_key_not_configured(feature_name: str) -> str:
    """统一生成「LeiZ API Key 未配置」提示，供所有依赖 LeiZ 接口的命令复用。"""
    return (
        f"❌ {feature_name}功能未启用\n\n"
        "📝 原因：未配置 LeiZ API 统一密钥\n"
        "💡 解决方法：\n"
        "   1. 打开插件配置面板\n"
        "   2. 找到「LeiZ API 统一密钥 (leiz_api_key)」字段\n"
        "   3. 填写您的 API Key（请求头 x-api-key）\n"
        "   4. 保存配置并重启插件\n\n"
        "⚠️ 根据 LeiZ API 公告，所有接口（含免费接口）均需携带 API Key"
    )


def _remove_file_safe(file_path: str) -> None:
    """安全删除文件，忽略不存在 / 删除失败的情况（用于临时文件清理）。"""
    try:
        os.remove(file_path)
    except (FileNotFoundError, OSError):
        pass
