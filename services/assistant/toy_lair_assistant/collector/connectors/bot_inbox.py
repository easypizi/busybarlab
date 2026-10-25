from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from toy_lair_assistant.collector.models import FetchContext, RawItem

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


class BotInbox:
    """URLs and forwards that the user sent to the bot. Jobs are handed in by the poller."""

    name = "bot"

    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []

    def feed(self, jobs: list[dict[str, Any]]) -> None:
        self.jobs = [j for j in jobs if j.get("kind") == "url"]

    def fetch(self, ctx: FetchContext) -> Iterator[RawItem]:
        for job in self.jobs:
            payload = job.get("payload") or {}
            text = str(payload.get("text") or "")
            urls = [str(u) for u in payload.get("urls") or []] or URL_RE.findall(text)
            first = text.strip().splitlines()[0] if text.strip() else ""
            url = urls[0] if urls else ""
            ext = str(job.get("id"))
            if ctx.seen(ext):
                continue
            yield RawItem(
                source=self.name,
                external_id=ext,
                url=url or f"bot:{ext}",
                title=first[:100],
                text=text,
                captured_at=str(payload.get("at") or ""),
                fetch_page=bool(url),
                extra={"job_id": ext},
            )
