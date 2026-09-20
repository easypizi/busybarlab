from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from toy_lair_assistant.models import CalendarEvent, Task
from toy_lair_assistant.task_sync import TaskSync


SETTINGS = SimpleNamespace(
    plan_default_minutes=60,
    timezone="America/Los_Angeles",
    google_tasks_calendar_id="",
)


class FakeTodoist:
    def __init__(self, tasks: list[Task]) -> None:
        self._tasks = tasks

    def open_tasks(self):
        return list(self._tasks)


class FakeCal:
    def __init__(self) -> None:
        self.events: dict[str, CalendarEvent] = {}
        self.upserts: list[tuple[str, str, str, str]] = []
        self.deletes: list[str] = []

    def ensure_calendar(self, name: str = "Tito") -> str:
        assert name == "Tito"
        return "tito-cal"

    def events_in_calendar(self, calendar_id: str, start, end):
        assert calendar_id == "tito-cal"
        return list(self.events.values())

    def upsert_task_event(self, calendar_id, todoist_id, title, start, end):
        event = CalendarEvent(
            id=f"ev-{todoist_id}",
            title=title,
            start=start,
            end=end,
            calendar_id=calendar_id,
            todoist_id=todoist_id,
        )
        self.events[todoist_id] = event
        self.upserts.append((todoist_id, title, start, end))
        return event

    def delete_task_event(self, calendar_id, event_id):
        self.deletes.append(event_id)
        for key, event in list(self.events.items()):
            if event.id == event_id:
                del self.events[key]


def _now():
    return datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))


def _task(**kwargs) -> Task:
    data = {
        "id": "1",
        "content": "Write brief",
        "due_date": "2026-09-21",
        "due_time": "2026-09-21T10:00:00-07:00",
        "duration_minutes": 60,
    }
    data.update(kwargs)
    return Task(**data)


def test_sync_creates_then_is_idempotent() -> None:
    calendar = FakeCal()
    todoist = FakeTodoist([_task()])
    sync = TaskSync(todoist, calendar, SETTINGS)
    first = sync.run(_now())
    second = sync.run(_now())
    assert first == {"created": 1, "updated": 0, "deleted": 0}
    assert second == {"created": 0, "updated": 0, "deleted": 0}
    assert calendar.upserts[0][0] == "1"
    assert "2026-09-21T10:00:00-07:00" in calendar.upserts[0][2]
    assert "2026-09-21T11:00:00-07:00" in calendar.upserts[0][3]


def test_sync_moves_and_renames() -> None:
    calendar = FakeCal()
    todoist = FakeTodoist([_task()])
    sync = TaskSync(todoist, calendar, SETTINGS)
    sync.run(_now())
    todoist._tasks = [
        _task(content="Write draft", due_time="2026-09-21T15:00:00-07:00")
    ]
    result = sync.run(_now())
    assert result["updated"] == 1
    assert calendar.events["1"].title == "Write draft"
    assert "15:00" in calendar.events["1"].start


def test_sync_deletes_mirror_of_closed_task() -> None:
    calendar = FakeCal()
    todoist = FakeTodoist([_task()])
    sync = TaskSync(todoist, calendar, SETTINGS)
    sync.run(_now())
    todoist._tasks = []
    result = sync.run(_now())
    assert result["deleted"] == 1
    assert calendar.deletes == ["ev-1"]
    assert calendar.events == {}
