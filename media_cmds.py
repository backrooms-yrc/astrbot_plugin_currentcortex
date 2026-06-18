    @filter.command("解析")
    async def media_parse_command(self, event: AstrMessageEvent):
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()
        if self._is_help_command(message_str):
            yield event.plain_result(MEDIA_PARSER_HELP_TEXT)
            return
        url = self._parse_media_url(message_str)
        if not url:
            yield event.plain_result("请提供有效的媒体链接")
            return
        try:
            result = await self._media_parser.parse(url)
            platform = result.get('platform', '')
            data = result.get('data', {})
            response_items = self._format_media_response(platform, data, event)
            for item in response_items:
                yield item
        except MediaParserError as e:
            yield event.plain_result(f"解析失败: {str(e)}")
        except Exception as e:
            yield event.plain_result(f"发生未知错误: {str(e)}")

    @filter.command("xhs", alias={'小红书'})
    async def xhs_parse_command(self, event: AstrMessageEvent):
        message_str = event.message_str.strip()
        if self._is_help_command(message_str):
            yield event.plain_result("小红书解析: /xhs <链接>")
            return
        url = self._parse_media_url(message_str)
        if not url or not URLExtractor.extract_xiaohongshu(url):
            yield event.plain_result("请提供有效的小红书链接")
            return
        try:
            data = await self._media_parser.xiaohongshu.parse(url)
            for item in self._format_xiaohongshu_response(data, event):
                yield item
        except Exception as e:
            yield event.plain_result(f"小红书解析失败: {str(e)}")

    @filter.command("bilibili", alias={'B站', 'b站'})
    async def bilibili_parse_command(self, event: AstrMessageEvent):
        message_str = event.message_str.strip()
        if self._is_help_command(message_str):
            yield event.plain_result("B站解析: /bilibili <链接>")
            return
        url = self._parse_media_url(message_str)
        if not url or not URLExtractor.extract_bilibili(url):
            yield event.plain_result("请提供有效的B站链接")
            return
        try:
            data = await self._media_parser.bilibili.parse(url)
            for item in self._format_bilibili_response(data, event):
                yield item
        except Exception as e:
            yield event.plain_result(f"B站解析失败: {str(e)}")

    @filter.command("douyin", alias={'抖音'})
    async def douyin_parse_command(self, event: AstrMessageEvent):
        message_str = event.message_str.strip()
        if self._is_help_command(message_str):
            yield event.plain_result("抖音解析: /douyin <链接>")
            return
        url = self._parse_media_url(message_str)
        if not url or not URLExtractor.extract_douyin(url):
            yield event.plain_result("请提供有效的抖音链接")
            return
        try:
            data = await self._media_parser.douyin.parse(url)
            for item in self._format_douyin_response(data, event):
                yield item
        except Exception as e:
            yield event.plain_result(f"抖音解析失败: {str(e)}")

    def _parse_media_url(self, message: str) -> Optional[str]:
        cleaned = re.sub(r'^[/!！]\s*(解析|xhs|小红书|bilibili|B站|b站|douyin|抖音)\s*', '', message.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'^(解析|xhs|小红书|bilibili|B站|b站|douyin|抖音)\s*', '', cleaned.strip(), flags=re.IGNORECASE)
        cleaned = cleaned.strip()
        if not cleaned or cleaned.lower() in ('help', '-h', '--help', '帮助'):
            return None
        url_pattern = re.compile(r'https?://[^\s]+')
        match = url_pattern.search(cleaned)
        if match:
            return match.group(0)
        if cleaned.startswith('xhslink.com/') or cleaned.startswith('b23.tv/') or cleaned.startswith('v.douyin.com/'):
            return f"https://{cleaned}"
        return None

    def _format_media_response(self, platform: str, data: Dict[str, Any], event: AstrMessageEvent) -> List[Any]:
        if platform == 'xiaohongshu':
            return self._format_xiaohongshu_response(data, event)
        elif platform == 'bilibili':
            return self._format_bilibili_response(data, event)
        elif platform == 'douyin':
            return self._format_douyin_response(data, event)
        return [event.plain_result("未知平台")]

    def _format_xiaohongshu_response(self, data: Dict[str, Any], event: AstrMessageEvent) -> List[Any]:
        title = data.get('title', '')
        desc = data.get('desc', '')
        author = data.get('author', '')
        likes = data.get('likes', '')
        images = data.get('images', [])
        video = data.get('video')
        url = data.get('url', '')
        parts = ["📕 小红书笔记解析"]
        if title: parts.append(f"📝 标题：{title}")
        if author: parts.append(f"👤 作者：{author}")
        if likes: parts.append(f"❤️ 点赞：{likes}")
        if desc: parts.append(f"📄 简介：{desc[:200]}")
        if url: parts.append(f"🔗 链接：{url}")
        results = [event.plain_result("\n".join(parts))]
        if images:
            for i, img in enumerate(images[:9]):
                img_url = img.get('url', '') if isinstance(img, dict) else str(img)
                if img_url:
                    results.append(event.image_result(img_url))
        if video and isinstance(video, dict) and video.get('url'):
            results.append(event.plain_result(f"🎬 视频：{video['url']}"))
        return results

    def _format_bilibili_response(self, data: Dict[str, Any], event: AstrMessageEvent) -> List[Any]:
        title = data.get('title', '')
        desc = data.get('desc', '')
        cover = data.get('cover', '')
        duration = data.get('duration', 0)
        link = data.get('link', '')
        owner = data.get('owner', {})
        stat = data.get('stat', {})
        download_url = data.get('download_url')
        pages = data.get('pages', [])
        owner_name = owner.get('name', '') if isinstance(owner, dict) else ''
        parts = ["📺 B站视频解析"]
        if title: parts.append(f"📝 标题：{title}")
        if owner_name: parts.append(f"👤 UP主：{owner_name}")
        if duration:
            mins, secs = divmod(duration, 60)
            parts.append(f"⏱️ 时长：{mins}:{secs:02d}")
        if pages and len(pages) > 1:
            parts.append(f"📑 分P：共{len(pages)}P")
        stat_parts = []
        view = stat.get('view', 0) if isinstance(stat, dict) else 0
        like = stat.get('like', 0) if isinstance(stat, dict) else 0
        if view: stat_parts.append(f"▶️ {self._format_number(view)}")
        if like: stat_parts.append(f"👍 {self._format_number(like)}")
        if stat_parts: parts.append(" ".join(stat_parts))
        if desc: parts.append(f"📄 简介：{desc[:200]}")
        if link: parts.append(f"🔗 链接：{link}")
        if download_url: parts.append(f"📥 下载：{download_url}")
        results = [event.plain_result("\n".join(parts))]
        if cover:
            results.append(event.image_result(cover))
        return results

    def _format_douyin_response(self, data: Dict[str, Any], event: AstrMessageEvent) -> List[Any]:
        title = data.get('title', '')
        desc = data.get('desc', '')
        author = data.get('author', '')
        likes = data.get('likes', '')
        comments = data.get('comments', '')
        shares = data.get('shares', '')
        cover = data.get('cover', '')
        video_url = data.get('video_url', '')
        url = data.get('url', '')
        parts = ["🎵 抖音视频解析"]
        if title: parts.append(f"📝 标题：{title}")
        if author: parts.append(f"👤 作者：{author}")
        stat_parts = []
        if likes: stat_parts.append(f"❤️ {likes}")
        if comments: stat_parts.append(f"💬 {comments}")
        if shares: stat_parts.append(f"🔄 {shares}")
        if stat_parts: parts.append(" ".join(stat_parts))
        if desc: parts.append(f"📄 简介：{desc[:200]}")
        if url: parts.append(f"🔗 链接：{url}")
        if video_url: parts.append(f"📥 无水印视频：{video_url}")
        results = [event.plain_result("\n".join(parts))]
        if cover:
            results.append(event.image_result(cover))
        return results

    @staticmethod
    def _format_number(num: int) -> str:
        if num >= 10000:
            return f"{num / 10000:.1f}万"
        return str(num)

