"""Crossword words and clues for today's issue. The model writes clues, code checks every pair."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..editor import clean_text

SKILL = (Path(__file__).parent.parent / "skills" / "crossword.md").read_text()
WANT = 16
MIN_LEN, MAX_LEN = 3, 11
SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"answer": {"type": "string"}, "clue": {"type": "string"}},
                "required": ["answer", "clue"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["entries"],
    "additionalProperties": False,
}
STOP = {
    "about", "after", "again", "also", "amid", "against", "among", "before", "being", "could", "from", "have", "into",
    "more", "most", "over", "says", "than", "that", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "under", "until", "what", "when", "where", "which", "while", "will", "with", "would", "your", "year",
    "years", "week", "today", "news", "first", "new", "its",
}


def corpus(issue: dict) -> str:
    rows = []
    lead = issue.get("lead")
    if lead:
        rows.append(lead["headline"] + ". " + lead.get("standfirst", ""))
    for s in issue.get("incidents", {}).get("stories", []):
        rows.append(s["headline"] + ". " + s.get("summary", ""))
    for sec in issue.get("sections", []):
        for s in sec["stories"]:
            rows.append(s["headline"] + ". " + s.get("summary", ""))
    return "\n".join(rows)


def _words(text: str) -> set[str]:
    return {w.upper() for w in re.findall(r"[A-Za-z]+", text)}


def validate(entries: list[dict], text: str) -> list[tuple[str, str]]:
    present = _words(text)
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for e in entries:
        answer = str(e.get("answer", "")).strip().upper()
        clue = clean_text(str(e.get("clue", "")).strip())
        if not re.fullmatch(r"[A-Z]+", answer) or not MIN_LEN <= len(answer) <= MAX_LEN:
            continue
        if answer in seen or answer not in present:
            continue
        if answer.lower() in clue.lower() or not clue or len(clue.split()) > 14:
            continue
        seen.add(answer)
        out.append((answer, clue))
    return out


def blanks(issue: dict, limit: int = WANT) -> list[tuple[str, str]]:
    """Fallback without the model: a headline with one word replaced by a blank."""
    heads = []
    lead = issue.get("lead")
    if lead:
        heads.append(lead["headline"])
    heads += [s["headline"] for s in issue.get("incidents", {}).get("stories", [])]
    for sec in issue.get("sections", []):
        heads += [s["headline"] for s in sec["stories"]]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for head in heads:
        for m in re.finditer(r"\b[A-Za-z]{4,11}\b", head):
            word = m.group(0)
            up = word.upper()
            if up in seen or word.lower() in STOP:
                continue
            seen.add(up)
            out.append((up, clean_text(head[: m.start()] + "____" + head[m.end():])))
            break
        if len(out) >= limit:
            break
    return out


def make(client: Any, model: str, issue: dict) -> list[tuple[str, str]]:
    text = corpus(issue)
    if not text.strip():
        return []
    pairs: list[tuple[str, str]] = []
    try:
        out = client.chat_json(model, SKILL, text[:9000], SCHEMA, "crossword_clues")
        pairs = validate(out.get("entries", []), text)
    except Exception:
        pairs = []
    if len(pairs) < 10:
        used = {a for a, _ in pairs}
        pairs += [p for p in blanks(issue) if p[0] not in used]
    return pairs[:WANT + 4]
