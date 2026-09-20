from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from toy_lair_assistant.agent import AgentResult
from toy_lair_assistant.day_plan import DayPlanner, render
from toy_lair_assistant.models import CalendarEvent, Task
from toy_lair_assistant.store import MemoryStore

ZONE = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 9, 20, 10, 0, tzinfo=ZONE)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        timezone="America/Los_Angeles",
        plan_hours_start=10,
        plan_hours_end=22,
        plan_horizon_days=7,
        plan_default_minutes=60,
        plan_weekends=True,
    )


class FakeTodoist:
    def __init__(self, tasks: list[Task]) -> None:
        self._tasks = tasks
        self.updates: list[tuple[str, dict]] = []

    def today(self):
        return list(self._tasks)

    def update(self, task_id: str, **fields) -> None:
        self.updates.append((task_id, fields))


class FakeCal:
    def __init__(self, events: list[CalendarEvent] | None = None) -> None:
        self._events = events or []

    def events_in_range(self, start, end):
        return list(self._events)


class JsonLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[list[str]] = []

    def complete(self, messages, tools):
        self.calls.append(list(tools))
        return AgentResult(reply=self.reply, tool_calls=[])


class FakeSync:
    def __init__(self) -> None:
        self.ran: list[datetime] = []

    def run(self, now) -> None:
        self.ran.append(now)


def _planner(tasks, events=None, reply="{}", sync=None) -> DayPlanner:
    return DayPlanner(
        todoist=FakeTodoist(tasks),
        calendar=FakeCal(events),
        llm=JsonLLM(reply),
        settings=_settings(),
        store=MemoryStore(),
        task_sync=sync,
    )


def test_timed_task_is_fixed() -> None:
    task = Task(
        id="run",
        content="Бег 10 Км",
        due_date="2026-09-20",
        due_time="2026-09-20T10:00:00-07:00",
        duration_minutes=60,
    )
    plan = _planner([task]).build(NOW)
    assert [item.task.id for item in plan.fixed] == ["run"]
    assert plan.suggested == []
    assert plan.anytime == []


def test_recurring_without_time_is_anytime() -> None:
    task = Task(
        id="cat",
        content="Поменять коту водичку",
        due_date="2026-09-20",
        is_recurring=True,
    )
    plan = _planner([task]).build(NOW)
    assert [item.id for item in plan.anytime] == ["cat"]
    assert plan.fixed == []
    assert plan.suggested == []


def test_llm_slot_inside_window_is_accepted() -> None:
    task = Task(id="market", content="Воскресный рынок", due_date="2026-09-20")
    reply = '{"scheduled":[{"ref":"t1","start":"13:00","minutes":60,"why":"morning market"}],"anytime":[]}'
    plan = _planner([task], reply=reply).build(NOW)
    assert len(plan.suggested) == 1
    assert plan.suggested[0].task_id == "market"
    assert plan.suggested[0].start == datetime(2026, 9, 20, 13, 0, tzinfo=ZONE)
    assert plan.suggested[0].minutes == 60
    assert plan.anytime == []


def test_overlap_or_outside_window_goes_anytime() -> None:
    fixed = Task(
        id="call",
        content="Позвонить маме",
        due_date="2026-09-20",
        due_time="2026-09-20T12:00:00-07:00",
        duration_minutes=60,
        priority=4,
    )
    overlap = Task(id="work", content="Сервис ДНД", due_date="2026-09-20")
    outside = Task(id="late", content="Ночной рейд", due_date="2026-09-20")
    reply = (
        '{"scheduled":['
        '{"ref":"t1","start":"12:15","minutes":60,"why":"overlap"},'
        '{"ref":"t2","start":"22:30","minutes":30,"why":"too late"}'
        '],"anytime":[]}'
    )
    plan = _planner([fixed, overlap, outside], reply=reply).build(NOW)
    ids = {item.id for item in plan.anytime}
    assert ids == {"work", "late"}
    assert plan.suggested == []
    assert [item.task.id for item in plan.fixed] == ["call"]


def test_broken_json_yields_no_suggestions() -> None:
    task = Task(id="clean", content="Уборка", due_date="2026-09-20")
    plan = _planner([task], reply="not json at all").build(NOW)
    assert plan.suggested == []
    assert [item.id for item in plan.anytime] == ["clean"]


def test_render_marks_suggestions_and_skips_empty() -> None:
    events = [
        CalendarEvent(
            id="e1",
            title="Бег 10 Км",
            start="2026-09-20T10:00:00-07:00",
            end="2026-09-20T11:00:00-07:00",
        )
    ]
    tasks = [
        Task(
            id="call",
            content="Позвонить маме",
            due_date="2026-09-20",
            due_time="2026-09-20T12:00:00-07:00",
            duration_minutes=30,
            priority=4,
        ),
        Task(id="market", content="Воскресный рынок Burlingame", due_date="2026-09-20"),
        Task(id="clean", content="Уборка", due_date="2026-09-20"),
        Task(id="pills", content="Supplements!", due_date="2026-09-20", is_recurring=True),
    ]
    reply = (
        '{"scheduled":[{"ref":"t1","start":"13:00","minutes":60,"why":"market"}],'
        '"anytime":["t2"]}'
    )
    plan = _planner(tasks, events=events, reply=reply).build(NOW)
    text = render(plan)
    assert "**Today** Sun 09-20" in text
    assert "**Schedule**" in text
    assert "- 10:00–11:00 Бег 10 Км" in text
    assert "- 12:00–12:30 🔴 Позвонить маме" in text
    assert "- ~ 13:00–14:00 Воскресный рынок Burlingame" in text
    assert "**Anytime**" in text
    assert "- Уборка" in text
    assert "- Supplements!" in text
    empty = render(_planner([]).build(NOW))
    assert "**Schedule**" not in empty
    assert "**Anytime**" not in empty


def test_apply_updates_only_suggested_and_runs_sync() -> None:
    tasks = [
        Task(
            id="call",
            content="Позвонить маме",
            due_date="2026-09-20",
            due_time="2026-09-20T12:00:00-07:00",
            duration_minutes=30,
        ),
        Task(id="market", content="Рынок", due_date="2026-09-20"),
        Task(id="pills", content="Supplements!", due_date="2026-09-20", is_recurring=True),
    ]
    reply = '{"scheduled":[{"ref":"t1","start":"13:00","minutes":60,"why":"x"}],"anytime":[]}'
    sync = FakeSync()
    planner = _planner(tasks, reply=reply, sync=sync)
    plan = planner.build(NOW)
    applied = planner.apply(plan.plan_id, NOW)
    assert applied is not None
    assert [item[0] for item in planner.todoist.updates] == ["market"]
    fields = planner.todoist.updates[0][1]
    assert fields["due_datetime"] == "2026-09-20T13:00:00-07:00"
    assert fields["duration_minutes"] == 60
    assert sync.ran == [NOW]
    assert planner.store.get_plan(plan.plan_id) is not None
