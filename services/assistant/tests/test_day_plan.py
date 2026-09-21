from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from toy_lair_assistant.agent import AgentResult
from toy_lair_assistant.day_plan import DayPlanner, parse_plan_lines, render, render_week
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
        plan_buffer_minutes=15,
        plan_focus_streak_minutes=180,
        plan_break_minutes=30,
        plan_daily_load_minutes=240,
        work_hours_start=9,
        work_hours_end=17,
        work_days="mon-fri",
    )


class FakeTodoist:
    def __init__(self, tasks: list[Task]) -> None:
        self._tasks = tasks
        self.updates: list[tuple[str, dict]] = []
        self.added: list[Task] = []

    def today(self):
        return list(self._tasks)

    def open_tasks(self):
        return list(self._tasks)

    def update(self, task_id: str, **fields) -> None:
        self.updates.append((task_id, fields))

    def add(self, content: str, **fields) -> Task:
        task = Task(
            id=f"new{len(self.added) + 1}",
            content=content,
            due_time=fields.get("due_datetime"),
            duration_minutes=fields.get("duration_minutes"),
        )
        self.added.append(task)
        self._tasks.append(task)
        return task


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


def test_parse_plan_lines_strips_markers_and_reads_hints() -> None:
    items = parse_plan_lines(
        "- уборка 30m\n* позвонить бате 18:00\n1. добавки\n\n  \nпочистить коту уши 1h"
    )
    assert [item.content for item in items] == [
        "уборка",
        "позвонить бате",
        "добавки",
        "почистить коту уши",
    ]
    assert items[0].duration_minutes == 30
    assert items[1].due_time == "18:00"
    assert items[2].duration_minutes is None
    assert items[3].duration_minutes == 60


def test_render_week_groups_days_and_hides_mirrors() -> None:
    now = datetime(2026, 9, 20, 10, 0, tzinfo=ZONE)
    tasks = [
        Task(id="mom", content="Call mom", due_date="2026-09-20"),
        Task(id="walk", content="Walk", due_date="2026-09-21", due_time="2026-09-21T09:00:00-07:00"),
        Task(id="pills", content="Supplements", due_date="2026-09-20", is_recurring=True),
        Task(id="later", content="Far away", due_date="2026-10-01"),
    ]
    events = [
        CalendarEvent(
            id="e1",
            title="Standup",
            start="2026-09-21T10:00:00-07:00",
            end="2026-09-21T10:30:00-07:00",
        ),
        CalendarEvent(
            id="m1",
            title="Call mom",
            start="2026-09-20T12:00:00-07:00",
            end="2026-09-20T13:00:00-07:00",
            todoist_id="mom",
        ),
    ]
    text = render_week(now, tasks, events)
    assert text.startswith("**Week**")
    assert "**Sun 09-20**" in text
    assert "- Call mom" in text
    assert "**Mon 09-21**" in text
    assert "- 09:00 Walk" in text
    assert "- 10:00 Standup" in text
    assert "**Rituals**" in text
    assert "- Supplements" in text
    assert "Far away" not in text
    assert text.count("Call mom") == 1
    assert "**Tue" not in text


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
    assert [item.task.id for item in plan.fixed] == ["call"]
    assert "late" in {item.id for item in plan.anytime}
    assert any(item.task_id == "work" and item.start >= datetime(2026, 9, 20, 13, 15, tzinfo=ZONE) for item in plan.suggested)


def test_broken_json_falls_back_to_greedy() -> None:
    high = Task(id="rent", content="Pay rent", due_date="2026-09-20", priority=4)
    low = Task(id="clean", content="Уборка", due_date="2026-09-20", priority=1)
    plan = _planner([high, low], reply="not json at all").build(NOW)
    assert [item.task_id for item in plan.suggested] == ["rent", "clean"]
    assert plan.suggested[0].start < plan.suggested[1].start
    assert plan.anytime == []


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
    assert "- ~ 13:00–14:00 Воскресный рынок Burlingame" in text or "- ~ 13:00–14:00 Воскресный рынок Burlingame ·" in text
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


def test_buffer_pushes_slot_past_meeting() -> None:
    meeting = CalendarEvent(
        id="e1",
        title="Созвон",
        start="2026-09-20T12:00:00-07:00",
        end="2026-09-20T13:00:00-07:00",
    )
    task = Task(id="clean", content="Уборка", due_date="2026-09-20")
    reply = '{"scheduled":[{"ref":"t1","start":"13:00","minutes":60,"why":"after call"}],"anytime":[]}'
    plan = _planner([task], events=[meeting], reply=reply).build(NOW)
    assert len(plan.suggested) == 1
    assert plan.suggested[0].start >= datetime(2026, 9, 20, 13, 15, tzinfo=ZONE)


def test_break_after_three_hour_streak() -> None:
    tasks = [
        Task(id=f"t{i}", content=f"Block {i}", due_date="2026-09-20", duration_minutes=60)
        for i in range(4)
    ]
    reply = (
        '{"scheduled":['
        '{"ref":"t1","start":"10:00","minutes":60,"why":"a"},'
        '{"ref":"t2","start":"11:00","minutes":60,"why":"b"},'
        '{"ref":"t3","start":"12:00","minutes":60,"why":"c"},'
        '{"ref":"t4","start":"13:00","minutes":60,"why":"d"}'
        '],"anytime":[]}'
    )
    plan = _planner(tasks, reply=reply).build(NOW)
    starts = [item.start.strftime("%H:%M") for item in plan.suggested]
    assert starts[:3] == ["10:00", "11:15", "12:30"]
    assert plan.suggested[3].start >= datetime(2026, 9, 20, 14, 0, tzinfo=ZONE)


def test_daily_load_cap_sends_overflow_to_anytime() -> None:
    tasks = [
        Task(id=f"t{i}", content=f"Hour {i}", due_date="2026-09-20", duration_minutes=60)
        for i in range(5)
    ]
    plan = _planner(tasks, reply="not json").build(NOW)
    assert sum(item.minutes for item in plan.suggested) == 240
    assert len(plan.anytime) == 1
    assert "занят" in (plan.anytime_why.get(plan.anytime[0].id) or "")


def test_work_hours_keep_sport_after_five() -> None:
    wednesday = datetime(2026, 9, 23, 10, 0, tzinfo=ZONE)
    run = Task(id="run", content="Бег 5 км", due_date="2026-09-23")
    pills = Task(id="pills", content="Добавки", due_date="2026-09-23", labels=["quick"])
    plan = _planner([run, pills], reply="not json").build(wednesday)
    by_id = {item.task_id: item for item in plan.suggested}
    assert by_id["run"].start.hour >= 17
    assert "после работы" in by_id["run"].why
    assert by_id["pills"].start.hour < 17


def test_weekend_allows_daytime_sport() -> None:
    run = Task(id="run", content="Бег 5 км", due_date="2026-09-20")
    plan = _planner([run], reply="not json").build(NOW)
    assert plan.suggested[0].start.hour < 17


def test_explicit_work_hour_is_kept_and_marked() -> None:
    wednesday = datetime(2026, 9, 23, 10, 0, tzinfo=ZONE)
    planner = _planner([], reply="{}")
    plan = planner.build_from_lines(["уборка 14:00"], wednesday)
    assert len(plan.suggested) == 1
    assert plan.suggested[0].start.hour == 14
    assert "рабочее" in plan.suggested[0].why


def test_build_from_lines_matches_open_task() -> None:
    existing = Task(id="clean", content="Уборка", due_date="2026-09-20")
    planner = _planner([existing], reply="not json")
    plan = planner.build_from_lines(["уборка", "новое письмо"], NOW)
    ids = {item.task_id for item in plan.suggested}
    assert "clean" in ids
    news = [item for item in plan.suggested if item.is_new]
    assert len(news) == 1
    assert news[0].content == "новое письмо"


def test_apply_updates_match_and_adds_new() -> None:
    existing = Task(id="clean", content="Уборка", due_date="2026-09-20")
    sync = FakeSync()
    planner = _planner([existing], reply="not json", sync=sync)
    plan = planner.build_from_lines(["уборка", "письмо Каю"], NOW)
    applied = planner.apply(plan.plan_id, NOW)
    assert applied is not None
    assert [item[0] for item in planner.todoist.updates] == ["clean"]
    assert [task.content for task in planner.todoist.added] == ["письмо Каю"]
    assert sync.ran == [NOW]


def test_render_includes_why_and_load() -> None:
    task = Task(id="clean", content="Уборка", due_date="2026-09-20")
    reply = '{"scheduled":[{"ref":"t1","start":"13:00","minutes":60,"why":"после рынка"}],"anytime":[]}'
    text = render(_planner([task], reply=reply).build(NOW))
    assert "Уборка · после рынка" in text
    assert "**Load** 1h of 4h" in text
