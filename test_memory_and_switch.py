"""跨群聊记忆 + 按群开关回归测试。

覆盖 cross_group_memory.py / group_switch_store.py 两个存储模块的
持久化格式迁移与全部公开方法，以及 main.py 中开关/忘记命令的
参数解析与守卫白名单逻辑（纯函数 + 命令协程，不碰网络）。

运行方式：python3 test_memory_and_switch.py
"""

import asyncio
import importlib
import json
import os
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

# --------------------------------------------------------------------------- #
# Mock 掉 AstrBot / aiohttp 等依赖，使 main.py 可在脱离框架时被 import。
# （与 test_reply_seg.py 相同的手法，但包名按目录实际名称动态推导）
# --------------------------------------------------------------------------- #


class MockLogger:
    def _add(self, level, message, *args, **kwargs):
        pass

    def info(self, message, *args, **kwargs):
        self._add("info", message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        self._add("debug", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self._add("warning", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._add("error", message, *args, **kwargs)


logger = MockLogger()
astrbot = types.ModuleType("astrbot")
astrbot_api = types.ModuleType("astrbot.api")
astrbot_api.__path__ = []
astrbot_api.logger = logger
astrbot_api.AstrBotConfig = dict


def _noop_decorator(*args, **kwargs):
    def _wrap(f):
        return f

    return _wrap


_FakeEventMessageType = types.SimpleNamespace(ALL="ALL")
_FakePlatformAdapterType = types.SimpleNamespace(ALL="ALL")
# main.py 在群聊判断处使用 MessageType.GROUP_MESSAGE，测试事件返回同一哨兵
_FakeMessageType = types.SimpleNamespace(
    GROUP_MESSAGE="GROUP_MESSAGE",
    PRIVATE_MESSAGE="PRIVATE_MESSAGE",
)

astrbot_event = types.ModuleType("astrbot.api.event")
astrbot_event.filter = types.SimpleNamespace(
    command=_noop_decorator,
    event_message_type=_noop_decorator,
    platform_adapter_type=_noop_decorator,
    on_llm_request=_noop_decorator,
    on_decorating_result=_noop_decorator,
    llm_tool=_noop_decorator,
    EventMessageType=_FakeEventMessageType,
    PlatformAdapterType=_FakePlatformAdapterType,
)
astrbot_event.AstrMessageEvent = object
astrbot_event.MessageEventResult = object
astrbot_event.MessageChain = type(
    "MessageChain", (), {
        "message": lambda self, *a, **k: self,
        "__init__": lambda self, chain=None, **k: setattr(self, "chain", chain or []),
    }
)

astrbot_event_filter = types.ModuleType("astrbot.api.event.filter")
astrbot_event_filter.EventMessageType = _FakeEventMessageType
astrbot_event_filter.PlatformAdapterType = _FakePlatformAdapterType
astrbot_event_filter.command = _noop_decorator
astrbot_event_filter.event_message_type = _noop_decorator
astrbot_event_filter.platform_adapter_type = _noop_decorator
astrbot_event_filter.on_llm_request = _noop_decorator
astrbot_event_filter.on_decorating_result = _noop_decorator
astrbot_event_filter.llm_tool = _noop_decorator

astrbot_star = types.ModuleType("astrbot.api.star")
astrbot_star.Context = object
astrbot_star.Star = object
astrbot_star.register = lambda *args, **kwargs: lambda cls: cls

astrbot_components = types.ModuleType("astrbot.api.message_components")
for comp_name in ("Plain", "At", "Reply", "Image", "Record", "Video", "Node"):
    setattr(
        astrbot_components,
        comp_name,
        type(comp_name, (), {"__init__": lambda self, **kw: None}),
    )

astrbot_provider = types.ModuleType("astrbot.api.provider")
astrbot_provider.ProviderRequest = object
astrbot_provider.LLMResponse = type("LLMResponse", (), {"completion_text": ""})

astrbot_platform = types.ModuleType("astrbot.api.platform")
astrbot_platform.MessageType = _FakeMessageType

astrbot_core = types.ModuleType("astrbot.core")
astrbot_core.__path__ = []
astrbot_core_agent = types.ModuleType("astrbot.core.agent")
astrbot_core_agent.__path__ = []
astrbot_core_agent_message = types.ModuleType("astrbot.core.agent.message")
astrbot_core_agent_message.TextPart = type("TextPart", (), {"__init__": lambda self, text="": setattr(self, "text", text)})

aiohttp_stub = types.ModuleType("aiohttp")
aiohttp_stub.ClientSession = object

sys.modules.update(
    {
        "astrbot": astrbot,
        "astrbot.api": astrbot_api,
        "astrbot.api.event": astrbot_event,
        "astrbot.api.event.filter": astrbot_event_filter,
        "astrbot.api.star": astrbot_star,
        "astrbot.api.message_components": astrbot_components,
        "astrbot.api.provider": astrbot_provider,
        "astrbot.api.platform": astrbot_platform,
        "astrbot.core": astrbot_core,
        "astrbot.core.agent": astrbot_core_agent,
        "astrbot.core.agent.message": astrbot_core_agent_message,
        "aiohttp": aiohttp_stub,
    }
)

# 包名取目录实际名称，测试不要求目录改名为 astrbot_plugin_pixiv
PKG = Path(__file__).resolve().parent.name
PLUGIN_DIR = Path(__file__).resolve().parent
plugin_parent = str(PLUGIN_DIR.parent)
if plugin_parent not in sys.path:
    sys.path.insert(0, plugin_parent)

# main.py 顶部的相对导入中，重依赖模块替换为空桩；
# cross_group_memory / group_switch_store 用真实实现（本测试的对象）。
class _StubURLExtractor:
    """URLExtractor 桩：自动解析监听器只用到 detect_platform。"""

    @staticmethod
    def detect_platform(text):
        text = text or ""
        if "bilibili.com/video/" in text or "b23.tv/" in text:
            return "bilibili"
        if "xiaohongshu.com" in text or "xhslink.com" in text:
            return "xiaohongshu"
        if "douyin.com" in text:
            return "douyin"
        if "weibo.com" in text or "weibo.cn" in text or "t.cn/" in text:
            return "weibo"
        return None

    @staticmethod
    def extract_bilibili(text):
        detected = _StubURLExtractor.detect_platform(text)
        if detected == "bilibili":
            return {"type": "bv", "id": "BV1stub"}
        return None


for module_name, attributes in {
    "dglab_device_store": {"DeviceStore": object},
    "dglab_connection_pool": {"DeviceConnectionPool": object},
    "dglab_commands": {"DGLabCommandHandler": object},
    "dglab_webui": {"DGLabWebUI": object},
    "dglab_user_store": {"UserStore": object},
    "dglab_permission_store": {"PermissionStore": object},
    "media_parser": {
        "MediaParserManager": object,
        "MediaParserError": Exception,
        "URLExtractor": _StubURLExtractor,
    },
}.items():
    module = types.ModuleType(f"{PKG}.{module_name}")
    for name, value in attributes.items():
        setattr(module, name, value)
    sys.modules[module.__name__] = module

main_mod = importlib.import_module(f"{PKG}.main")
memory_mod = importlib.import_module(f"{PKG}.cross_group_memory")
switch_mod = importlib.import_module(f"{PKG}.group_switch_store")

CrossGroupMemoryStore = memory_mod.CrossGroupMemoryStore
GroupSwitchStore = switch_mod.GroupSwitchStore
PluginCls = main_mod.CurrentCortexPlugin


# --------------------------------------------------------------------------- #
# 测试基建
# --------------------------------------------------------------------------- #


def _tmp_data_dir():
    d = tempfile.mkdtemp(prefix="cc_mem_switch_test_")
    return d


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class FakeEvent:
    """命令处理器所需的最小事件桩。"""

    def __init__(self, message_str, umo="aiocqhttp:GroupMessage:10000", admin=True):
        self.message_str = message_str
        self.unified_msg_origin = umo

    def get_message_type(self):
        return _FakeMessageType.GROUP_MESSAGE

    def is_admin(self):
        return True

    def get_platform_id(self):
        return self.unified_msg_origin.split(":", 1)[0] or "aiocqhttp"

    def get_sender_name(self):
        return "tester"

    def get_extra(self, key, default=None):
        return default

    async def send(self, result):
        if not hasattr(self, "sent"):
            self.sent = []
        self.sent.append(result)

    def plain_result(self, text):
        return ("plain", text)


def _run_command(gen):
    """收集异步生成器命令处理器的全部产出。"""

    async def _collect():
        return [item async for item in gen]

    return asyncio.run(_collect())


def _make_plugin(memory_store=None, switch_store=None):
    """构造仅初始化跨群记忆/开关相关属性的插件实例（绕过完整 __init__）。"""
    inst = PluginCls.__new__(PluginCls)
    inst._cross_group_enable = memory_store is not None
    inst._cross_group_store = memory_store
    inst._group_switch_enable = switch_store is not None
    inst._group_switch_store = switch_store
    inst._group_switch_admin_only = True
    return inst


def _texts(outputs):
    return "".join(t for kind, t in outputs if kind == "plain")


# --------------------------------------------------------------------------- #
# cross_group_memory.py
# --------------------------------------------------------------------------- #


def test_legacy_string_records_migrate_on_load():
    d = _tmp_data_dir()
    try:
        path = os.path.join(d, "currentcortex_cross_group.json")
        _write_json(path, {"p1": ["旧记录A", "旧记录B"]})
        store = CrossGroupMemoryStore(data_dir=d)
        recent = store.get_recent("p1", 10)
        assert recent == ["旧记录A", "旧记录B"], recent
        # 迁移后内部记录应为 dict 结构：ts=0.0（最旧）、tag=None
        buf = store._buffers["p1"]
        assert all(isinstance(r, dict) for r in buf), buf
        assert buf[0] == {"ts": 0.0, "tag": None, "content": "旧记录A"}, buf[0]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_record_appends_dict_and_trims():
    d = _tmp_data_dir()
    try:
        store = CrossGroupMemoryStore(data_dir=d)
        store.record("p1", "第1条", max_records=2)
        store.record("p1", "第2条", max_records=2)
        store.record("p1", "第3条", max_records=2)
        assert store.get_recent("p1", 10) == ["第2条", "第3条"]
        assert len(store._buffers["p1"]) == 2
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_record_persists_dict_format_roundtrip():
    d = _tmp_data_dir()
    try:
        store = CrossGroupMemoryStore(data_dir=d)
        store.record("p1", "内容X", max_records=5)
        store.flush()  # record 只改内存，读盘前需显式刷盘
        raw = _read_json(os.path.join(d, "currentcortex_cross_group.json"))
        rec = raw["p1"][0]
        assert set(rec.keys()) == {"ts", "tag", "content"}, rec
        assert rec["content"] == "内容X"
        # 重新加载仍是新格式
        store2 = CrossGroupMemoryStore(data_dir=d)
        assert store2.get_recent("p1", 5) == ["内容X"]
        store2.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_max_age_filters_old_records():
    d = _tmp_data_dir()
    try:
        now = time.time()
        path = os.path.join(d, "currentcortex_cross_group.json")
        _write_json(
            path,
            {
                "p1": [
                    {"ts": now - 7200, "tag": None, "content": "两小时前"},
                    {"ts": now - 10, "tag": None, "content": "刚刚"},
                    {"ts": 0.0, "tag": None, "content": "旧格式迁移记录"},
                ]
            },
        )
        store = CrossGroupMemoryStore(data_dir=d)
        # 只保留最近 1 小时内的记录
        got = store.get_recent("p1", 10, max_age_seconds=3600)
        assert got == ["刚刚"], got
        # 不传 max_age 时全部返回（旧行为）
        assert store.get_recent("p1", 10) == ["两小时前", "刚刚", "旧格式迁移记录"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_tag_filter():
    d = _tmp_data_dir()
    try:
        store = CrossGroupMemoryStore(data_dir=d)
        store.record("p1", "美食消息", max_records=10, tag="美食")
        store.record("p1", "天气消息", max_records=10, tag="天气")
        store.record("p1", "未分类消息", max_records=10)
        assert store.get_recent("p1", 10, tag="美食") == ["美食消息"]
        assert store.get_recent("p1", 10, tag="天气") == ["天气消息"]
        # tag=None 不过滤，返回全部（含未打标签）
        assert len(store.get_recent("p1", 10)) == 3
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_forget_keyword_case_insensitive():
    d = _tmp_data_dir()
    try:
        store = CrossGroupMemoryStore(data_dir=d)
        store.record("p1", "有人在聊Python", max_records=10)
        store.record("p1", "python真好玩", max_records=10)
        store.record("p1", "今天天气不错", max_records=10)
        removed = store.forget_keyword("p1", "PYTHON")
        assert removed == 2, removed
        assert store.get_recent("p1", 10) == ["今天天气不错"]
        # 删除已刷盘
        store.flush()
        raw = _read_json(os.path.join(d, "currentcortex_cross_group.json"))
        assert len(raw["p1"]) == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_record_defers_write_and_background_flush_persists():
    """record() 不得同步写盘（曾把事件循环卡 30 秒）；由后台线程延迟合并落盘。"""
    d = _tmp_data_dir()
    store = None
    try:
        path = os.path.join(d, "currentcortex_cross_group.json")
        store = CrossGroupMemoryStore(data_dir=d, flush_interval_seconds=0.05)
        store.record("p1", "第一条", max_records=5)
        # 消息热路径只改内存：此刻文件还不存在
        assert not os.path.exists(path), path
        store.record("p1", "第二条", max_records=5)
        # 后台线程在间隔到期后自动刷盘
        deadline = time.time() + 2
        while not os.path.exists(path) and time.time() < deadline:
            time.sleep(0.02)
        assert os.path.exists(path), path
        raw = _read_json(path)
        assert [r["content"] for r in raw["p1"]] == ["第一条", "第二条"]
    finally:
        if store is not None:
            store.close()
        shutil.rmtree(d, ignore_errors=True)


def test_close_flushes_pending_changes():
    """停用插件（close）必须把未落盘的变更同步写入，否则会丢最近的记录。"""
    d = _tmp_data_dir()
    try:
        path = os.path.join(d, "currentcortex_cross_group.json")
        store = CrossGroupMemoryStore(data_dir=d, flush_interval_seconds=60)
        store.record("p1", "待刷盘", max_records=5)
        assert not os.path.exists(path)  # 间隔很长，后台不会先写
        store.close()
        raw = _read_json(path)
        assert raw["p1"][0]["content"] == "待刷盘"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_forget_keyword_empty_or_no_match():
    d = _tmp_data_dir()
    try:
        store = CrossGroupMemoryStore(data_dir=d)
        store.record("p1", "内容", max_records=10)
        assert store.forget_keyword("p1", "") == 0
        assert store.forget_keyword("p1", "   ") == 0
        assert store.forget_keyword("p1", "不存在") == 0
        assert store.get_recent("p1", 10) == ["内容"]
        assert store.forget_keyword("没有的平台", "内容") == 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_clear_and_get_recent_limit():
    d = _tmp_data_dir()
    try:
        store = CrossGroupMemoryStore(data_dir=d)
        for i in range(5):
            store.record("p1", f"行{i}", max_records=10)
        assert store.get_recent("p1", 2) == ["行3", "行4"]
        assert store.clear("p1") == 5
        assert store.get_recent("p1", 10) == []
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- #
# group_switch_store.py
# --------------------------------------------------------------------------- #


def test_set_disabled_permanent():
    d = _tmp_data_dir()
    try:
        store = GroupSwitchStore(data_dir=d)
        assert store.is_enabled("umo-a") is True
        store.set_disabled("umo-a")
        assert store.is_enabled("umo-a") is False
        assert store.get_until("umo-a") is None  # None = 永久
        assert store.list_disabled() == ["umo-a"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_timed_disable_auto_recovers():
    d = _tmp_data_dir()
    try:
        store = GroupSwitchStore(data_dir=d)
        store.set_disabled("umo-a", duration_seconds=0.05)
        assert store.is_enabled("umo-a") is False
        until = store.get_until("umo-a")
        assert until is not None and until > time.time()
        time.sleep(0.1)
        # 懒惰过期：判断时自动清理并恢复
        assert store.is_enabled("umo-a") is True
        assert store.list_disabled() == []
        # 过期记录已被清理且刷盘
        raw = _read_json(os.path.join(d, "currentcortex_group_switch.json"))
        assert raw["disabled"] == {}, raw
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_get_until_future_timestamp():
    d = _tmp_data_dir()
    try:
        store = GroupSwitchStore(data_dir=d)
        before = time.time()
        store.set_disabled("umo-b", duration_seconds=3600)
        until = store.get_until("umo-b")
        assert before + 3595 <= until <= time.time() + 3605, until
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_list_disabled_detail():
    d = _tmp_data_dir()
    try:
        store = GroupSwitchStore(data_dir=d)
        store.set_disabled("umo-b")
        store.set_disabled("umo-a", duration_seconds=60)
        details = store.list_disabled_detail()
        assert [x["umo"] for x in details] == ["umo-a", "umo-b"]
        by_umo = {x["umo"]: x for x in details}
        assert by_umo["umo-a"]["permanent"] is False
        assert by_umo["umo-a"]["until"] is not None
        assert by_umo["umo-b"]["permanent"] is True
        assert by_umo["umo-b"]["until"] is None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_legacy_list_format_migration():
    d = _tmp_data_dir()
    try:
        path = os.path.join(d, "currentcortex_group_switch.json")
        _write_json(path, {"disabled": ["old-umo-1", "old-umo-2"]})
        store = GroupSwitchStore(data_dir=d)
        assert store.is_enabled("old-umo-1") is False
        assert store.is_enabled("old-umo-2") is False
        # 旧列表条目一律视为永久禁用
        assert store.get_until("old-umo-1") is None
        # 新代码保存后落盘为 dict 格式
        store.set_disabled("new-umo")
        raw = _read_json(path)
        assert raw["disabled"] == {
            "new-umo": None,
            "old-umo-1": None,
            "old-umo-2": None,
        }, raw["disabled"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_set_enabled_toggles():
    d = _tmp_data_dir()
    try:
        store = GroupSwitchStore(data_dir=d)
        assert store.set_enabled("umo-x") is False  # 本来就启用
        store.set_disabled("umo-x")
        assert store.set_enabled("umo-x") is True
        assert store.is_enabled("umo-x") is True
        assert store.set_enabled("umo-x") is False
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_new_dict_format_roundtrip():
    d = _tmp_data_dir()
    try:
        store = GroupSwitchStore(data_dir=d)
        until = time.time() + 120
        path = os.path.join(d, "currentcortex_group_switch.json")
        _write_json(path, {"disabled": {"umo-t": until, "umo-p": None}})
        store2 = GroupSwitchStore(data_dir=d)
        assert store2.is_enabled("umo-p") is False
        assert abs(store2.get_until("umo-t") - until) < 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- #
# main.py：开关/忘记命令解析与守卫白名单
# --------------------------------------------------------------------------- #


def _switch_plugin():
    d = _tmp_data_dir()
    store = GroupSwitchStore(data_dir=d)
    return _make_plugin(switch_store=store), store, d


def test_parse_switch_duration_units():
    inst = PluginCls.__new__(PluginCls)
    cases = {
        "/开关 off 2h": 7200.0,
        "/开关 off 30m": 1800.0,
        "/开关 off 1d": 86400.0,
        "/开关 off 45s": 45.0,
        "/开关 off 0.5h": 1800.0,
        "/开关 关 10秒": 10.0,
        "/开关 off 2小时": 7200.0,
        "/开关 off 30分钟": 1800.0,
        "off 1天": 86400.0,
    }
    for msg, expect in cases.items():
        got = inst._parse_switch_duration(msg)
        assert got == expect, f"{msg!r}: 期望 {expect}, 实际 {got}"


def test_parse_switch_duration_composite():
    inst = PluginCls.__new__(PluginCls)
    assert inst._parse_switch_duration("/开关 off 2小时30分钟") == 9000.0
    assert inst._parse_switch_duration("/开关 off 1d12h") == 129600.0
    assert inst._parse_switch_duration("/开关 off 1h 30m") == 5400.0


def test_parse_switch_duration_none_and_invalid():
    inst = PluginCls.__new__(PluginCls)
    # 无时长参数 → None（永久禁用，兼容旧用法）
    assert inst._parse_switch_duration("/开关 off") is None
    assert inst._parse_switch_duration("/开关 关") is None
    assert inst._parse_switch_duration("/开关") is None
    # 无法识别的参数必须抛 ValueError，绝不能静默当作永久禁用
    for bad in ("/开关 off 2x", "/开关 off abc", "/开关 off 2h30", "/开关 off 0s"):
        try:
            inst._parse_switch_duration(bad)
            raise AssertionError(f"{bad!r} 应当抛出 ValueError")
        except ValueError:
            pass


def test_parse_switch_action_first_token():
    inst = PluginCls.__new__(PluginCls)
    cases = {
        "/开关 off 2h": "off",
        "/开关 关 30m": "off",
        "开关 off": "off",
        "/开关 on": "on",
        "/开关 开": "on",
        "/开关 status": "status",
        "/开关 状态": "status",
        "/开关": "",
        "/开关 列表": "",
    }
    for msg, expect in cases.items():
        got = inst._parse_switch_action(msg)
        assert got == expect, f"{msg!r}: 期望 {expect}, 实际 {got}"


def test_is_switch_command_whitelist():
    # 守卫白名单必须覆盖开关列表命令（含别名），否则被禁群内会被静默拦截
    for msg in (
        "/开关 on",
        "/开关 off 2h",
        "开关 status",
        "/开关列表",
        "开关列表",
        "/switch_list",
        "/开关状态列表",
    ):
        assert PluginCls._is_switch_command(PluginCls.__new__(PluginCls), msg) is True, msg
    # 其他命令与相近词不得被放行
    for msg in ("/忘记 关键词", "开关机", "/weibo http://x", ""):
        assert PluginCls._is_switch_command(PluginCls.__new__(PluginCls), msg) is False, msg


def test_switch_off_invalid_duration_replies_error():
    inst, store, d = _switch_plugin()
    try:
        umo = "aiocqhttp:GroupMessage:10000"
        outputs = _run_command(
            inst.group_switch_command(FakeEvent("/开关 off 2x", umo=umo))
        )
        text = _texts(outputs)
        assert "无法识别" in text, text
        # 不得因解析失败而真的禁用
        assert store.is_enabled(umo) is True
        # 合法时长正常禁用
        outputs = _run_command(
            inst.group_switch_command(FakeEvent("/开关 off 10m", umo=umo))
        )
        assert store.is_enabled(umo) is False
        assert store.get_until(umo) is not None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_switch_list_command_filters_platform():
    inst, store, d = _switch_plugin()
    try:
        # 两个当前平台（aiocqhttp）的群 + 一个其他平台（telegram）的群
        store.set_disabled("aiocqhttp:GroupMessage:111")
        store.set_disabled("aiocqhttp:GroupMessage:222", duration_seconds=3600)
        store.set_disabled("telegram:GroupMessage:333")
        outputs = _run_command(
            inst.group_switch_list_command(
                FakeEvent("/开关列表", umo="aiocqhttp:GroupMessage:111")
            )
        )
        text = _texts(outputs)
        assert "群 111" in text and "永久" in text, text
        assert "群 222" in text and "自动恢复" in text, text
        assert "333" not in text and "telegram" not in text.lower(), text
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_switch_list_command_empty():
    inst, _, d = _switch_plugin()
    try:
        outputs = _run_command(
            inst.group_switch_list_command(
                FakeEvent("/开关列表", umo="aiocqhttp:GroupMessage:111")
            )
        )
        text = _texts(outputs)
        assert "没有被关闭" in text, text
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_forget_command_alias_keyword_extraction():
    # /忘记记忆 别名曾因正则备选顺序错误提取出「记忆 关键词」，此处回归
    d = _tmp_data_dir()
    try:
        store = CrossGroupMemoryStore(data_dir=d)
        store.record("aiocqhttp", "[某人/00:00:01]: 聊到某敏感词了", max_records=10)
        store.record("aiocqhttp", "[某人/00:00:02]: 无关内容", max_records=10)
        inst = _make_plugin(memory_store=store)
        outputs = _run_command(
            inst.cross_group_forget_command(FakeEvent("/忘记记忆 某敏感词"))
        )
        text = _texts(outputs)
        assert "已删除 1 条" in text, text
        assert store.get_recent("aiocqhttp", 10) == ["[某人/00:00:02]: 无关内容"]
        # 主命令名路径同样可用
        store.record("aiocqhttp", "[某人/00:00:03]: 又说某敏感词", max_records=10)
        outputs = _run_command(
            inst.cross_group_forget_command(FakeEvent("/忘记 某敏感词"))
        )
        assert "已删除 1 条" in _texts(outputs)
        assert store.get_recent("aiocqhttp", 10) == ["[某人/00:00:02]: 无关内容"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_forget_command_empty_keyword_hint():
    d = _tmp_data_dir()
    try:
        inst = _make_plugin(memory_store=CrossGroupMemoryStore(data_dir=d))
        outputs = _run_command(inst.cross_group_forget_command(FakeEvent("/忘记")))
        assert "用法" in _texts(outputs)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- #
# scope 分级开关（v2.2.0）与媒体解析批量
# --------------------------------------------------------------------------- #


def test_store_scope_semantics():
    d = _tmp_data_dir()
    try:
        store = GroupSwitchStore(data_dir=d)
        store.set_disabled("u1", scope="media", duration_seconds=3600)
        # scope 禁用不影响全局，也不影响其他 scope
        assert store.is_enabled("u1") is True
        assert store.is_enabled("u1", "media") is False
        assert store.is_enabled("u1", "music") is True
        # has_disabled_entry 只看条目本身，不受全局连带影响
        assert store.has_disabled_entry("u1", "media") is True
        assert store.has_disabled_entry("u1", "music") is False
        store.set_disabled("u1")  # 全局也关
        assert store.is_enabled("u1", "media") is False  # 全局优先
        assert store.has_disabled_entry("u1", "media") is True  # 条目仍在
        store.set_enabled("u1")  # 解除全局
        assert store.is_enabled("u1", "media") is False  # scope 仍单独禁用
        store.set_enabled("u1", scope="media")
        assert store.is_enabled("u1", "media") is True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_store_scoped_key_load_and_legacy():
    d = _tmp_data_dir()
    try:
        path = os.path.join(d, "currentcortex_group_switch.json")
        _write_json(
            path,
            {"disabled": {"old-umo": None, "u|music": time.time() + 60}},
        )
        store = GroupSwitchStore(data_dir=d)
        # 旧纯 umo key = 全局禁用；复合 key = 域级禁用
        assert store.is_enabled("old-umo") is False
        assert store.is_enabled("u") is True
        assert store.is_enabled("u", "music") is False
        assert store.is_enabled("u", "media") is True
        det = {f'{x["umo"]}|{x["scope"]}': x for x in store.list_disabled_detail()}
        assert "old-umo|None" in det and det["u|music"]["permanent"] is False
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_parse_switch_scope_tokens():
    inst = PluginCls.__new__(PluginCls)
    cases = {
        "/开关 off media 2h": "media",
        "/开关 off 媒体解析": "media",
        "/开关 off 音乐 30m": "music",
        "/开关 on 电击": "dglab",
        "/开关 media": "media",          # 省略动作词 = 查询该域
        "/开关 off 2h": None,
        "/开关 off": None,
        "/开关 status 跨群记忆": "memory",
        "/开关 off 天气": None,          # 非域词不误判
    }
    for msg, expect in cases.items():
        got = inst._parse_switch_scope(msg)
        assert got == expect, f"{msg!r}: 期望 {expect}, 实际 {got}"


def test_parse_switch_duration_skips_scope_token():
    inst = PluginCls.__new__(PluginCls)
    assert inst._parse_switch_duration("/开关 off media 2h") == 7200.0
    assert inst._parse_switch_duration("/开关 off 2h image") == 7200.0
    # 域参数后跟坏时长仍要报错，不能静默
    try:
        inst._parse_switch_duration("/开关 off media 2x")
        raise AssertionError("应当抛出 ValueError")
    except ValueError:
        pass


def test_detect_command_scope():
    dc = PluginCls._detect_command_scope
    assert dc("/解析 https://x") == "media"
    assert dc("/B站 BV1xx") == "media"
    assert dc("/pixiv") == "image"
    assert dc("/点歌 晴天") == "music"
    assert dc("今天天气不错") is None
    assert dc("/忘记 关键词") is None  # 杂项命令不属于任何功能域


def test_switch_on_scope_ordering_regression():
    """/开关 on <scope> 在全局关闭时不得误删 scope 条目（先判断后操作）。"""
    d = _tmp_data_dir()
    try:
        store = GroupSwitchStore(data_dir=d)
        umo = "aiocqhttp:GroupMessage:555"
        store.set_disabled(umo, scope="media", duration_seconds=3600)
        store.set_disabled(umo)  # 全局也关
        inst = _make_plugin(switch_store=store)
        text = _texts(
            _run_command(inst.group_switch_command(FakeEvent("/开关 on media", umo=umo)))
        )
        # scope 条目被显式恢复（用户明确要求），并如实提示全局仍关闭
        assert "已在本群重新启用" in text and "全局仍处于关闭状态" in text, text
        assert store.has_disabled_entry(umo, "media") is False
        assert store.is_enabled(umo) is False  # 全局条目不受影响

        # 反例：全局关 + 域未被单独关 → 只提示、零状态变更
        store2 = GroupSwitchStore(data_dir=d + "2")
        store2.set_disabled("u")
        inst2 = _make_plugin(switch_store=store2)
        before = store2.list_disabled_detail()
        text2 = _texts(
            _run_command(inst2.group_switch_command(FakeEvent("/开关 on media", umo="u")))
        )
        assert "并未被单独关闭" in text2 and "全局" in text2, text2
        assert store2.list_disabled_detail() == before  # 不得有任何误删

        # 常规：仅域禁用（全局开）→ 干净恢复
        store3 = GroupSwitchStore(data_dir=d + "3")
        store3.set_disabled("u", scope="media")
        inst3 = _make_plugin(switch_store=store3)
        text3 = _texts(
            _run_command(inst3.group_switch_command(FakeEvent("/开关 on media", umo="u")))
        )
        assert "已在本群重新启用" in text3 and "全局仍处于关闭" not in text3, text3
        assert store3.list_disabled_detail() == []
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(d + "2", ignore_errors=True)
        shutil.rmtree(d + "3", ignore_errors=True)


def test_switch_list_shows_scope_label():
    d = _tmp_data_dir()
    try:
        store = GroupSwitchStore(data_dir=d)
        store.set_disabled(
            "aiocqhttp:GroupMessage:111", scope="media", duration_seconds=3600
        )
        store.set_disabled("aiocqhttp:GroupMessage:222", scope="music")  # 永久
        inst = _make_plugin(switch_store=store)
        text = _texts(
            _run_command(
                inst.group_switch_list_command(
                    FakeEvent("/开关列表", umo="aiocqhttp:GroupMessage:999")
                )
            )
        )
        # 限时域条目：显示功能名 + 恢复时间
        assert "群 111" in text and "媒体解析" in text and "自动恢复" in text, text
        # 永久域条目：恢复命令带域参数
        assert "群 222" in text and "音乐点歌" in text, text
        assert "/开关 on music" in text
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_media_urls_extraction_and_batch_limit_message():
    inst = PluginCls.__new__(PluginCls)
    inst._cross_group_enable = False
    inst._cross_group_store = None
    inst._media_parser = _FakeMediaParserManager()
    urls = inst._parse_media_urls(
        "/解析 https://b23.tv/a https://b23.tv/a https://v.douyin.com/b。"
    )
    # 去重保序，尾部中文标点剥离
    assert urls == ["https://b23.tv/a", "https://v.douyin.com/b"], urls
    assert inst._parse_media_urls("/xhs https://xhslink.com/abc") == [
        "https://xhslink.com/abc"
    ]
    # 上限提示必须报告原始条数（截断前），而非恒等于上限值
    links = " ".join(f"https://b23.tv/x{i}" for i in range(7))
    outputs = _run_command(inst.media_parse_command(FakeEvent(f"/解析 {links}")))
    text = _texts(outputs)
    assert "检测到 7 条链接" in text, text[:200]
    assert "已取前 5 条" in text


class _FakeMediaParserManager:
    """media_parse_command 测试用的解析管理器桩。"""

    async def parse(self, url):
        return {"platform": "", "data": {}}


_BILI_DOWNLOAD_INFO = {
    "url": "https://upos.example/video.mp4",
    "size": 100,
    "segments": 1,
    "quality": 64,
}


class _BiliMediaParserManager:
    """返回带 durl 直链信息的 B站解析桩。"""

    async def parse(self, url):
        return {
            "platform": "bilibili",
            "data": {
                "title": "t",
                "bvid": "BV1xx",
                "download_url": dict(_BILI_DOWNLOAD_INFO),
            },
        }


def _make_media_parse_inst(manager, video_enable=True):
    inst = PluginCls.__new__(PluginCls)
    inst._cross_group_enable = False
    inst._cross_group_store = None
    inst._media_parser = manager
    inst._media_video_send_enable = video_enable
    inst._media_video_max_mb = 100
    return inst


def test_media_parse_video_send_fallback_link():
    """视频直发关闭时，回退输出直链文本。"""
    inst = _make_media_parse_inst(_BiliMediaParserManager(), video_enable=False)
    text = _texts(
        _run_command(inst.media_parse_command(FakeEvent("/解析 https://b23.tv/x")))
    )
    assert "📥 下载：https://upos.example/video.mp4" in text, text


def test_media_parse_video_direct_send_no_link():
    """视频直发成功时不输出直链兜底（避免重复）。"""
    inst = _make_media_parse_inst(_BiliMediaParserManager(), video_enable=True)
    calls = []

    async def _send_ok(event, platform, data):
        calls.append((platform, data.get("bvid")))
        return True

    inst._send_parsed_video = _send_ok
    text = _texts(
        _run_command(inst.media_parse_command(FakeEvent("/解析 https://b23.tv/x")))
    )
    assert "📥 下载：" not in text, text
    assert calls == [("bilibili", "BV1xx")], calls


def test_parsed_video_source_and_fallback_guards():
    """多段 durl 不直发（首段不完整）；下载头按域名定制（B站 CDN 要 Referer，LeiZ 要 Key）。"""
    inst = PluginCls.__new__(PluginCls)
    inst._leiz_api_key = "test-key"
    bili_cdn = dict(
        _BILI_DOWNLOAD_INFO,
        url="https://upos-sz-mirrorcosov.bilivideo.com/upgcxcode/v.mp4",
    )
    url, headers, stem = inst._parsed_video_source(
        "bilibili", {"bvid": "BV1xx", "download_url": bili_cdn}
    )
    assert url == bili_cdn["url"] and stem == "BV1xx"
    assert headers.get("Referer") == "https://www.bilibili.com/"
    assert "x-api-key" not in headers
    # LeiZ 票据流：带 x-api-key、不带 Referer
    leiz = dict(
        _BILI_DOWNLOAD_INFO, url="https://api.bileizhen.top/api/bilibili/stream?token=t"
    )
    _, headers2, _ = inst._parsed_video_source(
        "bilibili", {"bvid": "BV1xx", "download_url": leiz}
    )
    assert headers2.get("x-api-key") == "test-key"
    assert "Referer" not in headers2
    multi = dict(_BILI_DOWNLOAD_INFO, segments=3)
    assert inst._parsed_video_source("bilibili", {"download_url": multi}) is None
    assert "无法直接发送" in inst._parsed_video_fallback_text(
        "bilibili", {"download_url": multi}
    )
    assert inst._parsed_video_fallback_text("xiaohongshu", {}) == ""


def _make_auto_parse_inst(
    manager, *, enable=True, dedup_min=30, switch_store=None
):
    inst = PluginCls.__new__(PluginCls)
    inst._cross_group_enable = False
    inst._cross_group_store = None
    inst._media_parser = manager
    inst._media_video_send_enable = False
    inst._media_video_max_mb = 100
    inst._media_auto_parse_enable = enable
    inst._media_auto_parse_dedup_min = dedup_min
    inst._media_auto_parse_seen = {}
    inst._group_switch_enable = switch_store is not None
    inst._group_switch_store = switch_store
    return inst


def _sent_texts(event):
    return "\n".join(str(item[1]) for item in getattr(event, "sent", []))


def test_auto_parse_triggers_on_plain_link():
    """普通闲聊消息中含受支持平台链接时自动解析并回复。"""
    inst = _make_auto_parse_inst(_BiliMediaParserManager())
    ev = FakeEvent("看看这个 https://b23.tv/abc 哈哈哈")
    asyncio.run(inst.on_media_link_auto_parse(ev))
    text = _sent_texts(ev)
    assert "B站视频解析" in text and "📥 下载：" in text, text


def test_auto_parse_skips_commands_and_unsupported_links():
    """命令前缀消息与不受支持平台的链接不触发自动解析。"""
    inst = _make_auto_parse_inst(_BiliMediaParserManager())
    for msg in (
        "/解析 https://b23.tv/abc",
        "!bilibili https://b23.tv/abc",
        "刚看了个仓库 https://github.com/example/repo 挺不错",
        "今天天气不错",
    ):
        ev = FakeEvent(msg)
        asyncio.run(inst.on_media_link_auto_parse(ev))
        assert not getattr(ev, "sent", []), (msg, getattr(ev, "sent", []))


def test_auto_parse_dedup_same_link_same_chat():
    """同一会话窗口期内相同链接只自动解析一次；不同链接不受影响。"""
    inst = _make_auto_parse_inst(_BiliMediaParserManager())
    ev1 = FakeEvent("https://b23.tv/abc")
    asyncio.run(inst.on_media_link_auto_parse(ev1))
    assert "B站视频解析" in _sent_texts(ev1)
    ev2 = FakeEvent("再看一遍 https://b23.tv/abc")
    asyncio.run(inst.on_media_link_auto_parse(ev2))
    assert not getattr(ev2, "sent", []), ev2.sent
    ev3 = FakeEvent("https://www.bilibili.com/video/BV1other")
    asyncio.run(inst.on_media_link_auto_parse(ev3))
    assert "B站视频解析" in _sent_texts(ev3)


def test_auto_parse_respects_switch_and_disable():
    """总开关关闭或 media 域被 /开关 off media 关闭时不自动解析。"""
    inst = _make_auto_parse_inst(_BiliMediaParserManager(), enable=False)
    ev = FakeEvent("https://b23.tv/abc")
    asyncio.run(inst.on_media_link_auto_parse(ev))
    assert not getattr(ev, "sent", [])

    d = _tmp_data_dir()
    try:
        store = GroupSwitchStore(data_dir=d)
        store.set_disabled("aiocqhttp:GroupMessage:10000", scope="media")
        inst2 = _make_auto_parse_inst(_BiliMediaParserManager(), switch_store=store)
        ev2 = FakeEvent("https://b23.tv/abc")
        asyncio.run(inst2.on_media_link_auto_parse(ev2))
        assert not getattr(ev2, "sent", [])
        # 其他功能域关闭不影响媒体自动解析（换一个只关 music 的群）
        store.set_disabled("aiocqhttp:GroupMessage:22222", scope="music")
        ev3 = FakeEvent("https://b23.tv/abc", umo="aiocqhttp:GroupMessage:22222")
        asyncio.run(inst2.on_media_link_auto_parse(ev3))
        assert "B站视频解析" in _sent_texts(ev3)
    finally:
        shutil.rmtree(d, ignore_errors=True)


TESTS = [
    # cross_group_memory
    test_legacy_string_records_migrate_on_load,
    test_record_appends_dict_and_trims,
    test_record_persists_dict_format_roundtrip,
    test_max_age_filters_old_records,
    test_tag_filter,
    test_forget_keyword_case_insensitive,
    test_forget_keyword_empty_or_no_match,
    test_clear_and_get_recent_limit,
    # 后台刷盘（v2.5.1：record 不再同步写盘）
    test_record_defers_write_and_background_flush_persists,
    test_close_flushes_pending_changes,
    # group_switch_store
    test_set_disabled_permanent,
    test_timed_disable_auto_recovers,
    test_get_until_future_timestamp,
    test_list_disabled_detail,
    test_legacy_list_format_migration,
    test_set_enabled_toggles,
    test_new_dict_format_roundtrip,
    # main.py 命令逻辑
    test_parse_switch_duration_units,
    test_parse_switch_duration_composite,
    test_parse_switch_duration_none_and_invalid,
    test_parse_switch_action_first_token,
    test_is_switch_command_whitelist,
    test_switch_off_invalid_duration_replies_error,
    test_switch_list_command_filters_platform,
    test_switch_list_command_empty,
    test_forget_command_alias_keyword_extraction,
    test_forget_command_empty_keyword_hint,
    # scope 分级开关与媒体批量（v2.2.0）
    test_store_scope_semantics,
    test_store_scoped_key_load_and_legacy,
    test_parse_switch_scope_tokens,
    test_parse_switch_duration_skips_scope_token,
    test_detect_command_scope,
    test_switch_on_scope_ordering_regression,
    test_switch_list_shows_scope_label,
    test_media_urls_extraction_and_batch_limit_message,
    # 视频直发与兜底（v2.4.0）
    test_media_parse_video_send_fallback_link,
    test_media_parse_video_direct_send_no_link,
    test_parsed_video_source_and_fallback_guards,
    # 链接自动解析（v2.5.0）
    test_auto_parse_triggers_on_plain_link,
    test_auto_parse_skips_commands_and_unsupported_links,
    test_auto_parse_dedup_same_link_same_chat,
    test_auto_parse_respects_switch_and_disable,
]


def main_test():
    passed = 0
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            import traceback

            print(f"  FAIL  {test.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{'=' * 50}")
    print(f"结果: {passed} 通过, {failed} 失败 (共 {len(TESTS)} 项)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main_test())
