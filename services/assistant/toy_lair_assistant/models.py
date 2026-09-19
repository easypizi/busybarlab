from dataclasses import dataclass


@dataclass
class Task:
    id: str
    content: str
    due_date: str | None = None
    due_string: str | None = None
    due_time: str | None = None


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: str
    end: str


@dataclass
class Reminder:
    id: str
    fire_at: str
    text: str
    sent: bool = False
