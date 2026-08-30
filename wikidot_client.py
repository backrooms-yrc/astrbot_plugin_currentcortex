"""Wikidot 前端 JS 接口（ajax-module-connector.php）客户端。

复刻 Wikidot 站点前端 JavaScript 与后端交互的协议，使插件能以登录账号
身份编辑页面与管理站点。协议要点（与 ukwhatn/wikidot.py 及原版 Wikidot
源码 web/ajax-module-connector.php 一致）：

- 登录：POST https://www.wikidot.com/default--flow/login__LoginPopupScreen
  表单 login / password / action=Login2Action / event=login；成功判定为
  HTTP 200 + 响应体不含凭证错误提示 + 拿到 WIKIDOT_SESSION_ID cookie。
- AMC 调用：POST https://{site}.wikidot.com/ajax-module-connector.php，
  urlencoded 表单携带 moduleName 与各业务字段，并恒附 wikidot_token7=123456
  （表单与 cookie 均带该固定 token，这是前端 JS 的固定做法）。
  响应为 JSON：status=ok 时业务内容在 body（HTML 片段或纯数据）；
  try_again 表示限流（按 time_to_wait / 指数退避重试）；no_permission /
  form_errors / form_error 等为业务失败。
- 页面编辑走「锁」流程：edit/PageEditModule 抢锁取得 lock_id/lock_secret，
  WikiPageAction/savePage 保存，removePageEditLock 释放。
- 列表值按 jQuery.param 风格编码为 key[]=v（多条同名键）。

HTML 解析全部使用标准库（re + html.unescape + html.parser），不引入
BeautifulSoup 等新依赖。
"""

import asyncio
import json
import re
import time
from html import unescape
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from astrbot.api import logger

from .wikidot_session_store import WikidotSessionStore

# 前端 JS 的固定 CSRF token：cookie 与表单均携带该值
AMC_TOKEN = "123456"

LOGIN_URL = "https://www.wikidot.com/default--flow/login__LoginPopupScreen"
USER_INFO_URL = "https://www.wikidot.com/user:info/{unix_name}"

# ---- AMC 模块名（渲染类，返回 body HTML） ----
MODULE_MEMBERS_LIST = "membership/MembersListModule"
MODULE_VIEW_SOURCE = "viewsource/ViewSourceModule"
MODULE_PAGE_EDIT = "edit/PageEditModule"
MODULE_GENERAL_SETTINGS = "managesite/ManageSiteGeneralModule"
MODULE_ACCESS_POLICY = "managesite/ManageSiteAccessPolicyModule"
MODULE_NAVIGATION = "managesite/ManageSiteNavigationModule"
MODULE_LICENSE = "managesite/ManageSiteLicenseModule"
MODULE_TEMPLATES = "managesite/ManageSiteTemplatesModule"
MODULE_APPEARANCE = "managesite/themes/ManageSiteAppearanceModule"
MODULE_FORUM_LAYOUT = "managesite/ManageSiteGetForumLayoutModule"
MODULE_APPLICATIONS = "managesite/ManageSiteMembersApplicationsModule"


# ===================================================================== #
# 异常
# ===================================================================== #
class WikidotError(Exception):
    """Wikidot 接口错误（kind 分类便于上层给出用户友好提示）。"""

    KIND_AUTH = "auth"              # 未登录 / 登录失败 / 会话失效
    KIND_PERMISSION = "permission"  # 已登录但无权限（需站点管理员）
    KIND_NO_PAGE = "no_page"        # 页面不存在
    KIND_LOCKED = "locked"          # 页面被他人编辑锁占用
    KIND_FORM = "form"              # 表单校验失败（带逐字段错误）
    KIND_RATE_LIMITED = "rate_limited"
    KIND_NETWORK = "network"
    KIND_TIMEOUT = "timeout"
    KIND_API = "api"                # 其余服务端错误 / 响应异常

    def __init__(self, message: str, kind: str = KIND_API,
                 status_code: Any = None, errors: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.errors = errors or {}


# ===================================================================== #
# AMC 表单构造辅助（纯函数，便于离线单测）
# ===================================================================== #
def amc_checkbox(value: Any) -> Any:
    """复选框编码：真值为 "on"，假值返回 None（整个键省略不发）。"""
    return "on" if value else None


def amc_flag(value: Any) -> Any:
    """flag 编码：真值为 "true"，假值返回 None（整个键省略不发）。"""
    return "true" if value else None


def encode_amc_form(body: Dict[str, Any]) -> List[Tuple[str, str]]:
    """把 AMC body dict 编码为 urlencoded 键值对列表。

    - None / False 的键整体省略（对应 wikidot.py 的 omit_falsy 语义，0 保留）；
    - True 编码为 "true"；
    - 列表值按 jQuery.param 风格展开为多条 ``key[]``；
    - 恒附加 wikidot_token7。
    """
    pairs: List[Tuple[str, str]] = []
    for key, value in body.items():
        if value is None or value is False:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                pairs.append((f"{key}[]", _amc_str(item)))
        else:
            pairs.append((key, _amc_str(value)))
    pairs.append(("wikidot_token7", AMC_TOKEN))
    return pairs


def _amc_str(value: Any) -> str:
    if value is True:
        return "true"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


# ===================================================================== #
# HTML 解析辅助（纯函数，便于离线单测）
# ===================================================================== #
def strip_tags(fragment: str) -> str:
    """去掉 HTML 标签并反转义实体，压缩空白。"""
    text = unescape(re.sub(r"<[^>]+>", "", fragment or ""))
    return re.sub(r"\s+", " ", text).strip()


_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.DOTALL | re.IGNORECASE)
_USER_HREF_RE = re.compile(
    r'href="https?://(?:www\.)?wikidot\.com/user:info/([^"]+)"', re.IGNORECASE
)
_USER_ONCLICK_RE = re.compile(r"userInfo\((\d+)\)")

_ROW_SPLIT_RE = re.compile(r"<tr\b[^>]*>", re.IGNORECASE)
_ODATE_CLASS_RE = re.compile(r'class="([^"]*\bodate\b[^"]*)"', re.IGNORECASE)
_TIME_CLASS_RE = re.compile(r"time_(\d+)")


def parse_printuser(fragment: str) -> Optional[Dict[str, Any]]:
    """从 HTML 片段中解析第一个 printuser 用户锚点。

    锚点形如：
    ``<a href=".../user:info/unix" onclick="WIKIDOT.page.listeners.userInfo(123);
    return false;">Name</a>``。返回 ``{"user_id", "name", "unix_name"}``。
    """
    for attrs, inner in _ANCHOR_RE.findall(fragment or ""):
        href_m = _USER_HREF_RE.search(attrs)
        click_m = _USER_ONCLICK_RE.search(attrs)
        if not href_m or not click_m:
            continue
        name = strip_tags(inner)
        return {
            "user_id": int(click_m.group(1)),
            "unix_name": href_m.group(1),
            "name": name or href_m.group(1),
        }
    return None


def parse_members_html(body: str) -> List[Dict[str, Any]]:
    """解析 membership/MembersListModule 返回的成员表格 HTML。

    每行：第 1 列 printuser（用户），第 2 列 odate（加入时间，
    unix 时间戳编码在 ``time_N`` class 中）。
    """
    members: List[Dict[str, Any]] = []
    for row in _ROW_SPLIT_RE.split(body or "")[1:]:
        if "<td" not in row:
            continue
        user = parse_printuser(row)
        if not user:
            continue
        joined_ts = None
        odate_m = _ODATE_CLASS_RE.search(row)
        if odate_m:
            time_m = _TIME_CLASS_RE.search(odate_m.group(1))
            if time_m:
                joined_ts = float(time_m.group(1))
        entry = dict(user)
        entry["joined_ts"] = joined_ts
        members.append(entry)
    return members


def parse_last_page(body: str) -> int:
    """从成员列表分页器（div.pager）解析末页页码；无分页器返回 1。

    与 wikidot.py 一致：分页器最后一个 <a> 是 next 按钮，
    倒数第二个 <a> 的文本即末页页码。
    """
    pager_m = re.search(
        r'<div\s+class="pager"(.*?)</div>', body or "", re.DOTALL | re.IGNORECASE
    )
    if not pager_m:
        return 1
    anchors = [
        strip_tags(inner)
        for _attrs, inner in re.findall(
            r"<a\b([^>]*)>(.*?)</a>", pager_m.group(1), re.DOTALL | re.IGNORECASE
        )
    ]
    if len(anchors) >= 2 and anchors[-2].isdigit():
        return max(1, int(anchors[-2]))
    return 1


_PAGE_ID_PATTERNS = (
    re.compile(r"WIKIREQUEST\.info\.pageId\s*=\s*[\"']?(\d+)"),
    re.compile(r"[\"']pageId[\"']\s*:\s*[\"']?(\d+)"),
)


def extract_page_id(page_html: str) -> Optional[int]:
    """从站点页面 HTML 中解析 pageId（WIKIREQUEST.info.pageId 等）。"""
    for pattern in _PAGE_ID_PATTERNS:
        m = pattern.search(page_html or "")
        if m:
            return int(m.group(1))
    return None


_PAGE_SOURCE_RE = re.compile(
    r'<div\s+class="page-source"[^>]*>(.*?)</div>', re.DOTALL
)


def extract_page_source(body_html: str) -> str:
    """从 ViewSourceModule 的 body 中提取 wikitext 源码。"""
    m = _PAGE_SOURCE_RE.search(body_html or "")
    if not m:
        return ""
    text = unescape(m.group(1))
    # wikidot.py 的后处理：&nbsp; 归一为空格、strip、去行首缩进 Tab
    text = text.replace("\u00a0", " ").strip()
    if text.startswith("\t"):
        text = text[1:]
    return text


_ERROR_BLOCK_RE = re.compile(
    r'class="[^"]*\berror-block\b[^"]*"', re.IGNORECASE
)
_PROFILE_TITLE_RE = re.compile(
    r'<h1[^>]*class="[^"]*profile-title[^"]*"[^>]*>(.*?)</h1>', re.DOTALL
)
_BTN_XS_RE = re.compile(r'btn-default[^"]*btn-xs|btn-xs[^"]*btn-default')


def parse_user_info(user_html: str) -> Optional[Tuple[int, str]]:
    """解析 www.wikidot.com/user:info/{name} 页面，返回 (user_id, name)。

    页面不存在（error-block）返回 None；user_id 取自
    ``a.btn.btn-default.btn-xs`` 链接 href 的末段数字。
    """
    if _ERROR_BLOCK_RE.search(user_html or ""):
        return None
    title_m = _PROFILE_TITLE_RE.search(user_html or "")
    name = strip_tags(title_m.group(1)) if title_m else ""
    for attrs, _inner in _ANCHOR_RE.findall(user_html or ""):
        if not _BTN_XS_RE.search(attrs):
            continue
        href_m = re.search(r'href="([^"]+)"', attrs)
        if not href_m:
            continue
        seg = href_m.group(1).rstrip("/").rsplit("/", 1)[-1]
        if seg.isdigit():
            return int(seg), (name or seg)
    return None


def to_unix_name(name: str) -> str:
    """用户名 -> Wikidot unix name（小写、空白折叠为连字符）。"""
    slug = re.sub(r"\s+", "-", (name or "").strip().lower())
    return slug


class _FormParser(HTMLParser):
    """收集 form 内 input/select/textarea 字段（name -> 当前值）。

    - text/password/hidden：value 属性；
    - checkbox/radio：仅记录 checked 的项，值取 value（缺省 "on"）；
    - select：选中 option 的 value（无 selected 取第一个 option）；
    - textarea：标签内文本。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: Dict[str, str] = {}
        self._select_name: Optional[str] = None
        self._select_selected: Optional[str] = None
        self._select_first: Optional[str] = None
        self._textarea_name: Optional[str] = None
        self._textarea_buf: List[str] = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        name = attr.get("name")
        if tag == "input" and name:
            itype = (attr.get("type") or "text").lower()
            if itype in ("checkbox", "radio"):
                if "checked" in attr:
                    self.fields[name] = attr.get("value") or "on"
            else:
                self.fields[name] = attr.get("value") or ""
        elif tag == "select" and name:
            self._select_name = name
            self._select_selected = None
            self._select_first = None
        elif tag == "option":
            value = attr.get("value") or ""
            if self._select_name:
                if self._select_first is None:
                    self._select_first = value
                if "selected" in attr:
                    self._select_selected = value
        elif tag == "textarea" and name:
            self._textarea_name = name
            self._textarea_buf = []

    def handle_endtag(self, tag):
        if tag == "select" and self._select_name:
            value = self._select_selected
            if value is None:
                value = self._select_first if self._select_first is not None else ""
            self.fields[self._select_name] = value
            self._select_name = None
        elif tag == "textarea" and self._textarea_name:
            self.fields[self._textarea_name] = unescape(
                "".join(self._textarea_buf)
            ).strip()
            self._textarea_name = None

    def handle_data(self, data):
        if self._textarea_name is not None:
            self._textarea_buf.append(data)


def parse_form_fields(fragment: str) -> Dict[str, str]:
    """解析 HTML 片段中的表单字段当前值（无表单结构要求，全局收集）。"""
    parser = _FormParser()
    try:
        parser.feed(fragment or "")
        parser.close()
    except Exception:
        pass
    return parser.fields


def parse_select_options(fragment: str, select_name: str) -> List[Tuple[str, str]]:
    """解析指定 name 的 <select> 的全部选项，返回 [(value, label)]。"""
    results: List[Tuple[str, str]] = []
    pattern = re.compile(
        r"<select\b[^>]*name=[\"']" + re.escape(select_name) + r"[\"'][^>]*>(.*?)</select>",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(fragment or "")
    if not m:
        return results
    for opt_attrs, opt_inner in re.findall(
        r"<option\b([^>]*)>(.*?)</option>", m.group(1), re.DOTALL | re.IGNORECASE
    ):
        value_m = re.search(r'value="([^"]*)"', opt_attrs)
        results.append((value_m.group(1) if value_m else "", strip_tags(opt_inner)))
    return results


_APPLICATION_H3_SPLIT_RE = re.compile(r"<h3\b", re.IGNORECASE)
_TD_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)


def parse_applications_html(body: str) -> List[Dict[str, Any]]:
    """解析加入申请列表 HTML：每个 h3（申请人）配其后的 table（申请留言）。"""
    applications: List[Dict[str, Any]] = []
    for chunk in _APPLICATION_H3_SPLIT_RE.split(body or "")[1:]:
        user = parse_printuser(chunk)
        if not user:
            continue
        tds = _TD_RE.findall(chunk)
        text = strip_tags(tds[1]) if len(tds) >= 2 else ""
        entry = dict(user)
        entry["text"] = text
        applications.append(entry)
    return applications


# ===================================================================== #
# 客户端
# ===================================================================== #
class WikidotClient:
    """基于 aiohttp 的 Wikidot 前端 JS 接口客户端。

    所有请求短生命周期建连（与插件内其他 API 客户端一致）；登录会话由
    WikidotSessionStore 持久化，懒加载、失效自动重登一次。
    """

    def __init__(
        self,
        site: str = "",
        username: str = "",
        password: str = "",
        timeout: int = 20,
        session_store: Optional[WikidotSessionStore] = None,
        retry_attempts: int = 3,
    ) -> None:
        self._site = (site or "").strip()
        self._username = (username or "").strip()
        self._password = password or ""
        self._timeout = aiohttp.ClientTimeout(total=max(5, timeout))
        self._session_store = session_store
        self._retry_attempts = max(1, retry_attempts)
        self._session_id: Optional[str] = None

    # ---------------- 基础属性 ---------------- #
    @property
    def site(self) -> str:
        return self._site

    @property
    def username(self) -> str:
        return self._username

    def configured(self) -> bool:
        """站点与账号密码是否已配置齐全。"""
        return bool(self._site and self._username and self._password)

    def _base_url(self) -> str:
        return f"https://{self._site}.wikidot.com"

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "AstrBot-CurrentCortex-Plugin/1.0 (+wikidot)",
            "Referer": "https://www.wikidot.com/",
            "Accept": "application/json, text/html, */*",
        }

    def _cookies(self) -> Dict[str, str]:
        cookies = {"wikidot_token7": AMC_TOKEN}
        if self._session_id:
            cookies["WIKIDOT_SESSION_ID"] = self._session_id
        return cookies

    # ---------------- 底层 HTTP ---------------- #
    async def _post_form(
        self, url: str, pairs: List[Tuple[str, str]]
    ) -> Tuple[int, str, Dict[str, str]]:
        """POST urlencoded 表单，返回 (status, text, set_cookies)。"""
        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=self._headers()
        ) as session:
            try:
                async with session.post(
                    url, data=pairs, cookies=self._cookies()
                ) as resp:
                    text = await resp.text()
                    set_cookies = {
                        name: morsel.value
                        for name, morsel in resp.cookies.items()
                    }
                    return resp.status, text, set_cookies
            except asyncio.TimeoutError:
                raise WikidotError(
                    "请求 Wikidot 超时，请稍后重试", kind=WikidotError.KIND_TIMEOUT
                ) from None
            except aiohttp.ClientError as e:
                raise WikidotError(
                    f"网络请求失败: {e}", kind=WikidotError.KIND_NETWORK
                ) from e

    async def _get_text(self, url: str) -> Tuple[int, str]:
        """GET 页面，返回 (status, html)。"""
        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=self._headers()
        ) as session:
            try:
                async with session.get(url, cookies=self._cookies()) as resp:
                    return resp.status, await resp.text()
            except asyncio.TimeoutError:
                raise WikidotError(
                    "请求 Wikidot 超时，请稍后重试", kind=WikidotError.KIND_TIMEOUT
                ) from None
            except aiohttp.ClientError as e:
                raise WikidotError(
                    f"网络请求失败: {e}", kind=WikidotError.KIND_NETWORK
                ) from e

    # ---------------- 登录 / 会话 ---------------- #
    async def login(self, force: bool = False) -> str:
        """登录 Wikidot 并持久化会话。

        已有未失效会话且未 force 时直接复用。成功返回 WIKIDOT_SESSION_ID。
        """
        if not force and self._session_id:
            return self._session_id
        if self._session_store is not None and not force:
            saved = self._session_store.get()
            if saved:
                self._session_id = saved
                return saved
        if not (self._username and self._password):
            raise WikidotError(
                "未配置 Wikidot 账号或密码（wikidot_username / wikidot_password）",
                kind=WikidotError.KIND_AUTH,
            )
        status, text, set_cookies = await self._post_form(
            LOGIN_URL,
            [
                ("login", self._username),
                ("password", self._password),
                ("action", "Login2Action"),
                ("event", "login"),
            ],
        )
        if status != 200:
            raise WikidotError(
                f"登录失败（HTTP {status}）", kind=WikidotError.KIND_AUTH,
                status_code=status,
            )
        if "The login and password do not match" in text:
            raise WikidotError(
                "登录失败：账号或密码错误", kind=WikidotError.KIND_AUTH
            )
        session_id = set_cookies.get("WIKIDOT_SESSION_ID")
        if not session_id:
            raise WikidotError(
                "登录失败：服务端未返回会话（账号可能被风控或需要验证码）",
                kind=WikidotError.KIND_AUTH,
            )
        self._session_id = session_id
        if self._session_store is not None:
            self._session_store.set(session_id, self._username)
        logger.info(f"[Wikidot] 已登录 {self._username}@{self._site}")
        return session_id

    async def logout(self) -> None:
        """登出（尽力而为，失败不抛）。"""
        try:
            if self._session_id:
                await self.amc_request(
                    {
                        "action": "Login2Action",
                        "event": "logout",
                        "moduleName": "Empty",
                    }
                )
        except Exception:
            pass
        self._session_id = None
        if self._session_store is not None:
            self._session_store.clear()

    async def _ensure_logged_in(self) -> None:
        if not self._session_id:
            await self.login()

    # ---------------- AMC 核心 ---------------- #
    async def amc_request(
        self, body: Dict[str, Any], require_body: bool = False,
        _auth_retry: bool = True,
    ) -> Dict[str, Any]:
        """调用 ajax-module-connector.php，返回 status=ok 的响应 dict。

        - try_again 按 time_to_wait / 指数退避重试（上限 retry_attempts）；
        - 会话失效（body 含登录钩子）时清会话重登一次再重试；
        - require_body=True 时校验响应含 body 字段（防 moduleName 拼错）。
        """
        await self._ensure_logged_in()
        pairs = encode_amc_form(body)
        attempts = 0
        while True:
            attempts += 1
            status, text, _ = await self._post_form(self._base_url() + "/ajax-module-connector.php", pairs)
            if status != 200:
                # 与 wikidot.py 一致：500 + 空响应体 + 带 action 的请求
                # 视为不支持的 action/event，立即失败
                if status == 500 and not text.strip() and "action" in body:
                    raise WikidotError(
                        f"Wikidot 拒绝了该操作（HTTP 500，action 可能不支持）",
                        kind=WikidotError.KIND_API, status_code=500,
                    )
                raise WikidotError(
                    f"Wikidot 接口返回 HTTP {status}",
                    kind=WikidotError.KIND_API, status_code=status,
                )
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                if attempts >= self._retry_attempts:
                    raise WikidotError(
                        "Wikidot 接口返回了无法解析的内容",
                        kind=WikidotError.KIND_API,
                    ) from None
                await asyncio.sleep(min(2 ** (attempts - 1), 5))
                continue

            resp_status = data.get("status")
            if resp_status == "ok":
                body_html = data.get("body")
                if isinstance(body_html, str) and "loginClick(event)" in body_html:
                    # 会话已失效：清掉重登一次再重试
                    if _auth_retry:
                        self._session_id = None
                        if self._session_store is not None:
                            self._session_store.clear()
                        await self.login(force=True)
                        return await self.amc_request(
                            body, require_body=require_body, _auth_retry=False
                        )
                    raise WikidotError(
                        "Wikidot 会话已失效且重新登录后仍无权限",
                        kind=WikidotError.KIND_AUTH,
                    )
                if require_body and "body" not in data:
                    raise WikidotError(
                        f"Wikidot 模块未返回内容（moduleName={body.get('moduleName')}）",
                        kind=WikidotError.KIND_API,
                    )
                return data
            if resp_status == "try_again":
                if attempts >= self._retry_attempts:
                    raise WikidotError(
                        "Wikidot 限流（try_again），请稍后重试",
                        kind=WikidotError.KIND_RATE_LIMITED,
                    )
                wait = data.get("time_to_wait")
                delay = float(wait) if isinstance(wait, (int, float)) and wait > 0 \
                    else min(2 ** (attempts - 1), 10)
                await asyncio.sleep(min(delay, 30))
                continue
            if resp_status == "no_permission":
                raise WikidotError(
                    "没有权限执行该操作（需要该站点的管理员权限）",
                    kind=WikidotError.KIND_PERMISSION,
                    status_code=resp_status,
                )
            if resp_status in ("form_errors", "form_error"):
                errors = data.get("formErrors") or data.get("errors") or {}
                message = data.get("message") or ""
                if isinstance(errors, dict):
                    detail = "；".join(f"{k}: {v}" for k, v in errors.items())
                else:
                    detail = str(errors)
                raise WikidotError(
                    f"表单校验失败: {detail or message or resp_status}",
                    kind=WikidotError.KIND_FORM, status_code=resp_status,
                    errors=errors if isinstance(errors, dict) else {},
                )
            raise WikidotError(
                f"Wikidot 返回错误状态: {resp_status}",
                kind=WikidotError.KIND_API, status_code=resp_status,
            )

    # ---------------- 页面 ---------------- #
    async def fetch_page_html(self, fullname: str) -> Optional[str]:
        """GET 页面 HTML；404（页面不存在）返回 None。"""
        status, text = await self._get_text(
            f"{self._base_url()}/{fullname.strip('/')}"
        )
        if status == 404:
            return None
        if status != 200:
            raise WikidotError(
                f"获取页面失败（HTTP {status}）",
                kind=WikidotError.KIND_API, status_code=status,
            )
        return text

    async def get_page_id(self, fullname: str) -> Optional[int]:
        """解析页面 pageId；页面不存在返回 None。"""
        html_text = await self.fetch_page_html(fullname)
        if html_text is None:
            return None
        return extract_page_id(html_text)

    async def get_page_info(self, fullname: str) -> Dict[str, Any]:
        """获取页面概要（page_id、标题、标签、是否存在）。"""
        html_text = await self.fetch_page_html(fullname)
        if html_text is None:
            return {"exists": False, "fullname": fullname}
        title_m = re.search(
            r'<div[^>]*id="page-title"[^>]*>(.*?)</div>', html_text, re.DOTALL
        )
        tags = re.findall(
            r'href="/system:page-tags/tag/([^"/]+)#pages"', html_text
        )
        return {
            "exists": True,
            "fullname": fullname,
            "page_id": extract_page_id(html_text),
            "title": strip_tags(title_m.group(1)) if title_m else "",
            "tags": tags,
        }

    async def get_source(self, fullname: str) -> str:
        """获取页面 wikitext 源码；页面不存在抛 no_page。"""
        page_id = await self.get_page_id(fullname)
        if page_id is None:
            raise WikidotError(
                f"页面 {fullname} 不存在", kind=WikidotError.KIND_NO_PAGE
            )
        data = await self.amc_request(
            {"moduleName": MODULE_VIEW_SOURCE, "page_id": page_id},
            require_body=True,
        )
        return extract_page_source(data.get("body") or "")

    async def save_page(
        self,
        fullname: str,
        source: str,
        title: Optional[str] = None,
        comment: str = "",
        force: bool = False,
        tags: Optional[List[str]] = None,
        parent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """保存页面（新建或覆盖），走完整的「锁 -> savePage -> 释放锁」流程。

        title 为 None 且页面已存在时，先读取当前标题回填，避免清空标题；
        tags / parent 仅对新建页面有效（Wikidot 编辑表单语义）。
        """
        page_id: Optional[int] = None
        if title is None:
            info = await self.get_page_info(fullname)
            if info.get("exists"):
                page_id = info.get("page_id")
                title = info.get("title") or ""
            else:
                title = ""

        lock_body: Dict[str, Any] = {
            "moduleName": MODULE_PAGE_EDIT,
            "mode": "page",
            "wiki_page": fullname,
        }
        if page_id:
            lock_body["page_id"] = page_id
        if force:
            lock_body["force_lock"] = "yes"
        # 锁模块的 lock_id/lock_secret 在响应顶层而非 body 字段
        lock = await self.amc_request(lock_body)
        if lock.get("locked") or lock.get("other_locks"):
            raise WikidotError(
                f"页面 {fullname} 正在被他人编辑，稍后再试或使用强制覆盖",
                kind=WikidotError.KIND_LOCKED,
            )
        lock_id = lock.get("lock_id")
        lock_secret = lock.get("lock_secret")
        revision_id = str(lock.get("page_revision_id") or "")
        try:
            body: Dict[str, Any] = {
                "action": "WikiPageAction",
                "event": "savePage",
                "moduleName": "Empty",
                "mode": "page",
                "wiki_page": fullname,
                "lock_id": lock_id,
                "lock_secret": lock_secret,
                "revision_id": revision_id,
                "title": title or "",
                "source": source,
                "comments": comment,
            }
            if page_id:
                body["page_id"] = page_id
            if tags:
                body["tags"] = " ".join(tags)
            if parent:
                body["parentPage"] = parent
            data = await self.amc_request(body)
            if data.get("noLockError"):
                raise WikidotError(
                    "保存时编辑锁已失效，请重试",
                    kind=WikidotError.KIND_LOCKED,
                )
            return data
        finally:
            try:
                await self.amc_request({
                    "action": "WikiPageAction",
                    "event": "removePageEditLock",
                    "moduleName": "Empty",
                    "wiki_page": fullname,
                    "lock_id": lock_id,
                    "lock_secret": lock_secret,
                    **({"page_id": page_id} if page_id else {}),
                })
            except Exception:
                logger.debug(f"[Wikidot] 释放 {fullname} 编辑锁失败（忽略）")

    async def append_page(self, fullname: str, text: str, comment: str = "") -> str:
        """把 text 追加到页面末尾；页面不存在则等价于新建。"""
        page_id = await self.get_page_id(fullname)
        if page_id is None:
            await self.save_page(fullname, text, comment=comment or "append")
            return text
        current = await self.get_source(fullname)
        new_source = (current + "\n\n" + text).strip("\n") if current else text
        await self.save_page(fullname, new_source, comment=comment or "append")
        return new_source

    async def delete_page(self, fullname: str) -> None:
        page_id = await self.get_page_id(fullname)
        if page_id is None:
            raise WikidotError(
                f"页面 {fullname} 不存在", kind=WikidotError.KIND_NO_PAGE
            )
        await self.amc_request({
            "action": "WikiPageAction",
            "event": "deletePage",
            "moduleName": "Empty",
            "page_id": page_id,
        })

    async def rename_page(self, old: str, new: str, force: bool = False) -> None:
        page_id = await self.get_page_id(old)
        if page_id is None:
            raise WikidotError(
                f"页面 {old} 不存在", kind=WikidotError.KIND_NO_PAGE
            )
        body: Dict[str, Any] = {
            "action": "WikiPageAction",
            "event": "renamePage",
            "moduleName": "Empty",
            "page_id": page_id,
            "new_name": new,
        }
        if force:
            body["force"] = "yes"
        data = await self.amc_request(body)
        if data.get("locks"):
            raise WikidotError(
                "目标名称被占用或页面正被编辑", kind=WikidotError.KIND_LOCKED
            )
        if data.get("leftDeps"):
            raise WikidotError(
                "仍有其他页面链接到该页（回链依赖未解决）",
                kind=WikidotError.KIND_FORM,
            )

    async def set_parent(self, fullname: str, parent: Optional[str]) -> None:
        page_id = await self.get_page_id(fullname)
        if page_id is None:
            raise WikidotError(
                f"页面 {fullname} 不存在", kind=WikidotError.KIND_NO_PAGE
            )
        await self.amc_request({
            "action": "WikiPageAction",
            "event": "setParentPage",
            "moduleName": "Empty",
            "pageId": str(page_id),
            "parentName": parent or "",
        })

    async def save_tags(self, fullname: str, tags: List[str]) -> None:
        page_id = await self.get_page_id(fullname)
        if page_id is None:
            raise WikidotError(
                f"页面 {fullname} 不存在", kind=WikidotError.KIND_NO_PAGE
            )
        await self.amc_request({
            "action": "WikiPageAction",
            "event": "saveTags",
            "moduleName": "Empty",
            "pageId": str(page_id),
            "tags": " ".join(t.strip() for t in tags if t.strip()),
        })

    # ---------------- 用户与成员 ---------------- #
    async def resolve_user(self, username: str) -> Optional[Tuple[int, str]]:
        """用户名 -> (user_id, 显示名)；用户不存在返回 None。"""
        status, text = await self._get_text(
            USER_INFO_URL.format(unix_name=to_unix_name(username))
        )
        if status == 404:
            return None
        if status != 200:
            raise WikidotError(
                f"查询用户信息失败（HTTP {status}）",
                kind=WikidotError.KIND_API, status_code=status,
            )
        return parse_user_info(text)

    async def list_members(
        self, group: str = "", page: int = 1
    ) -> Tuple[List[Dict[str, Any]], int]:
        """获取成员列表（group: "" 全部 / "admins" / "moderators"）。

        返回 (本页成员, 末页页码)。
        """
        if group not in ("", "admins", "moderators"):
            raise ValueError("group 仅允许空串 / admins / moderators")
        data = await self.amc_request(
            {"moduleName": MODULE_MEMBERS_LIST, "page": page, "group": group},
            require_body=True,
        )
        return parse_members_html(data.get("body") or ""), parse_last_page(
            data.get("body") or ""
        )

    async def list_all_members(self, group: str = "") -> List[Dict[str, Any]]:
        """获取全部成员（自动翻页）。"""
        members, last_page = await self.list_members(group=group, page=1)
        for p in range(2, last_page + 1):
            more, _ = await self.list_members(group=group, page=p)
            members.extend(more)
        return members

    async def remove_member(self, user_id: int, ban: bool = False) -> None:
        body: Dict[str, Any] = {
            "action": "ManageSiteMembershipAction",
            "event": "removeMember",
            "moduleName": "Empty",
            "user_id": user_id,
        }
        if ban:
            body["ban"] = "yes"
        await self.amc_request(body)

    async def block_user(self, user_id: int, reason: str = "") -> None:
        await self.amc_request({
            "action": "ManageSiteBlockAction",
            "event": "blockUser",
            "moduleName": "Empty",
            "userId": user_id,
            "reason": (reason or "")[:200],
        })

    async def unblock_user(self, user_id: int) -> None:
        await self.amc_request({
            "action": "ManageSiteBlockAction",
            "event": "deleteBlock",
            "moduleName": "Empty",
            "userId": user_id,
        })

    # ---------------- 站点设置 ---------------- #
    _GENERAL_FIELDS = (
        "name", "subtitle", "language", "description",
        "default_page", "welcome_page",
    )

    async def get_general_settings(self) -> Dict[str, str]:
        data = await self.amc_request(
            {"moduleName": MODULE_GENERAL_SETTINGS}, require_body=True
        )
        fields = parse_form_fields(data.get("body") or "")
        return {
            key: fields.get(key, "")
            for key in self._GENERAL_FIELDS
        }

    async def save_general_settings(self, updates: Dict[str, str]) -> Dict[str, str]:
        """合并式保存常规设置（未提供的字段保留现值）。"""
        current = await self.get_general_settings()
        merged = {**current, **{k: str(v) for k, v in updates.items()}}
        merged.setdefault("language", "en")
        await self.amc_request({
            "action": "ManageSiteAction",
            "event": "saveGeneral",
            "moduleName": "Empty",
            **merged,
        })
        return merged

    async def get_access_policy(self) -> Dict[str, Any]:
        data = await self.amc_request(
            {"moduleName": MODULE_ACCESS_POLICY}, require_body=True
        )
        fields = parse_form_fields(data.get("body") or "")
        return {
            "privacy": fields.get("privacy", "open"),
            "by_apply": fields.get("by_apply") is not None,
            "by_domain": fields.get("by_domain") is not None,
            "by_password": fields.get("by_password") is not None,
            "password": fields.get("password", ""),
            "landingPage": fields.get("landingPage", ""),
            "allowHotlink": fields.get("allowHotlink") is not None,
            "hideNav": fields.get("hideNav") is not None,
        }

    async def save_access_policy(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """合并式保存访问策略（未提供的键保留现值）。"""
        if "privacy" in updates and updates["privacy"] not in (
            "open", "closed", "private"
        ):
            raise ValueError("privacy 仅允许 open / closed / private")
        current = await self.get_access_policy()
        merged = {**current, **updates}
        privacy = merged.get("privacy") or "open"
        if privacy not in ("open", "closed", "private"):
            raise ValueError("privacy 仅允许 open / closed / private")
        await self.amc_request({
            "action": "ManageSiteAction",
            "event": "savePrivateSettings",
            "moduleName": "Empty",
            "privacy": privacy,
            "by_domain": amc_checkbox(merged.get("by_domain")),
            "password": merged.get("password") or "",
            "landingPage": merged.get("landingPage") or "",
            "by_apply": amc_checkbox(merged.get("by_apply")),
            "by_password": amc_checkbox(merged.get("by_password")),
            "allowHotlink": amc_checkbox(merged.get("allowHotlink")),
            "hideNav": amc_checkbox(merged.get("hideNav")),
        })
        return merged

    async def get_navigation(self) -> Dict[str, str]:
        data = await self.amc_request(
            {"moduleName": MODULE_NAVIGATION}, require_body=True
        )
        return parse_form_fields(data.get("body") or "")

    async def save_navigation(
        self, top: Optional[str] = None, side: Optional[str] = None,
        use_default: bool = False,
    ) -> None:
        """保存导航元素；use_default=True 恢复站点默认导航。"""
        body: Dict[str, Any] = {
            "action": "ManageSiteAction",
            "event": "saveNavigation",
            "moduleName": "Empty",
        }
        if use_default:
            body["nav_default"] = amc_flag(True)
        else:
            body["top_bar_page_name"] = top or ""
            body["side_bar_page_name"] = side or ""
        await self.amc_request(body)

    async def get_license(self) -> Dict[str, Any]:
        data = await self.amc_request(
            {"moduleName": MODULE_LICENSE}, require_body=True
        )
        fields = parse_form_fields(data.get("body") or "")
        options = parse_select_options(data.get("body") or "", "license_id")
        return {
            "license_id": fields.get("license_id", ""),
            "license_other": fields.get("license_other", ""),
            "options": options,
        }

    async def set_license(
        self, license_id: Optional[str] = None, other: Optional[str] = None,
        use_default: bool = False,
    ) -> None:
        body: Dict[str, Any] = {
            "action": "ManageSiteAction",
            "event": "saveLicense",
            "moduleName": "Empty",
        }
        if use_default:
            body["license_default"] = amc_flag(True)
        else:
            if license_id and license_id.upper() == "OTHER" and not other:
                raise ValueError("使用自定义许可证时必须提供 other 内容")
            body["license_id"] = license_id or ""
            body["license_other"] = other or ""
        await self.amc_request(body)

    async def get_templates(self) -> Dict[str, Any]:
        data = await self.amc_request(
            {"moduleName": MODULE_TEMPLATES}, require_body=True
        )
        fields = parse_form_fields(data.get("body") or "")
        options = parse_select_options(data.get("body") or "", "template_id")
        return {
            "template_id": fields.get("template_id", ""),
            "options": options,
        }

    async def set_template(self, template_id: Optional[str]) -> None:
        body: Dict[str, Any] = {
            "action": "ManageSiteAction",
            "event": "saveTemplates",
            "moduleName": "Empty",
            "template_id": template_id or "",
        }
        await self.amc_request(body)

    async def get_appearance(self) -> Dict[str, Any]:
        data = await self.amc_request(
            {"moduleName": MODULE_APPEARANCE}, require_body=True
        )
        return parse_form_fields(data.get("body") or "")

    async def set_appearance(
        self, theme_id: Optional[str] = None, use_default: bool = False
    ) -> None:
        body: Dict[str, Any] = {
            "action": "ManageSiteThemeAction",
            "event": "saveAppearance",
            "moduleName": "Empty",
        }
        if use_default:
            body["theme_default"] = amc_flag(True)
        else:
            if not theme_id:
                raise ValueError("必须提供主题 ID 或使用默认主题")
            body["theme_id"] = theme_id
            body["theme_external_url"] = ""
        await self.amc_request(body)

    # ---------------- 论坛 ---------------- #
    async def get_forum_layout(self) -> Dict[str, Any]:
        """获取论坛版块结构：{groups: [...], default_nesting}。

        groups[i] 含 name/description/visible/group_id 与其 categories。
        """
        # groups/categories 在响应顶层（非 body 字段）
        data = await self.amc_request({"moduleName": MODULE_FORUM_LAYOUT})
        groups_raw = data.get("groups") or []
        cats_raw = data.get("categories") or []
        groups: List[Dict[str, Any]] = []
        for i, g in enumerate(groups_raw):
            if not isinstance(g, dict):
                continue
            group = {
                "name": g.get("name", ""),
                "description": g.get("description", ""),
                "visible": bool(g.get("visible", True)),
                "group_id": g.get("group_id"),
                "categories": [],
            }
            for raw_key in g:
                if raw_key not in group:
                    group[raw_key] = g[raw_key]
            cats = cats_raw[i] if i < len(cats_raw) and isinstance(
                cats_raw[i], list
            ) else []
            for c in cats:
                if isinstance(c, dict):
                    category = {
                        "name": c.get("name", ""),
                        "description": c.get("description", ""),
                        "max_nest_level": c.get("max_nest_level"),
                        "category_id": c.get("category_id"),
                    }
                    for raw_key in c:
                        if raw_key not in category:
                            category[raw_key] = c[raw_key]
                    group["categories"].append(category)
            groups.append(group)
        return {
            "groups": groups,
            "default_nesting": data.get("defaultNesting"),
        }

    @staticmethod
    def _forum_group_dict(group: Dict[str, Any]) -> Dict[str, Any]:
        """把 group 收敛为 saveForumLayout 需要的字典（未知字段透传）。"""
        result = dict(group)
        result["visible"] = bool(group.get("visible", True))
        if group.get("group_id"):
            result["group_id"] = group["group_id"]
        else:
            result.pop("group_id", None)
        result["categories"] = [
            WikidotClient._forum_category_dict(c)
            for c in group.get("categories", [])
        ]
        return result

    @staticmethod
    def _forum_category_dict(category: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(category)
        if category.get("category_id"):
            result["category_id"] = category["category_id"]
        else:
            result.pop("category_id", None)
        result.pop("number_threads", None)
        return result

    async def save_forum_layout(
        self,
        groups: List[Dict[str, Any]],
        deleted_group_ids: Optional[List[Any]] = None,
        deleted_category_ids: Optional[List[Any]] = None,
    ) -> None:
        """保存论坛版块结构（全量提交；删除项的 ID 一并给出）。

        groups / categories / deleted_* 需整体 JSON 编码为单个字符串
        （wikidot.py 的 json_param 语义），而非 jQuery 数组展开。
        """
        await self.amc_request({
            "action": "ManageSiteForumAction",
            "event": "saveForumLayout",
            "moduleName": "Empty",
            "groups": json.dumps(
                [self._forum_group_dict(g) for g in groups], ensure_ascii=False
            ),
            "categories": json.dumps(
                [
                    [self._forum_category_dict(c) for c in g.get("categories", [])]
                    for g in groups
                ],
                ensure_ascii=False,
            ),
            "deleted_groups": json.dumps(deleted_group_ids or []),
            "deleted_categories": json.dumps(deleted_category_ids or []),
        })

    async def activate_forum(self) -> None:
        await self.amc_request({
            "action": "ManageSiteForumAction",
            "event": "activateForum",
            "moduleName": "Empty",
        })

    async def set_forum_nesting(self, level: int) -> None:
        if not 0 <= int(level) <= 10:
            raise ValueError("嵌套深度必须在 0-10 之间")
        await self.amc_request({
            "action": "ManageSiteForumAction",
            "event": "saveForumDefaultNesting",
            "moduleName": "Empty",
            "max_nest_level": int(level),
        })

    # ---------------- 邀请与申请 ---------------- #
    async def invite_user(self, user_id: int, text: str = "") -> None:
        """邀请用户加入站点。已邀请/已是成员会抛出可读错误。"""
        try:
            await self.amc_request({
                "action": "ManageSiteMembershipAction",
                "event": "inviteMember",
                "moduleName": "Empty",
                "user_id": user_id,
                "text": text,
            })
        except WikidotError as e:
            if e.status_code == "already_invited":
                raise WikidotError(
                    "该用户已被邀请过", kind=WikidotError.KIND_FORM,
                    status_code=e.status_code,
                ) from e
            if e.status_code == "already_member":
                raise WikidotError(
                    "该用户已是站点成员", kind=WikidotError.KIND_FORM,
                    status_code=e.status_code,
                ) from e
            raise

    async def send_email_invitation(
        self, address: str, message: str = "", name: str = ""
    ) -> None:
        """发送单地址邮件邀请。"""
        addresses = [[address, name or address, False]]
        await self.amc_request({
            "action": "ManageSiteMembershipAction",
            "event": "sendEmailInvitations",
            "moduleName": "Empty",
            "addresses": json.dumps(addresses, ensure_ascii=False),
            "message": message,
        })

    async def set_let_users_invite(self, enabled: bool) -> None:
        await self.amc_request({
            "action": "ManageSiteMembershipAction",
            "event": "letUsersInviteSave",
            "moduleName": "Empty",
            "enableLetUsersInvite": "true" if enabled else "false",
        })

    async def list_applications(self) -> List[Dict[str, Any]]:
        data = await self.amc_request(
            {"moduleName": MODULE_APPLICATIONS}, require_body=True
        )
        return parse_applications_html(data.get("body") or "")

    async def process_application(self, user_id: int, accept: bool) -> None:
        """同意 / 拒绝加入申请（按申请人 user_id 定位）。"""
        try:
            await self.amc_request({
                "action": "ManageSiteMembershipAction",
                "event": "acceptApplication",
                "moduleName": "Empty",
                "user_id": user_id,
                "text": (
                    "your application has been accepted"
                    if accept else "your application has been declined"
                ),
                "type": "accept" if accept else "decline",
            })
        except WikidotError as e:
            if e.status_code == "no_application":
                raise WikidotError(
                    "找不到该用户的加入申请（可能已被处理）",
                    kind=WikidotError.KIND_NO_PAGE, status_code=e.status_code,
                ) from e
            raise
