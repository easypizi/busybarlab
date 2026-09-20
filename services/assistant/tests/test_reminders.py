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
    briefs = [t for t in sent if "Briefing" in t]
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


from types import SimpleNamespace

SETTINGS = SimpleNamespace(
    task_lead_minutes=15,
    deadline_lead_days=1,
    remind_label="remind",
    remind_nudge_hours=3,
    plan_hours_start=10,
    plan_hours_end=22,
    plan_default_minutes=60,
    plan_weekends=True,
    task_sync_interval_seconds=300,
)


class OpenTodoist:
    def __init__(self, tasks: list[Task]) -> None:
        self._tasks = tasks

    def open_tasks(self):
        return list(self._tasks)

    def today(self):
        return list(self._tasks)


class EmptyCal:
    def events_in_range(self, start, end):
        return []


class Rec:
    def __init__(self) -> None:
        self.sent: list[tuple[str, list | None]] = []

    def send_message(self, text: str, buttons=None) -> None:
        self.sent.append((text, buttons))


def _sched(todoist, calendar=None, notify=None, hour: int = 8) -> Scheduler:
    return Scheduler(
        todoist=todoist,
        calendar=calendar or EmptyCal(),
        store=MemoryStore(),
        notify=notify or Rec(),
        lead_minutes=15,
        briefing_hour=hour,
        timezone="America/Los_Angeles",
        settings=SETTINGS,
    )


def test_task_lead_once_with_buttons() -> None:
    rec = Rec()
    task = Task(
        id="t9",
        content="Call mom",
        due_date="2026-09-19",
        due_time="2026-09-19T11:15:00-07:00",
    )
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    sched = _sched(OpenTodoist([task]), notify=rec)
    first = sched.tick(now)
    second = sched.tick(now)
    texts = [text for text, _ in rec.sent]
    assert any("Call mom" in text for text in texts)
    assert first >= 1
    assert second == 0
    buttons = rec.sent[0][1]
    labels = [btn["text"] for row in buttons for btn in row]
    assert "✅ Done" in labels


def test_deadline_alert_day_before() -> None:
    rec = Rec()
    task = Task(id="t2", content="Taxes", deadline="2026-09-20")
    now = datetime(2026, 9, 19, 8, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    sched = _sched(OpenTodoist([task]), notify=rec)
    sched.tick(now)
    sched.tick(now)
    hits = [text for text, _ in rec.sent if "Deadline tomorrow" in text]
    assert len(hits) == 1
    assert "Taxes" in hits[0]


def test_remind_label_nudge() -> None:
    rec = Rec()
    task = Task(id="t3", content="Inbox", labels=["remind"])
    now = datetime(2026, 9, 19, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    sched = _sched(OpenTodoist([task]), notify=rec)
    sched.tick(now)
    sched.tick(now)
    hits = [text for text, _ in rec.sent if "Still open" in text]
    assert len(hits) == 1
    assert "Inbox" in hits[0]


def test_briefing_has_sections() -> None:
    rec = Rec()
    tasks = [
        Task(id="o", content="Old bill", due_date="2026-09-18"),
        Task(id="d", content="Taxes", deadline="2026-09-20"),
        Task(id="p", content="Pay rent", due_date="2026-09-19", priority=4),
        Task(id="q", content="Walk", due_date="2026-09-19", priority=1),
    ]
    calendar = FakeCal()
    now = datetime(2026, 9, 19, 8, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    sched = _sched(OpenTodoist(tasks), calendar=calendar, notify=rec)
    sched.tick(now)
    text = next(item for item, _ in rec.sent if "Briefing" in item)
    assert "**Overdue**" in text
    assert "**Deadlines**" in text
    assert "**Today**" in text
    assert "**Events**" in text
    assert text.index("Pay rent") < text.index("Walk")
    assert "🔴" in text
    assert "Dentist" in text


def test_briefing_uses_day_schedule() -> None:
    from toy_lair_assistant.agent import AgentResult
    from toy_lair_assistant.day_plan import DayPlanner

    rec = Rec()
    tasks = [
        Task(id="o", content="Old bill", due_date="2026-09-19"),
        Task(id="d", content="Taxes", deadline="2026-09-20"),
        Task(
            id="run",
            content="Бег",
            due_date="2026-09-20",
            due_time="2026-09-20T10:00:00-07:00",
            duration_minutes=60,
        ),
        Task(id="clean", content="Уборка", due_date="2026-09-20"),
        Task(id="pills", content="Supplements!", due_date="2026-09-20", is_recurring=True),
    ]

    class TodayTodoist(OpenTodoist):
        def today(self):
            return [task for task in self._tasks if task.due_date == "2026-09-20"]

    class ReplyLLM:
        def complete(self, messages, tools):
            return AgentResult(reply='{"scheduled":[],"anytime":["t1"]}', tool_calls=[])

    now = datetime(2026, 9, 20, 8, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    store = MemoryStore()
    planner = DayPlanner(
        todoist=TodayTodoist(tasks),
        calendar=EmptyCal(),
        llm=ReplyLLM(),
        settings=SETTINGS,
        store=store,
    )
    sched = Scheduler(
        todoist=TodayTodoist(tasks),
        calendar=EmptyCal(),
        store=store,
        notify=rec,
        lead_minutes=15,
        briefing_hour=8,
        timezone="America/Los_Angeles",
        settings=SETTINGS,
        day_planner=planner,
    )
    sched.tick(now)
    text, buttons = next(item for item in rec.sent if "Briefing" in item[0])
    assert "**Overdue**" in text
    assert "**Deadlines**" in text
    assert "**Schedule**" in text
    assert "**Anytime**" in text
    assert "Уборка" in text
    assert "Supplements!" in text


def test_event_lead_skips_task_mirrors() -> None:
    rec = Rec()

    class MirrorCal:
        def events_in_range(self, start, end):
            return [
                CalendarEvent(
                    id="m1",
                    title="Call mom",
                    start="2026-09-19T11:15:00-07:00",
                    end="2026-09-19T12:00:00-07:00",
                    todoist_id="t9",
                )
            ]

    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    sched = _sched(OpenTodoist([]), calendar=MirrorCal(), notify=rec)
    sched.tick(now)
    assert rec.sent == []
