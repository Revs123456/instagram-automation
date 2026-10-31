"""Comment-keyword -> DM rules."""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Rule:
    keywords: list[str]
    dm: str
    link: str = ""
    media_ids: list[str] = field(default_factory=list)  # empty = any reel/post
    public_replies: list[str] = field(default_factory=list)

    def matches(self, text: str, media_id: str | None) -> str | None:
        if self.media_ids and media_id not in self.media_ids:
            return None
        for kw in self.keywords:
            if re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", text, flags=re.IGNORECASE):
                return kw
        return None

    def render_dm(self, username: str = "") -> str:
        return self.dm.format(username=username or "there", link=self.link)

    def pick_public_reply(self, username: str = "") -> str | None:
        if not self.public_replies:
            return None
        return random.choice(self.public_replies).format(username=username or "")


@dataclass
class RuleSet:
    rules: list[Rule]
    hourly_dm_cap: int = 180

    def match(self, text: str, media_id: str | None) -> tuple[Rule, str] | None:
        # Media-specific rules take priority over global ones.
        for rule in sorted(self.rules, key=lambda r: not r.media_ids):
            kw = rule.matches(text, media_id)
            if kw:
                return rule, kw
        return None

    @classmethod
    def load(cls, path: str | Path) -> "RuleSet":
        data = json.loads(Path(path).read_text())
        rules = [Rule(**r) for r in data.get("rules", [])]
        return cls(rules=rules, hourly_dm_cap=data.get("hourly_dm_cap", 180))
