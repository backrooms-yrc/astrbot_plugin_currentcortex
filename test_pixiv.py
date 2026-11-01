"""Offline Pixiv source regressions: uv run --with aiohttp python test_pixiv.py."""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web

# Reuse the existing AstrBot stubs; no plugin lifecycle or external services run.
from test_music_audio import main

PixivWebAPIClient = main.PixivWebAPIClient
PixivAPIError = main.PixivAPIError


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
            if path == "/ranking.php":
                return web.json_response(
                    {"contents": [{"illust_id": k} for k in self.works]}
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
        self.assertIn(
            "pixiv_source",
            next(g for g in pages._CONFIG_GROUPS if g["key"] == "pixiv")["items"],
        )
        plugin = SimpleNamespace(config={}, context=SimpleNamespace())
        result = await pages._save_and_reload(plugin, {"pixiv_source": "leiz"})
        self.assertEqual(plugin.config["pixiv_source"], "leiz")
        self.assertEqual(result["changed"], ["pixiv_source"])


if __name__ == "__main__":
    unittest.main()
