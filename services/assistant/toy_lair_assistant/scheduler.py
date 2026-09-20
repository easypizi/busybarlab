from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from toy_lair_assistant.clients.telegram import task_buttons
from toy_lair_assistant.models import Task


class Scheduler:
    def __init__(
        self,
        todoist: Any,
        calendar: Any,
        store: Any,
        notify: Any,
        lead_minutes: int = 15,
        briefing_hour: int = 8,
        timezone: str = "America/Los_Angeles",
        settings: Any = None,
        task_sync: Any = None,
    ) -> None:
        self.todoist = todoist
        self.calendar = calendar
        self.store = store
        self.notify = notify
        self.lead_minutes = lead_minutes
        self.briefing_hour = briefing_hour
        self.timezone = timezone
        self.settings = settings
        self.task_sync = task_sync
        self._last_sync: datetime | None = None

    def tick(self, now: datetime) -> int:
        sent = 0
        sent += self._event_leads(now)
        sent += self._task_leads(now)
        sent += self._deadlines(now)
        sent += self._nudges(now)
        sent += self._briefing(now)
        sent += self._custom(now)
        self._maybe_sync(now)
        return sent

    def _send(self, text: str, buttons: list | None = None) -> None:
        if hasattr(self.notify, "send_message"):
            self.notify.send_message(text, buttons=buttons)
            return
        self.notify(text)

    def _maybe_sync(self, now: datetime) -> None:
        if self.task_sync is None:
            return
        interval = float(getattr(self.settings, "task_sync_interval_seconds", 300) or 300)
        if self._last_sync and (now - self._last_sync).total_seconds() < interval:
            return
        self.task_sync.run(now)
        self._last_sync = now

    def _event_leads(self, now: datetime) -> int:
        window_end = now + timedelta(minutes=self.lead_minutes)
        events = self.calendar.events_in_range(now, window_end + timedelta(minutes=1))
        count = 0
        for event in events:
            if getattr(event, "todoist_id", None):
                continue
            start = _as_dt(event.start, now)
            lead = start - timedelta(minutes=self.lead_minutes)
            if now < lead or now > start:
                continue
            key = f"event:{event.id}:{start.date().isoformat()}"
            if self.store.seen(key):
                continue
            self._send(f"Soon: {event.title} at {start.strftime('%H:%M')}")
            self.store.mark(key)
            count += 1
        return count

    def _task_leads(self, now: datetime) -> int:
        minutes = int(getattr(self.settings, "task_lead_minutes", 15) or 15)
        count = 0
        for task in self._open():
            start = _task_start(task, now)
            if start is None:
                continue
            lead = start - timedelta(minutes=minutes)
            if now < lead or now > start:
                continue
            stamp = task.due_time or task.due_date or start.date().isoformat()
            key = f"task:{task.id}:{stamp}"
            if self.store.seen(key):
                continue
            self._send(
                f"Soon: {task.content} at {start.strftime('%H:%M')}",
                buttons=task_buttons(task.id),
            )
            self.store.mark(key)
            count += 1
        return count

    def _deadlines(self, now: datetime) -> int:
        if now.hour != self.briefing_hour:
            return 0
        lead_days = int(getattr(self.settings, "deadline_lead_days", 1) or 1)
        count = 0
        for task in self._open():
            if not task.deadline:
                continue
            day = datetime.fromisoformat(task.deadline[:10]).date()
            delta = (day - now.date()).days
            if delta == lead_days:
                key = f"deadline:{task.id}:{day.isoformat()}:lead"
                text = f"Deadline tomorrow: {task.content}"
            elif delta == 0:
                key = f"deadline:{task.id}:{day.isoformat()}:day"
                text = f"Deadline today: {task.content}"
            else:
                continue
            if self.store.seen(key):
                continue
            self._send(text, buttons=task_buttons(task.id))
            self.store.mark(key)
            count += 1
        return count

    def _nudges(self, now: datetime) -> int:
        label = str(getattr(self.settings, "remind_label", "remind") or "remind").lower()
        hours = int(getattr(self.settings, "remind_nudge_hours", 3) or 3)
        start_h = int(getattr(self.settings, "plan_hours_start", 10) or 10)
        end_h = int(getattr(self.settings, "plan_hours_end", 22) or 22)
        if now.hour < start_h or now.hour >= end_h:
            return 0
        window = now.hour // hours
        count = 0
        for task in self._open():
            names = [item.lower() for item in task.labels]
            if label not in names:
                continue
            key = f"nudge:{task.id}:{now.date().isoformat()}:{window}"
            if self.store.seen(key):
                continue
            self._send(f"Still open: {task.content}", buttons=task_buttons(task.id))
            self.store.mark(key)
            count += 1
        return count

    def _briefing(self, now: datetime) -> int:
        if now.hour != self.briefing_hour:
            return 0
        key = f"briefing:{now.date().isoformat()}"
        if self.store.seen(key):
            return 0
        lines = ["**Briefing**"]
        tasks = self._open()
        overdue = [
            task
            for task in tasks
            if task.due_date and task.due_date < now.date().isoformat()
        ]
        deadlines = [
            task
            for task in tasks
            if task.deadline and task.deadline[:10] <= (now.date() + timedelta(days=1)).isoformat()
        ]
        today = [task for task in tasks if task.due_date == now.date().isoformat()]
        today.sort(key=lambda task: -int(task.priority or 1))
        if overdue:
            lines.append("**Overdue**")
            lines.extend(f"- {task.content}" for task in overdue)
        if deadlines:
            lines.append("**Deadlines**")
            lines.extend(
                f"- {task.content} {task.deadline[:10]}" for task in deadlines
            )
        if today:
            lines.append("**Today**")
            for task in today:
                mark = "🔴 " if int(task.priority or 1) >= 4 else ""
                lines.append(f"- {mark}{task.content}".rstrip())
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        events = [
            event
            for event in self.calendar.events_in_range(start, start + timedelta(days=1))
            if not getattr(event, "todoist_id", None)
        ]
        if events:
            lines.append("**Events**")
            for event in events:
                when = event.start[11:16] if len(event.start) >= 16 else event.start
                lines.append(f"- {event.title} {when}".rstrip())
        self._send("\n".join(lines))
        self.store.mark(key)
        return 1

    def _custom(self, now: datetime) -> int:
        count = 0
        for reminder in self.store.due_reminders(now):
            self._send(reminder.text)
            self.store.mark_sent(reminder.id)
            count += 1
        return count

    def _open(self) -> list[Task]:
        if hasattr(self.todoist, "open_tasks"):
            return list(self.todoist.open_tasks())
        return list(self.todoist.today())


def _as_dt(value: str, now: datetime) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=now.tzinfo or ZoneInfo("UTC"))
    return parsed


def _task_start(task: Task, now: datetime) -> datetime | None:
    raw = task.due_time
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=now.tzinfo or ZoneInfo("UTC"))
    return parsed
