"""Countdown: nearest RU or US holiday, or nearest friend birthday from Todoist."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import holidays

BIRTHDAY_PROJECT = "Friends & Family"
EXTRA_US = {(10, 31): "Halloween", (2, 14): "Valentine's Day", (12, 24): "Christmas Eve"}
EXTRA_RU = {(1, 7): "Orthodox Christmas", (3, 8): "International Women's Day"}

_TABLE = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(text: str) -> str:
    out = []
    for ch in text:
        low = ch.lower()
        if low in _TABLE:
            piece = _TABLE[low]
            out.append(piece.capitalize() if ch != low else piece)
        else:
            out.append(ch)
    return "".join(out)


def _holiday_dates(today: date) -> list[tuple[date, str]]:
    found: list[tuple[date, str]] = []
    years = [today.year, today.year + 1]
    for country, extra in (("US", EXTRA_US), ("RU", EXTRA_RU)):
        try:
            table = holidays.country_holidays(country, years=years, language="en_US")
        except Exception:
            table = holidays.country_holidays(country, years=years)
        for day, name in table.items():
            found.append((day, str(name).split(" (observed)")[0]))
        for year in years:
            for (month, dom), name in extra.items():
                found.append((date(year, month, dom), name))
    return found


def birthdays(tasks: list[Any]) -> list[tuple[date, str]]:
    out = []
    for task in tasks:
        if getattr(task, "project", None) != BIRTHDAY_PROJECT or not task.due_date:
            continue
        if "year" not in (task.due_string or "").lower():
            continue
        out.append((date.fromisoformat(task.due_date), f"{translit(task.content).strip()}'s birthday"))
    return out


def nearest(today: date, tasks: list[Any]) -> dict:
    options = [(d, label, 0) for d, label in birthdays(tasks)]
    options += [(d, label, 1) for d, label in _holiday_dates(today)]
    upcoming = [item for item in options if item[0] >= today]
    if not upcoming:
        return {"days": None, "label": "", "text": ""}
    upcoming.sort(key=lambda item: (item[0], item[2]))
    day, label, _ = upcoming[0]
    days = (day - today).days
    if days == 0:
        text = f"Today: {label}"
    elif days == 1:
        text = f"Tomorrow: {label}"
    else:
        text = f"{days} days to {label}"
    return {"days": days, "label": label, "text": text, "date": day.isoformat()}
