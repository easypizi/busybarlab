from datetime import datetime
from zoneinfo import ZoneInfo

from toy_lair_assistant.models import CalendarEvent, Task
from toy_lair_assistant.scheduler import Scheduler
from toy_lair_assistant.store import MemoryStore


class FakeTodoist:
    def today(self):
        return [
            Task(id="t1", content="Pay rent", due_date="2026-09-19", due_string="today 12:00"),
        ]

    def upcoming(self, days: int = 7):
        return self.today()


class FakeCal:
    def events_in_range(self, start, end):
        return [
            CalendarEvent(
                id="e1",
                title="Dentist",
                start="2026-09-19T11:15:00-07:00",
                end="2026-09-19T12:00:00-07:00",
            )
        ]


def test_tick_sends_event_lead_once() -> None:
    sent: list[str] = []
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    store = MemoryStore()
    sched = Scheduler(
        todoist=FakeTodoist(),
        calendar=FakeCal(),
        store=store,
        notify=lambda text: sent.append(text),
        lead_minutes=15,
        briefing_hour=8,
        timezone="America/Los_Angeles",
    )
    first = sched.tick(now)
    second = sched.tick(now)
    assert any("Dentist" in t for t in sent)
    assert first >= 1
    assert second == 0


def test_morning_briefing_once() -> None:
    sent: list[str] = []
    now = datetime(2026, 9, 19, 8, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    sched = Scheduler(
        todoist=FakeTodoist(),
        calendar=FakeCal(),
        store=MemoryStore(),
        notify=lambda text: sent.append(text),
        lead_minutes=15,
        briefing_hour=8,
        timezone="America/Los_Angeles",
    )
    sched.tick(now)
    sched.tick(now)
    briefs = [t for t in sent if t.startswith("Briefing")]
    assert len(briefs) == 1
    assert "Pay rent" in briefs[0]


def test_custom_reminder_fires() -> None:
    sent: list[str] = []
    store = MemoryStore()
    fire_at = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    store.add_reminder("r1", fire_at, "stand up")
    sched = Scheduler(
        todoist=FakeTodoist(),
        calendar=FakeCal(),
        store=store,
        notify=lambda text: sent.append(text),
        lead_minutes=15,
        briefing_hour=8,
        timezone="America/Los_Angeles",
    )
    sched.tick(fire_at)
    assert "stand up" in sent
