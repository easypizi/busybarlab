from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any


class Scheduler:
    def __init__(
        self,
        todoist: Any,
        calendar: Any,
        store: Any,
        notify: Callable[[str], None],
        lead_minutes: int = 15,
        briefing_hour: int = 8,
        timezone: str = "America/Los_Angeles",
    ) -> None:
        self.todoist = todoist
        self.calendar = calendar
        self.store = store
        self.notify = notify
        self.lead_minutes = lead_minutes
        self.briefing_hour = briefing_hour
        self.timezone = timezone

    def tick(self, now: datetime) -> int:
        sent = 0
        sent += self._event_leads(now)
        sent += self._briefing(now)
        sent += self._custom(now)
        return sent

    def _event_leads(self, now: datetime) -> int:
        window_end = now + timedelta(minutes=self.lead_minutes)
        events = self.calendar.events_in_range(now, window_end + timedelta(minutes=1))
        count = 0
        for event in events:
            start = _as_dt(event.start, now)
            lead = start - timedelta(minutes=self.lead_minutes)
            if now < lead or now > start:
                continue
            key = f"event:{event.id}:{start.date().isoformat()}"
            if self.store.seen(key):
                continue
            self.notify(f"Soon: {event.title} at {start.strftime('%H:%M')}")
            self.store.mark(key)
            count += 1
        return count

    def _briefing(self, now: datetime) -> int:
        if now.hour != self.briefing_hour:
            return 0
        key = f"briefing:{now.date().isoformat()}"
        if self.store.seen(key):
            return 0
        lines = ["Briefing"]
        for task in self.todoist.today():
            lines.append(f"- {task.content}")
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for event in self.calendar.events_in_range(start, start + timedelta(days=1)):
            lines.append(f"- {event.title}")
        self.notify("\n".join(lines))
        self.store.mark(key)
        return 1

    def _custom(self, now: datetime) -> int:
        count = 0
        for reminder in self.store.due_reminders(now):
            self.notify(reminder.text)
            self.store.mark_sent(reminder.id)
            count += 1
        return count


def _as_dt(value: str, now: datetime) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=now.tzinfo or ZoneInfo("UTC"))
    return parsed
