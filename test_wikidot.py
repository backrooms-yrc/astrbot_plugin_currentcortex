"""Wikidot 前端 JS 接口模块回归测试。

覆盖 wikidot_client.py（AMC 表单编码 / HTML 解析 / 登录与会话 / amc 状态
分发 / 页面锁流程）、wikidot_session_store.py（会话持久化）、
wikidot_commands.py（子命令分发 / 权限门禁 / 确认词 / 错误转译）以及
main.py 的 wikidot 命令接线。全部离线：网络层通过预置响应队列模拟。

运行方式：python3 test_wikidot.py
"""

import asyncio
import importlib
import json
import os
import sys
import tempfile
import types
from pathlib import Path


# --------------------------------------------------------------------------- #
# Mock 掉 AstrBot / aiohttp 等依赖（与 test_memory_and_switch.py 同款手法）
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
astrbot_core_agent_message.TextPart = type(
    "TextPart", (), {"__init__": lambda self, text="": setattr(self, "text", text)}
)


class _FakeClientError(Exception):
    pass


async def _noop_sleep(delay):
    return None


aiohttp_stub = types.ModuleType("aiohttp")
aiohttp_stub.ClientSession = object
aiohttp_stub.ClientError = _FakeClientError
aiohttp_stub.ClientTimeout = lambda **kwargs: types.SimpleNamespace(**kwargs)

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

PKG = Path(__file__).resolve().parent.name
PLUGIN_DIR = Path(__file__).resolve().parent
plugin_parent = str(PLUGIN_DIR.parent)
if plugin_parent not in sys.path:
    sys.path.insert(0, plugin_parent)

# main.py 的重依赖兄弟模块替换为空桩；wikidot_* 三件套与
# group_switch_store / cross_group_memory 用真实实现。
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
        "URLExtractor": object,
    },
}.items():
    module = types.ModuleType(f"{PKG}.{module_name}")
    for name, value in attributes.items():
        setattr(module, name, value)
    sys.modules[module.__name__] = module

wc_mod = importlib.import_module(f"{PKG}.wikidot_client")
ws_mod = importlib.import_module(f"{PKG}.wikidot_session_store")
wcmd_mod = importlib.import_module(f"{PKG}.wikidot_commands")
main_mod = importlib.import_module(f"{PKG}.main")

WikidotClient = wc_mod.WikidotClient
WikidotError = wc_mod.WikidotError
WikidotSessionStore = ws_mod.WikidotSessionStore
WikidotCommandHandler = wcmd_mod.WikidotCommandHandler
PluginCls = main_mod.CurrentCortexPlugin


def _patch_client_sleep():
    """把 wikidot_client 模块里的 asyncio 换成 sleep 为 no-op 的替身。"""
    wc_mod.asyncio = types.SimpleNamespace(
        TimeoutError=asyncio.TimeoutError, sleep=_noop_sleep
    )


def _restore_client_sleep():
    wc_mod.asyncio = asyncio


# --------------------------------------------------------------------------- #
# 测试基建
# --------------------------------------------------------------------------- #


def _tmp_data_dir():
    return tempfile.mkdtemp(prefix="cc_wikidot_test_")


class FakeEvent:
    def __init__(self, message_str, admin=True, umo="aiocqhttp:GroupMessage:10000"):
        self.message_str = message_str
        self.unified_msg_origin = umo
        self._admin = admin

    def is_admin(self):
        return self._admin

    def get_message_type(self):
        return _FakeMessageType.GROUP_MESSAGE

    def get_sender_name(self):
        return "tester"

    def plain_result(self, text):
        return ("plain", text)


def _run_command(gen):
    async def _collect():
        return [item async for item in gen]

    return asyncio.run(_collect())


def _texts(outputs):
    return "\n".join(t for kind, t in outputs if kind == "plain")


def _handler(client, admin_only=True):
    return WikidotCommandHandler(client, admin_only=admin_only)


def _dispatch(handler, message, admin=True):
    event = FakeEvent(message, admin=admin)
    return _texts(_run_command(handler.handle_command(event, message)))


class FakeClient:
    """记录调用的 WikidotClient 替身；responses 控制返回值/异常。"""

    def __init__(self, configured=True):
        self.calls = []
        self.responses = {}
        self._configured = configured
        self.site = "example-site"
        self.username = "tester"

    def configured(self):
        return self._configured

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        rv = self.responses.get(name)
        if isinstance(rv, Exception):
            raise rv
        if callable(rv):
            return rv(*args, **kwargs)
        return rv

    async def login(self, force=False):
        return self._record("login", force=force)

    async def get_page_info(self, fullname):
        return self._record("get_page_info", fullname) or {
            "exists": True, "fullname": fullname, "page_id": 1, "title": "T", "tags": [],
        }

    async def get_source(self, fullname):
        return self._record("get_source", fullname) or "SOURCE"

    async def save_page(self, fullname, source, title=None, comment="", force=False,
                        tags=None, parent=None):
        return self._record(
            "save_page", fullname, source, title=title, comment=comment,
            force=force, tags=tags, parent=parent,
        ) or {"status": "ok"}

    async def append_page(self, fullname, text, comment=""):
        return self._record("append_page", fullname, text, comment=comment)

    async def save_tags(self, fullname, tags):
        return self._record("save_tags", fullname, tags)

    async def rename_page(self, old, new, force=False):
        return self._record("rename_page", old, new, force=force)

    async def set_parent(self, fullname, parent):
        return self._record("set_parent", fullname, parent)

    async def delete_page(self, fullname):
        return self._record("delete_page", fullname)

    async def list_members(self, group="", page=1):
        return self._record("list_members", group=group, page=page) or ([], 1)

    async def list_all_members(self, group=""):
        return self._record("list_all_members", group=group) or []

    async def remove_member(self, user_id, ban=False):
        return self._record("remove_member", user_id, ban=ban)

    async def block_user(self, user_id, reason=""):
        return self._record("block_user", user_id, reason=reason)

    async def unblock_user(self, user_id):
        return self._record("unblock_user", user_id)

    async def resolve_user(self, username):
        return self._record("resolve_user", username)

    async def get_general_settings(self):
        return self._record("get_general_settings") or {
            "name": "Site", "subtitle": "", "language": "zh",
            "description": "", "default_page": "start", "welcome_page": "",
        }

    async def save_general_settings(self, updates):
        return self._record("save_general_settings", updates) or {}

    async def get_access_policy(self):
        return self._record("get_access_policy") or {
            "privacy": "open", "by_apply": False, "by_domain": False,
            "by_password": False, "password": "", "landingPage": "",
            "allowHotlink": True, "hideNav": False,
        }

    async def save_access_policy(self, updates):
        return self._record("save_access_policy", updates) or {}

    async def get_navigation(self):
        return self._record("get_navigation") or {}

    async def save_navigation(self, top=None, side=None, use_default=False):
        return self._record("save_navigation", top=top, side=side,
                            use_default=use_default)

    async def get_license(self):
        return self._record("get_license") or {"license_id": "1", "options": []}

    async def set_license(self, license_id=None, other=None, use_default=False):
        return self._record("set_license", license_id=license_id, other=other,
                            use_default=use_default)

    async def get_templates(self):
        return self._record("get_templates") or {"template_id": "", "options": []}

    async def set_template(self, template_id):
        return self._record("set_template", template_id)

    async def get_appearance(self):
        return self._record("get_appearance") or {}

    async def set_appearance(self, theme_id=None, use_default=False):
        return self._record("set_appearance", theme_id=theme_id,
                            use_default=use_default)

    async def get_forum_layout(self):
        return self._record("get_forum_layout") or {"groups": [], "default_nesting": 5}

    async def save_forum_layout(self, groups, deleted_group_ids=None,
                                deleted_category_ids=None):
        return self._record("save_forum_layout", groups,
                            deleted_group_ids=deleted_group_ids,
                            deleted_category_ids=deleted_category_ids)

    async def activate_forum(self):
        return self._record("activate_forum")

    async def set_forum_nesting(self, level):
        return self._record("set_forum_nesting", level)

    async def invite_user(self, user_id, text=""):
        return self._record("invite_user", user_id, text=text)

    async def send_email_invitation(self, address, message="", name=""):
        return self._record("send_email_invitation", address, message=message)

    async def set_let_users_invite(self, enabled):
        return self._record("set_let_users_invite", enabled)

    async def list_applications(self):
        return self._record("list_applications") or []

    async def process_application(self, user_id, accept):
        return self._record("process_application", user_id, accept=accept)


def _called(fake, name):
    return [c for c in fake.calls if c[0] == name]


# --------------------------------------------------------------------------- #
# wikidot_client：AMC 表单编码
# --------------------------------------------------------------------------- #


def test_encode_amc_form_injects_token_and_keeps_zero():
    pairs = wc_mod.encode_amc_form({"moduleName": "Empty", "count": 0})
    assert ("moduleName", "Empty") in pairs
    assert ("count", "0") in pairs
    assert ("wikidot_token7", "123456") in pairs


def test_encode_amc_form_omits_falsy_and_encodes_bools():
    pairs = wc_mod.encode_amc_form({
        "moduleName": "Empty",
        "ban": None,
        "flag": False,
        "checked": True,
    })
    keys = [k for k, _ in pairs]
    assert "ban" not in keys and "flag" not in keys
    assert ("checked", "true") in pairs


def test_encode_amc_form_list_values_use_jquery_brackets():
    pairs = wc_mod.encode_amc_form({"selected_categories": [3, 7]})
    assert ("selected_categories[]", "3") in pairs
    assert ("selected_categories[]", "7") in pairs


def test_amc_helpers():
    assert wc_mod.amc_checkbox(True) == "on"
    assert wc_mod.amc_checkbox(False) is None
    assert wc_mod.amc_flag(True) == "true"
    assert wc_mod.amc_flag("") is None


# --------------------------------------------------------------------------- #
# wikidot_client：HTML 解析
# --------------------------------------------------------------------------- #


def test_extract_page_source_unescapes_and_normalizes():
    body = '<div class="page-source">[[div]]&nbsp;hello&lt;b&gt;</div>'
    assert wc_mod.extract_page_source(body) == "[[div]] hello<b>"


def test_extract_page_id_patterns():
    html1 = "<script>WIKIREQUEST.info.pageId = 12345;</script>"
    assert wc_mod.extract_page_id(html1) == 12345
    html2 = 'var info = {"pageId": 678};'
    assert wc_mod.extract_page_id(html2) == 678
    assert wc_mod.extract_page_id("<html></html>") is None


def test_parse_form_fields_mixed_controls():
    html = """
    <form id="sm-general-form">
      <input type="text" name="name" value="My Site">
      <input type="hidden" name="default_page" value="start">
      <input type="checkbox" name="by_apply" checked>
      <input type="checkbox" name="by_domain">
      <input type="radio" name="privacy" value="open">
      <input type="radio" name="privacy" value="private" checked>
      <select name="license_id">
        <option value="">default</option>
        <option value="cc" selected>CC</option>
      </select>
      <textarea name="description">多行
描述</textarea>
    </form>
    """
    fields = wc_mod.parse_form_fields(html)
    assert fields["name"] == "My Site"
    assert fields["default_page"] == "start"
    assert fields["by_apply"] == "on"
    assert "by_domain" not in fields
    assert fields["privacy"] == "private"
    assert fields["license_id"] == "cc"
    assert fields["description"].startswith("多行")


def test_parse_select_options():
    html = '<select name="template_id"><option value="">（无）</option><option value="9">_default</option></select>'
    options = wc_mod.parse_select_options(html, "template_id")
    assert options == [("", "（无）"), ("9", "_default")]


def test_parse_members_html_rows_with_odate():
    body = """
    <table><tr><th>用户</th><th>加入时间</th></tr>
    <tr><td><span class="printuser"><a href="http://www.wikidot.com/user:info/jane-doe"
        onclick="WIKIDOT.page.listeners.userInfo(42); return false;">Jane Doe</a></span></td>
        <td><span class="odate time_1700000000">2023-11-14</span></td></tr>
    <tr><td><span class="printuser"><a href="https://www.wikidot.com/user:info/bob"
        onclick="WIKIDOT.page.listeners.userInfo(7); return false;">Bob</a></span></td>
        <td><span class="odate time_1600000000">2020-09-13</span></td></tr>
    </table>
    """
    members = wc_mod.parse_members_html(body)
    assert len(members) == 2
    assert members[0] == {
        "user_id": 42, "unix_name": "jane-doe", "name": "Jane Doe",
        "joined_ts": 1700000000.0,
    }
    assert members[1]["user_id"] == 7
    assert members[1]["joined_ts"] == 1600000000.0


def test_parse_last_page_from_pager():
    body = '<div class="pager"><span>1</span><a href="#">1</a><a>2</a><a>3</a><a>next</a></div>'
    assert wc_mod.parse_last_page(body) == 3
    assert wc_mod.parse_last_page("<div>no pager</div>") == 1


def test_parse_user_info_profile_page():
    html = """
    <h1 class="profile-title">Jane Doe</h1>
    <a class="btn btn-default btn-xs" href="https://www.wikidot.com/account/block/42">屏蔽</a>
    """
    assert wc_mod.parse_user_info(html) == (42, "Jane Doe")


def test_parse_user_info_error_block_means_missing():
    html = '<div class="error-block">user does not exist</div>'
    assert wc_mod.parse_user_info(html) is None


def test_parse_applications_html_pairs_user_and_text():
    body = """
    <h3><span class="printuser"><a href="http://www.wikidot.com/user:info/alice"
      onclick="WIKIDOT.page.listeners.userInfo(9); return false;">Alice</a></span></h3>
    <table><tr><th>字段</th><th>内容</th></tr>
    <tr><td>留言</td><td>我想加入这个站点</td></tr></table>
    """
    apps = wc_mod.parse_applications_html(body)
    assert len(apps) == 1
    assert apps[0]["user_id"] == 9
    assert apps[0]["text"] == "我想加入这个站点"


def test_to_unix_name():
    assert wc_mod.to_unix_name("Jane Doe") == "jane-doe"
    assert wc_mod.to_unix_name("  Bob ") == "bob"


# --------------------------------------------------------------------------- #
# wikidot_client：登录 / AMC 状态分发（网络层打桩）
# --------------------------------------------------------------------------- #


def _ok_body_html(payload="ok-render"):
    return json.dumps({"status": "ok", "body": payload})


class FakeHttp:
    """按 URL 前缀路由的 _post_form/_get_text 替身，响应按序消费。"""

    def __init__(self):
        self.post_responses = []
        self.post_calls = []
        self.get_responses = []
        self.get_calls = []

    async def post(self, url, pairs):
        self.post_calls.append((url, pairs))
        if not self.post_responses:
            raise AssertionError(f"未预置的 POST: {url}")
        status, text, cookies = self.post_responses.pop(0)
        if isinstance(status, Exception):
            raise status
        return status, text, cookies

    async def get(self, url):
        self.get_calls.append(url)
        if not self.get_responses:
            raise AssertionError(f"未预置的 GET: {url}")
        status, text = self.get_responses.pop(0)
        if isinstance(status, Exception):
            raise status
        return status, text


def _make_client(site="example-site", **kwargs):
    client = WikidotClient(site=site, username="bot", password="pw", **kwargs)
    return client


def test_login_success_saves_session_to_store():
    d = _tmp_data_dir()
    store = WikidotSessionStore(data_dir=d)
    client = _make_client(session_store=store)
    http = FakeHttp()
    http.post_responses = [
        (200, "ok", {"WIKIDOT_SESSION_ID": "SID123"}),
    ]
    client._post_form = http.post
    sid = asyncio.run(client.login())
    assert sid == "SID123"
    assert store.get() == "SID123"
    url, pairs = http.post_calls[0]
    assert url.endswith("/default--flow/login__LoginPopupScreen")
    assert ("login", "bot") in pairs and ("event", "login") in pairs


def test_login_bad_credentials_raises_auth():
    client = _make_client()
    http = FakeHttp()
    http.post_responses = [(200, "The login and password do not match", {})]
    client._post_form = http.post
    try:
        asyncio.run(client.login())
        raise AssertionError("应当抛出 WikidotError")
    except WikidotError as e:
        assert e.kind == WikidotError.KIND_AUTH
        assert "账号或密码错误" in str(e)


def test_login_no_session_cookie_raises_auth():
    client = _make_client()
    http = FakeHttp()
    http.post_responses = [(200, "welcome", {})]
    client._post_form = http.post
    try:
        asyncio.run(client.login())
        raise AssertionError("应当抛出 WikidotError")
    except WikidotError as e:
        assert e.kind == WikidotError.KIND_AUTH


def test_amc_request_ok_returns_data():
    client = _make_client()
    http = FakeHttp()
    http.post_responses = [(200, _ok_body_html("<b>x</b>"), {})]
    client._post_form = http.post
    client._session_id = "SID"
    data = asyncio.run(client.amc_request({"moduleName": "Empty"}))
    assert data["status"] == "ok"
    url, pairs = http.post_calls[0]
    assert url == "https://example-site.wikidot.com/ajax-module-connector.php"
    assert ("wikidot_token7", "123456") in pairs


def test_amc_request_no_permission_and_form_errors():
    client = _make_client()
    client._session_id = "SID"
    http = FakeHttp()
    http.post_responses = [
        (200, json.dumps({"status": "no_permission"}), {}),
        (200, json.dumps({"status": "form_errors", "formErrors": {"name": "太长"}}), {}),
    ]
    client._post_form = http.post
    try:
        asyncio.run(client.amc_request({"moduleName": "Empty"}))
        raise AssertionError("应当抛出 no_permission")
    except WikidotError as e:
        assert e.kind == WikidotError.KIND_PERMISSION
    try:
        asyncio.run(client.amc_request({"moduleName": "Empty"}))
        raise AssertionError("应当抛出 form")
    except WikidotError as e:
        assert e.kind == WikidotError.KIND_FORM
        assert e.errors == {"name": "太长"}


def test_amc_request_try_again_raises_rate_limited_after_attempts():
    _patch_client_sleep()
    try:
        client = _make_client(retry_attempts=2)
        client._session_id = "SID"
        http = FakeHttp()
        http.post_responses = [
            (200, json.dumps({"status": "try_again"}), {}),
            (200, json.dumps({"status": "try_again"}), {}),
        ]
        client._post_form = http.post
        try:
            asyncio.run(client.amc_request({"moduleName": "Empty"}))
            raise AssertionError("应当抛出 rate_limited")
        except WikidotError as e:
            assert e.kind == WikidotError.KIND_RATE_LIMITED
        assert len(http.post_calls) == 2
    finally:
        _restore_client_sleep()


def test_amc_request_login_click_body_triggers_relogin_and_retry():
    d = _tmp_data_dir()
    store = WikidotSessionStore(data_dir=d)
    store.set("SID-OLD", "bot")  # 预置旧会话，首次 amc 直接复用（不触发登录请求）
    client = _make_client(session_store=store)
    http = FakeHttp()
    http.post_responses = [
        # amc 首次请求：旧会话失效（body 带登录钩子）
        (200, _ok_body_html('WIKIDOT.page.listeners.loginClick(event)'), {}),
        # 强制重新登录
        (200, "ok", {"WIKIDOT_SESSION_ID": "SID-NEW"}),
        # 重试成功
        (200, _ok_body_html("fine"), {}),
    ]
    client._post_form = http.post
    data = asyncio.run(client.amc_request({"moduleName": "Empty"}, require_body=True))
    assert data["body"] == "fine"
    assert client._session_id == "SID-NEW"
    assert store.get() == "SID-NEW"


def test_amc_request_require_body_missing_body_raises():
    client = _make_client()
    client._session_id = "SID"
    http = FakeHttp()
    http.post_responses = [(200, json.dumps({"status": "ok"}), {})]
    client._post_form = http.post
    try:
        asyncio.run(client.amc_request({"moduleName": "Empty"}, require_body=True))
        raise AssertionError("应当抛出 api")
    except WikidotError as e:
        assert e.kind == WikidotError.KIND_API


def test_amc_request_500_with_action_fails_fast():
    client = _make_client()
    client._session_id = "SID"
    http = FakeHttp()
    http.post_responses = [(500, "", {})]
    client._post_form = http.post
    try:
        asyncio.run(client.amc_request({"action": "XAction", "event": "y"}))
        raise AssertionError("应当抛出 api")
    except WikidotError as e:
        assert e.kind == WikidotError.KIND_API and e.status_code == 500
    assert len(http.post_calls) == 1


# --------------------------------------------------------------------------- #
# wikidot_client：页面锁流程与业务方法
# --------------------------------------------------------------------------- #


def test_save_page_lock_flow_calls_release():
    client = _make_client()
    http = FakeHttp()
    http.post_responses = [
        # 抢锁
        (200, json.dumps({
            "status": "ok", "lock_id": 11, "lock_secret": 22,
            "page_revision_id": 5,
        }), {}),
        # 保存
        (200, json.dumps({"status": "ok", "revision_id": 6}), {}),
        # 释放锁
        (200, json.dumps({"status": "ok"}), {}),
    ]
    http.get_responses = [
        (200, '<div id="page-title">标题</div>WIKIREQUEST.info.pageId = 99;'),
    ]
    client._post_form = http.post
    client._get_text = http.get
    client._session_id = "SID"
    asyncio.run(client.save_page("start", "NEW SOURCE", comment="test"))
    events = []
    for _url, pairs in http.post_calls:
        kv = dict(pairs)
        events.append((kv.get("moduleName"), kv.get("event") or kv.get("action")))
    assert events[0] == ("edit/PageEditModule", None)
    assert events[1] == ("Empty", "savePage")
    assert dict(http.post_calls[1][1])["event"] == "savePage"
    assert dict(http.post_calls[1][1])["source"] == "NEW SOURCE"
    assert dict(http.post_calls[1][1])["lock_secret"] == "22"
    assert dict(http.post_calls[1][1])["revision_id"] == "5"
    assert dict(http.post_calls[1][1])["title"] == "标题"
    assert dict(http.post_calls[2][1])["event"] == "removePageEditLock"
    # 现有页面的 page_id 也要带到锁请求里
    assert dict(http.post_calls[0][1])["page_id"] == "99"


def test_save_page_locked_by_other_raises_locked():
    client = _make_client()
    http = FakeHttp()
    http.post_responses = [
        (200, json.dumps({"status": "ok", "locked": True, "other_locks": 1}), {}),
    ]
    http.get_responses = [(200, "WIKIREQUEST.info.pageId = 1;")]
    client._post_form = http.post
    client._get_text = http.get
    client._session_id = "SID"
    try:
        asyncio.run(client.save_page("start", "x"))
        raise AssertionError("应当抛出 locked")
    except WikidotError as e:
        assert e.kind == WikidotError.KIND_LOCKED


def test_get_source_flow():
    client = _make_client()
    http = FakeHttp()
    http.get_responses = [(200, "WIKIREQUEST.info.pageId = 7;")]
    http.post_responses = [
        (200, _ok_body_html('<div class="page-source">HELLO</div>'), {}),
    ]
    client._post_form = http.post
    client._get_text = http.get
    client._session_id = "SID"
    source = asyncio.run(client.get_source("start"))
    assert source == "HELLO"
    assert dict(http.post_calls[0][1])["moduleName"] == "viewsource/ViewSourceModule"


def test_get_source_missing_page_raises_no_page():
    client = _make_client()
    http = FakeHttp()
    http.get_responses = [(404, "not found")]
    client._get_text = http.get
    client._session_id = "SID"
    try:
        asyncio.run(client.get_source("nope"))
        raise AssertionError("应当抛出 no_page")
    except WikidotError as e:
        assert e.kind == WikidotError.KIND_NO_PAGE


def test_invite_user_translates_already_statuses():
    client = _make_client()
    http = FakeHttp()
    http.post_responses = [
        (200, json.dumps({"status": "already_member"}), {}),
        (200, json.dumps({"status": "already_invited"}), {}),
        (200, json.dumps({"status": "ok"}), {}),
    ]
    client._post_form = http.post
    client._session_id = "SID"
    try:
        asyncio.run(client.invite_user(5))
        raise AssertionError("应当抛出 form")
    except WikidotError as e:
        assert e.kind == WikidotError.KIND_FORM
        assert "已是站点成员" in str(e)
    try:
        asyncio.run(client.invite_user(5))
        raise AssertionError("应当抛出 form")
    except WikidotError as e:
        assert "已被邀请" in str(e)
    asyncio.run(client.invite_user(5))  # 第三次 ok 不抛


def test_forum_layout_get_and_save_roundtrip():
    client = _make_client()
    http = FakeHttp()
    http.post_responses = [
        (200, json.dumps({
            "status": "ok",
            "groups": [{"name": "G1", "description": "", "visible": True,
                        "group_id": 1}],
            "categories": [[{"name": "C1", "description": "d",
                             "category_id": 3, "number_threads": 9}]],
            "defaultNesting": 5,
        }), {}),
        (200, json.dumps({"status": "ok"}), {}),
    ]
    client._post_form = http.post
    client._session_id = "SID"
    layout = asyncio.run(client.get_forum_layout())
    group = layout["groups"][0]
    assert group["categories"][0]["name"] == "C1"
    asyncio.run(client.save_forum_layout(
        layout["groups"], deleted_group_ids=[1], deleted_category_ids=[3],
    ))
    kv = dict(http.post_calls[1][1])
    assert kv["event"] == "saveForumLayout"
    import json as _json
    groups = _json.loads(kv["groups"])
    assert groups[0]["name"] == "G1"
    assert "number_threads" not in groups[0]["categories"][0]
    assert _json.loads(kv["deleted_groups"]) == [1]


def test_set_forum_nesting_validates_range():
    client = _make_client()
    client._session_id = "SID"
    try:
        asyncio.run(client.set_forum_nesting(11))
        raise AssertionError("应当抛出 ValueError")
    except ValueError:
        pass


def test_save_access_policy_validates_privacy():
    client = _make_client()
    client._session_id = "SID"
    try:
        asyncio.run(client.save_access_policy({"privacy": "weird"}))
        raise AssertionError("应当抛出 ValueError")
    except ValueError:
        pass


# --------------------------------------------------------------------------- #
# wikidot_session_store
# --------------------------------------------------------------------------- #


def test_session_store_roundtrip_and_clear():
    d = _tmp_data_dir()
    store = WikidotSessionStore(data_dir=d)
    assert store.get() is None
    store.set("SID1", "alice")
    assert store.get() == "SID1"
    assert store.get_username() == "alice"
    # 重新加载（模拟重启）
    store2 = WikidotSessionStore(data_dir=d)
    assert store2.get() == "SID1"
    assert store2.get_username() == "alice"
    store2.clear()
    assert store2.get() is None
    assert WikidotSessionStore(data_dir=d).get() is None


def test_session_store_file_permissions_and_bad_json():
    d = _tmp_data_dir()
    store = WikidotSessionStore(data_dir=d)
    store.set("SID", "bob")
    path = os.path.join(d, "currentcortex_wikidot_session.json")
    mode = os.stat(path).st_mode & 0o777
    assert mode == 0o600, oct(mode)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{broken json")
    assert WikidotSessionStore(data_dir=d).get() is None


# --------------------------------------------------------------------------- #
# wikidot_commands：分发 / 权限 / 确认词
# --------------------------------------------------------------------------- #


def test_parse_command_strips_prefixes():
    handler = WikidotCommandHandler(FakeClient())
    assert handler._parse_command("/wikidot 源码 start") == ("源码", "start")
    assert handler._parse_command("/wd source start") == ("source", "start")
    assert handler._parse_command("维基 帮助") == ("help", "")
    assert handler._parse_command("/wikidot") == ("help", "")
    assert handler._parse_command("/wikidot 成员 管理员 2") == ("成员", "管理员 2")


def test_help_output():
    out = _dispatch(_handler(FakeClient()), "/wikidot 帮助")
    assert "源码" in out and "论坛" in out and "邀请" in out


def test_not_configured_hints_setup():
    out = _dispatch(_handler(FakeClient(configured=False)), "/wd 状态")
    assert "wikidot_site" in out and "未配置" in out


def test_write_requires_admin():
    fake = FakeClient()
    out = _dispatch(_handler(fake), "/wd 写入 new-page :: 内容", admin=False)
    assert "仅管理员" in out
    assert not _called(fake, "save_page")


def test_read_blocked_when_admin_only():
    out = _dispatch(_handler(FakeClient(), admin_only=True), "/wd 源码 start", admin=False)
    assert "仅管理员可用" in out


def test_read_allowed_when_not_admin_only():
    fake = FakeClient()
    out = _dispatch(_handler(fake, admin_only=False), "/wd 源码 start", admin=False)
    assert "SOURCE" in out


def test_source_output_and_missing_args():
    fake = FakeClient()
    out = _dispatch(_handler(fake), "/wd 源码 start")
    assert "SOURCE" in out
    out = _dispatch(_handler(fake), "/wd 源码")
    assert "用法" in out


def test_info_output():
    fake = FakeClient()
    fake.responses["get_page_info"] = {
        "exists": True, "fullname": "start", "page_id": 12,
        "title": "首页", "tags": ["main", "nav"],
    }
    out = _dispatch(_handler(fake), "/wd 信息 start")
    assert "首页" in out and "main" in out and "12" in out


def test_write_new_page_without_confirm():
    fake = FakeClient()
    fake.responses["get_page_info"] = {
        "exists": False, "fullname": "new-page",
    }
    out = _dispatch(_handler(fake), "/wd 写入 new-page :: 标题A :: 正文B")
    assert "已新建页面 new-page" in out
    name, args, kwargs = _called(fake, "save_page")[0]
    assert args[0] == "new-page" and args[1] == "正文B"
    assert kwargs["title"] == "标题A"


def test_write_existing_page_requires_overwrite_word():
    fake = FakeClient()
    out = _dispatch(_handler(fake), "/wd 写入 start :: 新内容")
    assert "已存在" in out and "覆盖" in out
    assert not _called(fake, "save_page")
    out = _dispatch(_handler(fake), "/wd 写入 start :: 新内容 覆盖")
    assert "已覆盖页面 start" in out
    name, args, kwargs = _called(fake, "save_page")[0]
    assert args[1] == "新内容"


def test_append_passes_content():
    fake = FakeClient()
    out = _dispatch(_handler(fake), "/wd 追加 start hello world")
    assert "已追加" in out
    name, args, kwargs = _called(fake, "append_page")[0]
    assert args == ("start", "hello world")


def test_tags_split_and_save():
    fake = FakeClient()
    out = _dispatch(_handler(fake), "/wd 标签 start scp 建筑, 二层")
    assert "已把 start 的标签设为" in out
    name, args, kwargs = _called(fake, "save_tags")[0]
    assert args == ("start", ["scp", "建筑", "二层"])


def test_rename_requires_confirm_word():
    fake = FakeClient()
    out = _dispatch(_handler(fake), "/wd 重命名 old new")
    assert "确认" in out and not _called(fake, "rename_page")
    out = _dispatch(_handler(fake), "/wd 重命名 old new 确认")
    assert "已重命名 old → new" in out
    assert _called(fake, "rename_page")


def test_delete_requires_confirm_word():
    fake = FakeClient()
    out = _dispatch(_handler(fake), "/wd 删除 start")
    assert "确认删除" in out and not _called(fake, "delete_page")
    out = _dispatch(_handler(fake), "/wd 删除 start 确认")
    assert "已删除页面 start" in out


def test_parent_none_word_clears_parent():
    fake = FakeClient()
    _dispatch(_handler(fake), "/wd 父页 child 无")
    name, args, kwargs = _called(fake, "set_parent")[0]
    assert args == ("child", None)


def test_members_render_with_group_and_page():
    fake = FakeClient()
    fake.responses["list_members"] = (
        [{
            "user_id": 1, "name": "张三", "unix_name": "zhang-san",
            "joined_ts": 1700000000.0,
        }],
        3,
    )
    out = _dispatch(_handler(fake), "/wd 成员 管理员 2")
    assert "管理员" in out and "张三" in out and "2/3" in out
    name, args, kwargs = _called(fake, "list_members")[0]
    assert kwargs == {"group": "admins", "page": 2}


def test_remove_member_resolves_user_and_optional_ban():
    fake = FakeClient()
    fake.responses["resolve_user"] = (42, "李四")
    out = _dispatch(_handler(fake), "/wd 移除成员 lisi 封禁")
    assert "李四" in out and "封禁" in out
    name, args, kwargs = _called(fake, "remove_member")[0]
    assert args == (42,) and kwargs == {"ban": True}


def test_remove_member_unknown_user_value_error():
    fake = FakeClient()
    fake.responses["resolve_user"] = None
    fake.responses["list_members"] = ([], 1)
    fake.responses["list_all_members"] = []
    out = _dispatch(_handler(fake), "/wd 移除成员 nobody")
    assert "未找到 Wikidot 用户" in out


def test_ban_unban_pass_reason():
    fake = FakeClient()
    fake.responses["resolve_user"] = (7, "王五")
    _dispatch(_handler(fake), "/wd 封禁 wangwu 灌水")
    name, args, kwargs = _called(fake, "block_user")[0]
    assert args == (7,) and kwargs == {"reason": "灌水"}
    _dispatch(_handler(fake), "/wd 解封 wangwu")
    assert _called(fake, "unblock_user")[0][1] == (7,)


def test_settings_show_and_save_with_chinese_keys():
    fake = FakeClient()
    out = _dispatch(_handler(fake), "/wd 设置")
    assert "Site" in out
    out = _dispatch(_handler(fake), '/wd 设置 名称="新 名字" 描述=hello')
    name, args, kwargs = _called(fake, "save_general_settings")[0]
    assert args[0] == {"name": "新 名字", "description": "hello"}


def test_settings_unknown_field_value_error():
    fake = FakeClient()
    out = _dispatch(_handler(fake), "/wd 设置 不存在=x")
    assert "参数错误" in out and "未知设置字段" in out


def test_policy_show_and_save():
    fake = FakeClient()
    out = _dispatch(_handler(fake), "/wd 访问策略")
    assert "open" in out
    _dispatch(_handler(fake), "/wd 访问策略 privacy=closed 申请=on")
    name, args, kwargs = _called(fake, "save_access_policy")[0]
    assert args[0]["privacy"] == "closed"
    assert args[0]["by_apply"] is True


def test_nav_default_and_custom():
    fake = FakeClient()
    _dispatch(_handler(fake), "/wd 导航 顶栏=nav:top")
    name, args, kwargs = _called(fake, "save_navigation")[0]
    assert kwargs == {"top": "nav:top", "side": None, "use_default": False}
    _dispatch(_handler(fake), "/wd 导航 默认")
    assert _called(fake, "save_navigation")[1][2] == {
        "top": None, "side": None, "use_default": True,
    }


def test_license_template_theme_write():
    fake = FakeClient()
    _dispatch(_handler(fake), "/wd 许可证 id=cc-by-sa-3.0")
    assert _called(fake, "set_license")[0][2] == {
        "license_id": "cc-by-sa-3.0", "other": None, "use_default": False,
    }
    _dispatch(_handler(fake), "/wd 模板 9")
    assert _called(fake, "set_template")[0][1] == ("9",)
    _dispatch(_handler(fake), "/wd 外观 默认")
    assert _called(fake, "set_appearance")[0][2] == {
        "theme_id": None, "use_default": True,
    }


def test_forum_show_and_nested_subcommands():
    fake = FakeClient()
    fake.responses["get_forum_layout"] = {
        "default_nesting": 5,
        "groups": [{
            "name": "讨论区", "description": "", "visible": True, "group_id": 1,
            "categories": [{"name": "灌水区", "description": "", "max_nest_level": None}],
        }],
    }
    out = _dispatch(_handler(fake), "/wd 论坛")
    assert "讨论区" in out and "灌水区" in out
    # 嵌套深度
    out = _dispatch(_handler(fake), "/wd 论坛 嵌套 8")
    assert "嵌套深度" in out
    assert _called(fake, "set_forum_nesting")[0][1] == (8,)
    # 加组
    out = _dispatch(_handler(fake), "/wd 论坛 加组 新组 说明文字")
    assert "已添加版块组「新组」" in out
    groups = _called(fake, "save_forum_layout")[0][1][0]
    assert groups[-1]["name"] == "新组"
    # 删组需要确认
    out = _dispatch(_handler(fake), "/wd 论坛 删组 新组")
    assert "确认" in out
    out = _dispatch(_handler(fake), "/wd 论坛 删组 新组 确认")
    assert "已删除版块组「新组」" in out
    call = _called(fake, "save_forum_layout")[-1]
    assert call[2]["deleted_group_ids"] == []


def test_forum_nested_write_denied_for_non_admin():
    fake = FakeClient()
    out = _dispatch(_handler(fake), "/wd 论坛 嵌套 3", admin=False)
    assert "仅管理员" in out


def test_forum_add_category_and_delete():
    fake = FakeClient()
    fake.responses["get_forum_layout"] = {
        "default_nesting": 5,
        "groups": [{
            "name": "G", "description": "", "visible": True, "group_id": 1,
            "categories": [{"name": "旧版块", "description": "",
                            "category_id": 9, "max_nest_level": None}],
        }],
    }
    out = _dispatch(_handler(fake), "/wd 论坛 加版块 G 新版块 描述x")
    assert "已在「G」下添加版块「新版块」" in out
    out = _dispatch(_handler(fake), "/wd 论坛 删版块 旧版块 确认")
    assert "已删除版块「旧版块」" in out
    call = _called(fake, "save_forum_layout")[-1]
    assert call[2]["deleted_category_ids"] == [9]


def test_invite_by_name_and_email_requires_admin():
    fake = FakeClient()
    fake.responses["resolve_user"] = (66, "赵六")
    out = _dispatch(_handler(fake), "/wd 邀请 zhaoliu 欢迎加入")
    assert "已邀请 赵六" in out
    call = _called(fake, "invite_user")[0]
    assert call[1] == (66,) and call[2] == {"text": "欢迎加入"}
    out = _dispatch(_handler(fake), "/wd 邀请 邮箱 a@b.com 过来看看", admin=False)
    assert "仅管理员" in out
    _dispatch(_handler(fake), "/wd 邀请 邮箱 a@b.com 过来看看")
    call = _called(fake, "send_email_invitation")[0]
    assert call[1] == ("a@b.com",) and call[2] == {"message": "过来看看"}


def test_invite_switch_on_off():
    fake = FakeClient()
    _dispatch(_handler(fake), "/wd 邀请开关 开")
    assert _called(fake, "set_let_users_invite")[0][1] == (True,)
    out = _dispatch(_handler(fake), "/wd 邀请开关 关")
    assert _called(fake, "set_let_users_invite")[1][1] == (False,)
    out = _dispatch(_handler(fake), "/wd 邀请开关 随便")
    assert "用法" in out


def test_applications_list_and_process():
    fake = FakeClient()
    fake.responses["list_applications"] = [
        {"user_id": 3, "name": "小明", "unix_name": "xiao-ming", "text": "求过"},
    ]
    out = _dispatch(_handler(fake), "/wd 申请")
    assert "小明" in out and "求过" in out
    fake.responses["resolve_user"] = (3, "小明")
    # 处理申请是写操作：非管理员拒绝
    out = _dispatch(_handler(fake), "/wd 申请 xiao-ming 同意", admin=False)
    assert "仅管理员" in out and not _called(fake, "process_application")
    out = _dispatch(_handler(fake), "/wd 申请 xiao-ming 同意")
    assert "已同意" in out
    assert _called(fake, "process_application")[0][2] == {"accept": True}


def test_wikidot_error_translated_friendly():
    fake = FakeClient()
    fake.responses["get_source"] = WikidotError(
        "页面 xxx 不存在", kind=WikidotError.KIND_NO_PAGE
    )
    out = _dispatch(_handler(fake), "/wd 源码 xxx")
    assert "📄" in out and "不存在" in out


def test_status_output():
    out = _dispatch(_handler(FakeClient()), "/wd 状态")
    assert "example-site" in out and "tester" in out


def test_unknown_subcommand():
    out = _dispatch(_handler(FakeClient()), "/wd 不存在的子命令")
    assert "未知的 Wikidot 子命令" in out


# --------------------------------------------------------------------------- #
# LLM 工具实现
# --------------------------------------------------------------------------- #


def test_tool_get_page():
    fake = FakeClient()
    fake.responses["get_page_info"] = {
        "exists": True, "title": "首页", "tags": ["a"],
    }
    handler = _handler(fake)
    out = asyncio.run(handler.tool_get_page("start"))
    assert "首页" in out and "SOURCE" in out


def test_tool_save_page_admin_gate():
    fake = FakeClient()
    handler = _handler(fake)
    out = asyncio.run(handler.tool_save_page(
        FakeEvent("x", admin=False), "start", "NEW"
    ))
    assert "仅管理员" in out
    assert not _called(fake, "save_page")
    out = asyncio.run(handler.tool_save_page(
        FakeEvent("x", admin=True), "start", "NEW"
    ))
    assert "已保存页面 start" in out
    assert _called(fake, "save_page")[0][1][1] == "NEW"


def test_tool_list_members_and_settings():
    fake = FakeClient()
    fake.responses["list_members"] = (
        [{"user_id": 1, "name": "A", "unix_name": "a", "joined_ts": None}], 1
    )
    handler = _handler(fake)
    out = asyncio.run(handler.tool_list_members())
    assert "A" in out
    out = asyncio.run(handler.tool_site_settings())
    assert "Site" in out


# --------------------------------------------------------------------------- #
# main.py 接线
# --------------------------------------------------------------------------- #


def _make_plugin(enable=True, handler=None, client=None):
    inst = PluginCls.__new__(PluginCls)
    inst._wikidot_enable = enable
    inst._wikidot_handler = handler
    inst._wikidot_client = client
    return inst


def test_main_wikidot_command_disabled_hint():
    inst = _make_plugin(enable=False)
    out = _texts(_run_command(inst.wikidot_command(FakeEvent("/wd 状态"))))
    assert "未启用" in out


def test_main_wikidot_command_delegates_to_handler():
    fake = FakeClient()
    handler = WikidotCommandHandler(fake)
    inst = _make_plugin(enable=True, handler=handler, client=fake)
    out = _texts(_run_command(inst.wikidot_command(FakeEvent("/wd 源码 start"))))
    assert "SOURCE" in out


def test_main_registers_wikidot_switch_scope():
    scopes = getattr(PluginCls, "_SWITCH_SCOPES", {})
    assert "wikidot" in scopes
    assert "wikidot" in scopes["wikidot"]["commands"]


def test_main_has_wikidot_llm_tools():
    # 装饰器为 no-op，工具方法应原样挂在类上
    for name in (
        "llm_tool_wikidot_get_page", "llm_tool_wikidot_save_page",
        "llm_tool_wikidot_append_page", "llm_tool_wikidot_members",
        "llm_tool_wikidot_forum", "llm_tool_wikidot_settings",
    ):
        assert hasattr(PluginCls, name), name
        assert hasattr(PluginCls, "wikidot_command")


def test_main_wikidot_tool_guard_paths():
    fake = FakeClient()
    handler = WikidotCommandHandler(fake)
    inst = _make_plugin(enable=True, handler=handler, client=fake)
    inst._llm_tools_enable = False
    assert "关闭" in inst._wikidot_tool_guard()
    inst._llm_tools_enable = True
    assert inst._wikidot_tool_guard() is None
    inst2 = _make_plugin(enable=False)
    inst2._llm_tools_enable = True
    assert "未启用" in inst2._wikidot_tool_guard()


def test_config_schema_contains_wikidot_keys():
    schema_path = PLUGIN_DIR / "_conf_schema.json"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    for key in (
        "wikidot_enable", "wikidot_site", "wikidot_username",
        "wikidot_password", "wikidot_admin_only", "wikidot_timeout",
    ):
        assert key in schema, key


TESTS = [
    # AMC 表单编码
    test_encode_amc_form_injects_token_and_keeps_zero,
    test_encode_amc_form_omits_falsy_and_encodes_bools,
    test_encode_amc_form_list_values_use_jquery_brackets,
    test_amc_helpers,
    # HTML 解析
    test_extract_page_source_unescapes_and_normalizes,
    test_extract_page_id_patterns,
    test_parse_form_fields_mixed_controls,
    test_parse_select_options,
    test_parse_members_html_rows_with_odate,
    test_parse_last_page_from_pager,
    test_parse_user_info_profile_page,
    test_parse_user_info_error_block_means_missing,
    test_parse_applications_html_pairs_user_and_text,
    test_to_unix_name,
    # 登录 / AMC 状态分发
    test_login_success_saves_session_to_store,
    test_login_bad_credentials_raises_auth,
    test_login_no_session_cookie_raises_auth,
    test_amc_request_ok_returns_data,
    test_amc_request_no_permission_and_form_errors,
    test_amc_request_try_again_raises_rate_limited_after_attempts,
    test_amc_request_login_click_body_triggers_relogin_and_retry,
    test_amc_request_require_body_missing_body_raises,
    test_amc_request_500_with_action_fails_fast,
    # 页面锁流程与业务方法
    test_save_page_lock_flow_calls_release,
    test_save_page_locked_by_other_raises_locked,
    test_get_source_flow,
    test_get_source_missing_page_raises_no_page,
    test_invite_user_translates_already_statuses,
    test_forum_layout_get_and_save_roundtrip,
    test_set_forum_nesting_validates_range,
    test_save_access_policy_validates_privacy,
    # 会话存储
    test_session_store_roundtrip_and_clear,
    test_session_store_file_permissions_and_bad_json,
    # 命令分发 / 权限 / 确认词
    test_parse_command_strips_prefixes,
    test_help_output,
    test_not_configured_hints_setup,
    test_write_requires_admin,
    test_read_blocked_when_admin_only,
    test_read_allowed_when_not_admin_only,
    test_source_output_and_missing_args,
    test_info_output,
    test_write_new_page_without_confirm,
    test_write_existing_page_requires_overwrite_word,
    test_append_passes_content,
    test_tags_split_and_save,
    test_rename_requires_confirm_word,
    test_delete_requires_confirm_word,
    test_parent_none_word_clears_parent,
    test_members_render_with_group_and_page,
    test_remove_member_resolves_user_and_optional_ban,
    test_remove_member_unknown_user_value_error,
    test_ban_unban_pass_reason,
    test_settings_show_and_save_with_chinese_keys,
    test_settings_unknown_field_value_error,
    test_policy_show_and_save,
    test_nav_default_and_custom,
    test_license_template_theme_write,
    test_forum_show_and_nested_subcommands,
    test_forum_nested_write_denied_for_non_admin,
    test_forum_add_category_and_delete,
    test_invite_by_name_and_email_requires_admin,
    test_invite_switch_on_off,
    test_applications_list_and_process,
    test_wikidot_error_translated_friendly,
    test_status_output,
    test_unknown_subcommand,
    # LLM 工具
    test_tool_get_page,
    test_tool_save_page_admin_gate,
    test_tool_list_members_and_settings,
    # main.py 接线
    test_main_wikidot_command_disabled_hint,
    test_main_wikidot_command_delegates_to_handler,
    test_main_registers_wikidot_switch_scope,
    test_main_has_wikidot_llm_tools,
    test_main_wikidot_tool_guard_paths,
    test_config_schema_contains_wikidot_keys,
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
