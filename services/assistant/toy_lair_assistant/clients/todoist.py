from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

import httpx

from toy_lair_assistant.models import Task

SYNC_PATH = "/api/v1/sync"


class TodoistClient:
    def __init__(
        self,
        token: str,
        http: httpx.Client | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.token = token
        self.http = http or httpx.Client(base_url="https://api.todoist.com", timeout=30)
        self.now = now
        self._owns_http = http is None

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _sync(self, payload: dict) -> dict:
        response = self.http.post(SYNC_PATH, headers=self._headers(), json=payload)
        response.raise_for_status()
        return response.json()

    def _items(self) -> list[dict]:
        data = self._sync({"sync_token": "*", "resource_types": ["items"]})
        return list(data.get("items") or [])

    def _today_stamp(self) -> str:
        if self.now:
            return self.now().date().isoformat()
        return datetime.now().date().isoformat()

    def today(self) -> list[Task]:
        stamp = self._today_stamp()
        out: list[Task] = []
        for raw in self._items():
            if raw.get("checked"):
                continue
            task = self._to_task(raw)
            if task.due_date == stamp:
                out.append(task)
        return out

    def upcoming(self, days: int = 7) -> list[Task]:
        if self.now is None:
            start = datetime.now().date()
        else:
            start = self.now().date()
        out: list[Task] = []
        for raw in self._items():
            if raw.get("checked"):
                continue
            task = self._to_task(raw)
            if not task.due_date:
                continue
            due = datetime.fromisoformat(task.due_date).date()
            delta = (due - start).days
            if 0 <= delta <= days:
                out.append(task)
        return out

    def add(self, content: str, due_string: str | None = None) -> Task:
        temp_id = str(uuid.uuid4())
        args: dict = {"content": content}
        if due_string:
            args["due"] = {"string": due_string}
        data = self._command("item_add", args, temp_id=temp_id)
        mapping = data.get("temp_id_mapping") or {}
        real_id = mapping.get(temp_id) or next(iter(mapping.values()), temp_id)
        return Task(id=str(real_id), content=content, due_string=due_string)

    def complete(self, task_id: str) -> None:
        self._command("item_complete", {"id": task_id})

    def update(self, task_id: str, **fields) -> None:
        args = {"id": task_id, **fields}
        self._command("item_update", args)

    def reschedule(self, task_id: str, due_string: str) -> None:
        self._command("item_update", {"id": task_id, "due": {"string": due_string}})

    def _command(self, command_type: str, args: dict, temp_id: str | None = None) -> dict:
        command = {
            "type": command_type,
            "uuid": str(uuid.uuid4()),
            "args": args,
        }
        if temp_id:
            command["temp_id"] = temp_id
        return self._sync({"commands": [command]})

    def _to_task(self, raw: dict) -> Task:
        due = raw.get("due") or {}
        return Task(
            id=str(raw.get("id")),
            content=str(raw.get("content") or ""),
            due_date=due.get("date"),
            due_string=due.get("string"),
            due_time=due.get("datetime"),
        )
