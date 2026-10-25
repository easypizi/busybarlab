from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING = re.compile(r"^(utm_|fbclid|igshid|gclid|mc_|ref$)", re.IGNORECASE)


class ConnectorAuthError(Exception):
    """The source refused us (expired session, checkpoint, bad password). Stop, do not retry."""


@dataclass
class RawItem:
    source: str
    external_id: str
    url: str
    title: str = ""
    author: str = ""
    text: str = ""
    captured_at: str = ""
    private: bool = False
    fetch_page: bool = False
    audio: Callable[[], bytes] | None = field(default=None, repr=False, compare=False)
    audio_mime: str = "audio/mp4"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.external_id}"


@dataclass
class Enriched:
    kind: str = "other"
    topics: list[str] = field(default_factory=list)
    summary: str = ""
    related: list[str] = field(default_factory=list)
    transcript: str = ""
    page_text: str = ""


@dataclass
class Processed:
    item: RawItem
    enriched: Enriched
    vault_path: str = ""


class FetchContext:
    """What a connector may use: dedupe, per-run limit, staged cursors."""

    def __init__(self, seen: Callable[[str], bool], limit: int, cursors: dict[str, str]) -> None:
        self.seen = seen
        self.limit = limit
        self._cursors = cursors
        self.staged: dict[str, str] = {}

    def cursor(self, name: str) -> str | None:
        return self.staged.get(name, self._cursors.get(name))

    def stage_cursor(self, name: str, value: str) -> None:
        self.staged[name] = value


def canonical_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = [(k, v) for k, v in parse_qsl(parsed.query) if not _TRACKING.match(k)]
    path = parsed.path.rstrip("/") or ""
    return urlunparse((parsed.scheme.lower() or "https", host, path, "", urlencode(query), ""))


def url_hash(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def item_hash(source: str, external_id: str) -> str:
    return hashlib.sha1(f"{source}:{external_id}".encode()).hexdigest()[:12]
