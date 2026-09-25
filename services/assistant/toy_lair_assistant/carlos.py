from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

STATUSES = {"done", "partial", "skipped"}
STATUS_RU = {"done": "сделано", "partial": "частично", "skipped": "пропуск"}


@dataclass
class CarlosResult:
    ok: bool
    reply: str = ""
    entry: dict[str, Any] | None = None
    line: str = ""
    action: str = ""


def entry_line(entry: dict[str, Any]) -> str:
    return STATUS_RU.get(str(entry.get("status") or ""), "")


def spoken(entry: dict[str, Any]) -> str:
    status = entry.get("status")
    if status == "skipped":
        return "Отметил пропуск."
    if status == "partial":
        return "Записал частично."
    return "Записал."


def parse_log_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _actual(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    return text or None


def _names(card: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in card.get("exercises") or []:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            continue
        if name:
            names.append(name)
    return names


def normalize_name(name: str) -> str:
    text = (name or "").strip().lower().replace("ё", "е")
    text = re.sub(r"^\d+\.\s*", "", text)
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return " ".join(text.split())


def match_name(spoken: str, names: list[str]) -> str | None:
    key = normalize_name(spoken)
    if not key:
        return None
    for name in names:
        if normalize_name(name) == key:
            return name
    return None


def validate_entry(data: dict[str, Any], text: str, card: dict[str, Any]) -> dict[str, Any] | None:
    status = data.get("status")
    if status not in STATUSES:
        return None
    allowed = _names(card)
    items: list[dict[str, Any]] = []
    raw_items = data.get("items")
    if raw_items is None:
        raw_items = []
    if not isinstance(raw_items, list):
        return None
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = match_name(str(item.get("name") or ""), allowed)
        if name is None:
            continue
        actual = _actual(item.get("actual"))
        if actual is None:
            continue
        items.append({"name": name, "actual": actual})
    return {
        "date": str(card.get("date") or ""),
        "sessionId": str(card.get("sessionId") or ""),
        "status": status,
        "items": items,
        "raw": text,
    }


def _prompt(text: str, card: dict[str, Any]) -> str:
    brief = {
        "date": card.get("date") or "",
        "sessionId": card.get("sessionId") or "",
        "title": card.get("title") or "",
        "exercises": _names(card),
    }
    return (
        "You turn one workout dictation into JSON. Reply with one JSON object and no other text.\n"
        "Keys only: date, sessionId, status, items, raw.\n"
        "Copy date and sessionId from the card.\n"
        "status is done, partial, or skipped.\n"
        "items lists only exercises named on the card, and only numbers spoken aloud.\n"
        'Each item is {"name":"...","actual":"..."}.\n'
        "Do not invent reps. Do not add an exercise that is not on the card.\n"
        "raw is the dictation unchanged.\n"
        'The phrase "Сделал" is status done and items [].\n'
        "Do not change the day's plan.\n"
        f"Card: {json.dumps(brief, ensure_ascii=False)}\n"
        f"Dictation: {text}"
    )


class CarlosAgent:
    def __init__(self, llm: Any, store: Any = None) -> None:
        self.llm = llm
        self.store = store

    def log(self, text: str, card: dict[str, Any]) -> CarlosResult:
        spoken_text = (text or "").strip()
        if not spoken_text:
            return CarlosResult(ok=False)
        result = self.llm.complete(
            [
                {"role": "system", "content": "Reply with JSON only."},
                {"role": "user", "content": _prompt(spoken_text, card)},
            ],
            [],
        )
        data = parse_log_json(getattr(result, "reply", "") or "")
        if data is None:
            return CarlosResult(ok=False)
        entry = validate_entry(data, spoken_text, card)
        if entry is None:
            return CarlosResult(ok=False)
        self._save(entry)
        return CarlosResult(
            ok=True,
            reply=spoken(entry),
            entry=entry,
            line=entry_line(entry),
            action="logged",
        )

    def _save(self, entry: dict[str, Any]) -> None:
        if self.store is None:
            return
        at = datetime.now(UTC)
        log_date = str(entry.get("date") or "")
        raw = str(entry.get("raw") or "")
        if "исправь" in raw.lower():
            if self.store.replace_last_workout_log(log_date, entry, at):
                return
        self.store.append_workout_log(log_date, entry, at)

    def last(self, log_date: str) -> dict[str, Any] | None:
        if self.store is None:
            return None
        entry = self.store.last_workout_log(log_date)
        return entry if isinstance(entry, dict) else None
