from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from toy_lair_assistant.clients.gcal import GoogleAuthExpired
from toy_lair_assistant.models import CalendarEvent, Task

CONFIRM_RE = re.compile(r"\b(yes|yep|yeah|confirm|да|ок|ok)\b", re.IGNORECASE)
DESTRUCTIVE = {"gcal_delete"}


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str = ""


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
        for index, event in enumerate(self.calendar.events_for_day(now), start=1):
            item = self._event_item(event)
            item["ref"] = f"e{index}"
            items.append(item)
        for index, task in enumerate(self.todoist.today(), start=1):
            item = self._task_item(task)
            item["ref"] = f"t{index}"
            items.append(item)
        return {"items": items}

    def handle_text(self, text: str, channel: str = "r1") -> AgentResult:
        now = self.now()
        try:
            events, tasks, task_map, event_map = self._catalog(now)
        except GoogleAuthExpired:
            return AgentResult(reply="Calendar auth expired.")
        system = self._system_prompt(now, tasks, events)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if self.store is not None and hasattr(self.store, "recent_turns"):
            for turn in self.store.recent_turns(channel, now, limit=6, ttl_minutes=15):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": text})
        confirmed = self._confirmed(text, messages)
        last = AgentResult(reply="ok")
        for _round in range(3):
            last = self.llm.complete(messages, list(self.tools))
            if not last.tool_calls:
                break
            blocked, notes, executed = self._run_tools(
                last.tool_calls, task_map, event_map, confirmed
            )
            if blocked:
                last = AgentResult(reply=blocked, tool_calls=last.tool_calls)
                break
            messages.append(self._assistant_tool_message(last))
            for call, note in zip(executed, notes):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.call_id or call.name,
                        "content": note,
                    }
                )
        reply = last.reply or "ok"
        self._remember(channel, text, reply, now)
        return AgentResult(reply=reply, tool_calls=last.tool_calls)

    def _catalog(
        self, now: datetime
    ) -> tuple[list[CalendarEvent], list[Task], dict[str, str], dict[str, str]]:
        events = list(self.calendar.events_for_day(now))
        tasks = list(self.todoist.today())
        task_map = {f"t{i}": task.id for i, task in enumerate(tasks, start=1)}
        event_map = {f"e{i}": event.id for i, event in enumerate(events, start=1)}
        return events, tasks, task_map, event_map

    def _system_prompt(
        self, now: datetime, tasks: list[Task], events: list[CalendarEvent]
    ) -> str:
        zone = getattr(now.tzinfo, "key", None) or str(now.tzinfo or "UTC")
        lines = [
            "You are a personal assistant for Todoist and Google Calendar.",
            f"Now: {now.strftime('%Y-%m-%d %H:%M')} {zone}.",
            "Reply briefly for speech. One or two sentences.",
            "Refer to tasks as t1, t2 and events as e1, e2. Use tools to change data.",
            "Deleting events or completing more than one task needs a confirm word.",
            "Tasks:",
        ]
        if not tasks:
            lines.append("(none)")
        for index, task in enumerate(tasks, start=1):
            when = task.due_string or task.due_date or ""
            lines.append(f"t{index} {task.content} {when} id={task.id}".strip())
        lines.append("Events:")
        if not events:
            lines.append("(none)")
        for index, event in enumerate(events, start=1):
            when = event.start[11:16] if len(event.start) >= 16 else event.start
            lines.append(f"e{index} {event.title} {when} id={event.id}".strip())
        return "\n".join(lines)

    def _confirmed(self, text: str, messages: list[dict[str, Any]]) -> bool:
        blob = " ".join(
            str(m.get("content") or "")
            for m in messages
            if m.get("role") == "user"
        )
        blob = f"{blob} {text}"
        return bool(CONFIRM_RE.search(blob))

    def _run_tools(
        self,
        calls: list[ToolCall],
        task_map: dict[str, str],
        event_map: dict[str, str],
        confirmed: bool,
    ) -> tuple[str | None, list[str], list[ToolCall]]:
        completes = sum(1 for call in calls if call.name == "todoist_complete")
        needs_confirm = any(call.name in DESTRUCTIVE for call in calls) or completes > 1
        if needs_confirm and not confirmed:
            return ("Say confirm to delete that event.", [], [])
        notes: list[str] = []
        executed: list[ToolCall] = []
        for index, call in enumerate(calls):
            if not call.call_id:
                call.call_id = f"call{index}"
            handler = self.tools.get(call.name)
            if handler is None:
                notes.append(f"unknown tool {call.name}")
                executed.append(call)
                continue
            args = self._resolve(call.arguments, task_map, event_map)
            notes.append(str(handler(**args)))
            executed.append(call)
        return (None, notes, executed)

    def _resolve(
        self,
        arguments: dict[str, Any],
        task_map: dict[str, str],
        event_map: dict[str, str],
    ) -> dict[str, Any]:
        out = dict(arguments)
        if "task_id" in out:
            key = str(out["task_id"])
            out["task_id"] = task_map.get(key, key)
        if "event_id" in out:
            key = str(out["event_id"])
            out["event_id"] = event_map.get(key, key)
        return out

    def _assistant_tool_message(self, result: AgentResult) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": result.reply or None,
            "tool_calls": [
                {
                    "id": call.call_id or call.name,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }
                for call in result.tool_calls
            ],
        }

    def _remember(self, channel: str, user: str, reply: str, now: datetime) -> None:
        if self.store is None or not hasattr(self.store, "add_turn"):
            return
        self.store.add_turn(channel, "user", user, now)
        self.store.add_turn(channel, "assistant", reply, now)

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
        self.store.add_reminder(
            fire_at.replace(":", "").replace("-", "")[:16], _parse_dt(fire_at), text
        )
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
