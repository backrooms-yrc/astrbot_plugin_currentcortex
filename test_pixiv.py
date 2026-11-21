"""Offline Pixiv source regressions: uv run --with aiohttp python test_pixiv.py."""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientSession, web

# Reuse the existing AstrBot stubs; no plugin lifecycle or external services run.
from test_music_audio import main

PixivWebAPIClient = main.PixivWebAPIClient
PixivAPIError = main.PixivAPIError
PixivUsageError = main.PixivUsageError


def work(pid="123", **extra):
    return {
        "id": pid,
        "title": "星空",
        "userName": "画师",
        "userId": "42",
        "xRestrict": 0,
        "aiType": 1,
        "illustType": 0,
        "width": 1600,
        "height": 900,
        "createDate": "2026-01-01T12:00:00+09:00",
        "tags": {
            "tags": [
                {"tag": "風景", "translation": {"en": "landscape"}},
                {"tag": "星空"},
            ]
        },
        "urls": {
            "regular": "https://i.pximg.net/regular.jpg",
            "original": "https://i.pximg.net/original.png",
            "small": "https://i.pximg.net/small.jpg",
        },
        **extra,
    }


class PixivTests(unittest.IsolatedAsyncioTestCase):
    def test_space_separated_parameters(self):
        self.assertEqual(
            main.CommandParser.parse("r18 tag 星空 num 2"),
            {"r18": 1, "tag": ["星空"], "num": 2},
        )
        self.assertEqual(
            main.CommandParser.parse(
                "搜索 风景 星空 数量 3 尺寸 原图 分级 全年龄 排除AI 是 比例 gt1.2 "
                "起始时间 1700000000000 结束时间 1800000000000"
            ),
            main.CommandParser.parse(
                "keyword:风景 num:3 size:original r18:0 excludeAI:true ratio:gt1.2 "
                "date_after:1700000000000 date_before:1800000000000"
            )
            | {"keyword": "风景 星空"},
        )
        self.assertEqual(
            main.CommandParser.parse("搜索 风景 排除AI 数量 3"),
            {"keyword": "风景", "excludeAI": True, "num": 3},
        )
        self.assertEqual(
            main.CommandParser.parse("搜索 风景 excludeAI false num 2"),
            {"keyword": "风景", "excludeAI": False, "num": 2},
        )

    def test_chinese_parameters_match_english(self):
        english = main.CommandParser.parse(
            "tag:風景 tag:星空|夜空 keyword:天空 uid:42 num:3 size:original "
            "r18:0 excludeAI:true ratio:gt1.2 date_after:1700000000000 date_before:1800000000000"
        )
        chinese = main.CommandParser.parse(
            "标签：風景 标签=星空|夜空 关键词:天空 作者ID:42 数量：3 尺寸=原图 "
            "分级:全年龄 排除AI:是 长宽比:gt1.2 起始时间:1700000000000 结束时间:1800000000000"
        )
        self.assertEqual(chinese, english)
        self.assertEqual(
            main.CommandParser.parse("风景 星空 数量:2 排除AI"),
            {"keyword": "风景 星空", "num": 2, "excludeAI": True},
        )
        for value, size in main.CommandParser.SIZE_ALIASES.items():
            self.assertEqual(main.CommandParser.parse(f"尺寸:{value}")["size"], size)
        for value, level in main.CommandParser.LEVEL_ALIASES.items():
            self.assertEqual(main.CommandParser.parse(f"分级:{value}")["r18"], level)

    def test_command_aliases_help_and_group_switch(self):
        plugin = main.CurrentCortexPlugin.__new__(main.CurrentCortexPlugin)
        plugin._default_r18, plugin._default_num = 0, 1
        plugin._default_size, plugin._exclude_ai = "regular", True
        expected = plugin._build_request_params(
            "/pixiv keyword:風景 num:2 excludeAI:false"
        )
        for command in ("pixiv", *main.PIXIV_COMMAND_ALIASES):
            self.assertEqual(
                plugin._build_request_params(f"/{command} 風景 数量:2 排除AI:否"),
                expected,
            )
            self.assertTrue(plugin._is_help_command(f"/{command} 帮助"))
            self.assertEqual(plugin._detect_command_scope(f"/{command} 風景"), "image")
        self.assertFalse(plugin._is_help_command("/pixiv 关键词:帮助"))
        for removed in ("插画", "搜图", "随机图"):
            self.assertIsNone(plugin._detect_command_scope(f"/{removed} 風景"))

    def test_chinese_subcommands_match_legacy_parameters(self):
        plugin = main.CurrentCortexPlugin.__new__(main.CurrentCortexPlugin)
        plugin._default_r18, plugin._default_num = 0, 1
        plugin._default_size, plugin._exclude_ai = "regular", False
        cases = (
            ("随机 数量 3", "num:3"),
            ("搜索 风景 星空 数量 3", "keyword:风景 num:3"),
            ("标签 星空 夜空|风景 数量 2", "tag:星空 tag:夜空|风景 num:2"),
            ("标签 星空，夜空 数量 2", "tag:星空 tag:夜空 num:2"),
            ("作者 42 数量 2", "uid:42 num:2"),
        )
        for chinese, legacy in cases:
            expected = plugin._build_request_params(f"/pixiv {legacy}")
            if chinese.startswith("搜索"):
                expected["keyword"] = "风景 星空"
            self.assertEqual(
                plugin._build_request_params(f"/pixiv {chinese}"), expected
            )
        self.assertTrue(plugin._is_help_command("/pixiv 帮助"))

    def test_chinese_subcommands_require_arguments(self):
        for text in ("搜索", "标签", "作者", "作者 abc", "作者 42 43", "随机 风景"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                main.CommandParser.parse(text)

    async def test_chinese_command_searches_and_sends(self):
        plugin = main.CurrentCortexPlugin.__new__(main.CurrentCortexPlugin)
        plugin._api_client = self.client
        plugin._image_proxy = "unused.example"
        plugin._default_r18, plugin._default_num = 0, 1
        plugin._default_size, plugin._exclude_ai = "regular", False
        plugin._maybe_promo_after_image = lambda: None
        plugin._with_promo = lambda x: x
        event = SimpleNamespace(
            message_str="/pixiv 搜索 風景 数量 1 排除AI 是",
            get_sender_name=lambda: "user",
            plain_result=lambda x: ("text", x),
            chain_result=lambda x: ("image", x),
        )
        with (
            patch.object(
                self.client,
                "download_image",
                AsyncMock(return_value="/tmp/test-pixiv.jpg"),
            ),
            patch.object(
                main.Comp,
                "Image",
                SimpleNamespace(fromFileSystem=lambda path: path),
                create=True,
            ),
        ):
            results = [r async for r in plugin.pixiv_command(event)]
        self.assertEqual(results[1], ("image", ["/tmp/test-pixiv.jpg"]))
        self.assertEqual(self.calls[0][1]["word"], "風景")

    async def asyncSetUp(self):
        self.calls = []
        self.self_user = None
        self.pages = {}
        self.works = {
            "123": work(),
            "124": work("124", xRestrict=1),
            "125": work("125", aiType=2),
        }

        async def handler(request):
            self.calls.append(
                (request.path, dict(request.query), dict(request.headers))
            )
            path = request.path
            if "/search/artworks/" in path:
                return web.json_response(
                    {
                        "error": False,
                        "body": {
                            "illustManga": {
                                "data": [{"id": k} for k in self.works],
                                "lastPage": 4,
                            }
                        },
                    }
                )
            if path == "/ajax/user/42/profile/all":
                return web.json_response(
                    {"error": False, "body": {"illusts": {"123": None}, "manga": {}}}
                )
            if path == "/ajax/user/self":
                return web.json_response({"userData": self.self_user})
            if path == "/ranking.php":
                return web.json_response(
                    {"contents": [{"illust_id": k} for k in self.works]}
                )
            if path.startswith("/ajax/illust/") and path.endswith("/pages"):
                pid = path.rsplit("/", 2)[-2]
                return web.json_response(
                    {"error": False, "body": self.pages.get(pid, [])}
                )
            if path.startswith("/ajax/illust/"):
                pid = path.rsplit("/", 1)[-1]
                return web.json_response({"error": False, "body": self.works[pid]})
            if path == "/blocked":
                return web.Response(status=403)
            if path == "/bad-json":
                return web.Response(
                    text="<html>challenge</html>", content_type="text/html"
                )
            if path == "/error":
                return web.json_response({"error": True, "message": "login required"})
            if path == "/redirect":
                return web.Response(
                    status=302, headers={"Location": f"http://localhost:{port}/image"}
                )
            if path == "/image":
                return web.Response(body=b"test-image", content_type="image/png")
            raise web.HTTPNotFound()

        app = web.Application()
        app.router.add_get("/{path:.*}", handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.client = PixivWebAPIClient(timeout=5)
        self.client.BASE = f"http://127.0.0.1:{port}"

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def test_search_no_token_pagination_and_filtering(self):
        result = await self.client.fetch_images(
            keyword="風景", num=20, size="original", excludeAI=True
        )
        self.assertEqual([x["pid"] for x in result["data"]["data"]], ["123"])
        self.assertEqual(
            result["data"]["data"][0]["urls"],
            {"original": "https://i.pximg.net/original.png"},
        )
        searches = [c for c in self.calls if "/search/" in c[0]]
        self.assertIn(len(searches), (2, 3))
        self.assertEqual(searches[0][1]["mode"], "safe")
        self.assertEqual(searches[0][1]["type"], "all")
        self.assertEqual(searches[0][1]["ai_type"], "1")
        for _, _, headers in self.calls:
            self.assertEqual(headers["Referer"], "https://www.pixiv.net/")
            self.assertFalse(
                any(
                    k.lower() in {"cookie", "authorization", "x-api-key"}
                    for k in headers
                )
            )

    async def test_author_uses_live_author_index(self):
        result = await self.client.fetch_images(
            uid="42", keyword="星空", tag=["landscape"], size="small"
        )
        self.assertEqual(result["data"]["data"][0]["author"], "画师")
        self.assertTrue(any("/user/42/profile/all" in c[0] for c in self.calls))
        self.assertFalse(any("/search/" in c[0] for c in self.calls))

    async def test_random_uses_ranking_and_excludes_restricted(self):
        result = await self.client.fetch_images(num=20)
        self.assertEqual({x["pid"] for x in result["data"]["data"]}, {"123", "125"})
        self.assertEqual(self.calls[0][0], "/ranking.php")

    async def test_r18_and_mixed_explicitly_rejected(self):
        for level in (1, 2):
            with self.assertRaisesRegex(PixivAPIError, "leiz"):
                await self.client.fetch_images(r18=level)
        self.assertEqual(self.calls, [])

    async def test_and_or_tags(self):
        result = await self.client.fetch_images(
            tag=["風景|landscape", "星空"], excludeAI=True
        )
        self.assertEqual(len(result["data"]["data"]), 1)
        words = {c[1]["word"] for c in self.calls if "/search/" in c[0]}
        self.assertEqual(words, {"風景 星空", "landscape 星空"})

    async def test_filters_enforced_on_details(self):
        original = work()
        for change in (
            {"xRestrict": 1},
            {"xRestrict": 2},
            {"xRestrict": None},
            {"isMasked": True},
            {"aiType": 2},
            {"aiType": 0},
        ):
            self.assertFalse(
                self.client._matches({**original, **change}, {"excludeAI": True})
            )
        self.assertTrue(
            self.client._matches(
                original,
                {
                    "uid": "42",
                    "aspectRatio": "gt1.7lt1.8",
                    "tag": ["风景|landscape", "星空"],
                },
            )
        )
        for params in (
            {"uid": "43"},
            {"aspectRatio": "lt1"},
            {"tag": ["cat"]},
            {"dateAfter": 1790000000000},
            {"dateBefore": 1700000000000},
        ):
            self.assertFalse(self.client._matches(original, params), params)

    async def test_empty_results_and_invalid_filters(self):
        self.works = {}
        self.assertEqual(
            (await self.client.fetch_images(keyword="nothing"))["data"]["data"], []
        )
        with self.assertRaisesRegex(PixivAPIError, "长宽比"):
            await self.client.fetch_images(aspectRatio="horizontal")
        with self.assertRaisesRegex(PixivAPIError, "UID"):
            await self.client.fetch_images(uid="../42")
        with self.assertRaisesRegex(PixivAPIError, "8"):
            await self.client.fetch_images(tag=["a|b|c", "d|e|f"])

    async def test_http_json_and_business_errors(self):
        import aiohttp

        async with aiohttp.ClientSession() as session:
            for path, code in (("/blocked", 403), ("/bad-json", 0), ("/error", 0)):
                with self.assertRaises(PixivAPIError) as caught:
                    await self.client._get(session, path)
                self.assertEqual(caught.exception.status_code, code)

    async def test_search_shape_changes_are_reported(self):
        with (
            patch.object(self.client, "_get", AsyncMock(return_value={"body": {}})),
            self.assertRaisesRegex(PixivAPIError, "格式"),
        ):
            await self.client.fetch_images(keyword="風景")

    async def test_timeout_is_user_facing(self):
        with (
            patch.object(
                self.client, "_fetch", AsyncMock(side_effect=asyncio.TimeoutError)
            ),
            self.assertRaisesRegex(PixivAPIError, "超时"),
        ):
            await self.client.fetch_images(keyword="風景")

    async def test_source_switch_and_missing_key(self):
        self.assertIsInstance(
            main._select_pixiv_client("pixiv_web", None, 5), PixivWebAPIClient
        )
        leiz = main.PixivAPIClient(api_key="test", timeout=5)
        self.assertIsInstance(
            main._select_pixiv_client("pixiv_web", leiz, 5), PixivWebAPIClient
        )
        self.assertIs(main._select_pixiv_client("leiz", leiz, 5), leiz)
        self.assertIsNone(main._select_pixiv_client("leiz", None, 5))
        limited = main._select_pixiv_client("pixiv_web", None, 5, max_pages=7)
        self.assertEqual(limited.max_pages_per_work, 7)

    async def test_leiz_transport_preserved(self):
        leiz = main.PixivAPIClient(api_key="test")
        with patch.object(main, "API_BASE_URL", self.client.BASE + "/ranking.php"):
            await leiz.fetch_images(num=1)
        self.assertEqual(self.calls[0][2]["x-api-key"], "test")
        # Check POST normalization without changing the existing LeiZ wire format.
        self.assertEqual(
            leiz._normalize_post_params({"tag": "風景", "size": "small"}),
            {"tag": ["風景"], "size": ["small"]},
        )

    async def test_image_download_headers_and_expired_cleanup(self):
        module = __import__(PixivWebAPIClient.__module__, fromlist=["urlsplit"])
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "astrbot_pixiv"
            directory.mkdir()
            expired = directory / "expired.jpg"
            expired.write_bytes(b"old")
            os.utime(expired, (1, 1))
            # Route the validated image host to our local HTTP fixture.
            with (
                patch.object(
                    module,
                    "urlsplit",
                    return_value=SimpleNamespace(
                        scheme="https", hostname="i.pximg.net"
                    ),
                ),
                patch.object(module.tempfile, "gettempdir", return_value=temp),
            ):
                path = await self.client.download_image(self.client.BASE + "/image")
            self.assertEqual(Path(path).read_bytes(), b"test-image")
            self.assertFalse(expired.exists())
            self.assertEqual(self.calls[-1][2]["Referer"], "https://www.pixiv.net/")

    async def test_image_size_limit_and_host_validation(self):
        with self.assertRaisesRegex(PixivAPIError, "地址"):
            await self.client.download_image("http://127.0.0.1/image")
        module = __import__(PixivWebAPIClient.__module__, fromlist=["urlsplit"])
        with tempfile.TemporaryDirectory() as temp:
            with (
                patch.object(
                    module,
                    "urlsplit",
                    return_value=SimpleNamespace(
                        scheme="https", hostname="i.pximg.net"
                    ),
                ),
                patch.object(module.tempfile, "gettempdir", return_value=temp),
                patch.object(self.client, "MAX_IMAGE_BYTES", 2),
                self.assertRaisesRegex(PixivAPIError, "32 MB"),
            ):
                await self.client.download_image(self.client.BASE + "/image")
            self.assertEqual(list((Path(temp) / "astrbot_pixiv").iterdir()), [])

    def _yuri_plugin_and_event(self, message):
        plugin = main.CurrentCortexPlugin.__new__(main.CurrentCortexPlugin)
        plugin._yuri_client = self.client
        plugin._api_client = None  # LeiZ source selected without a key.
        plugin._exclude_ai = True
        event = SimpleNamespace(
            message_str=message,
            plain_result=lambda text: text,
            chain_result=lambda parts: parts,
        )
        return plugin, event

    async def test_yuri_command_sends_only_one_all_age_exact_tag_work(self):
        self.works = {
            "123": work(tags=["百合"]),
            "124": work("124", tags=["百合"], xRestrict=1),
            "125": work("125", tags=["百合"], aiType=2),
            "126": work("126", tags=["非百合"]),
            "127": work("127", tags=["百合"], isMasked=True),
        }
        plugin, event = self._yuri_plugin_and_event("/yuri")
        with (
            patch.object(
                self.client, "download_image", AsyncMock(return_value="/tmp/yuri.jpg")
            ) as download,
            patch.object(main.Comp, "Plain", lambda text: text, create=True),
            patch.object(
                main.Comp, "Image", SimpleNamespace(fromFileSystem=str), create=True
            ),
        ):
            for command in ("/yuri", "/百合"):
                event.message_str = command
                replies = [reply async for reply in plugin.yuri_command(event)]
                self.assertEqual(len(replies), 1)
                caption, path = replies[0]
                self.assertIn("https://www.pixiv.net/artworks/123", caption)
                self.assertEqual(path, "/tmp/yuri.jpg")
            self.assertEqual(download.await_count, 2)
            download.assert_awaited_with("https://i.pximg.net/regular.jpg")

        searches = [query for path, query, _ in self.calls if "/search/" in path]
        self.assertTrue(searches)
        for params in searches:
            self.assertEqual(params["word"], "百合")
            self.assertEqual(params["s_mode"], "s_tag_full")
            self.assertEqual(params["mode"], "safe")
            self.assertEqual(params["ai_type"], "1")
        self.assertTrue(all("Cookie" not in headers for _, _, headers in self.calls))

    async def test_yuri_help_and_group_switch(self):
        plugin, event = self._yuri_plugin_and_event("/yuri help")
        plugin._group_switch_enable = True
        plugin._group_switch_store = SimpleNamespace(
            is_enabled=lambda origin, scope=None: scope != "image"
        )
        plugin._notify_switch_disabled_once = AsyncMock()
        event.get_message_type = lambda: "group"
        event.unified_msg_origin = "platform:GroupMessage:1"
        event.stop_event = Mock()
        with patch.object(main, "MessageType", SimpleNamespace(GROUP_MESSAGE="group")):
            for message in ("/yuri help", "/百合 帮助"):
                event.message_str = message
                replies = [reply async for reply in plugin.yuri_command(event)]
                self.assertIn(main.YURI_HELP_TEXT, replies[0])
                await plugin.on_message_group_switch_guard(event)
                plugin._notify_switch_disabled_once.assert_awaited_with(
                    event, event.unified_msg_origin, "image"
                )
        self.assertEqual(event.stop_event.call_count, 2)
        self.assertEqual(self.calls, [])

    async def test_yuri_distinguishes_empty_search_and_download_errors(self):
        plugin, event = self._yuri_plugin_and_event("/yuri")
        item = {"pid": "123", "urls": {"regular": "https://i.pximg.net/regular.jpg"}}
        plugin._yuri_client = SimpleNamespace(
            fetch_images=AsyncMock(return_value={"data": {"data": []}}),
            download_image=AsyncMock(),
        )
        replies = [reply async for reply in plugin.yuri_command(event)]
        self.assertIn("暂未找到", replies[0])
        plugin._yuri_client.download_image.assert_not_awaited()

        fake_cookie = "test_session=fixture"
        failure = PixivAPIError(fake_cookie, status_code=403)
        with patch.object(main.logger, "warning") as warning:
            plugin._yuri_client.fetch_images.side_effect = failure
            replies = [reply async for reply in plugin.yuri_command(event)]
            self.assertIn("Pixiv 请求失败", replies[0])
            plugin._yuri_client.fetch_images.side_effect = None
            plugin._yuri_client.fetch_images.return_value = {"data": {"data": [item]}}
            plugin._yuri_client.download_image.side_effect = failure
            replies += [reply async for reply in plugin.yuri_command(event)]
            self.assertIn("图片下载失败", replies[1])
        for message in replies:
            self.assertNotIn(fake_cookie, message)
        self.assertEqual(warning.call_count, 2)
        for call in warning.call_args_list:
            self.assertNotIn(fake_cookie, call.args[0])
            self.assertIn("HTTP 403", call.args[0])

    async def test_yuri_server_cookie_is_scoped_to_search_and_details(self):
        fake_cookie = "test_session=fixture"
        authenticated = PixivWebAPIClient(timeout=5, cookie=fake_cookie)
        authenticated.BASE = self.client.BASE
        self.works = {"123": work(tags=["百合"])}
        await authenticated.fetch_images(tag=["百合"], exact_tags=True)
        self.assertTrue(any(path == "/ajax/illust/123" for path, _, _ in self.calls))
        self.assertTrue(
            all(headers.get("Cookie") == fake_cookie for _, _, headers in self.calls)
        )

        self.calls.clear()
        async with ClientSession() as session:
            with self.assertRaises(PixivAPIError) as caught:
                await authenticated._get(session, "/redirect")
        self.assertEqual(caught.exception.status_code, 302)
        self.assertEqual([path for path, _, _ in self.calls], ["/redirect"])

        self.calls.clear()
        module = __import__(PixivWebAPIClient.__module__, fromlist=["urlsplit"])
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(
                module,
                "urlsplit",
                return_value=SimpleNamespace(scheme="https", hostname="i.pximg.net"),
            ),
            patch.object(module.tempfile, "gettempdir", return_value=temp),
        ):
            await authenticated.download_image(authenticated.BASE + "/image")
        await self.client.fetch_images(tag=["百合"])
        self.assertEqual(self.calls[0][0], "/image")
        self.assertTrue(all("Cookie" not in headers for _, _, headers in self.calls))

    async def test_command_llm_and_local_image_delivery(self):
        plugin = main.CurrentCortexPlugin.__new__(main.CurrentCortexPlugin)
        plugin._api_client = self.client
        plugin._image_proxy = "unused.example"
        plugin._build_request_params = lambda _: {
            "keyword": "風景",
            "num": 1,
            "size": "small",
            "excludeAI": True,
        }
        plugin._maybe_promo_after_image = lambda: None
        plugin._with_promo = lambda x: x
        event = SimpleNamespace(
            message_str="/pixiv keyword:風景",
            get_sender_name=lambda: "user",
            plain_result=lambda x: ("text", x),
            chain_result=lambda x: ("image", x),
            send=AsyncMock(),
        )
        image = SimpleNamespace(fromFileSystem=lambda path: ("file", path))
        with (
            patch.object(
                self.client,
                "download_image",
                AsyncMock(return_value="/tmp/test-pixiv.jpg"),
            ),
            patch.object(main.Comp, "Image", image, create=True),
        ):
            results = [r async for r in plugin.pixiv_command(event)]
            self.assertEqual(results[1], ("image", [("file", "/tmp/test-pixiv.jpg")]))
            await plugin._llm_fetch_pixiv(event, plugin._build_request_params(""))
            self.assertEqual(event.send.await_count, 2)

    async def test_pages_schema_exposes_source(self):
        import test_relay_pages

        pages = test_relay_pages.P
        schema = pages._load_schema()
        self.assertEqual(schema["pixiv_source"]["default"], "pixiv_web")
        self.assertEqual(schema["pixiv_source"]["options"], ["pixiv_web", "leiz"])
        self.assertEqual(schema["yuri_pixiv_cookie"]["default"], "")
        self.assertEqual(schema["pixiv_web_max_images"]["default"], 20)
        pixiv_group = next(g for g in pages._CONFIG_GROUPS if g["key"] == "pixiv")
        self.assertIn("pixiv_source", pixiv_group["items"])
        self.assertIn("yuri_pixiv_cookie", pixiv_group["items"])
        self.assertIn("pixiv_web_max_images", pixiv_group["items"])
        plugin = SimpleNamespace(config={}, context=SimpleNamespace())
        result = await pages._save_and_reload(plugin, {"pixiv_source": "leiz"})
        self.assertEqual(plugin.config["pixiv_source"], "leiz")
        self.assertEqual(result["changed"], ["pixiv_source"])


    def test_yuri_cookie_prefers_config_over_env(self):
        with patch.dict(
            os.environ, {"CURRENTCORTEX_YURI_PIXIV_COOKIE": "env_cookie"}
        ):
            self.assertEqual(
                main._resolve_yuri_cookie({"yuri_pixiv_cookie": "config_cookie"}),
                "config_cookie",
            )
            self.assertEqual(
                main._resolve_yuri_cookie({"yuri_pixiv_cookie": "   "}),
                "env_cookie",
            )
            self.assertEqual(main._resolve_yuri_cookie({}), "env_cookie")
        with patch.dict(os.environ, {"CURRENTCORTEX_YURI_PIXIV_COOKIE": ""}):
            self.assertEqual(main._resolve_yuri_cookie({}), "")
        self.assertEqual(
            main._resolve_yuri_cookie(
                {"yuri_pixiv_cookie": " Cookie: PHPSESSID=abc; foo=bar "}
            ),
            "PHPSESSID=abc; foo=bar",
        )
        self.assertEqual(
            main._resolve_yuri_cookie({"yuri_pixiv_cookie": '"PHPSESSID=abc"'}),
            "PHPSESSID=abc",
        )
        self.assertEqual(
            main._resolve_yuri_cookie({"yuri_pixiv_cookie": "123456_abcdef"}),
            "PHPSESSID=123456_abcdef",
        )
        self.assertEqual(
            main._resolve_yuri_cookie(
                {"yuri_pixiv_cookie": "PHPSESSID=123456_abcdef; foo=bar"}
            ),
            "PHPSESSID=123456_abcdef; foo=bar",
        )

    def test_yuri_parameters_match_pixiv_and_keep_base_tag(self):
        plugin = main.CurrentCortexPlugin.__new__(main.CurrentCortexPlugin)
        plugin._exclude_ai = False
        cases = {
            "/yuri": {
                "tag": ["百合"], "exact_tags": True, "r18": 0,
                "num": 1, "size": "regular",
            },
            "/百合 搜索 星空 数量 2 尺寸 原图": {
                "tag": ["百合"], "keyword": "星空", "num": 2, "size": "original",
            },
            "/yuri 标签 校园 原创 数量 3": {
                "tag": ["百合", "校园", "原创"], "num": 3,
            },
            "/yuri 标签 百合 校园": {"tag": ["百合", "校园"]},
            "/yuri 作者 42 数量 2": {"uid": "42", "num": 2},
            "/yuri 分级 成人": {"r18": 1},
            "/yuri r18 2 tag 校园 num 2": {
                "tag": ["百合", "校园"], "r18": 2, "num": 2,
            },
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                params = plugin._build_yuri_request_params(text)
                for key, value in expected.items():
                    self.assertEqual(params[key], value)
                self.assertTrue(params["exact_tags"])

        self.assertEqual(plugin._build_yuri_request_params("/yuri 数量 100")["num"], 20)
        self.assertEqual(plugin._build_yuri_request_params("/yuri 数量 0")["num"], 1)
        plugin._exclude_ai = True
        self.assertTrue(plugin._build_yuri_request_params("/yuri")["excludeAI"])
        plugin._exclude_ai = False
        self.assertTrue(
            plugin._build_yuri_request_params("/yuri 排除AI 是")["excludeAI"]
        )
        self.assertNotIn(
            "excludeAI", plugin._build_yuri_request_params("/yuri 排除AI 否")
        )

        for text in ("/yuri 标签", "/yuri 搜索", "/yuri 作者 abc", "/yuri 随机 校园"):
            with self.subTest(text=text), self.assertRaises(ValueError) as caught:
                plugin._build_yuri_request_params(text)
            self.assertIn("/yuri", str(caught.exception))
        for text, hint in (("/yuri 尺寸 巨大", "尺寸"), ("/yuri r18 5", "分级")):
            with self.subTest(text=text), self.assertRaises(ValueError) as caught:
                plugin._build_yuri_request_params(text)
            self.assertIn(hint, str(caught.exception))

    async def test_yuri_search_tags_and_author_keep_yuri_tag(self):
        self.works = {
            "123": work(tags=["百合", "校园"]),
            "124": work("124", tags=["百合"], title="星空"),
            "125": work("125", tags=["非百合"], title="校园"),
        }
        plugin, event = self._yuri_plugin_and_event("/yuri 标签 校园 数量 2")
        with (
            patch.object(
                self.client, "download_image", AsyncMock(return_value="/tmp/yuri.jpg")
            ) as download,
            patch.object(main.Comp, "Plain", lambda text: text, create=True),
            patch.object(
                main.Comp, "Image", SimpleNamespace(fromFileSystem=str), create=True
            ),
        ):
            replies = [reply async for reply in plugin.yuri_command(event)]
            self.assertEqual(len(replies), 1)
            self.assertIn("/artworks/123", replies[0][0])
            download.assert_awaited_with("https://i.pximg.net/regular.jpg")

            tag_searches = [q for p, q, _ in self.calls if "/search/" in p]
            self.assertTrue(tag_searches)
            self.assertEqual(tag_searches[0]["word"], "百合 校园")
            self.assertEqual(tag_searches[0]["s_mode"], "s_tag_full")
            self.assertEqual(tag_searches[0]["mode"], "safe")

            self.calls.clear()
            download.reset_mock()
            event.message_str = "/yuri 搜索 星空 数量 2"
            [reply async for reply in plugin.yuri_command(event)]
            self.assertEqual(download.await_count, 2)
            search_calls = [q for p, q, _ in self.calls if "/search/" in p]
            self.assertTrue(search_calls)
            self.assertTrue(all("百合" in q["word"] for q in search_calls))
            self.assertTrue(any("星空" in q["word"] for q in search_calls))
            self.assertTrue(all(q["s_mode"] == "s_tc" for q in search_calls))

            self.calls.clear()
            download.reset_mock()
            event.message_str = "/yuri 作者 42"
            replies = [reply async for reply in plugin.yuri_command(event)]
            self.assertTrue(any("/user/42/profile/all" in p for p, _, _ in self.calls))
            self.assertFalse(any("/search/" in p for p, _, _ in self.calls))
            self.assertEqual(len(replies), 1)

    async def test_yuri_multiple_images_have_numbered_captions(self):
        self.works = {
            "123": work(tags=["百合"]),
            "124": work("124", tags=["百合"]),
        }
        plugin, event = self._yuri_plugin_and_event("/yuri 数量 2")
        with (
            patch.object(
                self.client, "download_image", AsyncMock(return_value="/tmp/yuri.jpg")
            ),
            patch.object(main.Comp, "Plain", lambda text: text, create=True),
            patch.object(
                main.Comp, "Image", SimpleNamespace(fromFileSystem=str), create=True
            ),
        ):
            replies = [reply async for reply in plugin.yuri_command(event)]
        self.assertEqual(len(replies), 1)
        caption, *images = replies[0]
        self.assertIn("[1/2]", caption)
        self.assertIn("[2/2]", caption)
        self.assertEqual(len(images), 2)

    async def test_pixiv_web_multi_page_urls_are_complete(self):
        self.works = {"123": work(tags=["百合"], pageCount=3)}
        self.pages = {
            "123": [
                {"urls": {"regular": "https://i.pximg.net/p1.jpg"}},
                {"urls": {"regular": "https://i.pximg.net/p2.jpg"}},
                {"urls": {"regular": "https://i.pximg.net/p3.jpg"}},
            ]
        }
        result = await self.client.fetch_images(
            tag=["百合"], exact_tags=True, num=1
        )
        item = result["data"]["data"][0]
        self.assertEqual(item["page_count"], 3)
        self.assertEqual(
            item["page_urls"],
            [
                "https://i.pximg.net/p1.jpg",
                "https://i.pximg.net/p2.jpg",
                "https://i.pximg.net/p3.jpg",
            ],
        )
        self.assertTrue(
            any("/ajax/illust/123/pages" in path for path, _, _ in self.calls)
        )

    async def test_yuri_multi_page_sends_all_pages(self):
        self.works = {"123": work(tags=["百合"], pageCount=3)}
        self.pages = {
            "123": [
                {"urls": {"regular": "https://i.pximg.net/p1.jpg"}},
                {"urls": {"regular": "https://i.pximg.net/p2.jpg"}},
                {"urls": {"regular": "https://i.pximg.net/p3.jpg"}},
            ]
        }
        plugin, event = self._yuri_plugin_and_event("/yuri")
        plugin._pixiv_web_max_images = 3
        with (
            patch.object(
                self.client, "download_image", AsyncMock(return_value="/tmp/page.jpg")
            ) as download,
            patch.object(main.Comp, "Plain", lambda text: text, create=True),
            patch.object(
                main.Comp, "Image", SimpleNamespace(fromFileSystem=str), create=True
            ),
        ):
            replies = [reply async for reply in plugin.yuri_command(event)]
        self.assertEqual(len(replies), 1)
        caption, *images = replies[0]
        self.assertIn("组图：共 3 页", caption)
        self.assertNotIn("已达到单次发送上限", caption)
        self.assertEqual(len(images), 3)
        self.assertEqual(
            [call.args[0] for call in download.await_args_list],
            [
                "https://i.pximg.net/p1.jpg",
                "https://i.pximg.net/p2.jpg",
                "https://i.pximg.net/p3.jpg",
            ],
        )

    async def test_yuri_single_message_respects_max_images(self):
        self.works = {
            "123": work(tags=["百合"], pageCount=2),
            "124": work("124", tags=["百合"], pageCount=2),
        }
        self.pages = {
            "123": [
                {"urls": {"regular": "https://i.pximg.net/a1.jpg"}},
                {"urls": {"regular": "https://i.pximg.net/a2.jpg"}},
            ],
            "124": [
                {"urls": {"regular": "https://i.pximg.net/b1.jpg"}},
                {"urls": {"regular": "https://i.pximg.net/b2.jpg"}},
            ],
        }
        plugin, event = self._yuri_plugin_and_event("/yuri 数量 2")
        plugin._pixiv_web_max_images = 3
        with (
            patch.object(
                self.client, "download_image", AsyncMock(return_value="/tmp/page.jpg")
            ) as download,
            patch.object(main.Comp, "Plain", lambda text: text, create=True),
            patch.object(
                main.Comp, "Image", SimpleNamespace(fromFileSystem=str), create=True
            ),
        ):
            replies = [reply async for reply in plugin.yuri_command(event)]
        self.assertEqual(len(replies), 1)
        caption, *images = replies[0]
        self.assertEqual(len(images), 3)
        self.assertEqual(download.await_count, 3)
        self.assertIn("上限 3 张", caption)

    async def test_pixiv_web_max_pages_cap(self):
        self.works = {"123": work(tags=["百合"], pageCount=3)}
        self.pages = {
            "123": [
                {"urls": {"regular": "https://i.pximg.net/p1.jpg"}},
                {"urls": {"regular": "https://i.pximg.net/p2.jpg"}},
                {"urls": {"regular": "https://i.pximg.net/p3.jpg"}},
            ]
        }
        client = PixivWebAPIClient(timeout=5, max_pages=2)
        client.BASE = self.client.BASE
        result = await client.fetch_images(
            tag=["百合"], exact_tags=True, num=1
        )
        item = result["data"]["data"][0]
        self.assertEqual(item["page_count"], 3)
        self.assertEqual(len(item["page_urls"]), 2)

    async def test_pixiv_process_response_multi_page(self):
        plugin = main.CurrentCortexPlugin.__new__(main.CurrentCortexPlugin)
        plugin._api_client = self.client
        item = {
            "pid": "123",
            "title": "组图",
            "author": "画师",
            "tags": ["百合"],
            "width": 800,
            "height": 1200,
            "urls": {"regular": "https://i.pximg.net/p1.jpg"},
            "page_urls": [
                "https://i.pximg.net/p1.jpg",
                "https://i.pximg.net/p2.jpg",
            ],
            "page_count": 2,
            "source": "pixiv_web",
        }
        event = SimpleNamespace(
            plain_result=lambda text: ("text", text),
            chain_result=lambda parts: ("chain", parts),
            image_result=lambda url: ("image", url),
        )
        with (
            patch.object(
                self.client, "download_image", AsyncMock(return_value="/tmp/page.jpg")
            ),
            patch.object(
                main.Comp, "Image", SimpleNamespace(fromFileSystem=str), create=True
            ),
        ):
            responses = await plugin._process_response(
                {"type": "json", "data": {"data": [item]}},
                {"r18": 0},
                event,
            )
        self.assertEqual(len(responses), 3)
        self.assertEqual(responses[0][0], "text")
        self.assertIn("组图：共 2 页", responses[0][1])
        self.assertEqual([reply[0] for reply in responses[1:]], ["chain", "chain"])

    async def test_yuri_r18_requires_cookie_and_uses_pixiv_modes(self):
        self.works = {
            "123": work(tags=["百合"]),
            "124": work("124", tags=["百合"], xRestrict=1),
            "125": work("125", tags=["百合"], xRestrict=2),
        }
        with self.assertRaises(PixivUsageError) as caught:
            await self.client.fetch_images(tag=["百合"], exact_tags=True, r18=1)
        self.assertIn("CURRENTCORTEX_YURI_PIXIV_COOKIE", str(caught.exception))
        self.assertIn("leiz", str(caught.exception))
        self.assertEqual(self.calls, [])

        authenticated = PixivWebAPIClient(timeout=5, cookie="test_session=fixture")
        authenticated.BASE = self.client.BASE
        expected = {0: {"123"}, 1: {"124", "125"}, 2: {"123", "124", "125"}}
        modes = {0: "safe", 1: "r18", 2: "all"}
        for level in (0, 1, 2):
            with self.subTest(level=level):
                self.calls.clear()
                result = await authenticated.fetch_images(
                    tag=["百合"], exact_tags=True, r18=level, num=20
                )
                self.assertEqual(
                    {item["pid"] for item in result["data"]["data"]},
                    expected[level],
                )
                searches = [
                    query
                    for path, query, _ in self.calls
                    if "/search/" in path
                ]
                self.assertTrue(searches)
                self.assertEqual(searches[0]["mode"], modes[level])
                self.assertTrue(
                    all(
                        headers.get("Cookie") == "test_session=fixture"
                        for _, _, headers in self.calls
                    )
                )

    async def test_yuri_mixed_allows_safe_results_without_r18_hint(self):
        self.works = {"123": work(tags=["百合"])}  # All-age only.
        client = PixivWebAPIClient(timeout=5, cookie="PHPSESSID=invalid")
        client.BASE = self.client.BASE
        self.self_user = None
        result = await client.fetch_images(
            tag=["百合"], exact_tags=True, r18=2, num=1
        )
        self.assertEqual(
            [item["pid"] for item in result["data"]["data"]], ["123"]
        )

    async def test_yuri_r18_invalid_cookie_reports_login_hint(self):
        self.works = {"123": work(tags=["百合"])}  # All-age only.
        client = PixivWebAPIClient(timeout=5, cookie="PHPSESSID=invalid")
        client.BASE = self.client.BASE
        self.self_user = None
        with self.assertRaises(PixivUsageError) as caught:
            await client.fetch_images(tag=["百合"], exact_tags=True, r18=1, num=1)
        message = str(caught.exception)
        self.assertIn("未登录", message)
        self.assertIn("PHPSESSID", message)

    async def test_yuri_r18_logged_in_but_disabled_reports_setting_hint(self):
        self.works = {"123": work(tags=["百合"])}  # All-age only.
        client = PixivWebAPIClient(timeout=5, cookie="PHPSESSID=valid")
        client.BASE = self.client.BASE
        self.self_user = {"id": "42", "xRestrict": 0}
        with self.assertRaises(PixivUsageError) as caught:
            await client.fetch_images(tag=["百合"], exact_tags=True, r18=1, num=1)
        message = str(caught.exception)
        self.assertIn("R18 显示设置为 0", message)
        self.assertIn("浏览限制", message)

    async def test_yuri_r18_logged_in_no_adult_results_hint(self):
        self.works = {"123": work(tags=["百合"])}  # All-age only.
        client = PixivWebAPIClient(timeout=5, cookie="PHPSESSID=valid")
        client.BASE = self.client.BASE
        self.self_user = {"id": "42", "xRestrict": 1}
        with self.assertRaises(PixivUsageError) as caught:
            await client.fetch_images(tag=["百合"], exact_tags=True, r18=1, num=1)
        message = str(caught.exception)
        self.assertIn("已登录", message)
        self.assertIn("调整标签", message)

    async def test_yuri_command_r18_requires_cookie_and_renders_adult_caption(self):
        plugin, event = self._yuri_plugin_and_event("/yuri 分级 成人")
        replies = [reply async for reply in plugin.yuri_command(event)]
        self.assertIn("CURRENTCORTEX_YURI_PIXIV_COOKIE", replies[0])
        self.assertEqual(self.calls, [])

        authenticated = PixivWebAPIClient(timeout=5, cookie="test_session=fixture")
        authenticated.BASE = self.client.BASE
        plugin._yuri_client = authenticated
        self.works = {
            "123": work(tags=["百合"], xRestrict=0),
            "124": work("124", tags=["百合"], xRestrict=1),
        }
        with (
            patch.object(
                authenticated,
                "download_image",
                AsyncMock(return_value="/tmp/yuri18.jpg"),
            ) as download,
            patch.object(main.Comp, "Plain", lambda text: text, create=True),
            patch.object(
                main.Comp, "Image", SimpleNamespace(fromFileSystem=str), create=True
            ),
        ):
            event.message_str = "/yuri 分级 成人"
            replies = [reply async for reply in plugin.yuri_command(event)]
        self.assertEqual(len(replies), 1)
        self.assertIn("[R-18]", replies[0][0])
        download.assert_awaited_with("https://i.pximg.net/regular.jpg")

    async def test_yuri_llm_tool_sends_images(self):
        self.works = {
            "123": work(tags=["百合", "校园"]),
            "124": work("124", tags=["百合", "校园"]),
        }
        plugin, event = self._yuri_plugin_and_event("/yuri")
        plugin._llm_tools_enable = True
        plugin._verify_ok = True
        event.send = AsyncMock()
        with (
            patch.object(
                self.client, "download_image", AsyncMock(return_value="/tmp/yuri.jpg")
            ),
            patch.object(main.Comp, "Plain", lambda text: text, create=True),
            patch.object(
                main.Comp, "Image", SimpleNamespace(fromFileSystem=str), create=True
            ),
        ):
            reply = await plugin.llm_tool_yuri(
                event, keyword="", tags="校园,百合", num=2, r18=0
            )
        self.assertIn("已发送 2 张", reply)
        self.assertEqual(event.send.await_count, 1)
        searches = [q for p, q, _ in self.calls if "/search/" in p]
        self.assertTrue(searches)
        self.assertEqual(searches[0]["word"], "百合 校园")
        self.assertEqual(searches[0]["s_mode"], "s_tag_full")

        event.send.reset_mock()
        reply = await plugin.llm_tool_yuri(event, keyword="", tags="", num=1, r18=1)
        self.assertIn("CURRENTCORTEX_YURI_PIXIV_COOKIE", reply)
        self.assertEqual(event.send.await_count, 0)

    async def test_yuri_thumb_size_uses_pixiv_web_url(self):
        self.works = {
            "123": work(
                tags=["百合"],
                urls={
                    "regular": "https://i.pximg.net/regular.jpg",
                    "thumb_mini": "https://i.pximg.net/thumb_mini.jpg",
                },
            )
        }
        plugin, event = self._yuri_plugin_and_event("/yuri 尺寸 缩略图")
        with (
            patch.object(
                self.client, "download_image", AsyncMock(return_value="/tmp/thumb.jpg")
            ) as download,
            patch.object(main.Comp, "Plain", lambda text: text, create=True),
            patch.object(
                main.Comp, "Image", SimpleNamespace(fromFileSystem=str), create=True
            ),
        ):
            replies = [reply async for reply in plugin.yuri_command(event)]
        self.assertEqual(len(replies), 1)
        download.assert_awaited_with("https://i.pximg.net/thumb_mini.jpg")


if __name__ == "__main__":
    unittest.main()
