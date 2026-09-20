from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from toy_lair_assistant.models import CalendarEvent

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_ROOT = "https://www.googleapis.com/calendar/v3"


class GoogleAuthExpired(Exception):
    pass


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
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.calendar_id = calendar_id
        self.http = http or httpx.Client(timeout=30)
        self.now = now
        self.timezone = timezone
        self.on_auth_error = on_auth_error
        self._access_token: str | None = None
        self._owns_http = http is None

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def _current(self) -> datetime:
        if self.now:
            return self.now()
        return datetime.now(ZoneInfo(self.timezone))

    def _token(self) -> str:
        if self._access_token:
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
        self._access_token = response.json()["access_token"]
        return self._access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}

    def _events_url(self, event_id: str | None = None) -> str:
        base = f"{API_ROOT}/calendars/{self.calendar_id}/events"
        if event_id:
            return f"{base}/{event_id}"
        return base

    def events_for_day(self, day: datetime | None = None) -> list[CalendarEvent]:
        moment = day or self._current()
        start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self.events_in_range(start, end)

    def events_in_range(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        response = self.http.get(
            self._events_url(),
            headers=self._headers(),
            params={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
        response.raise_for_status()
        return [self._to_event(raw) for raw in response.json().get("items") or []]

    def create(self, title: str, start: str, end: str) -> CalendarEvent:
        response = self.http.post(
            self._events_url(),
            headers=self._headers(),
            json={"summary": title, "start": {"dateTime": start}, "end": {"dateTime": end}},
        )
        response.raise_for_status()
        return self._to_event(response.json())

    def move(self, event_id: str, start: str, end: str) -> CalendarEvent:
        response = self.http.patch(
            self._events_url(event_id),
            headers=self._headers(),
            json={"start": {"dateTime": start}, "end": {"dateTime": end}},
        )
        response.raise_for_status()
        return self._to_event(response.json())

    def delete(self, event_id: str) -> None:
        response = self.http.delete(self._events_url(event_id), headers=self._headers())
        response.raise_for_status()

    def _to_event(self, raw: dict) -> CalendarEvent:
        start = raw.get("start") or {}
        end = raw.get("end") or {}
        return CalendarEvent(
            id=str(raw.get("id")),
            title=str(raw.get("summary") or "(no title)"),
            start=str(start.get("dateTime") or start.get("date") or ""),
            end=str(end.get("dateTime") or end.get("date") or ""),
        )
