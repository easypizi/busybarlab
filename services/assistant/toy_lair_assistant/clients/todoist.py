from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx

from toy_lair_assistant.models import Task

SYNC_PATH = "/api/v1/sync"


class TodoistClient:
    def __init__(
        self,
        token: str,
        http: httpx.Client | None = None,
        now: Callable[[], datetime] | None = None,
        timezone: str = "America/Los_Angeles",
    ) -> None:
        self.token = token
        self.http = http or httpx.Client(base_url="https://api.todoist.com", timeout=30)
        self.now = now
        self.timezone = timezone
        self._owns_http = http is None
        self._projects: dict[str, str] = {}
        self._projects_at: datetime | None = None

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _sync(self, payload: dict) -> dict:
        response = self.http.post(SYNC_PATH, headers=self._headers(), json=payload)
        response.raise_for_status()
        return response.json()

    def _current(self) -> datetime:
        if self.now:
            return self.now()
        return datetime.now()

    def projects(self) -> dict[str, str]:
        now = self._current()
        if self._projects and self._projects_at and now - self._projects_at < timedelta(minutes=10):
            return self._projects
        self._snapshot()
        return self._projects

    def _snapshot(self) -> list[dict]:
        data = self._sync(
            {"sync_token": "*", "resource_types": ["items", "projects"]}
        )
        self._projects = {
            str(raw.get("id")): str(raw.get("name") or "")
            for raw in data.get("projects") or []
        }
        self._projects_at = self._current()
        return list(data.get("items") or [])

    def _items(self) -> list[dict]:
        return self._snapshot()

    def _today_stamp(self) -> str:
        return self._current().date().isoformat()

    def open_tasks(self) -> list[Task]:
        items = self._snapshot()
        names = self._projects
        out: list[Task] = []
        for raw in items:
            if raw.get("checked") or raw.get("is_deleted"):
                continue
            out.append(self._to_task(raw, names))
        return out

    def today(self) -> list[Task]:
        stamp = self._today_stamp()
        return [task for task in self.open_tasks() if task.due_date == stamp]

    def upcoming(self, days: int = 7) -> list[Task]:
        start = self._current().date()
        out: list[Task] = []
        for task in self.open_tasks():
            if not task.due_date:
                continue
            due = datetime.fromisoformat(task.due_date).date()
            delta = (due - start).days
            if 0 <= delta <= days:
                out.append(task)
        return out

    def add(
        self,
        content: str,
        due_string: str | None = None,
        due_datetime: str | None = None,
        priority: int | None = None,
        labels: list[str] | str | None = None,
        deadline: str | None = None,
        description: str | None = None,
        duration_minutes: int | None = None,
        project: str | None = None,
        project_id: str | None = None,
    ) -> Task:
        temp_id = str(uuid.uuid4())
        args: dict[str, Any] = {"content": content}
        self._apply_fields(
            args,
            due_string=due_string,
            due_datetime=due_datetime,
            priority=priority,
            labels=labels,
            deadline=deadline,
            description=description,
            duration_minutes=duration_minutes,
            project=project,
            project_id=project_id,
        )
        data = self._command("item_add", args, temp_id=temp_id)
        mapping = data.get("temp_id_mapping") or {}
        real_id = mapping.get(temp_id) or next(iter(mapping.values()), temp_id)
        return Task(
            id=str(real_id),
            content=content,
            due_string=due_string,
            due_time=due_datetime,
            due_date=due_datetime.split("T")[0] if due_datetime else None,
            priority=int(priority or 1),
            labels=_labels(labels),
            deadline=deadline,
            description=description or "",
            duration_minutes=duration_minutes,
            project=project,
            project_id=project_id,
        )

    def complete(self, task_id: str) -> None:
        self._command("item_complete", {"id": task_id})

    def update(self, task_id: str, **fields: Any) -> None:
        args: dict[str, Any] = {"id": task_id}
        self._apply_fields(args, **fields)
        if "content" in fields and fields["content"] is not None:
            args["content"] = fields["content"]
        self._command("item_update", args)

    def reschedule(self, task_id: str, due_string: str) -> None:
        self._command("item_update", {"id": task_id, "due": {"string": due_string}})

    def _apply_fields(self, args: dict[str, Any], **fields: Any) -> None:
        if fields.get("due_datetime"):
            args["due"] = {"date": fields["due_datetime"], "timezone": self.timezone}
        elif fields.get("due_string"):
            args["due"] = {"string": fields["due_string"]}
        if fields.get("priority") is not None:
            args["priority"] = int(fields["priority"])
        if fields.get("labels") is not None:
            args["labels"] = _labels(fields["labels"])
        if fields.get("deadline"):
            args["deadline"] = {"date": str(fields["deadline"])[:10]}
        if fields.get("description") is not None:
            args["description"] = fields["description"]
        if fields.get("duration_minutes") is not None:
            minutes = int(fields["duration_minutes"])
            args["duration"] = {"amount": minutes, "unit": "minute"} if minutes else None
        project_id = fields.get("project_id")
        if not project_id and fields.get("project"):
            names = self.projects()
            wanted = str(fields["project"]).lower()
            project_id = next(
                (pid for pid, name in names.items() if name.lower() == wanted),
                None,
            )
        if project_id:
            args["project_id"] = project_id

    def _command(self, command_type: str, args: dict, temp_id: str | None = None) -> dict:
        command = {
            "type": command_type,
            "uuid": str(uuid.uuid4()),
            "args": args,
        }
        if temp_id:
            command["temp_id"] = temp_id
        return self._sync({"commands": [command]})

    def _to_task(self, raw: dict, names: dict[str, str] | None = None) -> Task:
        due = raw.get("due") or {}
        raw_date = due.get("date")
        due_date = None
        due_time = due.get("datetime")
        if raw_date:
            due_date = str(raw_date).split("T")[0]
            if "T" in str(raw_date) and not due_time:
                due_time = str(raw_date)
        deadline = raw.get("deadline") or {}
        duration = raw.get("duration") or {}
        minutes = None
        if duration.get("amount"):
            amount = int(duration["amount"])
            minutes = amount * 24 * 60 if duration.get("unit") == "day" else amount
        project_id = str(raw.get("project_id") or "") or None
        return Task(
            id=str(raw.get("id")),
            content=str(raw.get("content") or ""),
            due_date=due_date,
            due_string=due.get("string"),
            due_time=due_time,
            priority=int(raw.get("priority") or 1),
            labels=list(raw.get("labels") or []),
            deadline=(deadline.get("date") if isinstance(deadline, dict) else None),
            description=str(raw.get("description") or ""),
            duration_minutes=minutes,
            project_id=project_id,
            project=(names or {}).get(project_id or ""),
            is_recurring=bool(due.get("is_recurring")),
        )


def _labels(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(item).strip() for item in value if str(item).strip()]
