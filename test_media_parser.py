"""媒体解析回归测试（media_parser.py，离线，不碰网络）。

重点覆盖 v2.4.0 修复的 b23.tv 短链 bug：短码（如 KZclOli）曾被
extract_bilibili 误判为 av 号，导致 _av2bv(int("KZclOli")) 抛
ValueError。现在短码标记为 type='short'，由解析器跳转还原成 BV 号。

运行方式：python3 test_media_parser.py
"""

import asyncio
import sys
import types

# --------------------------------------------------------------------------- #
# Mock 掉 AstrBot / aiohttp 依赖，使 media_parser.py 可脱离框架被 import。
# （与 test_memory_and_switch.py 相同的手法）
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

aiohttp_stub = types.ModuleType("aiohttp")
aiohttp_stub.ClientTimeout = lambda **kwargs: None
aiohttp_stub.ClientSession = object


class _ClientError(Exception):
    pass


aiohttp_stub.ClientError = _ClientError
aiohttp_stub.InvalidURL = _ClientError

sys.modules.setdefault("astrbot", astrbot)
sys.modules["astrbot.api"] = astrbot_api
sys.modules["aiohttp"] = aiohttp_stub

from media_parser import (  # noqa: E402
    BilibiliParser,
    DouyinParser,
    LeiZMediaAPI,
    MediaParserError,
    URLExtractor,
)

_LEIZ_BILI_PAYLOAD = {
    "kind": "video",
    "aid": 117,
    "bvid": "BV1pD4U62E85",
    "cid": 414,
    "page": 1,
    "pageCount": 2,
    "title": "标题",
    "partTitle": "P1",
    "cover": "http://i2.hdslb.com/cover.jpg",
    "duration": 20,
    "owner": "UP主",
    "ownerUid": 150,
    "ownerFace": "http://i2.hdslb.com/face.jpg",
    "actualQuality": 80,
    "qualityLabel": "高清 1080P",
    "merged": {
        "url": "/api/bilibili/stream?token=t1",
        "prepareUrl": "/api/bilibili/stream/prepare?token=t1",
        "statusUrl": "/api/bilibili/stream/status?token=t1",
    },
}


def test_leiz_bilibili_mapping_and_paths():
    """LeiZ B站响应映射：票据相对路径绝对化、download_url 带预拉取字段。"""
    api = LeiZMediaAPI("test-key")

    async def fake_get(path, params):
        assert path == "/api/bilibili"
        assert params.get("url") == "https://b23.tv/KZclOli"
        return _LEIZ_BILI_PAYLOAD

    api._get_json = fake_get
    result = asyncio.run(api.parse_bilibili("看这个 https://b23.tv/KZclOli"))
    assert result["bvid"] == "BV1pD4U62E85"
    assert result["owner"]["name"] == "UP主"
    assert result["page_count"] == 2
    assert result["source"] == "leiz"
    du = result["download_url"]
    assert du["url"] == "https://api.bileizhen.top/api/bilibili/stream?token=t1"
    assert du["prepare_url"].endswith("/stream/prepare?token=t1")
    assert du["status_url"].endswith("/stream/status?token=t1")
    assert du["quality"] == 80 and du["quality_label"] == "高清 1080P"


def test_bilibili_parser_prefers_leiz_and_falls_back():
    """配置 Key 后优先走 LeiZ；LeiZ 失败回退官方路径。"""
    parser = BilibiliParser(leiz_api_key="test-key")
    assert parser._leiz.available

    async def fake_leiz(url_or_text):
        return {"bvid": "BV1leiz", "title": "leiz", "download_url": None, "source": "leiz"}

    parser._leiz.parse_bilibili = fake_leiz
    data = asyncio.run(parser.parse("https://b23.tv/KZclOli"))
    assert data["bvid"] == "BV1leiz"

    async def failed_leiz(url_or_text):
        return None

    async def fake_resolve(short_url):
        return "BV1official"

    async def fake_detail(bvid):
        return {"bvid": bvid}

    parser._leiz.parse_bilibili = failed_leiz
    parser._resolve_short_link = fake_resolve
    parser._fetch_video_detail = fake_detail
    data2 = asyncio.run(parser.parse("https://b23.tv/KZclOli"))
    assert data2["bvid"] == "BV1official"


def test_leiz_douyin_mapping_video_and_gallery():
    """LeiZ 抖音响应映射：视频取 nwm_url，图集取 image_urls 且不发视频。"""
    api = LeiZMediaAPI("test-key")
    payload = {
        "content_type": "video",
        "aweme_id": "7123456789012345678",
        "desc": "文案",
        "cover_url": "http://cover.jpg",
        "author_nickname": "作者",
        "nwm_url": "http://nwm.mp4",
        "statistics": {"digg_count": 11, "comment_count": 22, "share_count": 33},
    }

    async def fake_get(path, params):
        return payload

    api._get_json = fake_get
    result = asyncio.run(api.parse_douyin("https://v.douyin.com/abc/"))
    assert result["video_url"] == "http://nwm.mp4"
    assert result["likes"] == "11" and result["shares"] == "33"
    assert result["images"] == []
    assert result["url"].endswith("/video/7123456789012345678")

    payload["content_type"] = "image"
    payload["image_data"] = {"image_urls": ["http://1.jpg", "http://2.jpg"]}
    payload["nwm_url"] = ""
    result2 = asyncio.run(api.parse_douyin("https://v.douyin.com/abc/"))
    assert result2["images"] == ["http://1.jpg", "http://2.jpg"]
    assert result2["video_url"] == ""


def test_leiz_unavailable_without_key():
    assert LeiZMediaAPI("").available is False
    assert LeiZMediaAPI("  ").available is False


def test_leiz_bili_qn_passthrough_and_clamp():
    """目标清晰度透传到请求参数，越界值钳制到 [16, 127]。"""
    api = LeiZMediaAPI("k", bili_qn=120)
    captured = {}

    async def fake_get(path, params):
        captured.update(params)
        return _LEIZ_BILI_PAYLOAD

    api._get_json = fake_get
    asyncio.run(api.parse_bilibili("https://b23.tv/KZclOli"))
    assert captured.get("qn") == "120", captured
    assert LeiZMediaAPI("k", bili_qn=999)._bili_qn == 127
    assert LeiZMediaAPI("k", bili_qn=1)._bili_qn == 16
    assert LeiZMediaAPI("k")._bili_qn == 80  # 默认 1080P


def test_extract_bilibili_classifies_b23_short_code():
    """b23.tv 短码必须标记为 'short'，而不是被误判为 av 号。"""
    assert URLExtractor.extract_bilibili("https://b23.tv/KZclOli") == {
        "type": "short",
        "id": "KZclOli",
    }
    # 分享文案带前缀文字也能提取
    assert URLExtractor.extract_bilibili(
        "【来看看】 https://b23.tv/KZclOli 快点开！"
    ) == {"type": "short", "id": "KZclOli"}


def test_extract_bilibili_bv_and_av_not_regressed():
    assert URLExtractor.extract_bilibili(
        "https://www.bilibili.com/video/BV1pD4U62E85"
    ) == {"type": "bv", "id": "BV1pD4U62E85"}
    assert URLExtractor.extract_bilibili("https://b23.tv/BV1pD4U62E85") == {
        "type": "bv",
        "id": "BV1pD4U62E85",
    }
    assert URLExtractor.extract_bilibili(
        "https://www.bilibili.com/video/av170001"
    ) == {"type": "av", "id": "170001"}


def test_detect_platform_recognizes_b23_link():
    assert URLExtractor.detect_platform("https://b23.tv/KZclOli") == "bilibili"


def test_bilibili_parse_resolves_short_code():
    """短链解析流程：short → 跳转还原 BV → 取详情，全程不应对短码 int()。"""

    class _StubParser(BilibiliParser):
        def __init__(self):
            super().__init__()
            self.resolved = None

        async def _resolve_short_link(self, short_url):
            self.resolved = short_url
            return "BV1pD4U62E85"

        async def _fetch_video_detail(self, bvid):
            return {"bvid": bvid, "title": "stub"}

    parser = _StubParser()
    data = asyncio.run(parser.parse("【分享】 https://b23.tv/KZclOli"))
    assert data == {"bvid": "BV1pD4U62E85", "title": "stub"}, data
    assert "https://b23.tv/KZclOli" in parser.resolved


def test_bilibili_parse_av_link_still_converts():
    """av 号完整链接仍走 _av2bv 转换（av170001 ↔ BV17x411w7KC）。"""

    class _StubParser(BilibiliParser):
        async def _fetch_video_detail(self, bvid):
            return {"bvid": bvid}

    data = asyncio.run(_StubParser().parse("https://www.bilibili.com/video/av170001"))
    assert data["bvid"] == "BV17x411w7KC", data


def test_bilibili_parse_unrecognized_link_raises_format():
    parser = BilibiliParser()
    try:
        asyncio.run(parser.parse("https://example.com/nope"))
    except MediaParserError as e:
        assert e.kind == MediaParserError.KIND_FORMAT
    else:
        raise AssertionError("应当抛出 format 类 MediaParserError")


def test_bilibili_resolve_short_link_rejects_text_without_url():
    """_resolve_short_link 对不含短链的文本应在发请求前抛 format 错误。"""
    parser = BilibiliParser()
    try:
        asyncio.run(parser._resolve_short_link("没有任何链接的文本"))
    except MediaParserError as e:
        assert e.kind == MediaParserError.KIND_FORMAT
    else:
        raise AssertionError("应当抛出 format 类 MediaParserError")


def test_fetch_download_url_uses_durl_with_fnval0():
    """fnval 必须为 0：fnval=16 时 B 站只回 DASH 分离流不填 durl。"""
    parser = BilibiliParser()
    captured = {}

    async def fake_fetch_json(url, headers=None, params=None):
        captured.update(params or {})
        return {
            "code": 0,
            "data": {
                "quality": 64,
                "durl": [{"url": "//upos.example/video.mp4", "size": 12345}],
            },
        }

    parser._fetch_json = fake_fetch_json
    info = asyncio.run(parser._fetch_download_url("BV1xx", 111))
    assert captured.get("fnval") == "0", captured
    # 协议相对直链 //xxx 补全为 https
    assert info == {
        "url": "https://upos.example/video.mp4",
        "size": 12345,
        "segments": 1,
        "quality": 64,
    }, info


def test_fetch_download_url_dash_only_returns_none():
    """只返回 dash（无 durl）时不得抛异常，返回 None 走无直链兜底。"""
    parser = BilibiliParser()

    async def fake_fetch_json(url, headers=None, params=None):
        return {"code": 0, "data": {"quality": 64, "dash": {"video": [], "audio": []}}}

    parser._fetch_json = fake_fetch_json
    assert asyncio.run(parser._fetch_download_url("BV1xx", 111)) is None


TESTS = [
    test_extract_bilibili_classifies_b23_short_code,
    test_extract_bilibili_bv_and_av_not_regressed,
    test_detect_platform_recognizes_b23_link,
    test_bilibili_parse_resolves_short_code,
    test_bilibili_parse_av_link_still_converts,
    test_bilibili_parse_unrecognized_link_raises_format,
    test_bilibili_resolve_short_link_rejects_text_without_url,
    test_fetch_download_url_uses_durl_with_fnval0,
    test_fetch_download_url_dash_only_returns_none,
    test_leiz_bilibili_mapping_and_paths,
    test_bilibili_parser_prefers_leiz_and_falls_back,
    test_leiz_douyin_mapping_video_and_gallery,
    test_leiz_unavailable_without_key,
    test_leiz_bili_qn_passthrough_and_clamp,
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
    print(f"\n{passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main_test() else 1)
