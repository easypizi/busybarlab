from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

WEEKDAY_SHORT = {
    "mon": "пн",
    "tue": "вт",
    "wed": "ср",
    "thu": "чт",
    "fri": "пт",
    "sat": "сб",
    "sun": "вс",
}


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _iso(day: date) -> str:
    return day.isoformat()


def _add(day: date, count: int) -> date:
    return day + timedelta(days=count)


def load_days(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    days = data.get("days") if isinstance(data, dict) else None
    if not isinstance(days, list):
        return []
    return [day for day in days if isinstance(day, dict) and day.get("date")]


def render_week(days: list[dict[str, Any]], logs: list[dict[str, Any]], monday: date) -> str:
    by_date = {str(day["date"]): day for day in days}
    dates = [_iso(_add(monday, offset)) for offset in range(7)]
    current = [by_date[item] for item in dates if item in by_date]
    if len(current) != 7:
        return ""
    logged = {str(item.get("date") or "") for item in logs}
    done = sum(1 for item in dates if item in logged)
    empty = [WEEKDAY_SHORT[by_date[item]["weekday"]] for item in dates if item not in logged]
    head = current[0]
    lines = [
        f"Неделя {head['week']}, {head['block']}.",
        f"Записано {done} из 7.",
    ]
    if empty:
        lines.append("Пусто: " + ", ".join(empty) + ".")
    else:
        lines.append("Пустых дней нет.")
    nxt_dates = [_iso(_add(monday, 7 + offset)) for offset in range(7)]
    nxt = [by_date[item] for item in nxt_dates if item in by_date]
    if len(nxt) == 7:
        titles = ", ".join(
            f"{WEEKDAY_SHORT[day['weekday']]} {day['title']}" for day in nxt
        )
        lines.append("Дальше: " + titles + ".")
        if nxt[0].get("deload"):
            lines.append("Разгрузка.")
    return "\n".join(lines)


def maybe_send(
    now: datetime,
    store: Any,
    notify: Any,
    days_path: Path,
    hour: int,
) -> bool:
    if now.weekday() != 6 or now.hour != hour:
        return False
    monday = monday_of(now.date())
    key = f"carlos_week:{monday.isoformat()}"
    if store.seen(key):
        return False
    days = load_days(days_path)
    if not days:
        return False
    logs = store.workout_logs_between(monday.isoformat(), _iso(_add(monday, 6)))
    text = render_week(days, logs, monday)
    if not text:
        return False
    notify(text)
    store.mark(key)
    return True
