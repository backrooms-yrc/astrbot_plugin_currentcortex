"""Pixiv 命令参数解析器。

将用户输入的文本解析为 Pixiv API 查询参数字典。
"""
import re
from typing import Any, Dict


class CommandParser:
    PARAM_MAP = {
        "r18": "r18",
        "tag": "tag",
        "keyword": "keyword",
        "num": "num",
        "size": "size",
        "uid": "uid",
        "excludeai": "excludeAI",
        "exclude_ai": "excludeAI",
        "ratio": "aspectRatio",
        "date_after": "dateAfter",
        "date_before": "dateBefore",
    }

    @classmethod
    def parse(cls, raw_text: str) -> Dict[str, Any]:
        if not raw_text or not raw_text.strip():
            return {}

        text = raw_text.strip()
        params: Dict[str, Any] = {}

        key_value_pattern = re.compile(
            r"([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([^\s]+)",
        )
        consumed_positions = []
        for match in key_value_pattern.finditer(text):
            key = match.group(1).lower()
            value = match.group(2).strip()
            mapped_key = cls.PARAM_MAP.get(key, key)

            if mapped_key == "tag":
                existing = params.get("tag", [])
                existing.append(value)
                params["tag"] = existing
            elif mapped_key in ("r18", "num"):
                try:
                    params[mapped_key] = int(value)
                except ValueError:
                    pass
            elif mapped_key == "excludeAI":
                params[mapped_key] = value.lower() in ("true", "1", "yes")
            else:
                params[mapped_key] = value
            consumed_positions.append((match.start(), match.end()))

        remaining = text
        for start, end in sorted(consumed_positions, reverse=True):
            remaining = remaining[:start] + remaining[end:]

        remaining_tokens = remaining.strip().split()
        for token in remaining_tokens:
            token_lower = token.lower()
            if token_lower == "r18":
                params.setdefault("r18", 1)
            elif token_lower == "mixed":
                params.setdefault("r18", 2)
            elif token_lower == "safe" or token_lower == "sfw":
                params.setdefault("r18", 0)

        return params
