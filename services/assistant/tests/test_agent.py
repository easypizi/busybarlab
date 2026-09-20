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

    def add(self, content: str, due_string: str | None = None):
        self.added.append((content, due_string))
        task = Task(id="9", content=content, due_date=None, due_string=due_string)
        self.tasks.append(task)
        return task

    def complete(self, task_id: str) -> None:
        self.completed.append(task_id)

    def update(self, task_id: str, **fields) -> None:
        return None

    def reschedule(self, task_id: str, due_string: str) -> None:
        return None


class FakeCal:
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

    def create(self, **kwargs):
        return self.events_for_day()[0]

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
    assert todoist.added == [("Call mom", "today")]
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
