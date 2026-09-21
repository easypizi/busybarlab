from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from toy_lair_assistant.models import CalendarEvent, Task
from toy_lair_assistant.planner import WEEKDAYS, Slot, format_slots, free_slots


MIN_MINUTES = 15
MAX_MINUTES = 180
LINE_MARK = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
DURATION_TAIL = re.compile(r"\s+(\d+)\s*(h|m|min|mins|hour|hours)\s*$", re.IGNORECASE)
TIME_TAIL = re.compile(r"\s+(\d{1,2}:\d{2})\s*$")
PHYSICAL_RE = re.compile(
    r"бег|трен|зал|спорт|run|gym|workout|тренир",
    re.IGNORECASE,
)


@dataclass
class PlanLine:
    content: str
    duration_minutes: int | None = None
    due_time: str | None = None


def parse_plan_lines(text: str) -> list[PlanLine]:
    items: list[PlanLine] = []
    for raw in (text or "").splitlines():
        line = LINE_MARK.sub("", raw).strip()
        if not line:
            continue
        duration = None
        due_time = None
        match = DURATION_TAIL.search(line)
        if match:
            amount = int(match.group(1))
            unit = match.group(2).lower()
            duration = amount * 60 if unit.startswith("h") else amount
            line = line[: match.start()].strip()
        match = TIME_TAIL.search(line)
        if match:
            due_time = match.group(1)
            hour, minute = due_time.split(":")
            due_time = f"{int(hour):02d}:{int(minute):02d}"
            line = line[: match.start()].strip()
        match = DURATION_TAIL.search(line)
        if match and duration is None:
            amount = int(match.group(1))
            unit = match.group(2).lower()
            duration = amount * 60 if unit.startswith("h") else amount
            line = line[: match.start()].strip()
        if not line:
            continue
        items.append(PlanLine(content=line, duration_minutes=duration, due_time=due_time))
    return items


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
    is_new: bool = False
    explicit: bool = False


@dataclass
class DayPlan:
    plan_id: str
    date: datetime
    events: list[CalendarEvent] = field(default_factory=list)
    fixed: list[FixedBlock] = field(default_factory=list)
    suggested: list[SuggestedSlot] = field(default_factory=list)
    anytime: list[Task] = field(default_factory=list)
    anytime_why: dict[str, str] = field(default_factory=dict)
    kind: str = "today"
    source_lines: list[str] = field(default_factory=list)
    day_offset: int = 0


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
                "is_new": item.is_new,
                "explicit": item.explicit,
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
        "anytime_why": dict(plan.anytime_why),
        "kind": plan.kind,
        "source_lines": list(plan.source_lines),
        "day_offset": plan.day_offset,
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
            is_new=bool(raw.get("is_new")),
            explicit=bool(raw.get("explicit")),
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
        anytime_why={str(key): str(value) for key, value in (payload.get("anytime_why") or {}).items()},
        kind=str(payload.get("kind") or "today"),
        source_lines=[str(item) for item in payload.get("source_lines") or []],
        day_offset=int(payload.get("day_offset") or 0),
    )


def _mark(priority: int) -> str:
    return "🔴 " if int(priority or 1) >= 4 else ""


def _span(start: datetime, minutes: int) -> str:
    end = start + timedelta(minutes=minutes)
    return f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"


def _task_day(task: Task) -> str:
    if task.due_time:
        return _parse_dt(task.due_time, ZoneInfo("UTC")).date().isoformat()
    return task.due_date or ""


def _event_start(event: CalendarEvent, zone) -> datetime:
    return _parse_dt(event.start, zone or ZoneInfo("UTC"))


def render_week(
    now: datetime,
    tasks: list[Task],
    events: list[CalendarEvent],
    days: int = 7,
) -> str:
    zone = now.tzinfo or ZoneInfo("UTC")
    start = now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
    visible = [event for event in events if not getattr(event, "todoist_id", None)]
    rituals = [
        task
        for task in tasks
        if task.is_recurring and not task.due_time
    ]
    ritual_ids = {task.id for task in rituals}
    dated = [task for task in tasks if task.id not in ritual_ids]
    lines = ["**Week**"]
    for offset in range(days):
        day = start + timedelta(days=offset)
        stamp = day.date().isoformat()
        rows: list[tuple[datetime, str]] = []
        for event in visible:
            when = _event_start(event, zone)
            if when.date() != day.date():
                continue
            rows.append((when, f"- {when.strftime('%H:%M')} {event.title}"))
        for task in dated:
            if _task_day(task) != stamp:
                continue
            mark = _mark(task.priority)
            if task.due_time:
                when = _parse_dt(task.due_time, zone)
                rows.append((when, f"- {when.strftime('%H:%M')} {mark}{task.content}".rstrip()))
            else:
                rows.append((day, f"- {mark}{task.content}".rstrip()))
        if not rows:
            continue
        rows.sort(key=lambda row: row[0])
        lines.append(f"**{WEEKDAYS[day.weekday()]} {day.strftime('%m-%d')}**")
        lines.extend(row for _, row in rows)
    if rituals:
        lines.append("**Rituals**")
        for task in rituals:
            lines.append(f"- {_mark(task.priority)}{task.content}".rstrip())
    if len(lines) == 1:
        lines.append("Quiet week.")
    return "\n".join(lines)


def _why(text: str) -> str:
    return f" · {text}" if text else ""


def _load_label(minutes: int, cap: int) -> str:
    return f"**Load** {_hm(minutes)} of {_hm(cap)}"


def _hm(minutes: int) -> str:
    hours, rest = divmod(max(int(minutes), 0), 60)
    if hours and rest:
        return f"{hours}h {rest}m"
    if hours:
        return f"{hours}h"
    return f"{rest}m"


def render(plan: DayPlan) -> str:
    zone = plan.date.tzinfo
    day = plan.date.astimezone(zone) if zone else plan.date
    title = "Plan" if plan.kind == "plan" else "Today"
    lines = [f"**{title}** {WEEKDAYS[day.weekday()]} {day.strftime('%m-%d')}"]
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
        plus = "+ " if item.is_new else ""
        rows.append(
            (
                item.start,
                (
                    f"- ~ {_span(item.start, item.minutes)} {_mark(item.priority)}"
                    f"{plus}{item.content}{_why(item.why)}"
                ).rstrip(),
            )
        )
    rows.sort(key=lambda row: row[0])
    if rows:
        lines.append("**Schedule**")
        lines.extend(row for _, row in rows)
    if plan.anytime:
        lines.append("**Anytime**")
        for task in plan.anytime:
            extra = _why(plan.anytime_why.get(task.id, ""))
            plus = "+ " if str(task.id).startswith("new:") else ""
            lines.append(f"- {_mark(task.priority)}{plus}{task.content}{extra}".rstrip())
    load = sum(block.minutes for block in plan.fixed) + sum(item.minutes for item in plan.suggested)
    cap = 240
    lines.append(_load_label(load, cap))
    return "\n".join(lines)


def plan_buttons(plan: DayPlan) -> list[list[dict[str, str]]] | None:
    if not plan.suggested and plan.kind != "plan":
        return None
    row = [
        {"text": "✅ Apply plan", "callback_data": f"plan:apply:{plan.plan_id}"},
        {"text": "🔁 Reshuffle", "callback_data": "plan:redo"},
    ]
    if plan.kind == "plan" or plan.source_lines:
        row.append({"text": "📅 Tomorrow", "callback_data": "plan:tomorrow"})
    return [row]


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
        self._draft_lines: list[str] = []
        self._draft_offset = 0

    def build(self, now: datetime) -> DayPlan:
        return self._assemble(now, list(self.todoist.today()), kind="today")

    def build_from_lines(self, lines: list[str] | str, now: datetime, day_offset: int = 0) -> DayPlan:
        if isinstance(lines, str):
            parsed = parse_plan_lines(lines)
            stored = [str(item) for item in lines.splitlines() if str(item).strip()]
        else:
            parsed = parse_plan_lines("\n".join(str(item) for item in lines))
            stored = [str(item) for item in lines]
        self._draft_lines = stored
        self._draft_offset = day_offset
        zone = _zone(now, self.settings)
        now = now.astimezone(zone) if now.tzinfo else now.replace(tzinfo=zone)
        day = now + timedelta(days=day_offset)
        if day_offset:
            hour = int(getattr(self.settings, "plan_hours_start", 10) or 10)
            day = day.replace(hour=hour, minute=0, second=0, microsecond=0)
        open_tasks = (
            list(self.todoist.open_tasks())
            if hasattr(self.todoist, "open_tasks")
            else list(self.todoist.today())
        )
        tasks: list[Task] = []
        for item in parsed:
            match = _match_open(item.content, open_tasks)
            if match is not None:
                task = Task(
                    id=match.id,
                    content=match.content,
                    due_date=day.date().isoformat(),
                    due_time=_stamp(day, item.due_time) if item.due_time else None,
                    priority=match.priority,
                    labels=list(match.labels),
                    duration_minutes=item.duration_minutes or match.duration_minutes,
                    deadline=match.deadline,
                )
            else:
                task = Task(
                    id=f"new:{uuid.uuid4().hex[:8]}",
                    content=item.content,
                    due_date=day.date().isoformat(),
                    due_time=_stamp(day, item.due_time) if item.due_time else None,
                    duration_minutes=item.duration_minutes,
                )
            tasks.append(task)
        return self._assemble(
            day,
            tasks,
            kind="plan",
            source_lines=self._draft_lines,
            day_offset=day_offset,
            explicit_ids={task.id for task in tasks if task.due_time},
        )

    def apply(self, plan_id: str, now: datetime) -> DayPlan | None:
        if self.store is None or not hasattr(self.store, "get_plan"):
            return None
        payload = self.store.get_plan(plan_id)
        if not payload:
            return None
        plan = plan_from_payload(payload)
        created = 0
        for item in plan.suggested:
            if item.is_new or str(item.task_id).startswith("new:"):
                self.todoist.add(
                    item.content,
                    due_datetime=item.start.isoformat(),
                    duration_minutes=item.minutes,
                )
                created += 1
            else:
                self.todoist.update(
                    item.task_id,
                    due_datetime=item.start.isoformat(),
                    duration_minutes=item.minutes,
                )
        if self.task_sync is not None:
            self.task_sync.run(now)
        return plan

    def _assemble(
        self,
        now: datetime,
        tasks: list[Task],
        *,
        kind: str,
        source_lines: list[str] | None = None,
        day_offset: int = 0,
        explicit_ids: set[str] | None = None,
    ) -> DayPlan:
        zone = _zone(now, self.settings)
        now = now.astimezone(zone) if now.tzinfo else now.replace(tzinfo=zone)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        events = [
            event
            for event in self.calendar.events_in_range(day_start, day_start + timedelta(days=1))
            if not getattr(event, "todoist_id", None)
        ]
        fixed: list[FixedBlock] = []
        anytime: list[Task] = []
        candidates: list[Task] = []
        explicit = set(explicit_ids or ())
        for task in tasks:
            if task.due_time and kind == "today":
                start = _parse_dt(task.due_time, zone)
                fixed.append(FixedBlock(task=task, start=start, minutes=_minutes(task, self.settings)))
            elif task.is_recurring and not task.due_time:
                anytime.append(task)
            else:
                candidates.append(task)
                if task.due_time:
                    explicit.add(task.id)
        busy = list(events)
        for block in fixed:
            busy.append(
                _busy_event(f"task:{block.task.id}", block.task.content, block.start, block.minutes)
            )
        windows = free_slots(busy, now, self.settings, horizon_days=1)
        leftover: list[Task] = []
        suggested: list[SuggestedSlot] = []
        notes: dict[str, str] = {}
        if candidates:
            leftover, suggested, notes = self._propose(
                candidates,
                windows,
                now,
                zone,
                busy,
                explicit,
                used=sum(block.minutes for block in fixed),
            )
        plan = DayPlan(
            plan_id=uuid.uuid4().hex[:8],
            date=now,
            events=events,
            fixed=fixed,
            suggested=suggested,
            anytime=anytime + leftover,
            anytime_why=notes,
            kind=kind,
            source_lines=list(source_lines or []),
            day_offset=day_offset,
        )
        if self.store is not None and hasattr(self.store, "save_plan"):
            self.store.save_plan(plan.plan_id, plan_to_payload(plan), now)
        return plan

    def _propose(
        self,
        candidates: list[Task],
        windows: list[Slot],
        now: datetime,
        zone,
        busy: list[CalendarEvent],
        explicit: set[str],
        used: int = 0,
    ) -> tuple[list[Task], list[SuggestedSlot], dict[str, str]]:
        refs = {f"t{index}": task for index, task in enumerate(candidates, start=1)}
        default = int(getattr(self.settings, "plan_default_minutes", 60) or 60)
        cap = int(getattr(self.settings, "plan_daily_load_minutes", 240) or 240)
        buffer = int(getattr(self.settings, "plan_buffer_minutes", 15) or 15)
        streak = int(getattr(self.settings, "plan_focus_streak_minutes", 180) or 180)
        brk = int(getattr(self.settings, "plan_break_minutes", 30) or 30)
        work_start = int(getattr(self.settings, "work_hours_start", 9) or 9)
        work_end = int(getattr(self.settings, "work_hours_end", 17) or 17)
        from toy_lair_assistant.profile import profile_text

        lines = []
        for index, task in enumerate(candidates, start=1):
            bits = [f"t{index}", task.content, f"p{task.priority}", task_kind(task)]
            bits.extend(f"@{label}" for label in task.labels)
            bits.append(f"{task.duration_minutes or default}m")
            if task.id in explicit and task.due_time:
                bits.append(
                    f"fixed {task.due_time[11:16] if len(task.due_time) >= 16 else task.due_time}"
                )
            lines.append(" ".join(bits))
        prompt = (
            f"{profile_text(self.settings)}\n"
            f"Date: {WEEKDAYS[now.weekday()]} {now.date().isoformat()}\n"
            f"Free windows: {format_slots(windows) or 'none'}\n"
            f"Busy: {self._busy_lines(busy, zone) or 'none'}\n"
            f"Budget left: {max(cap - used, 0)}m of {cap}m. Buffer {buffer}m around meetings. "
            f"After {streak}m streak take a {brk}m break. "
            f"Weekdays {work_start:02d}:00-{work_end:02d}:00: only light/desk tasks, no sport or errands.\n"
            f"Candidates:\n" + "\n".join(lines) + "\n"
            'Reply with JSON only: {"scheduled":[{"ref":"t1","start":"HH:MM","minutes":60,"why":"..."}],'
            '"anytime":["t2"]}. Fill what fits the budget. why: at most four words. '
            "Leftovers go to anytime. Do not pack past the budget."
        )
        try:
            result = self.llm.complete([{"role": "user", "content": prompt}], [])
            data = _parse_llm(getattr(result, "reply", "") or "")
        except Exception:
            data = None
        if not data:
            leftover, suggested = self._greedy(
                candidates, windows, now, zone, busy, explicit, used
            )
            return leftover, suggested, {task.id: "день занят" for task in leftover}
        scheduled = data.get("scheduled") or []
        taken: list[tuple[datetime, datetime]] = [_span_tuple(event, zone) for event in busy]
        suggested = []
        used_ids: set[str] = set()
        leftover = []
        load = used
        for raw in scheduled:
            ref = str(raw.get("ref") or "")
            task = refs.get(ref)
            if task is None or ref in used_ids:
                continue
            used_ids.add(ref)
            payload = dict(raw)
            if task.id in explicit and task.due_time:
                payload["start"] = (
                    task.due_time[11:16] if len(task.due_time) >= 16 else task.due_time
                )
                payload["explicit"] = True
            slot = self._valid_slot(payload, now, zone, windows, taken, task=task, load=load)
            if slot is None:
                leftover.append(task)
                continue
            start, minutes, why = slot
            taken.append((start, start + timedelta(minutes=minutes)))
            load += minutes
            suggested.append(
                SuggestedSlot(
                    task_id=task.id,
                    content=task.content,
                    start=start,
                    minutes=minutes,
                    why=why or str(raw.get("why") or ""),
                    priority=int(task.priority or 1),
                    is_new=str(task.id).startswith("new:"),
                    explicit=task.id in explicit,
                )
            )
        for ref, task in refs.items():
            if ref not in used_ids:
                leftover.append(task)
        return leftover, suggested, {task.id: "день занят" for task in leftover}

    def _greedy(
        self,
        candidates: list[Task],
        windows: list[Slot],
        now: datetime,
        zone,
        busy: list[CalendarEvent],
        explicit: set[str],
        used: int,
    ) -> tuple[list[Task], list[SuggestedSlot]]:
        ordered = sorted(
            candidates,
            key=lambda task: (
                -int(task.priority or 1),
                task.deadline or "9999",
                _minutes(task, self.settings),
            ),
        )
        taken: list[tuple[datetime, datetime]] = [_span_tuple(event, zone) for event in busy]
        suggested: list[SuggestedSlot] = []
        leftover: list[Task] = []
        load = used
        for task in ordered:
            if task.id in explicit and task.due_time:
                stamp = task.due_time[11:16] if len(task.due_time) >= 16 else task.due_time
                slot = self._valid_slot(
                    {
                        "start": stamp,
                        "minutes": _minutes(task, self.settings),
                        "explicit": True,
                    },
                    now,
                    zone,
                    windows,
                    taken,
                    task=task,
                    load=load,
                )
            else:
                slot = self._earliest(task, now, zone, windows, taken, load)
            if slot is None:
                leftover.append(task)
                continue
            start, minutes, why = slot
            taken.append((start, start + timedelta(minutes=minutes)))
            load += minutes
            suggested.append(
                SuggestedSlot(
                    task_id=task.id,
                    content=task.content,
                    start=start,
                    minutes=minutes,
                    why=why,
                    priority=int(task.priority or 1),
                    is_new=str(task.id).startswith("new:"),
                    explicit=task.id in explicit,
                )
            )
        suggested.sort(key=lambda item: item.start)
        return leftover, suggested

    def _earliest(
        self,
        task: Task,
        now: datetime,
        zone,
        windows: list[Slot],
        taken: list[tuple[datetime, datetime]],
        load: int,
    ) -> tuple[datetime, int, str] | None:
        minutes = _minutes(task, self.settings)
        for window in windows:
            cursor = max(window.start, now).replace(second=0, microsecond=0)
            if cursor.minute % 15:
                cursor += timedelta(minutes=15 - cursor.minute % 15)
            while cursor + timedelta(minutes=minutes) <= window.end:
                slot = self._valid_slot(
                    {"start": cursor.strftime("%H:%M"), "minutes": minutes},
                    now,
                    zone,
                    windows,
                    taken,
                    task=task,
                    load=load,
                )
                if slot is not None:
                    return slot
                cursor += timedelta(minutes=15)
        return None

    def _valid_slot(
        self,
        raw: dict[str, Any],
        now: datetime,
        zone,
        windows: list[Slot],
        taken: list[tuple[datetime, datetime]],
        task: Task | None = None,
        load: int = 0,
    ) -> tuple[datetime, int, str] | None:
        try:
            minutes = int(raw.get("minutes") or getattr(self.settings, "plan_default_minutes", 60) or 60)
        except (TypeError, ValueError):
            return None
        if minutes < MIN_MINUTES or minutes > MAX_MINUTES:
            return None
        cap = int(getattr(self.settings, "plan_daily_load_minutes", 240) or 240)
        if load + minutes > cap:
            return None
        stamp = str(raw.get("start") or "")
        try:
            hour, minute = stamp.split(":")[:2]
            start = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
        except (TypeError, ValueError):
            return None
        explicit = bool(raw.get("explicit"))
        start = self._snap(start, minutes, now, windows, taken, task, explicit)
        if start is None:
            return None
        end = start + timedelta(minutes=minutes)
        if not _fits(start, end, windows):
            return None
        why = ""
        if (
            explicit
            and task is not None
            and task_kind(task) != "light"
            and _work_overlap(start, end, now, self.settings)
        ):
            why = "в рабочее время"
        elif (
            task is not None
            and task_kind(task) != "light"
            and start.hour >= int(getattr(self.settings, "work_hours_end", 17) or 17)
            and now.weekday() < 5
        ):
            why = "после работы"
        return start, minutes, why

    def _snap(
        self,
        start: datetime,
        minutes: int,
        now: datetime,
        windows: list[Slot],
        taken: list[tuple[datetime, datetime]],
        task: Task | None,
        explicit: bool,
    ) -> datetime | None:
        buffer = 0 if explicit else int(getattr(self.settings, "plan_buffer_minutes", 15) or 15)
        brk = int(getattr(self.settings, "plan_break_minutes", 30) or 30)
        streak = int(getattr(self.settings, "plan_focus_streak_minutes", 180) or 180)
        work_end_h = int(getattr(self.settings, "work_hours_end", 17) or 17)
        cursor = start
        for _ in range(48):
            end = cursor + timedelta(minutes=minutes)
            if not _fits(cursor, end, windows):
                cursor += timedelta(minutes=15)
                continue
            blocks = [
                (item[0] - timedelta(minutes=buffer), item[1] + timedelta(minutes=buffer))
                for item in taken
            ]
            hit = next((block for block in blocks if cursor < block[1] and block[0] < end), None)
            if hit is not None:
                cursor = hit[1]
                continue
            if not explicit and taken:
                trail = _trailing_streak(taken, brk)
                last_end = max(item[1] for item in taken)
                if trail >= streak and cursor < last_end + timedelta(minutes=brk):
                    cursor = last_end + timedelta(minutes=brk)
                    continue
            if (
                task is not None
                and not explicit
                and task_kind(task) != "light"
                and _work_overlap(cursor, end, now, self.settings)
            ):
                cursor = now.replace(hour=work_end_h, minute=0, second=0, microsecond=0)
                continue
            return cursor
        return None

    def _busy_lines(self, events: list[CalendarEvent], zone) -> str:
        parts = []
        for event in events:
            start = _parse_dt(event.start, zone)
            end = _parse_dt(event.end, zone) if event.end else start
            parts.append(f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')} {event.title}")
        return ", ".join(parts)


def task_kind(task: Task) -> str:
    labels = {str(label).lower().lstrip("@") for label in task.labels}
    if "quick" in labels or "desk" in labels:
        return "light"
    if task.duration_minutes is not None and int(task.duration_minutes) <= 15:
        return "light"
    if "sport" in labels or PHYSICAL_RE.search(task.content or ""):
        return "physical"
    return "normal"


def _work_overlap(start: datetime, end: datetime, now: datetime, settings: Any) -> bool:
    days = str(getattr(settings, "work_days", "mon-fri") or "mon-fri")
    if days == "mon-fri" and now.weekday() >= 5:
        return False
    work_start = now.replace(
        hour=int(getattr(settings, "work_hours_start", 9) or 9),
        minute=0,
        second=0,
        microsecond=0,
    )
    work_end = now.replace(
        hour=int(getattr(settings, "work_hours_end", 17) or 17),
        minute=0,
        second=0,
        microsecond=0,
    )
    return start < work_end and end > work_start


def _trailing_streak(taken: list[tuple[datetime, datetime]], break_minutes: int) -> int:
    if not taken:
        return 0
    items = sorted(taken)
    total = 0
    prev_start = items[-1][0]
    for start, end in reversed(items):
        if total and (prev_start - end) >= timedelta(minutes=break_minutes):
            break
        total += int((end - start).total_seconds() // 60)
        prev_start = start
    return total


def _span_tuple(event: CalendarEvent, zone) -> tuple[datetime, datetime]:
    start = _parse_dt(event.start, zone)
    end = _parse_dt(event.end, zone) if event.end else start
    return start, end


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def _match_open(content: str, tasks: list[Task]) -> Task | None:
    needle = _norm(content)
    exact = [task for task in tasks if _norm(task.content) == needle]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    partial = [
        task
        for task in tasks
        if needle in _norm(task.content) or _norm(task.content) in needle
    ]
    if len(partial) == 1:
        return partial[0]
    return None


def _stamp(day: datetime, hhmm: str) -> str:
    hour, minute = hhmm.split(":")
    return day.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0).isoformat()
