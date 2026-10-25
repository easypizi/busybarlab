from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any

import httpx

from toy_lair_assistant.collector.models import Enriched, RawItem

log = logging.getLogger(__name__)

KINDS = ("recipe", "workout", "tool", "article", "idea", "video", "email", "place", "product", "other")
PAGE_LIMIT = 6000
CLASSIFY_TEXT_LIMIT = 5000


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style", "noscript", "svg", "head"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "head"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return " ".join(parser.parts)


def page_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return " ".join(match.group(1).split()) if match else ""


class Enricher:
    def __init__(
        self,
        transcribe: Callable[[bytes, str], str] | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        self.transcribe = transcribe
        self.http = http or httpx.Client(timeout=20, follow_redirects=True)

    def enrich(self, item: RawItem) -> tuple[str, str]:
        """Return (transcript, page_text). Failures degrade to empty strings."""
        transcript = ""
        page = ""
        if item.audio is not None and self.transcribe is not None:
            try:
                transcript = self.transcribe(item.audio(), item.audio_mime)
            except Exception:
                log.exception("transcribe failed key=%s", item.key)
        if item.fetch_page and item.url.startswith("http"):
            try:
                response = self.http.get(item.url, headers={"User-Agent": "Mozilla/5.0 (Paco)"})
                response.raise_for_status()
                if "html" in response.headers.get("content-type", "html"):
                    if not item.title:
                        item.title = page_title(response.text)
                    page = html_to_text(response.text)[:PAGE_LIMIT]
            except Exception:
                log.warning("page fetch failed key=%s", item.key)
        return transcript, page


class Classifier:
    def __init__(self, llm: Any) -> None:
        self.llm = llm

    def classify(self, item: RawItem, transcript: str, page: str, titles: list[str]) -> Enriched:
        body = "\n".join(p for p in (item.text, transcript, page) if p)[:CLASSIFY_TEXT_LIMIT]
        prompt = (
            "Classify one saved item for a personal knowledge base. Reply with JSON only: "
            '{"kind": one of ' + ", ".join(KINDS) + ', "topics": [up to 4 short strings], '
            '"summary": "2 sentences, plain words, same language as the item", '
            '"related": [up to 3 titles copied exactly from the note list, or empty]}.\n'
            f"Source: {item.source}\nTitle: {item.title}\nAuthor: {item.author}\nURL: {item.url}\n"
            f"Text:\n{body}\n\nNote list:\n" + "\n".join(titles[:300])
        )
        try:
            result = self.llm.complete(
                [
                    {"role": "system", "content": "You tag saved links. Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                [],
                [],
            )
            data = _parse_json(result.reply)
        except Exception:
            log.exception("classify failed key=%s", item.key)
            data = {}
        kind = str(data.get("kind") or "other").lower()
        if kind not in KINDS:
            kind = "other"
        topics = [str(t).strip() for t in (data.get("topics") or []) if str(t).strip()][:4]
        summary = str(data.get("summary") or "").strip() or (body[:200] if not item.private else "")
        related = [str(t).strip() for t in (data.get("related") or []) if str(t).strip()][:3]
        return Enriched(
            kind=kind, topics=topics, summary=summary, related=related,
            transcript=transcript, page_text=page,
        )


def _parse_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
