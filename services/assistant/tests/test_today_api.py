from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from toy_lair_assistant.agent import Agent, AgentResult
from toy_lair_assistant.clock import Clock
from toy_lair_assistant.main import create_app
from toy_lair_assistant.models import CalendarEvent, Task
from toy_lair_assistant.settings import Settings


class FakeTodoist:
    def today(self):
        return [Task(id="1", content="Buy milk", due_date="2026-09-19", due_string="today")]

    def complete(self, task_id: str) -> None:
        self.completed = task_id


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


class EmptyLLM:
    def complete(self, messages, tools):
        return AgentResult(reply="ok", tool_calls=[])


def test_today_and_complete() -> None:
    todoist = FakeTodoist()
    clock = Clock("America/Los_Angeles")
    clock.now = lambda: datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    agent = Agent(todoist=todoist, calendar=FakeCal(), llm=EmptyLLM(), now=clock.now)
    app = create_app(
        Settings(assistant_api_token="secret"),
        clock=clock,
        todoist=todoist,
        calendar=FakeCal(),
        agent=agent,
    )
    with TestClient(app) as client:
        today = client.get("/api/today", headers={"X-Assistant-Token": "secret"})
        assert today.status_code == 200
        titles = [item["title"] for item in today.json()["items"]]
        assert "Buy milk" in titles
        done = client.post("/api/tasks/1/complete", headers={"X-Assistant-Token": "secret"})
    assert done.status_code == 200
    assert todoist.completed == "1"
