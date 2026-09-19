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
    def __init__(self, calls: list[ToolCall], text: str = "ok") -> None:
        self.calls = calls
        self.text = text

    def complete(self, messages, tools):
        return AgentResult(reply=self.text, tool_calls=list(self.calls))


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
