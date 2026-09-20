from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from toy_lair_assistant.models import CalendarEvent

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_ROOT = "https://www.googleapis.com/calendar/v3"


class GoogleAuthExpired(Exception):
    pass


def _emails(attendees: Sequence[str] | str | None) -> list[str]:
    if not attendees:
        return []
    if isinstance(attendees, str):
        return [part.strip() for part in attendees.split(",") if part.strip()]
    return [str(item).strip() for item in attendees if str(item).strip()]


class GoogleCalendarClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        calendar_id: str = "primary",
        http: httpx.Client | None = None,
        now: Callable[[], datetime] | None = None,
        timezone: str = "America/Los_Angeles",
        on_auth_error: Callable[[], None] | None = None,
        read_calendars: str = "all",
        tasks_calendar_id: str = "",
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.calendar_id = calendar_id
        self.http = http or httpx.Client(timeout=30)
        self.now = now
        self.timezone = timezone
        self.on_auth_error = on_auth_error
        self.read_calendars = read_calendars
        self.tasks_calendar_id = tasks_calendar_id
        self._access_token: str | None = None
        self._expires_at: datetime | None = None
        self._owns_http = http is None
        self._cals: list[dict] = []
        self._cals_at: datetime | None = None
        self._ensured_id: str | None = None

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def _current(self) -> datetime:
        if self.now:
            return self.now()
        return datetime.now(ZoneInfo(self.timezone))

    def _reset_token(self) -> None:
        self._access_token = None
        self._expires_at = None

    def _token(self) -> str:
        now = self._current()
        if self._access_token and self._expires_at and now < self._expires_at:
            return self._access_token
        response = self.http.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code >= 400:
            body = response.text
            if "invalid_grant" in body or response.status_code == 401:
                if self.on_auth_error:
                    self.on_auth_error()
                raise GoogleAuthExpired("Google calendar auth expired")
            response.raise_for_status()
        data = response.json()
        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in") or 3600)
        self._expires_at = now + timedelta(seconds=max(expires_in - 60, 1))
        return self._access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}

    def _events_url(
        self, event_id: str | None = None, calendar_id: str | None = None
    ) -> str:
        cid = calendar_id or self.calendar_id
        base = f"{API_ROOT}/calendars/{cid}/events"
        if event_id:
            return f"{base}/{event_id}"
        return base

    def calendars(self) -> list[dict]:
        now = self._current()
        if self._cals and self._cals_at and now - self._cals_at < timedelta(hours=1):
            return self._cals
        response = self._api("GET", f"{API_ROOT}/users/me/calendarList")
        self._cals = list(response.json().get("items") or [])
        self._cals_at = now
        return self._cals

    def _read_ids(self) -> list[str]:
        raw = (self.read_calendars or "all").strip()
        if raw not in ("", "all"):
            return [part.strip() for part in raw.split(",") if part.strip()]
        if raw == "primary":
            return [self.calendar_id]
        try:
            items = self.calendars()
        except GoogleAuthExpired:
            raise
        except Exception:
            return [self.calendar_id]
        ids = [str(item["id"]) for item in items if item.get("selected", True) and item.get("id")]
        return ids or [self.calendar_id]

    def ensure_calendar(self, name: str = "Tito") -> str:
        if self.tasks_calendar_id:
            return self.tasks_calendar_id
        if self._ensured_id:
            return self._ensured_id
        for item in self.calendars():
            if item.get("summary") == name and item.get("id"):
                self._ensured_id = str(item["id"])
                return self._ensured_id
        response = self._api("POST", f"{API_ROOT}/calendars", json={"summary": name})
        self._ensured_id = str(response.json()["id"])
        self._cals_at = None
        return self._ensured_id

    def _when(self, value: str) -> dict[str, str]:
        return {"dateTime": value, "timeZone": self.timezone}

    def _api(
        self,
        method: str,
        url: str,
        *,
        retry: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        response = self.http.request(method, url, headers=self._headers(), **kwargs)
        if response.status_code == 401 and retry:
            self._reset_token()
            response = self.http.request(method, url, headers=self._headers(), **kwargs)
        response.raise_for_status()
        return response

    def events_for_day(self, day: datetime | None = None) -> list[CalendarEvent]:
        moment = day or self._current()
        start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self.events_in_range(start, end)

    def events_in_calendar(
        self, calendar_id: str, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        response = self._api(
            "GET",
            self._events_url(calendar_id=calendar_id),
            params={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
        return [
            self._to_event(raw, calendar_id)
            for raw in response.json().get("items") or []
        ]

    def events_in_range(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for calendar_id in self._read_ids():
            events.extend(self.events_in_calendar(calendar_id, start, end))
        events.sort(key=lambda event: event.start)
        return events

    def upsert_task_event(
        self,
        calendar_id: str,
        todoist_id: str,
        title: str,
        start: str,
        end: str,
    ) -> CalendarEvent:
        body = {
            "summary": title,
            "start": self._when(start),
            "end": self._when(end),
            "extendedProperties": {"private": {"todoist_id": todoist_id}},
        }
        found = self._find_task_event(calendar_id, todoist_id)
        if found:
            response = self._api(
                "PATCH", self._events_url(found.id, calendar_id), json=body
            )
        else:
            response = self._api(
                "POST", self._events_url(calendar_id=calendar_id), json=body
            )
        return self._to_event(response.json(), calendar_id)

    def delete_task_event(self, calendar_id: str, event_id: str) -> None:
        self._api("DELETE", self._events_url(event_id, calendar_id))

    def _find_task_event(self, calendar_id: str, todoist_id: str) -> CalendarEvent | None:
        response = self._api(
            "GET",
            self._events_url(calendar_id=calendar_id),
            params={
                "privateExtendedProperty": f"todoist_id={todoist_id}",
                "singleEvents": "true",
            },
        )
        items = response.json().get("items") or []
        if not items:
            return None
        return self._to_event(items[0], calendar_id)

    def create(
        self,
        title: str,
        start: str,
        end: str,
        attendees: Sequence[str] | str | None = None,
        description: str | None = None,
    ) -> CalendarEvent:
        body: dict[str, Any] = {
            "summary": title,
            "start": self._when(start),
            "end": self._when(end),
        }
        if description:
            body["description"] = description
        emails = _emails(attendees)
        if emails:
            body["attendees"] = [{"email": email} for email in emails]
        params = {"sendUpdates": "all"} if emails else None
        response = self._api("POST", self._events_url(), json=body, params=params)
        return self._to_event(response.json())

    def move(self, event_id: str, start: str, end: str) -> CalendarEvent:
        response = self._api(
            "PATCH",
            self._events_url(event_id),
            json={"start": self._when(start), "end": self._when(end)},
        )
        return self._to_event(response.json())

    def delete(self, event_id: str) -> None:
        self._api("DELETE", self._events_url(event_id))

    def _to_event(self, raw: dict, calendar_id: str | None = None) -> CalendarEvent:
        start = raw.get("start") or {}
        end = raw.get("end") or {}
        private = ((raw.get("extendedProperties") or {}).get("private") or {})
        return CalendarEvent(
            id=str(raw.get("id")),
            title=str(raw.get("summary") or "(no title)"),
            start=str(start.get("dateTime") or start.get("date") or ""),
            end=str(end.get("dateTime") or end.get("date") or ""),
            calendar_id=calendar_id or self.calendar_id,
            todoist_id=private.get("todoist_id"),
        )
