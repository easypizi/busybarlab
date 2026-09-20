from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from toy_lair_assistant.models import Task


class TaskSync:
    def __init__(self, todoist: Any, calendar: Any, settings: Any) -> None:
        self.todoist = todoist
        self.calendar = calendar
        self.settings = settings

    def run(self, now: datetime) -> dict[str, int]:
        calendar_id = self.calendar.ensure_calendar("Tito")
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=14)
        zone = str(getattr(self.settings, "timezone", "America/Los_Angeles") or "America/Los_Angeles")
        timed = [
            task
            for task in self.todoist.open_tasks()
            if _has_time(task) and _in_window(task, start, end, zone)
        ]
        existing = self.calendar.events_in_calendar(calendar_id, start, end)
        by_task = {
            event.todoist_id: event
            for event in existing
            if event.todoist_id
        }
        created = updated = deleted = 0
        seen: set[str] = set()
        default = int(getattr(self.settings, "plan_default_minutes", 60))
        for task in timed:
            seen.add(task.id)
            event_start, event_end = _span(task, default, zone)
            current = by_task.get(task.id)
            if current and _same(current, task.content, event_start, event_end):
                continue
            self.calendar.upsert_task_event(
                calendar_id, task.id, task.content, event_start, event_end
            )
            if current:
                updated += 1
            else:
                created += 1
        for todoist_id, event in by_task.items():
            if todoist_id in seen:
                continue
            self.calendar.delete_task_event(calendar_id, event.id)
            deleted += 1
        return {"created": created, "updated": updated, "deleted": deleted}


def _has_time(task: Task) -> bool:
    return bool(task.due_time)


def _in_window(
    task: Task, start: datetime, end: datetime, timezone: str = "America/Los_Angeles"
) -> bool:
    moment = _start(task, timezone)
    if moment is None:
        return False
    return start <= moment < end


def _start(task: Task, timezone: str = "America/Los_Angeles") -> datetime | None:
    raw = task.due_time or ""
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo(timezone))
    return parsed


def _span(
    task: Task, default_minutes: int, timezone: str = "America/Los_Angeles"
) -> tuple[str, str]:
    start = _start(task, timezone)
    if start is None:
        raise ValueError("task has no time")
    minutes = int(task.duration_minutes or default_minutes)
    finish = start + timedelta(minutes=minutes)
    return start.isoformat(), finish.isoformat()


def _same(event: Any, title: str, start: str, end: str) -> bool:
    return event.title == title and event.start == start and event.end == end
