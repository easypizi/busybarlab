"""Section desk: picks and writes the rubric stories. Code downloads the articles and enforces every guard."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from .articles import fetch_article
from .config import SECTION_LIMITS, SECTION_ORDER, SECTION_TITLES
from .editor import WINDOW_HOURS, _parse_time, _similar, clean_text

log = logging.getLogger(__name__)
SKILL = (Path(__file__).parent / "skills" / "desk.md").read_text()
CANDIDATES_SHOWN = 25
SPARES = 2
SUMMARY_MAX = 300

PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"index": {"type": "integer"}, "score": {"type": "integer"}, "reason": {"type": "string"}},
                "required": ["index", "score", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["picks"],
    "additionalProperties": False,
}
WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"index": {"type": "integer"}, "headline": {"type": "string"}, "summary": {"type": "string"}},
                "required": ["index", "headline", "summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["stories"],
    "additionalProperties": False,
}


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[: last + 1] if last > limit * 0.5 else cut.rsplit(" ", 1)[0].rstrip(",:") + "."


class Desk:
    def __init__(self, client: Any, model: str, http: httpx.Client, now: datetime, workers: int = 3) -> None:
        self.client = client
        self.model = model
        self.http = http
        self.now = now
        self.workers = workers
        self.stats: dict[str, dict] = {}

    # ---- one section ----

    def _fresh(self, row: dict) -> bool:
        stamp = _parse_time(row.get("published"))
        if stamp is None:
            return False
        return self.now.astimezone(timezone.utc) - stamp.astimezone(timezone.utc) <= timedelta(hours=WINDOW_HOURS)

    def _rows(self, rows: list[dict], exclude_urls: set[str], exclude_titles: list[str]) -> list[dict]:
        out = []
        for row in rows:
            if row["url"] in exclude_urls or any(_similar(row["title"], t) for t in exclude_titles):
                continue
            if not self._fresh(row):
                continue
            out.append(row)
            if len(out) >= CANDIDATES_SHOWN:
                break
        return out

    def _pick(self, sid: str, rows: list[dict], lo: int, hi: int) -> list[int]:
        user = json.dumps(
            {
                "step": "pick",
                "section": SECTION_TITLES[sid],
                "want_min": lo,
                "want_max": hi,
                "candidates": [
                    {"i": i, "title": r["title"], "outlet": r["outlet"], "published": r["published"], "snippet": r.get("snippet", "")}
                    for i, r in enumerate(rows)
                ],
            },
            ensure_ascii=False,
        )
        out = self.client.chat_json(self.model, SKILL, user, PICK_SCHEMA, "desk_pick")
        seen: list[int] = []
        for pick in sorted(out.get("picks", []), key=lambda p: -int(p.get("score", 0))):
            index = pick.get("index")
            if isinstance(index, int) and 0 <= index < len(rows) and index not in seen:
                seen.append(index)
        return seen[: hi + SPARES]

    def _write(self, sid: str, opened: list[tuple[int, dict, str]], hi: int) -> dict[int, dict]:
        user = json.dumps(
            {
                "step": "write",
                "section": SECTION_TITLES[sid],
                "articles": [{"i": i, "outlet": row["outlet"], "title": row["title"], "text": text} for i, row, text in opened],
            },
            ensure_ascii=False,
        )
        out = self.client.chat_json(self.model, SKILL, user, WRITE_SCHEMA, "desk_write")
        valid = {i for i, _, _ in opened}
        written: dict[int, dict] = {}
        for item in out.get("stories", []):
            index = item.get("index")
            headline = clean_text(str(item.get("headline") or "").strip())
            summary = clean_text(str(item.get("summary") or "").strip())
            if index in valid and index not in written and headline and summary:
                written[index] = {"headline": headline, "summary": _cut(summary, SUMMARY_MAX)}
        return written

    def section(self, sid: str, rows: list[dict], exclude_urls: set[str], exclude_titles: list[str]) -> list[dict]:
        lo, hi = SECTION_LIMITS[sid]
        stat = {"candidates": len(rows), "picked": 0, "opened": 0, "written": 0}
        self.stats[sid] = stat
        shown = self._rows(rows, exclude_urls, exclude_titles)
        if not shown:
            return []
        picked = self._pick(sid, shown, lo, hi)
        stat["picked"] = len(picked)
        if not picked:
            return []

        def open_one(index: int) -> tuple[int, dict, str] | None:
            row = shown[index]
            try:
                _, text = fetch_article(self.http, row["url"])
            except Exception as exc:
                log.info("desk %s: could not open %s: %s", sid, row["url"], exc)
                return None
            return (index, row, text) if text.strip() else None

        with ThreadPoolExecutor(max_workers=4) as pool:
            opened = [item for item in pool.map(open_one, picked) if item]
        opened = opened[:hi + SPARES]
        stat["opened"] = len(opened)
        if not opened:
            return []
        written = self._write(sid, opened, hi)
        stories = []
        for index, row, _ in opened:
            if index in written and len(stories) < hi:
                stories.append({**written[index], "url": row["url"], "source": row["outlet"], "published": row["published"]})
        stat["written"] = len(stories)
        return stories

    # ---- all sections ----

    def run(self, pool: dict[str, list[dict]], exclude_urls: set[str], exclude_titles: list[str]) -> list[dict]:
        ids = [sid for sid in SECTION_ORDER if sid in SECTION_LIMITS and pool.get(sid)]

        def one(sid: str) -> tuple[str, list[dict]]:
            try:
                return sid, self.section(sid, pool[sid], exclude_urls, exclude_titles)
            except Exception as exc:
                log.warning("desk section %s failed: %s", sid, exc)
                return sid, []

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            results = dict(executor.map(one, ids))
        seen_urls = set(exclude_urls)
        seen_titles = list(exclude_titles)
        sections = []
        for sid in SECTION_ORDER:
            keep = []
            for story in results.get(sid, []):
                if story["url"] in seen_urls or any(_similar(story["headline"], t) for t in seen_titles):
                    continue
                seen_urls.add(story["url"])
                seen_titles.append(story["headline"])
                keep.append(story)
            if keep:
                sections.append({"id": sid, "title": SECTION_TITLES[sid], "stories": keep})
        log.info("gazeta desk: %s", {sid: s for sid, s in self.stats.items()})
        return sections
