from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from toy_lair_assistant.models import CalendarEvent, Task


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class AgentResult:
    reply: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class Agent:
    def __init__(
        self,
        todoist: Any,
        calendar: Any,
        llm: Any,
        now: Callable[[], datetime],
        store: Any = None,
        zayka: Any = None,
    ) -> None:
        self.todoist = todoist
        self.calendar = calendar
        self.llm = llm
        self.now = now
        self.store = store
        self.zayka = zayka
        self.tools = {
            "todoist_today": self._todoist_today,
            "todoist_add": self._todoist_add,
            "todoist_complete": self._todoist_complete,
            "todoist_update": self._todoist_update,
            "todoist_reschedule": self._todoist_reschedule,
            "gcal_events": self._gcal_events,
            "gcal_create": self._gcal_create,
            "gcal_move": self._gcal_move,
            "gcal_delete": self._gcal_delete,
            "reminder": self._reminder,
            "zayka_search": self._zayka_search,
            "zayka_read": self._zayka_read,
        }

    def today_payload(self, now: datetime) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for event in self.calendar.events_for_day(now):
            items.append(self._event_item(event))
        for task in self.todoist.today():
            items.append(self._task_item(task))
        return {"items": items}

    def handle_text(self, text: str, channel: str = "r1") -> AgentResult:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a personal assistant for Todoist and Google Calendar. "
                    "Use tools to change data. Reply briefly."
                ),
            },
            {"role": "user", "content": text},
        ]
        result = self.llm.complete(messages, list(self.tools))
        notes: list[str] = []
        for call in result.tool_calls:
            handler = self.tools.get(call.name)
            if handler is None:
                notes.append(f"unknown tool {call.name}")
                continue
            notes.append(str(handler(**call.arguments)))
        reply = result.reply
        if notes and reply:
            return AgentResult(reply=reply, tool_calls=result.tool_calls)
        if notes and not reply:
            return AgentResult(reply="\n".join(notes), tool_calls=result.tool_calls)
        return AgentResult(reply=reply or "ok", tool_calls=result.tool_calls)

    def _task_item(self, task: Task) -> dict[str, Any]:
        return {
            "id": task.id,
            "kind": "task",
            "title": task.content,
            "when": task.due_string or task.due_date or "",
        }

    def _event_item(self, event: CalendarEvent) -> dict[str, Any]:
        when = event.start[11:16] if len(event.start) >= 16 else event.start
        return {"id": event.id, "kind": "event", "title": event.title, "when": when}

    def _todoist_today(self) -> str:
        tasks = self.todoist.today()
        if not tasks:
            return "No tasks today."
        return "\n".join(f"- {t.content}" for t in tasks)

    def _todoist_add(self, content: str, due_string: str | None = None) -> str:
        task = self.todoist.add(content, due_string=due_string)
        return f"Added {task.content}."

    def _todoist_complete(self, task_id: str) -> str:
        self.todoist.complete(task_id)
        return f"Completed {task_id}."

    def _todoist_update(self, task_id: str, content: str) -> str:
        self.todoist.update(task_id, content=content)
        return f"Updated {task_id}."

    def _todoist_reschedule(self, task_id: str, due_string: str) -> str:
        self.todoist.reschedule(task_id, due_string)
        return f"Rescheduled {task_id} to {due_string}."

    def _gcal_events(self, day: str | None = None) -> str:
        events = self.calendar.events_for_day()
        if not events:
            return "No events."
        return "\n".join(f"- {e.title} {e.start}" for e in events)

    def _gcal_create(self, title: str, start: str, end: str) -> str:
        event = self.calendar.create(title=title, start=start, end=end)
        return f"Created {event.title}."

    def _gcal_move(self, event_id: str, start: str, end: str) -> str:
        event = self.calendar.move(event_id, start=start, end=end)
        return f"Moved {event.title}."

    def _gcal_delete(self, event_id: str) -> str:
        self.calendar.delete(event_id)
        return f"Deleted {event_id}."

    def _reminder(self, fire_at: str, text: str) -> str:
        if self.store is None:
            return "Reminders are not configured."
        self.store.add_reminder(fire_at.replace(":", "").replace("-", "")[:16], _parse_dt(fire_at), text)
        return f"Reminder set for {fire_at}."

    def _zayka_search(self, query: str) -> str:
        if self.zayka is None:
            return "Zayka is not configured."
        hits = self.zayka.search(query)
        if not hits:
            return "No notes."
        return "\n".join(f"- {hit.path}: {hit.snippet}" for hit in hits[:8])

    def _zayka_read(self, path: str) -> str:
        if self.zayka is None:
            return "Zayka is not configured."
        return self.zayka.read(path)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)
