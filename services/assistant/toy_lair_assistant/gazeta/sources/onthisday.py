"""Wikipedia 'On this day': a few entries from different eras."""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from ..editor import clean_text

log = logging.getLogger(__name__)
URL = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/selected/{m:02d}/{d:02d}"
WORDS = 30
COUNT = 4


def _short(text: str) -> str:
    text = re.sub(r"\s*\([^)]*pictured[^)]*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()
    if len(words) <= WORDS:
        return clean_text(text)
    cut = " ".join(words[:WORDS])
    last = max(cut.rfind(". "), cut.rfind(", "))
    cut = cut[:last] if last > 40 else cut
    return clean_text(cut.rstrip(",;:") + ".")


def pick(entries: list[dict]) -> list[dict]:
    rows = [e for e in entries if isinstance(e.get("year"), int) and e.get("text")]
    rows.sort(key=lambda e: e["year"])
    if len(rows) <= COUNT:
        chosen = rows
    else:
        step = (len(rows) - 1) / (COUNT - 1)
        chosen = [rows[round(i * step)] for i in range(COUNT)]
    return [{"year": e["year"], "text": _short(e["text"])} for e in chosen]


def fetch(http: Any, today: date) -> list[dict]:
    try:
        response = http.get(URL.format(m=today.month, d=today.day))
        response.raise_for_status()
        return pick(response.json().get("selected", []))
    except Exception as exc:
        log.warning("on this day skipped: %s", exc)
        return []
