from dataclasses import dataclass, field


@dataclass
class Task:
    id: str
    content: str
    due_date: str | None = None
    due_string: str | None = None
    due_time: str | None = None
    priority: int = 1
    labels: list[str] = field(default_factory=list)
    deadline: str | None = None
    description: str = ""
    duration_minutes: int | None = None
    project_id: str | None = None
    project: str | None = None
    is_recurring: bool = False


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: str
    end: str
    calendar_id: str = ""
    todoist_id: str | None = None


@dataclass
class Reminder:
    id: str
    fire_at: str
    text: str
    sent: bool = False
