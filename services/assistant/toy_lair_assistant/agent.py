from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from toy_lair_assistant.clients.gcal import GoogleAuthExpired
from toy_lair_assistant.models import CalendarEvent, Task
from toy_lair_assistant.planner import format_slots, free_slots
from toy_lair_assistant.settings import Settings

CONFIRM_RE = re.compile(
    r"\b(yes|yep|yeah|confirm|ok|ок|давай|подтверждаю|да)\b",
    re.IGNORECASE,
)
DESTRUCTIVE = {"gcal_delete", "plan_apply"}
LOG = logging.getLogger("toy_lair_assistant")


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str = ""


@dataclass
class AgentResult:
    reply: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    used_tools: list[str] = field(default_factory=list)


def invoke_agent(
    agent: Any,
    text: str,
    channel: str = "r1",
    notify: Any = None,
) -> AgentResult:
    started = time.perf_counter()
    result = agent.handle_text(text, channel=channel)
    ms = int((time.perf_counter() - started) * 1000)
    tools = [call.name for call in getattr(result, "tool_calls", []) or []]
    LOG.info("agent channel=%s tools=%s ms=%s", channel, tools, ms)
    if channel == "r1" and notify is not None:
        from toy_lair_assistant.cards import render_schedule_card, schedule_kind, short_tito

        kind = schedule_kind(text)
        used = set(getattr(result, "used_tools", []) or [])
        from toy_lair_assistant.cards import LIST_TOOLS

        if kind or used & LIST_TOOLS:
            planner = getattr(notify, "day_planner", None)
            card, _buttons = render_schedule_card(planner, agent, kind or "today", agent.now())
            note = short_tito(getattr(result, "reply", "") or "")
            body = "\n".join(part for part in (card, note) if part)
            if body:
                notify.send_text(body)
    return result


class Agent:
    def __init__(
        self,
        todoist: Any,
        calendar: Any,
        llm: Any,
        now: Callable[[], datetime],
        store: Any = None,
        zayka: Any = None,
        settings: Settings | None = None,
        task_sync: Any = None,
    ) -> None:
        self.todoist = todoist
        self.calendar = calendar
        self.llm = llm
        self.now = now
        self.store = store
        self.zayka = zayka
        self.settings = settings or Settings()
        self.task_sync = task_sync
        self.tools = {
            "todoist_today": self._todoist_today,
            "todoist_add": self._todoist_add,
            "todoist_complete": self._todoist_complete,
            "todoist_update": self._todoist_update,
            "todoist_reschedule": self._todoist_reschedule,
            "todoist_upcoming": self._todoist_upcoming,
            "gcal_events": self._gcal_events,
            "gcal_calendars": self._gcal_calendars,
            "gcal_create": self._gcal_create,
            "gcal_move": self._gcal_move,
            "gcal_delete": self._gcal_delete,
            "free_slots": self._free_slots,
            "plan_apply": self._plan_apply,
            "reminder": self._reminder,
            "zayka_search": self._zayka_search,
            "zayka_read": self._zayka_read,
        }

    def today_payload(self, now: datetime) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for index, event in enumerate(self._visible_events(now), start=1):
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
        system = self._system_prompt(now, tasks, events, channel)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if self.store is not None and hasattr(self.store, "recent_turns"):
            for turn in self.store.recent_turns(channel, now, limit=6, ttl_minutes=15):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": text})
        confirmed = self._confirmed(text, messages)
        last = AgentResult(reply="ok")
        used_tools: list[str] = []
        for _round in range(4):
            last = self.llm.complete(messages, list(self.tools))
            if not last.tool_calls:
                break
            used_tools.extend(call.name for call in last.tool_calls)
            blocked, notes, executed = self._run_tools(
                last.tool_calls, task_map, event_map, confirmed
            )
            if blocked:
                last = AgentResult(reply=blocked, tool_calls=last.tool_calls, used_tools=used_tools)
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
        return AgentResult(reply=reply, tool_calls=last.tool_calls, used_tools=used_tools)

    def _catalog(
        self, now: datetime
    ) -> tuple[list[CalendarEvent], list[Task], dict[str, str], dict[str, str]]:
        events = self._visible_events(now)
        tasks = list(self.todoist.today())
        task_map = {f"t{i}": task.id for i, task in enumerate(tasks, start=1)}
        event_map = {f"e{i}": event.id for i, event in enumerate(events, start=1)}
        return events, tasks, task_map, event_map

    def _visible_events(self, now: datetime) -> list[CalendarEvent]:
        return [
            event
            for event in self.calendar.events_for_day(now)
            if not getattr(event, "todoist_id", None)
        ]

    def _system_prompt(
        self,
        now: datetime,
        tasks: list[Task],
        events: list[CalendarEvent],
        channel: str = "r1",
    ) -> str:
        zone = getattr(now.tzinfo, "key", None) or str(now.tzinfo or "UTC")
        from toy_lair_assistant.profile import profile_text

        lines = [
            "You are Tito, a laid-back Californian butler. Warm, short, no fuss.",
            "Never delete Todoist tasks: close with todoist_complete or reschedule.",
            f"Now: {now.strftime('%Y-%m-%d %H:%M')} {zone}.",
            profile_text(self.settings),
            "Refer to tasks as t1, t2 and events as e1, e2. Use tools to change data.",
            "Deleting events or completing more than one task needs a confirm word.",
            "If the user dictates several to-dos, call free_slots and todoist_upcoming first, propose a day-and-time plan, then wait for a confirm word before plan_apply.",
        ]
        if channel == "telegram":
            lines.extend(
                [
                    "Telegram: use **headers** and - lists. Never list tasks in one comma sentence.",
                    "Do not recite every recurring ritual unless asked. One next step, not 'what next?'.",
                ]
            )
        else:
            lines.extend(
                [
                    "Reply briefly for speech. One or two sentences.",
                    "Plain text only, for speech. Do not read the catalog. If the list is long, point to the Telegram card.",
                ]
            )
        names = self._calendar_names()
        lines.append("Calendars: " + (", ".join(names) if names else "(none)"))
        nxt = self._next_event(now)
        lines.append(f"Next: {nxt}" if nxt else "Next: (none)")
        lines.append("Events: today only. For other days call gcal_events.")
        lines.append("Tasks:")
        if not tasks:
            lines.append("(none)")
        for index, task in enumerate(tasks, start=1):
            lines.append(f"t{index} {_task_line(task)} id={task.id}".strip())
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
            if any(call.name == "plan_apply" for call in calls):
                return ("Say confirm to apply the plan.", [], [])
            return ("Say confirm to delete that event.", [], [])
        notes: list[str] = []
        executed: list[ToolCall] = []
        for index, call in enumerate(calls):
            if not call.call_id:
                call.call_id = f"call{index}"
            if call.name.startswith("todoist_") and "delete" in call.name:
                notes.append("Tito does not delete tasks")
                executed.append(call)
                continue
            handler = self.tools.get(call.name)
            if handler is None:
                if call.name.startswith("todoist_"):
                    notes.append("Tito does not delete tasks")
                else:
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
            "priority": task.priority,
        }

    def _event_item(self, event: CalendarEvent) -> dict[str, Any]:
        when = event.start[11:16] if len(event.start) >= 16 else event.start
        return {"id": event.id, "kind": "event", "title": event.title, "when": when}

    def _end_iso(self, start: str, duration_minutes: int) -> str:
        return (datetime.fromisoformat(start) + timedelta(minutes=duration_minutes)).isoformat()

    def _todoist_today(self) -> str:
        tasks = self.todoist.today()
        if not tasks:
            return "No tasks today."
        return "\n".join(f"- {t.content}" for t in tasks)

    def _todoist_add(
        self,
        content: str,
        due_string: str | None = None,
        due_datetime: str | None = None,
        priority: int | None = None,
        labels: Any = None,
        deadline: str | None = None,
        description: str | None = None,
        duration_minutes: int | None = None,
        project: str | None = None,
    ) -> str:
        task = self.todoist.add(
            content,
            due_string=due_string,
            due_datetime=due_datetime,
            priority=priority,
            labels=labels,
            deadline=deadline,
            description=description,
            duration_minutes=duration_minutes,
            project=project,
        )
        return f"Added {task.content}."

    def _todoist_complete(self, task_id: str) -> str:
        self.todoist.complete(task_id)
        return f"Completed {task_id}."

    def _todoist_update(
        self,
        task_id: str,
        content: str | None = None,
        priority: int | None = None,
        labels: Any = None,
        deadline: str | None = None,
        description: str | None = None,
        duration_minutes: int | None = None,
        due_string: str | None = None,
        due_datetime: str | None = None,
        project: str | None = None,
    ) -> str:
        fields: dict[str, Any] = {}
        if content is not None:
            fields["content"] = content
        if priority is not None:
            fields["priority"] = priority
        if labels is not None:
            fields["labels"] = labels
        if deadline is not None:
            fields["deadline"] = deadline
        if description is not None:
            fields["description"] = description
        if duration_minutes is not None:
            fields["duration_minutes"] = duration_minutes
        if due_string is not None:
            fields["due_string"] = due_string
        if due_datetime is not None:
            fields["due_datetime"] = due_datetime
        if project is not None:
            fields["project"] = project
        self.todoist.update(task_id, **fields)
        return f"Updated {task_id}."

    def _todoist_reschedule(self, task_id: str, due_string: str) -> str:
        self.todoist.reschedule(task_id, due_string)
        return f"Rescheduled {task_id} to {due_string}."

    def _todoist_upcoming(self, days: int = 7) -> str:
        tasks = self.todoist.upcoming(int(days))
        if not tasks:
            return "No upcoming tasks."
        lines = []
        for task in tasks:
            when = task.due_string or task.due_date or ""
            lines.append(f"- {task.content} {when}".strip())
        return "\n".join(lines)

    def _gcal_events(self, days: int = 1, day: str | None = None) -> str:
        now = self.now()
        horizon = max(1, min(int(days or 1), 7))
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        events = [
            event
            for event in self.calendar.events_in_range(start, start + timedelta(days=horizon))
            if not getattr(event, "todoist_id", None)
        ]
        if not events:
            return "No events."
        return "\n".join(f"- {event.title} {event.start}" for event in events)

    def _gcal_calendars(self) -> str:
        names = self._calendar_names()
        if not names:
            return "No calendars."
        return "\n".join(f"- {name}" for name in names)

    def _calendar_names(self) -> list[str]:
        if not hasattr(self.calendar, "calendars"):
            return []
        try:
            items = list(self.calendar.calendars())
        except Exception:
            return []
        names = []
        for item in items:
            if item.get("hidden"):
                continue
            name = str(item.get("summary") or item.get("id") or "").strip()
            if not name:
                continue
            if name == "Tito":
                names.append("Tito (task mirror)")
            else:
                names.append(name)
        return names

    def _next_event(self, now: datetime) -> str:
        start = now
        end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=7)
        try:
            events = [
                event
                for event in self.calendar.events_in_range(start, end)
                if not getattr(event, "todoist_id", None)
            ]
        except Exception:
            return ""
        if not events:
            return ""
        event = events[0]
        when = _parse_dt(event.start)
        from toy_lair_assistant.planner import WEEKDAYS

        return f"{WEEKDAYS[when.weekday()]} {when.strftime('%m-%d %H:%M')} {event.title}"

    def _gcal_create(
        self,
        title: str,
        start: str,
        end: str | None = None,
        attendees: Any = None,
        description: str | None = None,
        duration_minutes: int | None = None,
    ) -> str:
        if not end:
            minutes = int(duration_minutes or self.settings.plan_default_minutes)
            end = self._end_iso(start, minutes)
        event = self.calendar.create(
            title=title,
            start=start,
            end=end,
            attendees=attendees,
            description=description,
        )
        return f"Created {event.title}."

    def _gcal_move(self, event_id: str, start: str, end: str) -> str:
        event = self.calendar.move(event_id, start=start, end=end)
        return f"Moved {event.title}."

    def _gcal_delete(self, event_id: str) -> str:
        self.calendar.delete(event_id)
        return f"Deleted {event_id}."

    def _free_slots(self, days: int | None = None) -> str:
        now = self.now()
        horizon = int(days or self.settings.plan_horizon_days)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        events = self.calendar.events_in_range(start, start + timedelta(days=horizon))
        slots = free_slots(events, now, self.settings, horizon_days=horizon)
        text = format_slots(slots)
        return text or "No free slots."

    def _plan_apply(self, items: Any) -> str:
        if isinstance(items, str):
            items = json.loads(items)
        planned = 0
        events = 0
        default = int(self.settings.plan_default_minutes)
        for item in items or []:
            content = str(item.get("content") or "").strip()
            start = str(item.get("start") or "").strip()
            if not content or not start:
                continue
            minutes = int(item.get("duration_minutes") or default)
            self.todoist.add(content, due_datetime=start, duration_minutes=minutes)
            planned += 1
        if planned and self.task_sync is not None:
            self.task_sync.run(self.now())
            events = planned
        return f"Planned {planned} items, {events} events."

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


def _task_line(task: Task) -> str:
    bits = [task.content]
    when = task.due_string or (task.due_time[11:16] if task.due_time and len(task.due_time) >= 16 else "") or task.due_date or ""
    if when:
        bits.append(when)
    if int(task.priority or 1) >= 4:
        bits.append("p1")
    elif int(task.priority or 1) == 3:
        bits.append("p2")
    bits.extend(f"@{label}" for label in task.labels)
    if task.deadline:
        bits.append(f"deadline {task.deadline[5:10] if len(task.deadline) >= 10 else task.deadline}")
    if task.duration_minutes:
        bits.append(f"{task.duration_minutes}m")
    return " ".join(bits)
