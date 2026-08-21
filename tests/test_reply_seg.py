"""分段回复（reply-seg）切分算法回归测试。

只覆盖纯函数：_split_by_punct / _split_by_length / _segment_text /
_merge_short_segments，不经过框架钩子、不碰网络与对话历史。

运行方式：python3 test_reply_seg.py
"""

import sys
import types
import json
from pathlib import Path

# --------------------------------------------------------------------------- #
# Mock 掉 AstrBot / aiohttp 等依赖，使 main.py 可在脱离框架时被 import。
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

# 最小化的消息段 stub，供 _build_seg_first_chain 测试使用。
# 类名与真实组件保持一致，便于按 type.__name__ 断言。
_StubPlain = type("Plain", (), {"__init__": lambda self, text="", **kw: setattr(self, "text", text)})
_StubReply = type("Reply", (), {"__init__": lambda self, id=None, **kw: setattr(self, "id", id)})
_StubAt = type("At", (), {"__init__": lambda self, qq=None, **kw: setattr(self, "qq", qq)})
astrbot_components.Plain = _StubPlain
astrbot_components.Reply = _StubReply
astrbot_components.At = _StubAt

astrbot_provider = types.ModuleType("astrbot.api.provider")
astrbot_provider.ProviderRequest = object
astrbot_provider.LLMResponse = type("LLMResponse", (), {"completion_text": ""})

astrbot_platform = types.ModuleType("astrbot.api.platform")
astrbot_platform.MessageType = object

astrbot_core = types.ModuleType("astrbot.core")
astrbot_core.__path__ = []
astrbot_core_agent = types.ModuleType("astrbot.core.agent")
astrbot_core_agent.__path__ = []
astrbot_core_agent_message = types.ModuleType("astrbot.core.agent.message")
astrbot_core_agent_message.TextPart = object

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

plugin_parent = str(Path(__file__).resolve().parent.parent.parent)
if plugin_parent not in sys.path:
    sys.path.insert(0, plugin_parent)

# main.py 顶部有若干嵌套包相对导入（dglab.* / media.* / group.* / clients.*），
# 重依赖模块替换为空桩；clients.* 依赖均已 stub，可自然加载真实实现。
for module_name, attributes in {
    "dglab.dglab_device_store": {"DeviceStore": object},
    "dglab.dglab_connection_pool": {"DeviceConnectionPool": object},
    "dglab.dglab_commands": {"DGLabCommandHandler": object},
    "dglab.dglab_webui": {"DGLabWebUI": object},
    "dglab.dglab_user_store": {"UserStore": object},
    "dglab.dglab_permission_store": {"PermissionStore": object},
    "media.media_parser": {
        "MediaParserManager": object,
        "MediaParserError": Exception,
        "URLExtractor": object,
    },
    "group.cross_group_memory": {"CrossGroupMemoryStore": object},
    "group.group_switch_store": {"GroupSwitchStore": object},
}.items():
    module = types.ModuleType(f"astrbot_plugin_currentcortex.{module_name}")
    for name, value in attributes.items():
        setattr(module, name, value)
    sys.modules[module.__name__] = module

from astrbot_plugin_currentcortex import main  # noqa: E402

Cls = main.CurrentCortexPlugin

# 默认配置（与 _conf_schema.json / __init__ 默认值保持一致）。
DEFAULT_SYMBOLS = "。！？!?~～…\n,，"
DEFAULT_WORDS = ["喵", "qwq", "owo", "awa", "ovo"]
DEFAULT_THRESHOLD = 4


def _make_plugin(**overrides):
    """构造一个仅初始化分段相关属性的插件实例（绕过完整 __init__）。"""
    inst = Cls.__new__(Cls)
    inst._reply_seg_symbols = overrides.get("symbols", DEFAULT_SYMBOLS)
    inst._reply_seg_words = overrides.get("words", list(DEFAULT_WORDS))
    inst._reply_seg_mode = overrides.get("mode", "punct")
    inst._reply_seg_merge_threshold = overrides.get("merge_threshold", DEFAULT_THRESHOLD)
    inst._reply_seg_min_length = overrides.get("min_length", 15)
    inst._reply_seg_max_length = overrides.get("max_length", 80)
    # llm 模式相关：density 决定 max_segments（与 __init__ 逻辑保持一致）
    density = overrides.get("llm_density", "medium")
    inst._reply_seg_llm_density = density
    cfg_max_seg = overrides.get("llm_max_segments", 0)
    if cfg_max_seg and cfg_max_seg > 0:
        inst._reply_seg_llm_max_segments = cfg_max_seg
    else:
        inst._reply_seg_llm_max_segments = Cls._REPLY_SEG_DENSITY_PROFILES[density]["max_segments"]
    inst._reply_seg_llm_provider_id = overrides.get("llm_provider_id", "")
    inst._reply_seg_llm_min_chars = overrides.get("llm_min_chars", 30)
    inst._reply_seg_llm_timeout = overrides.get("llm_timeout", 30)
    # 宣传（QQ 群）相关：群号为类常量，水印概率固定 5%，无需配置
    # _segment_by_llm 需要 context.llm_generate / get_current_chat_provider_id
    inst.context = overrides.get("context", _FakeContext())
    return inst


class _FakeLLMResponse:
    """模拟 astrbot.api.provider.LLMResponse。"""

    def __init__(self, completion_text=""):
        self.completion_text = completion_text


class _FakeContext:
    """模拟 Star.context，用于控制 llm_generate / provider 解析行为。"""

    def __init__(self, llm_text="", provider_id="fake-provider", raise_llm=False):
        self._llm_text = llm_text
        self._provider_id = provider_id
        self._raise_llm = raise_llm
        self.llm_generate_calls = []  # 记录调用参数，便于断言

    async def get_current_chat_provider_id(self, umo=""):
        return self._provider_id

    async def llm_generate(self, *, chat_provider_id, system_prompt="", prompt="", **kw):
        self.llm_generate_calls.append({
            "chat_provider_id": chat_provider_id,
            "system_prompt": system_prompt,
            "prompt": prompt,
            "extra": kw,
        })
        if self._raise_llm:
            raise RuntimeError("mock llm failure")
        return _FakeLLMResponse(self._llm_text)


class _FakeEvent:
    """模拟 AstrMessageEvent，只暴露分段/工具用到的字段。"""

    def __init__(self, umo="fake-umo", message_id=None, sender_id=""):
        self.unified_msg_origin = umo
        self.message_obj = type("MObj", (), {"message_id": message_id})()
        self._sender_id = sender_id

    def get_sender_id(self):
        return self._sender_id


# --------------------------------------------------------------------------- #
# 断言辅助
# --------------------------------------------------------------------------- #

class _AssertionError(AssertionError):
    pass


def _check(name, got, expected):
    if got != expected:
        raise _AssertionError(f"[{name}] 失败\n  期望: {expected}\n  实际: {got}")


def _check_true(name, cond, msg):
    if not cond:
        raise _AssertionError(f"[{name}] 失败: {msg}")


# --------------------------------------------------------------------------- #
# 测试用例
# --------------------------------------------------------------------------- #


def _split_punct(text, symbols=DEFAULT_SYMBOLS, words=None, threshold=DEFAULT_THRESHOLD):
    """以默认实例调用 _split_by_punct（它是实例方法，内部依赖 self）。"""
    return _make_plugin(words=list(words or DEFAULT_WORDS))._split_by_punct(
        text, symbols, list(words or DEFAULT_WORDS), threshold,
    )


def test_punct_basic_sentence_split():
    """句号处自然分句，符号保留在段尾；不产生纯标点段。"""
    segs = _split_punct("我刚才在忙没看到消息。现在有空了，你说吧。")
    # 至少在第一个句号处断开
    _check_true("基本分句-断点", any(s.endswith("消息。") for s in segs), f"未在句号断开: {segs}")
    # 全文内容无损
    _check_true("基本分句-无损", "".join(segs) == "我刚才在忙没看到消息。现在有空了，你说吧。",
                f"内容丢失: {segs}")


def test_punct_isolated_punct_merged():
    """切分词后紧跟的孤立标点段应合并回前段，不再产生 1 字纯标点段。"""
    # owo 后紧跟「。」：切分会先得到 [..owo, 。, 你呢？]，合并后「。」回到前段
    segs = _split_punct("今天玩得超开心的owo。你呢？")
    _check_true("孤立标点合并", "。" not in segs, f"出现孤立标点段: {segs}")
    # 不应残留长度 < 阈值(4) 的段（过短段也会被并回前段）
    for s in segs:
        _check_true("过短段已合并", len(s) >= DEFAULT_THRESHOLD,
                    f"残留过短段({len(s)}字): {s!r}")


def test_punct_valid_short_sentence_kept():
    """有效短句（好的。/ 是的。）作为首段不应被合并吞掉。"""
    for text in ["好的。", "是的。", "没问题。"]:
        segs = _split_punct(text)
        _check_true(f"有效短句保留 {text}", len(segs) == 1 and segs[0] == text,
                    f"被误并: {segs}")


def test_punct_multiple_short_sentences():
    """多个有效短句各自成段，不应互相吞并。"""
    segs = _split_punct("好的。没问题。马上就好。")
    _check("多短句", segs, ["好的。", "没问题。", "马上就好。"])


def test_punct_comma_fragments_reduced():
    """逗号切出的碎片应通过合并兜底，不再满屏 2~3 字碎片。"""
    text = "苹果，香蕉，橘子，葡萄，西瓜，芒果，桃子，梨，草莓，蓝莓，你最喜欢哪个？"
    segs = _split_punct(text)
    # 合并前会是 11 段几乎全是 ≤3 字碎片；合并后段数应大幅下降
    _check_true("逗号碎片减少", len(segs) <= 4,
                f"仍有过多碎片（{len(segs)} 段）: {segs}")
    # 不应出现孤立的纯标点段
    punct = set("。！？!?~～…\n,，、；;：: ")
    for s in segs:
        _check_true("无纯标点段", not all(c in punct for c in s), f"存在纯标点段: {s!r}")


def test_punct_merge_threshold_zero_disables():
    """threshold=0 关闭合并，恢复旧行为（会产生孤立标点段）。"""
    segs = _split_punct("今天玩得超开心的owo。你呢？", threshold=0)
    # 不合并时，「。」应单独成段
    _check_true("关闭合并", "。" in segs, f"threshold=0 仍合并了: {segs}")


def test_merge_short_segments_static():
    """直接测 _merge_short_segments：过短段与纯标点段并回前段。"""
    segs = ["今天很开心owo", "。", "你", "吃饭了吗？"]
    _check("合并静态", Cls._merge_short_segments(segs, 4),
           ["今天很开心owo。你", "吃饭了吗？"])
    # 首段即便短也保留（无前段可并）
    _check("首段保留", Cls._merge_short_segments(["嗯", "好的"], 4), ["嗯好的"])
    # 单段原样返回
    _check("单段", Cls._merge_short_segments(["仅一段"], 4), ["仅一段"])


def test_default_words_no_english_mischop():
    """默认词去掉单字符 w 后，英文单词 network 不应被劈开。"""
    inst = _make_plugin()
    # 含 w 的英文句：默认词中无 w，不会被误切
    segs = inst._segment_text("I think the network connection is weak, can you check?")
    joined = "".join(segs)
    _check_true("英文不误切", "network" in joined and "weak" in joined,
                f"英文被误切: {segs}")


def test_segment_text_dispatch_punct():
    """_segment_text 按 mode=punct 分派，应用合并。"""
    inst = _make_plugin(mode="punct")
    segs = inst._segment_text("今天玩得超开心的owo。你呢？")
    _check_true("punct 分派", "。" not in segs, f"仍有孤立标点: {segs}")


def test_length_mode_long_text():
    """length 模式：超长文本在标点处切分，段长受控。"""
    inst = _make_plugin(mode="length", min_length=10, max_length=30)
    text = ("这是第一句比较长的话应该在三十个字以内的标点处切分。"
            "第二句同样需要被切出来作为独立的一段出现。"
            "最后一句收尾的内容也比较长需要处理一下才行。")
    segs = inst._segment_text(text)
    _check_true("length 段数", len(segs) >= 2, f"未切分: {segs}")
    # 不应有硬切产生的段超出 max_len 的 2 倍（容差）
    for s in segs:
        _check_true("length 段长受控", len(s) <= 30 * 2 + 5, f"段过长({len(s)}): {s!r}")


def test_length_mode_tail_merge():
    """length 模式末尾过短段合并回前段。"""
    inst = _make_plugin(mode="length", min_length=10, max_length=20)
    text = "一二三四五六七八九十十一十二十三。尾"
    segs = inst._segment_text(text)
    # 末尾的「尾」(1字) 应被并回前段
    if len(segs) >= 1:
        _check_true("length 末尾合并", not (len(segs[-1]) < 6 and len(segs) > 1),
                    f"末尾过短未合并: {segs}")


# --------------------------------------------------------------------------- #
# llm 模式测试
# --------------------------------------------------------------------------- #


def _run(coro):
    """同步跑一个协程（测试套件是同步驱动的）。"""
    import asyncio as _asyncio
    return _asyncio.get_event_loop().run_until_complete(coro) \
        if not _asyncio.get_event_loop().is_closed() \
        else _asyncio.new_event_loop().run_until_complete(coro)


def test_parse_llm_segments_basic():
    """标准 JSON 数组解析。"""
    _check("标准JSON", Cls._parse_llm_segments('["第一段","第二段","第三段"]'),
           ["第一段", "第二段", "第三段"])


def test_parse_llm_segments_code_fence():
    """带 markdown 代码块围栏也能解析。"""
    raw = '```json\n["段一", "段二"]\n```'
    _check("代码块", Cls._parse_llm_segments(raw), ["段一", "段二"])


def test_parse_llm_segments_with_prefix():
    """模型在 JSON 前后加了多余文字，截取 [ ] 后能解析。"""
    raw = '好的，结果如下：\n["段一","段二"]\n希望对你有用'
    _check("前后缀", Cls._parse_llm_segments(raw), ["段一", "段二"])


def test_parse_llm_segments_invalid():
    """非法格式返回空列表（不抛异常）。"""
    _check("非数组对象", Cls._parse_llm_segments('{"a":1}'), [])
    _check("纯文字", Cls._parse_llm_segments("这不是json"), [])
    _check("空字符串", Cls._parse_llm_segments(""), [])


def test_parse_llm_segments_filters_non_string():
    """数组中混入非字符串元素时被过滤，只保留非空字符串。"""
    _check("过滤非字符串", Cls._parse_llm_segments('["a", 123, null, "", "b"]'),
           ["a", "b"])


def test_cap_llm_segments():
    """段数超过上限时合并超出部分到末段。"""
    segs = ["a", "b", "c", "d", "e", "f"]
    _check("上限3", Cls._cap_llm_segments(list(segs), 3), ["a", "b", "cdef"])
    _check("上限2", Cls._cap_llm_segments(list(segs), 2), ["a", "bcdef"])
    _check("不超过上限", Cls._cap_llm_segments(list(segs), 8), list(segs))
    _check("单段上限1", Cls._cap_llm_segments(["only"], 1), ["only"])


def test_text_close_enough():
    """字数接近判断：去除空白后比较，允许 10% 偏差。"""
    _check_true("完全相同", Cls._text_close_enough("你好世界", "你好世界"), "")
    _check_true("仅空白差异", Cls._text_close_enough("你 好 世 界", "你好世界"), "")
    # 偏差 20% 应判为不接近
    _check_true("偏差过大应False",
                not Cls._text_close_enough("你好世界呀", "你好世界"), "")
    _check_true("悬殊应False",
                not Cls._text_close_enough("短", "这是一个比较长的原文内容"), "")


def test_segment_by_llm_too_short_returns_none():
    """原文短于 min_chars 时不调用 LLM，返回 None。"""
    inst = _make_plugin(llm_min_chars=100, llm_provider_id="p1")
    result = _run(inst._segment_by_llm("这是一段比较短的文本。", _FakeEvent()))
    _check("短文本不调用", result, None)
    # 确认没有发起 llm_generate 调用
    _check_true("未调用llm", len(inst.context.llm_generate_calls) == 0, "不应调用 LLM")


def test_segment_by_llm_no_provider_returns_none():
    """没有可用 provider 时降级（返回 None）。"""
    inst = _make_plugin(
        llm_provider_id="",
        context=_FakeContext(provider_id=""),  # 当前会话也取不到
    )
    result = _run(inst._segment_by_llm("这是一段足够长的文本用于触发 llm 分段测试。", _FakeEvent()))
    _check("无provider降级", result, None)


def test_segment_by_llm_call_failure_returns_none():
    """LLM 调用抛异常时降级（返回 None）。"""
    inst = _make_plugin(
        llm_provider_id="p1",
        context=_FakeContext(raise_llm=True),
    )
    text = "这是一段足够长的文本用于触发 llm 分段测试，内容要超过三十个字才行。"
    result = _run(inst._segment_by_llm(text, _FakeEvent()))
    _check("调用异常降级", result, None)


class _SlowContext(_FakeContext):
    """模拟慢速 LLM：sleep 后才返回，用于测超时降级。"""

    def __init__(self, delay, llm_text="[]"):
        super().__init__(llm_text=llm_text)
        self._delay = delay

    async def llm_generate(self, *, chat_provider_id, system_prompt="", prompt="", **kw):
        import asyncio as _a
        await _a.sleep(self._delay)
        return await super().llm_generate(
            chat_provider_id=chat_provider_id, system_prompt=system_prompt, prompt=prompt, **kw
        )


def test_segment_by_llm_timeout_returns_none():
    """LLM 调用超时时降级（返回 None）。"""
    inst = _make_plugin(
        llm_provider_id="p1",
        llm_timeout=1,  # 1 秒超时
        context=_SlowContext(delay=3),  # 3 秒后才返回 → 必超时
    )
    text = "这是一段足够长的文本用于触发 llm 分段测试，内容要超过三十个字才行。"
    result = _run(inst._segment_by_llm(text, _FakeEvent()))
    _check("超时降级", result, None)


def test_segment_by_llm_clean_call():
    """调用 llm_generate 时不传 max_tokens / request_max_retries（让 provider 用默认重试）。"""
    text = "这是一段足够长的文本用于触发 llm 分段测试，必须超过三十个字才行嗯。"
    resp = f'["{text}"]'
    inst = _make_plugin(
        llm_provider_id="p1",
        context=_FakeContext(llm_text=resp),
    )
    _run(inst._segment_by_llm(text, _FakeEvent()))
    calls = inst.context.llm_generate_calls
    _check_true("已调用", len(calls) == 1, f"调用次数: {len(calls)}")
    extra = calls[0].get("extra", {})
    _check_true("不传max_tokens", "max_tokens" not in extra, f"extra: {extra}")
    _check_true("不传request_max_retries", "request_max_retries" not in extra, f"extra: {extra}")


def test_segment_by_llm_success():
    """正常调用：返回的 JSON 数组拼接后与原文接近，应原样返回分段。"""
    text = "今天玩得超开心的喵！和你聊天总是很有意思。对了，你吃饭了吗？"
    # 模型返回的切分结果（拼接后与原文一致）
    resp = '["今天玩得超开心的喵！", "和你聊天总是很有意思。", "对了，你吃饭了吗？"]'
    inst = _make_plugin(
        llm_provider_id="p1",
        context=_FakeContext(llm_text=resp),
    )
    result = _run(inst._segment_by_llm(text, _FakeEvent()))
    _check("成功分段", result,
           ["今天玩得超开心的喵！", "和你聊天总是很有意思。", "对了，你吃饭了吗？"])
    # 确认 system_prompt 里带了 max_segments
    _check_true("prompt含约束",
                "5" in inst.context.llm_generate_calls[0]["system_prompt"], "")


def test_segment_by_llm_drift_returns_none():
    """模型改写了原文（字数偏差过大）时降级（返回 None）。"""
    text = "今天玩得超开心的喵！和你聊天总是很有意思。对了，你吃饭了吗？"
    # 返回内容明显比原文短很多 → 字数校验失败
    resp = '["好的", "没问题"]'
    inst = _make_plugin(
        llm_provider_id="p1",
        context=_FakeContext(llm_text=resp),
    )
    result = _run(inst._segment_by_llm(text, _FakeEvent()))
    _check("字数偏差降级", result, None)


def test_segment_by_llm_caps_segments():
    """模型切出超过上限的段数时，合并超出部分到末段。"""
    # text 必须等于模型返回 6 段拼接后的结果，否则字数校验会降级
    parts = ["一二三四", "五六七八", "九十", "十一", "十二", "十三。"]
    text = "".join(parts)
    resp = json.dumps(parts)  # 6 段
    inst = _make_plugin(
        llm_provider_id="p1",
        llm_max_segments=3,
        llm_min_chars=10,  # text 只有 18 字，调低门槛以触发 LLM 分段
        context=_FakeContext(llm_text=resp),
    )
    result = _run(inst._segment_by_llm(text, _FakeEvent()))
    _check_true("段数裁剪-段数", result is not None and len(result) == 3, f"实际: {result}")
    # 拼接后内容应与原文一致（裁剪只合并不改内容）
    _check_true("裁剪无损", result and "".join(result) == text, f"内容: {result}")


def test_segment_by_llm_falls_back_provider_id():
    """未配置 provider_id 时，复用当前会话模型。"""
    text = "这是一段足够长的文本用于触发 llm 分段测试，超过三十字。"
    resp = f'["{text}"]'
    inst = _make_plugin(
        llm_provider_id="",
        context=_FakeContext(provider_id="session-provider", llm_text=resp),
    )
    result = _run(inst._segment_by_llm(text, _FakeEvent()))
    # 只切出 1 段且字数一致，合法（调用方会据此决定是否分段）
    _check_true("复用会话provider", result == [text], f"实际: {result}")
    _check_true("用的是会话provider",
                inst.context.llm_generate_calls[0]["chat_provider_id"] == "session-provider", "")


def test_density_profiles_exist():
    """三档密度映射齐全，且关键字段齐全。"""
    profiles = Cls._REPLY_SEG_DENSITY_PROFILES
    for key in ("low", "medium", "high"):
        _check_true(f"档位{key}存在", key in profiles, f"缺少档位: {key}")
        p = profiles[key]
        _check_true(f"档位{key}-target_chars",
                    isinstance(p["target_chars"], tuple) and len(p["target_chars"]) == 2, "")
        _check_true(f"档位{key}-max_segments", isinstance(p["max_segments"], int) and p["max_segments"] >= 2, "")
        _check_true(f"档位{key}-guidance", isinstance(p["guidance"], str) and p["guidance"], "")


def test_density_auto_max_segments():
    """llm_max_segments 留空(0)时，按密度档位自动推算上限。"""
    inst_low = _make_plugin(llm_density="low", llm_max_segments=0)
    inst_med = _make_plugin(llm_density="medium", llm_max_segments=0)
    inst_high = _make_plugin(llm_density="high", llm_max_segments=0)
    _check("low推算", inst_low._reply_seg_llm_max_segments,
           Cls._REPLY_SEG_DENSITY_PROFILES["low"]["max_segments"])
    _check("medium推算", inst_med._reply_seg_llm_max_segments,
           Cls._REPLY_SEG_DENSITY_PROFILES["medium"]["max_segments"])
    _check("high推算", inst_high._reply_seg_llm_max_segments,
           Cls._REPLY_SEG_DENSITY_PROFILES["high"]["max_segments"])
    # low < medium < high，段数随密度递增
    _check_true("递增关系",
                inst_low._reply_seg_llm_max_segments < inst_med._reply_seg_llm_max_segments
                < inst_high._reply_seg_llm_max_segments, "")


def test_density_manual_override_max_segments():
    """用户手动指定 max_segments 时，覆盖档位自动推算。"""
    inst = _make_plugin(llm_density="high", llm_max_segments=4)
    _check("手动覆盖", inst._reply_seg_llm_max_segments, 4)


def test_density_prompt_injection():
    """不同档位会把对应目标字数写进 system_prompt。"""
    text = "这是一段足够长的文本用于触发 llm 分段测试，必须超过三十个字才行嗯。"
    resp = f'["{text}"]'
    for density in ("low", "medium", "high"):
        inst = _make_plugin(
            llm_density=density,
            llm_provider_id="p1",
            context=_FakeContext(llm_text=resp),
        )
        _run(inst._segment_by_llm(text, _FakeEvent()))
        sp = inst.context.llm_generate_calls[0]["system_prompt"]
        tmin, tmax = Cls._REPLY_SEG_DENSITY_PROFILES[density]["target_chars"]
        _check_true(f"{density}-目标下限", str(tmin) in sp, f"prompt 缺少目标下限 {tmin}: {sp}")
        _check_true(f"{density}-目标上限", str(tmax) in sp, f"prompt 缺少目标上限 {tmax}: {sp}")
        _check_true(f"{density}-引导语",
                    Cls._REPLY_SEG_DENSITY_PROFILES[density]["guidance"][:6] in sp, "")


def test_build_seg_first_chain_with_mention():
    """首段消息链含 Reply + At + Plain（顺序正确）。"""
    ev = _FakeEvent(message_id="msg123", sender_id="10086")
    chain = Cls._build_seg_first_chain(ev, "你好呀")
    types = [type(c).__name__ for c in chain.chain]
    _check("含3段", len(chain.chain), 3)
    _check("Reply在首", types[0], "Reply")
    _check("At在次", types[1], "At")
    _check("Plain在末", types[2], "Plain")
    # Reply 的 id 正确
    _check("Reply-id", chain.chain[0].id, "msg123")
    # At 的 qq 正确
    _check("At-qq", str(chain.chain[0 + 1].qq), "10086")


def test_build_seg_first_chain_no_message_id():
    """无 message_id 时不加 Reply，但仍有 At + Plain。"""
    ev = _FakeEvent(message_id=None, sender_id="10086")
    chain = Cls._build_seg_first_chain(ev, "你好")
    types = [type(c).__name__ for c in chain.chain]
    _check_true("无Reply", "Reply" not in types, f"不应有Reply: {types}")
    _check_true("有At", "At" in types, f"应有At: {types}")
    _check_true("有Plain", "Plain" in types, f"应有Plain: {types}")


def test_build_seg_first_chain_no_sender():
    """无 sender_id 时不加 At，降级为纯 Plain。"""
    ev = _FakeEvent(message_id=None, sender_id="")
    chain = Cls._build_seg_first_chain(ev, "你好")
    _check("纯文本降级", len(chain.chain), 1)
    _check("仅Plain", type(chain.chain[0]).__name__, "Plain")


# --------------------------------------------------------------------------- #
# 宣传（QQ 群）测试
# --------------------------------------------------------------------------- #


def test_promo_group_line():
    """群号为固定官方常量，宣传文本含群号。"""
    inst = _make_plugin()
    line = inst._promo_group_line()
    _check_true("含群号", Cls._PROMO_QQ_GROUP in line, line)
    _check_true("不含链接", "http" not in line, line)


def test_promo_with_promo():
    """_with_promo 在 help 文本末尾追加群号。"""
    inst = _make_plugin()
    result = inst._with_promo("帮助文本")
    _check_true("help追加群号",
                Cls._PROMO_QQ_GROUP in result and result.startswith("帮助文本"), result)


def test_promo_after_image_probability():
    """图片后群号按概率（~10%）触发：大量采样命中率和非命中率合理。"""
    inst = _make_plugin()
    hit = sum(1 for _ in range(500) if inst._maybe_promo_after_image())
    # 500 次中命中率应在 10% 附近（容差 3%~18%）
    _check_true("概率合理", 0.03 <= hit / 500 <= 0.18, f"命中率 {hit}/500 = {hit/500:.0%}")
    # 命中时应含群号、无链接
    for _ in range(50):
        text = inst._maybe_promo_after_image()
        if text:
            _check_true("含群号", Cls._PROMO_QQ_GROUP in text, text)
            _check_true("不含链接", "http" not in text, text)
            break


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

TESTS = [
    test_punct_basic_sentence_split,
    test_punct_isolated_punct_merged,
    test_punct_valid_short_sentence_kept,
    test_punct_multiple_short_sentences,
    test_punct_comma_fragments_reduced,
    test_punct_merge_threshold_zero_disables,
    test_merge_short_segments_static,
    test_default_words_no_english_mischop,
    test_segment_text_dispatch_punct,
    test_length_mode_long_text,
    test_length_mode_tail_merge,
    # llm 模式
    test_parse_llm_segments_basic,
    test_parse_llm_segments_code_fence,
    test_parse_llm_segments_with_prefix,
    test_parse_llm_segments_invalid,
    test_parse_llm_segments_filters_non_string,
    test_cap_llm_segments,
    test_text_close_enough,
    test_segment_by_llm_too_short_returns_none,
    test_segment_by_llm_no_provider_returns_none,
    test_segment_by_llm_call_failure_returns_none,
    test_segment_by_llm_timeout_returns_none,
    test_segment_by_llm_clean_call,
    test_segment_by_llm_success,
    test_segment_by_llm_drift_returns_none,
    test_segment_by_llm_caps_segments,
    test_segment_by_llm_falls_back_provider_id,
    # llm 模式：密度档位
    test_density_profiles_exist,
    test_density_auto_max_segments,
    test_density_manual_override_max_segments,
    test_density_prompt_injection,
    # 首段消息链（@ + 引用回复）
    test_build_seg_first_chain_with_mention,
    test_build_seg_first_chain_no_message_id,
    test_build_seg_first_chain_no_sender,
    # 宣传（QQ 群）
    test_promo_group_line,
    test_promo_with_promo,
    test_promo_after_image_probability,
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
            print(f"  FAIL  {test.__name__}\n        {e}")
            failed += 1
    print(f"\n{'=' * 50}")
    print(f"结果: {passed} 通过, {failed} 失败 (共 {len(TESTS)} 项)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main_test())
