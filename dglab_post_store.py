"""帖子系统 - 发现页面的帖子存储"""

import json
import os
import threading
import time
import secrets
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from astrbot.api import logger


@dataclass
class Post:
    post_id: str
    author: str
    title: str
    summary: str
    content: str
    created_at: float
    views: int = 0


class PostStore:
    def __init__(self, data_dir: str = "data"):
        self._data_dir = data_dir
        self._file_path = os.path.join(data_dir, "dglab_posts.json")
        self._lock = threading.Lock()
        self._posts: Dict[str, Post] = {}
        os.makedirs(self._data_dir, exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(self._file_path):
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    with self._lock:
                        for pid, pdata in data.items():
                            if isinstance(pdata, dict):
                                try:
                                    # Migrate old posts without title/summary
                                    if "title" not in pdata:
                                        pdata["title"] = pdata.get("content", "")[:30]
                                    if "summary" not in pdata:
                                        pdata["summary"] = pdata.get("content", "")[
                                            :100
                                        ]
                                    if "views" not in pdata:
                                        pdata["views"] = 0
                                    self._posts[pid] = Post(**pdata)
                                except Exception as e:
                                    logger.error(
                                        f"[DGLab Post] 加载帖子 {pid} 失败: {e}"
                                    )
                logger.info(f"[DGLab Post] 已加载 {len(self._posts)} 条帖子")
            except Exception as e:
                logger.error(f"[DGLab Post] 加载帖子数据失败: {e}")

    def _save(self):
        try:
            with self._lock:
                data = {pid: asdict(p) for pid, p in self._posts.items()}
            temp = self._file_path + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, self._file_path)
        except Exception as e:
            logger.error(f"[DGLab Post] 保存帖子数据失败: {e}")

    def create_post(
        self, author: str, title: str, summary: str, content: str
    ) -> Optional[str]:
        """Create a new post. Returns post_id on success."""
        if not title.strip():
            return None
        post_id = secrets.token_hex(8)
        post = Post(
            post_id=post_id,
            author=author,
            title=title.strip(),
            summary=summary.strip(),
            content=content.strip(),
            created_at=time.time(),
            views=0,
        )
        with self._lock:
            self._posts[post_id] = post
        self._save()
        return post_id

    def get_post(self, post_id: str) -> Optional[dict]:
        """Get a single post by ID, incrementing view count."""
        with self._lock:
            post = self._posts.get(post_id)
            if not post:
                return None
            post.views += 1
            result = asdict(post)
        self._save()
        return result

    def list_posts(
        self, limit: int = 50, sort: str = "newest", query: str = ""
    ) -> List[dict]:
        """Return posts with optional search and sort."""
        with self._lock:
            posts = list(self._posts.values())

        # Filter by search query
        if query:
            q = query.lower()
            posts = [p for p in posts if q in p.title.lower() or q in p.summary.lower()]

        # Sort
        if sort == "oldest":
            posts.sort(key=lambda p: p.created_at)
        elif sort == "popular":
            posts.sort(key=lambda p: p.views, reverse=True)
        else:  # newest (default)
            posts.sort(key=lambda p: p.created_at, reverse=True)

        # Return without full content for list view
        result = []
        for p in posts[:limit]:
            d = asdict(p)
            del d["content"]
            result.append(d)
        return result

    def delete_post(self, post_id: str, username: str, is_admin: bool = False) -> bool:
        """Delete a post. Only the author or an admin can delete."""
        with self._lock:
            post = self._posts.get(post_id)
            if not post:
                return False
            if post.author != username and not is_admin:
                return False
            del self._posts[post_id]
        self._save()
        return True
