from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from toy_lair_assistant.day_plan import plan_buttons, render, render_week

SCHEDULE_RE = re.compile(
    r"(сегодня|завтра|недел|календар|расписан|today|tomorrow|week|calendar|schedule)",
    re.IGNORECASE,
)
WEEK_RE = re.compile(r"(недел|week)", re.IGNORECASE)
TOMORROW_RE = re.compile(r"(завтра|tomorrow)", re.IGNORECASE)
LIST_TOOLS = {"todoist_today", "todoist_upcoming", "gcal_events", "gcal_calendars"}


def schedule_kind(text: str) -> str | None:
    blob = text or ""
    if not SCHEDULE_RE.search(blob):
        return None
    if WEEK_RE.search(blob):
        return "week"
    if TOMORROW_RE.search(blob):
        return "tomorrow"
    return "today"


def looks_like_list(text: str) -> bool:
    raw = (text or "").strip()
    if raw.startswith("/"):
        return False
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return len(lines) >= 2


def short_tito(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    first = re.split(r"[.!?]", raw, 1)[0].strip()
    if "\n" in raw or raw.count(",") >= 2 or len(raw) > 160:
        return first.split(",")[0].strip()
    return raw


def render_schedule_card(planner: Any, agent: Any, kind: str, now: datetime) -> tuple[str, Any]:
    if kind == "week":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tasks = list(agent.todoist.upcoming(7))
        events = list(agent.calendar.events_in_range(start, start + timedelta(days=7)))
        return render_week(now, tasks, events), None
    day = now + timedelta(days=1) if kind == "tomorrow" else now
    if planner is None:
        return "", None
    plan = planner.build(day)
    return render(plan), plan_buttons(plan)
