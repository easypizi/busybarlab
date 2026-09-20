from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from toy_lair_assistant.models import CalendarEvent, Task
from toy_lair_assistant.planner import WEEKDAYS, Slot, format_slots, free_slots


MIN_MINUTES = 15
MAX_MINUTES = 180


@dataclass
class FixedBlock:
    task: Task
    start: datetime
    minutes: int


@dataclass
class SuggestedSlot:
    task_id: str
    content: str
    start: datetime
    minutes: int
    why: str = ""
    priority: int = 1


@dataclass
class DayPlan:
    plan_id: str
    date: datetime
    events: list[CalendarEvent] = field(default_factory=list)
    fixed: list[FixedBlock] = field(default_factory=list)
    suggested: list[SuggestedSlot] = field(default_factory=list)
    anytime: list[Task] = field(default_factory=list)


def _zone(now: datetime, settings: Any) -> ZoneInfo | Any:
    if now.tzinfo is not None:
        return now.tzinfo
    return ZoneInfo(getattr(settings, "timezone", "UTC"))


def _parse_dt(value: str, zone) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def _minutes(task: Task, settings: Any) -> int:
    raw = task.duration_minutes or getattr(settings, "plan_default_minutes", 60) or 60
    return int(raw)


def _busy_event(block_id: str, title: str, start: datetime, minutes: int) -> CalendarEvent:
    end = start + timedelta(minutes=minutes)
    return CalendarEvent(
        id=block_id,
        title=title,
        start=start.isoformat(),
        end=end.isoformat(),
    )


def _parse_llm(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
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


def _fits(start: datetime, end: datetime, windows: list[Slot]) -> bool:
    return any(window.start <= start and end <= window.end for window in windows)


def _overlaps(start: datetime, end: datetime, taken: list[tuple[datetime, datetime]]) -> bool:
    return any(start < other_end and other_start < end for other_start, other_end in taken)


def plan_to_payload(plan: DayPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "date": plan.date.isoformat(),
        "events": [
            {
                "id": event.id,
                "title": event.title,
                "start": event.start,
                "end": event.end,
                "todoist_id": event.todoist_id,
            }
            for event in plan.events
        ],
        "fixed": [
            {
                "task_id": block.task.id,
                "content": block.task.content,
                "start": block.start.isoformat(),
                "minutes": block.minutes,
                "priority": block.task.priority,
            }
            for block in plan.fixed
        ],
        "suggested": [
            {
                "task_id": item.task_id,
                "content": item.content,
                "start": item.start.isoformat(),
                "minutes": item.minutes,
                "why": item.why,
                "priority": item.priority,
            }
            for item in plan.suggested
        ],
        "anytime": [
            {
                "id": task.id,
                "content": task.content,
                "priority": task.priority,
                "is_recurring": task.is_recurring,
            }
            for task in plan.anytime
        ],
    }


def plan_from_payload(payload: dict[str, Any]) -> DayPlan:
    date = datetime.fromisoformat(str(payload["date"]))
    events = [
        CalendarEvent(
            id=str(raw.get("id") or ""),
            title=str(raw.get("title") or ""),
            start=str(raw.get("start") or ""),
            end=str(raw.get("end") or ""),
            todoist_id=raw.get("todoist_id"),
        )
        for raw in payload.get("events") or []
    ]
    fixed = [
        FixedBlock(
            task=Task(
                id=str(raw.get("task_id") or ""),
                content=str(raw.get("content") or ""),
                priority=int(raw.get("priority") or 1),
            ),
            start=datetime.fromisoformat(str(raw["start"])),
            minutes=int(raw.get("minutes") or 60),
        )
        for raw in payload.get("fixed") or []
    ]
    suggested = [
        SuggestedSlot(
            task_id=str(raw.get("task_id") or ""),
            content=str(raw.get("content") or ""),
            start=datetime.fromisoformat(str(raw["start"])),
            minutes=int(raw.get("minutes") or 60),
            why=str(raw.get("why") or ""),
            priority=int(raw.get("priority") or 1),
        )
        for raw in payload.get("suggested") or []
    ]
    anytime = [
        Task(
            id=str(raw.get("id") or ""),
            content=str(raw.get("content") or ""),
            priority=int(raw.get("priority") or 1),
            is_recurring=bool(raw.get("is_recurring")),
        )
        for raw in payload.get("anytime") or []
    ]
    return DayPlan(
        plan_id=str(payload.get("plan_id") or ""),
        date=date,
        events=events,
        fixed=fixed,
        suggested=suggested,
        anytime=anytime,
    )


def _mark(priority: int) -> str:
    return "🔴 " if int(priority or 1) >= 4 else ""


def _span(start: datetime, minutes: int) -> str:
    end = start + timedelta(minutes=minutes)
    return f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"


def render(plan: DayPlan) -> str:
    zone = plan.date.tzinfo
    day = plan.date.astimezone(zone) if zone else plan.date
    lines = [f"**Today** {WEEKDAYS[day.weekday()]} {day.strftime('%m-%d')}"]
    rows: list[tuple[datetime, str]] = []
    for event in plan.events:
        if getattr(event, "todoist_id", None):
            continue
        start = _parse_dt(event.start, zone or ZoneInfo("UTC"))
        end = _parse_dt(event.end, zone or ZoneInfo("UTC")) if event.end else start
        rows.append((start, f"- {start.strftime('%H:%M')}–{end.strftime('%H:%M')} {event.title}"))
    for block in plan.fixed:
        rows.append(
            (
                block.start,
                f"- {_span(block.start, block.minutes)} {_mark(block.task.priority)}{block.task.content}".rstrip(),
            )
        )
    for item in plan.suggested:
        rows.append(
            (
                item.start,
                f"- ~ {_span(item.start, item.minutes)} {_mark(item.priority)}{item.content}".rstrip(),
            )
        )
    rows.sort(key=lambda row: row[0])
    if rows:
        lines.append("**Schedule**")
        lines.extend(row for _, row in rows)
    if plan.anytime:
        lines.append("**Anytime**")
        for task in plan.anytime:
            lines.append(f"- {_mark(task.priority)}{task.content}".rstrip())
    return "\n".join(lines)


def plan_buttons(plan: DayPlan) -> list[list[dict[str, str]]] | None:
    if not plan.suggested:
        return None
    return [
        [
            {"text": "✅ Apply plan", "callback_data": f"plan:apply:{plan.plan_id}"},
            {"text": "🔁 Reshuffle", "callback_data": "plan:redo"},
        ]
    ]


class DayPlanner:
    def __init__(
        self,
        todoist: Any,
        calendar: Any,
        llm: Any,
        settings: Any,
        store: Any,
        task_sync: Any = None,
    ) -> None:
        self.todoist = todoist
        self.calendar = calendar
        self.llm = llm
        self.settings = settings
        self.store = store
        self.task_sync = task_sync

    def build(self, now: datetime) -> DayPlan:
        zone = _zone(now, self.settings)
        now = now.astimezone(zone) if now.tzinfo else now.replace(tzinfo=zone)
        tasks = list(self.todoist.today())
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        events = [
            event
            for event in self.calendar.events_in_range(day_start, day_start + timedelta(days=1))
            if not getattr(event, "todoist_id", None)
        ]
        fixed: list[FixedBlock] = []
        anytime: list[Task] = []
        candidates: list[Task] = []
        for task in tasks:
            if task.due_time:
                start = _parse_dt(task.due_time, zone)
                fixed.append(FixedBlock(task=task, start=start, minutes=_minutes(task, self.settings)))
            elif task.is_recurring:
                anytime.append(task)
            else:
                candidates.append(task)
        busy = list(events)
        for block in fixed:
            busy.append(
                _busy_event(f"task:{block.task.id}", block.task.content, block.start, block.minutes)
            )
        windows = free_slots(busy, now, self.settings, horizon_days=1)
        suggested: list[SuggestedSlot] = []
        leftover = list(candidates)
        if candidates:
            leftover, suggested = self._propose(candidates, windows, now, zone, busy)
        plan = DayPlan(
            plan_id=uuid.uuid4().hex[:8],
            date=now,
            events=events,
            fixed=fixed,
            suggested=suggested,
            anytime=anytime + leftover,
        )
        if self.store is not None and hasattr(self.store, "save_plan"):
            self.store.save_plan(plan.plan_id, plan_to_payload(plan), now)
        return plan

    def apply(self, plan_id: str, now: datetime) -> DayPlan | None:
        if self.store is None or not hasattr(self.store, "get_plan"):
            return None
        payload = self.store.get_plan(plan_id)
        if not payload:
            return None
        plan = plan_from_payload(payload)
        for item in plan.suggested:
            self.todoist.update(
                item.task_id,
                due_datetime=item.start.isoformat(),
                duration_minutes=item.minutes,
            )
        if self.task_sync is not None:
            self.task_sync.run(now)
        return plan

    def _propose(
        self,
        candidates: list[Task],
        windows: list[Slot],
        now: datetime,
        zone,
        busy: list[CalendarEvent],
    ) -> tuple[list[Task], list[SuggestedSlot]]:
        refs = {f"t{index}": task for index, task in enumerate(candidates, start=1)}
        default = int(getattr(self.settings, "plan_default_minutes", 60) or 60)
        lines = []
        for index, task in enumerate(candidates, start=1):
            bits = [f"t{index}", task.content, f"p{task.priority}"]
            bits.extend(f"@{label}" for label in task.labels)
            bits.append(f"{task.duration_minutes or default}m")
            lines.append(" ".join(bits))
        prompt = (
            f"Date: {WEEKDAYS[now.weekday()]} {now.date().isoformat()}\n"
            f"Free windows: {format_slots(windows) or 'none'}\n"
            f"Busy: {self._busy_lines(busy, zone) or 'none'}\n"
            f"Candidates:\n" + "\n".join(lines) + "\n"
            'Reply with JSON only: {"scheduled":[{"ref":"t1","start":"HH:MM","minutes":60,"why":"..."}],'
            '"anytime":["t2"]}. Slot a task only when its context suggests a time of day or an order '
            "next to other items. Otherwise anytime. Do not pack: leftovers go to anytime."
        )
        try:
            result = self.llm.complete([{"role": "user", "content": prompt}], [])
            data = _parse_llm(getattr(result, "reply", "") or "")
        except Exception:
            data = None
        if not data:
            return list(candidates), []
        scheduled = data.get("scheduled") or []
        anytime_refs = {str(item) for item in (data.get("anytime") or [])}
        taken: list[tuple[datetime, datetime]] = []
        suggested: list[SuggestedSlot] = []
        used: set[str] = set()
        leftover: list[Task] = []
        for raw in scheduled:
            ref = str(raw.get("ref") or "")
            task = refs.get(ref)
            if task is None or ref in used:
                continue
            used.add(ref)
            slot = self._valid_slot(raw, now, zone, windows, taken)
            if slot is None:
                leftover.append(task)
                continue
            start, minutes = slot
            taken.append((start, start + timedelta(minutes=minutes)))
            suggested.append(
                SuggestedSlot(
                    task_id=task.id,
                    content=task.content,
                    start=start,
                    minutes=minutes,
                    why=str(raw.get("why") or ""),
                    priority=int(task.priority or 1),
                )
            )
        for ref, task in refs.items():
            if ref in used or ref in anytime_refs:
                if ref not in used:
                    leftover.append(task)
                continue
            leftover.append(task)
        return leftover, suggested

    def _valid_slot(
        self,
        raw: dict[str, Any],
        now: datetime,
        zone,
        windows: list[Slot],
        taken: list[tuple[datetime, datetime]],
    ) -> tuple[datetime, int] | None:
        try:
            minutes = int(raw.get("minutes") or getattr(self.settings, "plan_default_minutes", 60) or 60)
        except (TypeError, ValueError):
            return None
        if minutes < MIN_MINUTES or minutes > MAX_MINUTES:
            return None
        stamp = str(raw.get("start") or "")
        try:
            hour, minute = stamp.split(":")[:2]
            start = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
        except (TypeError, ValueError):
            return None
        end = start + timedelta(minutes=minutes)
        if not _fits(start, end, windows):
            return None
        if _overlaps(start, end, taken):
            return None
        return start, minutes

    def _busy_lines(self, events: list[CalendarEvent], zone) -> str:
        parts = []
        for event in events:
            start = _parse_dt(event.start, zone)
            end = _parse_dt(event.end, zone) if event.end else start
            parts.append(f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')} {event.title}")
        return ", ".join(parts)
