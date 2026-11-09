"""RSS candidates per section inside a freshness window."""

from __future__ import annotations

import calendar
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from toy_lair_assistant.gazeta.config import FEEDS

WINDOW_HOURS = 36
PER_FEED = 12
TAG_RE = re.compile(r"<[^>]+>")


def _entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    return None


def parse_feed(content: bytes, outlet: str, now: datetime) -> list[dict]:
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    out = []
    for entry in feedparser.parse(content).entries:
        stamp = _entry_time(entry)
        if stamp is None or stamp < cutoff:
            continue
        link = str(entry.get("link") or "").strip()
        title = " ".join(str(entry.get("title") or "").split())
        if not link or not title:
            continue
        summary = " ".join(TAG_RE.sub(" ", str(entry.get("summary") or "")).split())[:250]
        out.append({"title": title, "url": link, "outlet": outlet, "published": stamp.isoformat(), "snippet": summary})
        if len(out) >= PER_FEED:
            break
    return out


def _load(http: httpx.Client, outlet: str, url: str, now: datetime) -> list[dict]:
    try:
        response = http.get(url)
        response.raise_for_status()
        return parse_feed(response.content, outlet, now)
    except Exception:
        return []


def fetch_all(http: httpx.Client, now: datetime, feeds: dict | None = None) -> dict[str, list[dict]]:
    catalog = feeds if feeds is not None else FEEDS
    jobs = {(section, outlet, url) for section, items in catalog.items() for outlet, url in items}
    cache: dict[tuple[str, str], list[dict]] = {}
    with ThreadPoolExecutor(8) as pool:
        futures = {(outlet, url): pool.submit(_load, http, outlet, url, now) for _, outlet, url in jobs}
        for key, future in futures.items():
            cache[key] = future.result()
    result: dict[str, list[dict]] = {}
    for section, items in catalog.items():
        seen: set[str] = set()
        rows: list[dict] = []
        for outlet, url in items:
            for row in cache[(outlet, url)]:
                if row["url"] in seen:
                    continue
                seen.add(row["url"])
                rows.append(row)
        rows.sort(key=lambda row: row["published"], reverse=True)
        result[section] = rows
    return result
