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


def test_complete_sends_item_complete() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"sync_status": {"x": "ok"}})

    _client(handler).complete("1")
    assert seen["body"]["commands"][0]["type"] == "item_complete"
    assert seen["body"]["commands"][0]["args"]["id"] == "1"
