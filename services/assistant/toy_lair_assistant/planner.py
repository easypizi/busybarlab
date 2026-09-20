from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from toy_lair_assistant.models import CalendarEvent

MIN_SLOT = timedelta(minutes=30)
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime


def _zone(now: datetime, settings: Any) -> ZoneInfo | Any:
    if now.tzinfo is not None:
        return now.tzinfo
    return ZoneInfo(getattr(settings, "timezone", "UTC"))


def _parse(value: str, zone) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def free_slots(
    events: list[CalendarEvent],
    now: datetime,
    settings: Any,
    horizon_days: int | None = None,
) -> list[Slot]:
    zone = _zone(now, settings)
    now = now.astimezone(zone) if now.tzinfo else now.replace(tzinfo=zone)
    horizon = int(horizon_days if horizon_days is not None else settings.plan_horizon_days)
    start_hour = int(settings.plan_hours_start)
    end_hour = int(settings.plan_hours_end)
    weekends = bool(settings.plan_weekends)
    busy = sorted(
        (_parse(event.start, zone), _parse(event.end, zone)) for event in events
    )
    slots: list[Slot] = []
    for offset in range(horizon):
        day = now.date() + timedelta(days=offset)
        if not weekends and day.weekday() >= 5:
            continue
        window_start = datetime(day.year, day.month, day.day, start_hour, 0, tzinfo=zone)
        window_end = datetime(day.year, day.month, day.day, end_hour, 0, tzinfo=zone)
        if day == now.date() and now > window_start:
            window_start = now.replace(second=0, microsecond=0)
        if window_start >= window_end:
            continue
        cursor = window_start
        for raw_start, raw_end in busy:
            if raw_end <= cursor or raw_start >= window_end:
                continue
            gap_end = min(raw_start, window_end)
            if gap_end - cursor >= MIN_SLOT:
                slots.append(Slot(start=cursor, end=gap_end))
            cursor = max(cursor, raw_end)
        if window_end - cursor >= MIN_SLOT:
            slots.append(Slot(start=cursor, end=window_end))
    return slots


def format_slots(slots: list[Slot]) -> str:
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for slot in slots:
        key = f"{WEEKDAYS[slot.start.weekday()]} {slot.start.strftime('%m-%d')}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(
            f"{slot.start.strftime('%H:%M')}-{slot.end.strftime('%H:%M')}"
        )
    return "\n".join(f"{key}: {', '.join(groups[key])}" for key in order)
