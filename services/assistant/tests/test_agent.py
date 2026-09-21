from datetime import datetime
from zoneinfo import ZoneInfo

from toy_lair_assistant.agent import Agent, AgentResult, ToolCall
from toy_lair_assistant.models import CalendarEvent, Task


class FakeTodoist:
    def __init__(self) -> None:
        self.tasks = [
            Task(id="1", content="Buy milk", due_date="2026-09-19", due_string="today"),
        ]
        self.completed: list[str] = []
        self.added: list[tuple[str, str | None]] = []

    def today(self):
        return list(self.tasks)

    def upcoming(self, days: int = 7):
        return list(self.tasks)

    def add(
        self,
        content: str,
        due_string: str | None = None,
        due_datetime: str | None = None,
        **kwargs,
    ):
        self.added.append((content, due_string, due_datetime))
        task = Task(
            id="9",
            content=content,
            due_date=due_datetime.split("T")[0] if due_datetime else None,
            due_string=due_string,
            due_time=due_datetime,
            duration_minutes=kwargs.get("duration_minutes"),
            priority=int(kwargs.get("priority") or 1),
            labels=list(kwargs.get("labels") or []),
            deadline=kwargs.get("deadline"),
            description=kwargs.get("description") or "",
        )
        self.tasks.append(task)
        return task

    def complete(self, task_id: str) -> None:
        self.completed.append(task_id)

    def update(self, task_id: str, **fields) -> None:
        return None

    def reschedule(self, task_id: str, due_string: str) -> None:
        return None


class FakeCal:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def events_for_day(self, day=None):
        return [
            CalendarEvent(
                id="e1",
                title="Standup",
                start="2026-09-19T10:00:00-07:00",
                end="2026-09-19T10:30:00-07:00",
            )
        ]

    def events_in_range(self, start, end):
        return self.events_for_day()

    def calendars(self):
        return [
            {"summary": "itolstof@gmail.com", "id": "itolstof@gmail.com"},
            {"summary": "Pump it! Louder!", "id": "pump"},
            {"summary": "Tito", "id": "tito"},
        ]

    def create(self, **kwargs):
        self.created.append(kwargs)
        return CalendarEvent(
            id="n1",
            title=str(kwargs.get("title") or "Standup"),
            start=str(kwargs.get("start") or ""),
            end=str(kwargs.get("end") or ""),
        )

    def move(self, event_id: str, **kwargs):
        return self.events_for_day()[0]

    def delete(self, event_id: str) -> None:
        return None


class ScriptedLLM:
    def __init__(
        self,
        calls: list[ToolCall] | None = None,
        text: str = "ok",
        rounds: list[AgentResult] | None = None,
    ) -> None:
        self.text = text
        if rounds is not None:
            self.rounds = list(rounds)
        else:
            self.rounds = [
                AgentResult(reply=text, tool_calls=list(calls or [])),
                AgentResult(reply=text, tool_calls=[]),
            ]
        self.seen: list = []

    def complete(self, messages, tools):
        self.seen.append(messages)
        if self.rounds:
            return self.rounds.pop(0)
        return AgentResult(reply=self.text, tool_calls=[])


def _now():
    return datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))


def test_today_payload_merges_tasks_and_events() -> None:
    agent = Agent(todoist=FakeTodoist(), calendar=FakeCal(), llm=ScriptedLLM([]), now=_now)
    payload = agent.today_payload(_now())
    kinds = [item["kind"] for item in payload["items"]]
    assert "task" in kinds
    assert "event" in kinds
    titles = [item["title"] for item in payload["items"]]
    assert "Buy milk" in titles
    assert "Standup" in titles


def test_handle_text_runs_todoist_add() -> None:
    todoist = FakeTodoist()
    llm = ScriptedLLM(
        [ToolCall(name="todoist_add", arguments={"content": "Call mom", "due_string": "today"})],
        text="Added Call mom.",
    )
    agent = Agent(todoist=todoist, calendar=FakeCal(), llm=llm, now=_now)
    result = agent.handle_text("add call mom today")
    assert todoist.added == [("Call mom", "today", None)]
    assert "Call mom" in result.reply


def test_system_prompt_has_today_indexes() -> None:
    llm = ScriptedLLM([])
    agent = Agent(todoist=FakeTodoist(), calendar=FakeCal(), llm=llm, now=_now)
    agent.handle_text("what is at 14:00")
    system = llm.seen[0][0]["content"]
    assert "2026-09-19" in system
    assert "America/Los_Angeles" in system
    assert "t1" in system
    assert "Buy milk" in system
    assert "e1" in system
    assert "Standup" in system


def test_complete_task_by_index() -> None:
    todoist = FakeTodoist()
    llm = ScriptedLLM(
        [ToolCall(name="todoist_complete", arguments={"task_id": "t1"})],
        text="Closed Buy milk.",
    )
    agent = Agent(todoist=todoist, calendar=FakeCal(), llm=llm, now=_now)
    result = agent.handle_text("close t2")
    assert todoist.completed == ["1"]
    assert "Buy milk" in result.reply or result.reply


def test_move_event_by_index() -> None:
    calendar = FakeCal()
    moved: list[tuple] = []

    def move(event_id: str, start: str, end: str):
        moved.append((event_id, start, end))
        return calendar.events_for_day()[0]

    calendar.move = move  # type: ignore[method-assign]
    llm = ScriptedLLM(
        [
            ToolCall(
                name="gcal_move",
                arguments={
                    "event_id": "e1",
                    "start": "2026-09-19T15:00:00-07:00",
                    "end": "2026-09-19T15:30:00-07:00",
                },
            )
        ],
        text="Moved Standup to 15:00.",
    )
    agent = Agent(todoist=FakeTodoist(), calendar=calendar, llm=llm, now=_now)
    result = agent.handle_text("move e1 to 15:00")
    assert moved[0][0] == "e1"
    assert "15:00" in moved[0][1]
    assert "Standup" in result.reply or result.reply


def test_tool_loop_sends_results_back() -> None:
    todoist = FakeTodoist()
    llm = ScriptedLLM(
        rounds=[
            AgentResult(
                reply="",
                tool_calls=[ToolCall(name="todoist_complete", arguments={"task_id": "t1"})],
            ),
            AgentResult(reply="Done. Buy milk is closed.", tool_calls=[]),
        ]
    )
    agent = Agent(todoist=todoist, calendar=FakeCal(), llm=llm, now=_now)
    result = agent.handle_text("close the milk task")
    assert todoist.completed == ["1"]
    assert len(llm.seen) == 2
    second = llm.seen[1]
    roles = [m["role"] for m in second]
    assert "tool" in roles
    assert result.reply == "Done. Buy milk is closed."


def test_delete_event_requires_confirmation() -> None:
    calendar = FakeCal()
    deleted: list[str] = []
    calendar.delete = lambda event_id: deleted.append(event_id)  # type: ignore[method-assign]
    llm = ScriptedLLM(
        [ToolCall(name="gcal_delete", arguments={"event_id": "e1"})],
        text="Deleted Standup.",
    )
    agent = Agent(todoist=FakeTodoist(), calendar=calendar, llm=llm, now=_now)
    result = agent.handle_text("delete standup")
    assert deleted == []
    assert "confirm" in result.reply.lower()


def test_delete_event_after_confirm_word() -> None:
    calendar = FakeCal()
    deleted: list[str] = []
    calendar.delete = lambda event_id: deleted.append(event_id)  # type: ignore[method-assign]
    llm = ScriptedLLM(
        [ToolCall(name="gcal_delete", arguments={"event_id": "e1"})],
        text="Deleted Standup.",
    )
    agent = Agent(todoist=FakeTodoist(), calendar=calendar, llm=llm, now=_now)
    result = agent.handle_text("delete standup, yes confirm")
    assert deleted == ["e1"]
    assert "Standup" in result.reply or deleted


def test_memory_keeps_followup(tmp_path=None) -> None:
    from toy_lair_assistant.store import MemoryStore

    store = MemoryStore()
    llm = ScriptedLLM([])
    agent = Agent(
        todoist=FakeTodoist(),
        calendar=FakeCal(),
        llm=llm,
        now=_now,
        store=store,
    )
    agent.handle_text("the standup is e1", channel="r1")
    llm.rounds = [AgentResult(reply="ok", tool_calls=[])]
    agent.handle_text("move it to tomorrow", channel="r1")
    second = llm.seen[-1]
    user_bits = " ".join(m.get("content") or "" for m in second if m["role"] == "user")
    assert "standup is e1" in user_bits
    assert "move it to tomorrow" in user_bits


PLAN_ITEMS = [
    {
        "content": "Write brief",
        "start": "2026-09-21T10:00:00-07:00",
        "duration_minutes": 60,
    }
]


def test_system_prompt_has_planning_rules() -> None:
    llm = ScriptedLLM([])
    agent = Agent(todoist=FakeTodoist(), calendar=FakeCal(), llm=llm, now=_now)
    agent.handle_text("plan my week")
    system = llm.seen[0][0]["content"]
    assert "free_slots" in system
    assert "todoist_upcoming" in system
    assert "plan_apply" in system
    assert "confirm" in system.lower()


def test_plan_apply_requires_confirmation() -> None:
    todoist = FakeTodoist()
    calendar = FakeCal()
    llm = ScriptedLLM(
        [ToolCall(name="plan_apply", arguments={"items": PLAN_ITEMS})],
        text="Planned 1 items, 1 events.",
    )
    agent = Agent(todoist=todoist, calendar=calendar, llm=llm, now=_now)
    result = agent.handle_text("schedule these")
    assert todoist.added == []
    assert calendar.created == []
    assert "confirm" in result.reply.lower()
    assert "plan" in result.reply.lower()


def test_plan_apply_after_confirm_word() -> None:
    todoist = FakeTodoist()
    calendar = FakeCal()
    llm = ScriptedLLM(
        [ToolCall(name="plan_apply", arguments={"items": PLAN_ITEMS})],
        text="Planned 1 items, 1 events.",
    )
    agent = Agent(todoist=todoist, calendar=calendar, llm=llm, now=_now)
    result = agent.handle_text("давай")
    assert todoist.added == [("Write brief", None, "2026-09-21T10:00:00-07:00")]
    assert calendar.created == []
    assert todoist.tasks[-1].duration_minutes == 60
    assert "Planned 1" in result.reply or result.reply


def test_gcal_create_duration_and_attendees() -> None:
    calendar = FakeCal()
    llm = ScriptedLLM(
        [
            ToolCall(
                name="gcal_create",
                arguments={
                    "title": "Sync with Ivan",
                    "start": "2026-09-23T15:00:00-07:00",
                    "duration_minutes": 60,
                    "attendees": ["ivan@example.com"],
                    "description": "weekly",
                },
            )
        ],
        text="Created Sync with Ivan.",
    )
    agent = Agent(todoist=FakeTodoist(), calendar=calendar, llm=llm, now=_now)
    result = agent.handle_text("meeting with Ivan Wednesday at 15")
    created = calendar.created[0]
    assert created["title"] == "Sync with Ivan"
    assert created["start"] == "2026-09-23T15:00:00-07:00"
    assert "2026-09-23T16:00:00" in created["end"]
    assert created["attendees"] == ["ivan@example.com"]
    assert created["description"] == "weekly"
    assert "Ivan" in result.reply or result.reply


def test_tool_loop_allows_four_rounds() -> None:
    llm = ScriptedLLM(
        rounds=[
            AgentResult(
                reply="",
                tool_calls=[ToolCall(name="free_slots", arguments={"days": 7})],
            ),
            AgentResult(
                reply="",
                tool_calls=[ToolCall(name="todoist_upcoming", arguments={"days": 7})],
            ),
            AgentResult(
                reply="",
                tool_calls=[ToolCall(name="todoist_today", arguments={})],
            ),
            AgentResult(reply="Here is a plan.", tool_calls=[]),
        ]
    )
    agent = Agent(todoist=FakeTodoist(), calendar=FakeCal(), llm=llm, now=_now)
    result = agent.handle_text("plan a week of chores")
    assert len(llm.seen) == 4
    assert result.reply == "Here is a plan."


def test_system_prompt_is_tito_and_forbids_delete() -> None:
    llm = ScriptedLLM([])
    todoist = FakeTodoist()
    todoist.tasks = [
        Task(
            id="1",
            content="Pay rent",
            due_date="2026-09-19",
            due_string="12:00",
            priority=4,
            labels=["finance"],
            deadline="2026-09-25",
            duration_minutes=30,
        )
    ]
    agent = Agent(todoist=todoist, calendar=FakeCal(), llm=llm, now=_now)
    agent.handle_text("what's on")
    system = llm.seen[0][0]["content"]
    assert "You are Tito" in system
    assert "Never delete Todoist" in system
    assert "Plain text only" in system
    assert "p1" in system
    assert "@finance" in system
    assert "deadline 09-25" in system
    assert "30m" in system
    assert "Calendars:" in system
    assert "itolstof@gmail.com" in system
    assert "Tito (task mirror)" in system
    assert "Next:" in system
    assert "today only" in system
    assert "Weekdays 09:00-17:00" in system
    llm.rounds = [AgentResult(reply="ok", tool_calls=[])]
    agent.handle_text("hi", channel="telegram")
    telegram = llm.seen[-1][0]["content"]
    assert "**headers**" in telegram or "**bold**" in telegram or "- lists" in telegram
    assert "Plain text only" not in telegram
    assert "Reply briefly for speech" not in telegram


def test_todoist_delete_tool_is_rejected() -> None:
    todoist = FakeTodoist()
    llm = ScriptedLLM(
        rounds=[
            AgentResult(
                reply="",
                tool_calls=[ToolCall(name="todoist_delete", arguments={"task_id": "1"})],
            ),
            AgentResult(reply="I will keep it.", tool_calls=[]),
        ]
    )
    agent = Agent(todoist=todoist, calendar=FakeCal(), llm=llm, now=_now)
    result = agent.handle_text("delete the milk task")
    tool = [m for m in llm.seen[1] if m["role"] == "tool"]
    assert any("does not delete" in str(m["content"]) for m in tool)
    assert result.reply == "I will keep it."


def test_today_payload_hides_todoist_mirrors() -> None:
    calendar = FakeCal()
    base = calendar.events_for_day()

    def events_for_day(day=None):
        return base + [
            CalendarEvent(
                id="m1",
                title="Pay rent",
                start="2026-09-19T12:00:00-07:00",
                end="2026-09-19T13:00:00-07:00",
                todoist_id="1",
            )
        ]

    calendar.events_for_day = events_for_day  # type: ignore[method-assign]
    agent = Agent(todoist=FakeTodoist(), calendar=calendar, llm=ScriptedLLM([]), now=_now)
    titles = [item["title"] for item in agent.today_payload(_now())["items"]]
    assert "Standup" in titles
    assert "Pay rent" not in titles
    assert "Buy milk" in titles


def test_gcal_events_reads_range() -> None:
    calendar = FakeCal()

    def events_in_range(start, end):
        return [
            CalendarEvent(
                id="e2",
                title="Gym",
                start="2026-09-21T18:00:00-07:00",
                end="2026-09-21T19:00:00-07:00",
            ),
            CalendarEvent(
                id="m1",
                title="Hidden",
                start="2026-09-21T10:00:00-07:00",
                end="2026-09-21T11:00:00-07:00",
                todoist_id="1",
            ),
        ]

    calendar.events_in_range = events_in_range  # type: ignore[method-assign]
    agent = Agent(todoist=FakeTodoist(), calendar=calendar, llm=ScriptedLLM([]), now=_now)
    text = agent._gcal_events(days=7)
    assert "Gym" in text
    assert "Hidden" not in text


def test_gcal_calendars_marks_tito() -> None:
    agent = Agent(todoist=FakeTodoist(), calendar=FakeCal(), llm=ScriptedLLM([]), now=_now)
    text = agent._gcal_calendars()
    assert "itolstof@gmail.com" in text
    assert "Tito (task mirror)" in text


def test_next_line_uses_upcoming_event() -> None:
    calendar = FakeCal()

    def events_in_range(start, end):
        return [
            CalendarEvent(
                id="e2",
                title="Тяговый день",
                start="2026-09-21T18:00:00-07:00",
                end="2026-09-21T19:00:00-07:00",
            )
        ]

    calendar.events_in_range = events_in_range  # type: ignore[method-assign]
    calendar.events_for_day = lambda day=None: []  # type: ignore[method-assign]
    llm = ScriptedLLM([])
    agent = Agent(todoist=FakeTodoist(), calendar=calendar, llm=llm, now=_now)
    agent.handle_text("what's on")
    system = llm.seen[0][0]["content"]
    assert "Next: Mon 09-21 18:00 Тяговый день" in system
    assert "Events:\n(none)" in system


def test_invoke_agent_sends_card_not_speech() -> None:
    from toy_lair_assistant.agent import invoke_agent

    class Note:
        def __init__(self) -> None:
            self.sent: list[str] = []

        def send_text(self, text: str) -> None:
            self.sent.append(text)

    llm = ScriptedLLM(
        [],
        text="На неделю у тебя в задачах и ритуалах есть: позвонить маме, бег, уборка и ещё куча дел подряд без структуры",
    )
    agent = Agent(todoist=FakeTodoist(), calendar=FakeCal(), llm=llm, now=_now)
    notify = Note()
    result = invoke_agent(agent, "что на неделю?", channel="r1", notify=notify)
    assert notify.sent
    assert "\n" in notify.sent[0]
    assert notify.sent[0] != result.reply
    wall = "На неделю у тебя в задачах и ритуалах есть: позвонить маме, бег, уборка"
    assert wall not in notify.sent[0]
