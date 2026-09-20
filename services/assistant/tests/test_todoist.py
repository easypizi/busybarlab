import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from toy_lair_assistant.clients.todoist import TodoistClient


def _client(handler) -> TodoistClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://api.todoist.com")
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    return TodoistClient(token="t", http=http, now=lambda: now)


def test_today_returns_only_due_today() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/sync"
        assert request.headers["authorization"] == "Bearer t"
        return httpx.Response(
            200,
            json={
                "sync_token": "abc",
                "items": [
                    {
                        "id": "1",
                        "content": "Buy milk",
                        "checked": False,
                        "due": {"date": "2026-09-19", "string": "today"},
                    },
                    {
                        "id": "2",
                        "content": "Later",
                        "checked": False,
                        "due": {"date": "2026-09-21", "string": "Mon"},
                    },
                    {"id": "3", "content": "No due", "checked": False, "due": None},
                ],
            },
        )

    tasks = _client(handler).today()
    assert [t.id for t in tasks] == ["1"]
    assert tasks[0].content == "Buy milk"


def test_add_sends_item_add() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"sync_status": {"x": "ok"}, "temp_id_mapping": {"tmp": "99"}},
        )

    created = _client(handler).add("Ship it", due_string="tomorrow")
    command = seen["body"]["commands"][0]
    assert command["type"] == "item_add"
    assert command["args"]["content"] == "Ship it"
    assert command["args"]["due"]["string"] == "tomorrow"
    assert created.id == "99"


def test_add_sends_due_datetime_with_timezone() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"sync_status": {"x": "ok"}, "temp_id_mapping": {"tmp": "88"}},
        )

    created = _client(handler).add(
        "Write plan", due_datetime="2026-09-21T15:00:00-07:00"
    )
    due = seen["body"]["commands"][0]["args"]["due"]
    assert due["date"] == "2026-09-21T15:00:00-07:00"
    assert due["timezone"] == "America/Los_Angeles"
    assert created.id == "88"


def test_complete_sends_item_complete() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"sync_status": {"x": "ok"}})

    _client(handler).complete("1")
    assert seen["body"]["commands"][0]["type"] == "item_complete"
    assert seen["body"]["commands"][0]["args"]["id"] == "1"


def test_to_task_reads_all_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "sync_token": "abc",
                "projects": [{"id": "p1", "name": "Home"}],
                "items": [
                    {
                        "id": "7",
                        "content": "Pay rent",
                        "checked": False,
                        "priority": 4,
                        "labels": ["finance"],
                        "description": "monthly",
                        "project_id": "p1",
                        "due": {
                            "date": "2026-09-19T12:00:00",
                            "string": "today 12:00",
                            "is_recurring": True,
                        },
                        "deadline": {"date": "2026-09-25"},
                        "duration": {"amount": 30, "unit": "minute"},
                    }
                ],
            },
        )

    tasks = _client(handler).open_tasks()
    task = tasks[0]
    assert task.priority == 4
    assert task.labels == ["finance"]
    assert task.deadline == "2026-09-25"
    assert task.description == "monthly"
    assert task.duration_minutes == 30
    assert task.project == "Home"
    assert task.project_id == "p1"
    assert task.is_recurring is True
    assert task.due_time == "2026-09-19T12:00:00"
    assert task.due_date == "2026-09-19"


def test_add_sends_deadline_duration_priority() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"sync_status": {"x": "ok"}, "temp_id_mapping": {"tmp": "55"}},
        )

    created = _client(handler).add(
        "Pay rent",
        priority=4,
        labels=["finance"],
        deadline="2026-09-25",
        description="monthly",
        duration_minutes=30,
    )
    args = seen["body"]["commands"][0]["args"]
    assert args["priority"] == 4
    assert args["labels"] == ["finance"]
    assert args["deadline"] == {"date": "2026-09-25"}
    assert args["description"] == "monthly"
    assert args["duration"] == {"amount": 30, "unit": "minute"}
    assert created.id == "55"


def test_no_todoist_delete_tool() -> None:
    from toy_lair_assistant.agent import Agent
    from toy_lair_assistant.llm import TOOL_SCHEMAS

    names = [schema["function"]["name"] for schema in TOOL_SCHEMAS]
    assert not any(name.startswith("todoist_") and "delete" in name for name in names)
    agent = Agent(todoist=object(), calendar=object(), llm=object(), now=lambda: None)
    assert not any(name.startswith("todoist_") and "delete" in name for name in agent.tools)
