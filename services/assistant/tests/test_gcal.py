import json
from datetime import datetime, timedelta
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
        read_calendars="primary",
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
        assert body["start"]["timeZone"] == "America/Los_Angeles"
        assert body["end"]["timeZone"] == "America/Los_Angeles"
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


def test_expired_token_is_refreshed() -> None:
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    clock = {"t": now}
    tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            tokens.append(f"acc{len(tokens) + 1}")
            return httpx.Response(
                200, json={"access_token": tokens[-1], "expires_in": 3600}
            )
        assert request.headers["authorization"] == f"Bearer {tokens[-1]}"
        return httpx.Response(200, json={"items": []})

    client = GoogleCalendarClient(
        client_id="id",
        client_secret="sec",
        refresh_token="ref",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        now=lambda: clock["t"],
        timezone="America/Los_Angeles",
    )
    client.events_for_day()
    assert len(tokens) == 1
    clock["t"] = now + timedelta(minutes=30)
    client.events_for_day()
    assert len(tokens) == 1
    clock["t"] = now + timedelta(seconds=3541)
    client.events_for_day()
    assert len(tokens) == 2


def test_events_401_refreshes_token_and_retries() -> None:
    auths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            n = 1 + sum(1 for item in auths if item.startswith("token"))
            auths.append(f"token{n}")
            return httpx.Response(
                200, json={"access_token": f"acc{n}", "expires_in": 3600}
            )
        auths.append(request.headers["authorization"])
        if request.headers["authorization"] == "Bearer acc1":
            return httpx.Response(401, json={"error": "unauthorized"})
        return httpx.Response(200, json={"items": []})

    events = _client(handler).events_for_day()
    assert events == []
    assert "Bearer acc1" in auths
    assert "Bearer acc2" in auths


def test_create_includes_attendees_and_description() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "acc", "expires_in": 3600})
        seen["body"] = json.loads(request.content)
        seen["query"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "id": "e3",
                "summary": "Sync",
                "start": {"dateTime": "2026-09-23T15:00:00-07:00"},
                "end": {"dateTime": "2026-09-23T16:00:00-07:00"},
            },
        )

    event = _client(handler).create(
        title="Sync",
        start="2026-09-23T15:00:00-07:00",
        end="2026-09-23T16:00:00-07:00",
        attendees=["ivan@example.com"],
        description="weekly",
    )
    assert event.id == "e3"
    assert seen["body"]["attendees"] == [{"email": "ivan@example.com"}]
    assert seen["body"]["description"] == "weekly"
    assert "sendUpdates=all" in seen["query"]


def test_calendars_are_cached_for_an_hour() -> None:
    calls: list[str] = []
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    clock = {"t": now}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "acc", "expires_in": 3600})
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={"items": [{"id": "primary", "summary": "Primary", "selected": True}]},
        )

    client = GoogleCalendarClient(
        client_id="id",
        client_secret="sec",
        refresh_token="ref",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        now=lambda: clock["t"],
        read_calendars="all",
    )
    first = client.calendars()
    clock["t"] = now + timedelta(minutes=30)
    second = client.calendars()
    assert first == second
    assert calls.count("/calendar/v3/users/me/calendarList") == 1


def test_events_in_range_merges_selected_calendars() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "acc", "expires_in": 3600})
        path = request.url.path
        if path.endswith("/calendarList"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "work", "summary": "Work", "selected": True},
                        {"id": "home", "summary": "Home", "selected": True},
                        {"id": "hidden", "summary": "Hidden", "selected": False},
                    ]
                },
            )
        if "/calendars/work/events" in path:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "w1",
                            "summary": "Standup",
                            "start": {"dateTime": "2026-09-19T10:00:00-07:00"},
                            "end": {"dateTime": "2026-09-19T10:30:00-07:00"},
                        }
                    ]
                },
            )
        if "/calendars/home/events" in path:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "h1",
                            "summary": "Dinner",
                            "start": {"dateTime": "2026-09-19T18:00:00-07:00"},
                            "end": {"dateTime": "2026-09-19T19:00:00-07:00"},
                            "extendedProperties": {"private": {"todoist_id": "t3"}},
                        }
                    ]
                },
            )
        raise AssertionError(path)

    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    client = GoogleCalendarClient(
        client_id="id",
        client_secret="sec",
        refresh_token="ref",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        now=lambda: now,
        read_calendars="all",
    )
    events = client.events_in_range(now, now + timedelta(days=1))
    assert [event.title for event in events] == ["Standup", "Dinner"]
    assert events[0].calendar_id == "work"
    assert events[1].todoist_id == "t3"


def test_ensure_calendar_creates_once() -> None:
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "acc", "expires_in": 3600})
        if request.url.path.endswith("/calendarList"):
            return httpx.Response(200, json={"items": []})
        if request.method == "POST" and request.url.path.endswith("/calendars"):
            posts.append(request.url.path)
            body = json.loads(request.content)
            assert body["summary"] == "Tito"
            return httpx.Response(200, json={"id": "tito-cal", "summary": "Tito"})
        raise AssertionError(f"{request.method} {request.url.path}")

    client = GoogleCalendarClient(
        client_id="id",
        client_secret="sec",
        refresh_token="ref",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        now=lambda: datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
        read_calendars="all",
    )
    assert client.ensure_calendar("Tito") == "tito-cal"
    assert client.ensure_calendar("Tito") == "tito-cal"
    assert len(posts) == 1
