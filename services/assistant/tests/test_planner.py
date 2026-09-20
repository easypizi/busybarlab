from datetime import datetime
from zoneinfo import ZoneInfo

from toy_lair_assistant.models import CalendarEvent
from toy_lair_assistant.planner import Slot, format_slots, free_slots
from toy_lair_assistant.settings import Settings

ZONE = ZoneInfo("America/Los_Angeles")


def _settings(**overrides) -> Settings:
    values = {
        "plan_hours_start": 10,
        "plan_hours_end": 22,
        "plan_horizon_days": 7,
        "plan_default_minutes": 60,
        "plan_weekends": True,
        "timezone": "America/Los_Angeles",
    }
    values.update(overrides)
    return Settings(**values)


def test_free_slots_cover_weekends_and_work_hours() -> None:
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZONE)
    slots = free_slots([], now, _settings())
    days = {slot.start.date().isoformat() for slot in slots}
    assert "2026-09-19" in days
    assert "2026-09-20" in days
    assert "2026-09-21" in days
    assert all(slot.start.hour >= 10 for slot in slots)
    assert all(slot.end.hour == 22 or slot.end.time() >= slot.start.time() for slot in slots)
    saturday = [slot for slot in slots if slot.start.date().isoformat() == "2026-09-19"]
    assert saturday[0].start == datetime(2026, 9, 19, 11, 0, tzinfo=ZONE)
    assert saturday[0].end == datetime(2026, 9, 19, 22, 0, tzinfo=ZONE)


def test_free_slots_can_skip_weekends() -> None:
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZONE)
    slots = free_slots([], now, _settings(plan_weekends=False))
    assert slots
    weekdays = {slot.start.weekday() for slot in slots}
    assert 5 not in weekdays
    assert 6 not in weekdays
    assert weekdays <= {0, 1, 2, 3, 4}


def test_free_slots_subtracts_events() -> None:
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZONE)
    events = [
        CalendarEvent(
            id="e1",
            title="Standup",
            start="2026-09-19T14:00:00-07:00",
            end="2026-09-19T15:30:00-07:00",
        )
    ]
    slots = free_slots(events, now, _settings())
    today = [slot for slot in slots if slot.start.date().isoformat() == "2026-09-19"]
    assert today[0] == Slot(
        start=datetime(2026, 9, 19, 11, 0, tzinfo=ZONE),
        end=datetime(2026, 9, 19, 14, 0, tzinfo=ZONE),
    )
    assert today[1] == Slot(
        start=datetime(2026, 9, 19, 15, 30, tzinfo=ZONE),
        end=datetime(2026, 9, 19, 22, 0, tzinfo=ZONE),
    )


def test_free_slots_drops_windows_under_30_minutes() -> None:
    now = datetime(2026, 9, 19, 10, 0, tzinfo=ZONE)
    events = [
        CalendarEvent(
            id="e1",
            title="Long",
            start="2026-09-19T11:00:00-07:00",
            end="2026-09-19T21:40:00-07:00",
        )
    ]
    slots = free_slots(events, now, _settings())
    today = [slot for slot in slots if slot.start.date().isoformat() == "2026-09-19"]
    assert today == [
        Slot(
            start=datetime(2026, 9, 19, 10, 0, tzinfo=ZONE),
            end=datetime(2026, 9, 19, 11, 0, tzinfo=ZONE),
        )
    ]


def test_format_slots_is_compact() -> None:
    slots = [
        Slot(
            start=datetime(2026, 9, 21, 10, 0, tzinfo=ZONE),
            end=datetime(2026, 9, 21, 12, 30, tzinfo=ZONE),
        ),
        Slot(
            start=datetime(2026, 9, 21, 14, 0, tzinfo=ZONE),
            end=datetime(2026, 9, 21, 22, 0, tzinfo=ZONE),
        ),
    ]
    assert format_slots(slots) == "Mon 09-21: 10:00-12:30, 14:00-22:00"
