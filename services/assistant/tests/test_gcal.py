import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from toy_lair_assistant.clients.gcal import GoogleCalendarClient


def _client(handler) -> GoogleCalendarClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    return GoogleCalendarClient(
        client_id="id",
        client_secret="sec",
        refresh_token="ref",
        calendar_id="primary",
        http=http,
        now=lambda: now,
    )


def test_events_for_day_uses_access_token() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "acc"})
        assert request.headers["authorization"] == "Bearer acc"
        assert "timeMin" in str(request.url)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "e1",
                        "summary": "Standup",
                        "start": {"dateTime": "2026-09-19T10:00:00-07:00"},
                        "end": {"dateTime": "2026-09-19T10:30:00-07:00"},
                    }
                ]
            },
        )

    events = _client(handler).events_for_day()
    assert calls[0] == "/token"
    assert events[0].id == "e1"
    assert events[0].title == "Standup"


def test_create_event_posts_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "acc"})
        assert request.method == "POST"
        body = json.loads(request.content)
        assert body["summary"] == "Dentist"
        return httpx.Response(200, json={"id": "e2", "summary": "Dentist", "start": {"dateTime": "2026-09-20T09:00:00-07:00"}, "end": {"dateTime": "2026-09-20T10:00:00-07:00"}})

    event = _client(handler).create(
        title="Dentist",
        start="2026-09-20T09:00:00-07:00",
        end="2026-09-20T10:00:00-07:00",
    )
    assert event.id == "e2"


def test_move_and_delete() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "acc"})
        methods.append(request.method)
        return httpx.Response(
            200,
            json={
                "id": "e1",
                "summary": "Standup",
                "start": {"dateTime": "2026-09-19T11:00:00-07:00"},
                "end": {"dateTime": "2026-09-19T11:30:00-07:00"},
            },
        )

    client = _client(handler)
    client.move("e1", start="2026-09-19T11:00:00-07:00", end="2026-09-19T11:30:00-07:00")
    client.delete("e1")
    assert "PATCH" in methods
    assert "DELETE" in methods


def test_invalid_grant_calls_on_auth_error() -> None:
    alerts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(500)

    client = GoogleCalendarClient(
        client_id="id",
        client_secret="sec",
        refresh_token="ref",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        now=lambda: datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
        on_auth_error=lambda: alerts.append("expired"),
    )
    from toy_lair_assistant.clients.gcal import GoogleAuthExpired

    try:
        client.events_for_day()
        raise AssertionError("expected GoogleAuthExpired")
    except GoogleAuthExpired:
        pass
    assert alerts == ["expired"]
