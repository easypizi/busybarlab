import logging

from toy_lair_assistant.agent import AgentResult
from toy_lair_assistant.clients.telegram import TelegramBot


class FakeAgent:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def handle_text(self, text: str, channel: str = "telegram"):
        self.seen.append(text)
        return AgentResult(reply="done: " + text, tool_calls=[])


class FakeSpeech:
    def transcribe(self, data: bytes, mime: str) -> str:
        return "voice task"

    def speak(self, text: str) -> str:
        return "YQ=="


def test_ignores_unknown_chat() -> None:
    sent: list[dict] = []
    bot = TelegramBot(
        token="bot",
        chat_id="111",
        sender=lambda payload: sent.append(payload),
    )
    bot.handle_update(
        {"message": {"chat": {"id": 999}, "text": "hi"}},
        FakeAgent(),
        FakeSpeech(),
    )
    assert sent == []


def test_text_from_allowed_chat_goes_to_agent() -> None:
    sent: list[dict] = []
    agent = FakeAgent()
    bot = TelegramBot(
        token="bot",
        chat_id="111",
        sender=lambda payload: sent.append(payload),
    )
    bot.handle_update(
        {"message": {"chat": {"id": 111}, "text": "add milk"}},
        agent,
        FakeSpeech(),
    )
    assert agent.seen == ["add milk"]
    assert sent[0]["chat_id"] == "111"
    assert sent[0]["text"] == "done: add milk"
    assert sent[0]["parse_mode"] == "HTML"
    assert sent[0]["reply_markup"]["inline_keyboard"][0][0]["text"] == "👍"


def test_voice_is_transcribed() -> None:
    sent: list[dict] = []
    agent = FakeAgent()
    bot = TelegramBot(
        token="bot",
        chat_id="111",
        sender=lambda payload: sent.append(payload),
        downloader=lambda file_id: b"ogg",
    )
    bot.handle_update(
        {"message": {"chat": {"id": 111}, "voice": {"file_id": "f1"}}},
        agent,
        FakeSpeech(),
    )
    assert agent.seen == ["voice task"]
    assert "done: voice task" in sent[0]["text"]


def test_telegram_logs_agent_line(caplog) -> None:
    sent: list[dict] = []
    bot = TelegramBot(
        token="bot",
        chat_id="111",
        sender=lambda payload: sent.append(payload),
    )
    with caplog.at_level(logging.INFO):
        bot.handle_update(
            {"message": {"chat": {"id": 111}, "text": "add milk"}},
            FakeAgent(),
            FakeSpeech(),
        )
    assert "agent channel=telegram" in caplog.text
    assert "ms=" in caplog.text


from datetime import datetime
from zoneinfo import ZoneInfo

from toy_lair_assistant.clients.telegram import to_html
from toy_lair_assistant.models import CalendarEvent, Task
from toy_lair_assistant.store import MemoryStore


def test_to_html_escapes_and_formats() -> None:
    assert to_html("a <b> & **x**") == "a &lt;b&gt; &amp; <b>x</b>"
    assert to_html("- milk") == "• milk"


class DayAgent:
    def __init__(self) -> None:
        self.seen: list[str] = []
        self.todoist = _WeekTodoist()
        self.calendar = _WeekCal()

    def now(self):
        return datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))

    def today_payload(self, now):
        return {
            "items": [
                {"kind": "task", "title": "Walk dog", "when": "", "priority": 1},
                {"kind": "task", "title": "Pay rent", "when": "12:00", "priority": 4},
                {"kind": "event", "title": "Standup", "when": "10:00"},
            ]
        }

    def handle_text(self, text: str, channel: str = "telegram"):
        self.seen.append(text)
        return AgentResult(reply="planned: " + text, tool_calls=[])


class _WeekTodoist:
    def upcoming(self, days: int = 7):
        return [
            Task(id="1", content="Pay rent", due_date="2026-09-19", due_string="12:00", priority=4),
            Task(id="2", content="Walk", due_date="2026-09-20", due_string="Mon", priority=1),
        ]


class _WeekCal:
    def events_in_range(self, start, end):
        return [
            CalendarEvent(
                id="e1",
                title="Standup",
                start="2026-09-19T10:00:00-07:00",
                end="2026-09-19T10:30:00-07:00",
            ),
            CalendarEvent(
                id="m1",
                title="Pay rent",
                start="2026-09-19T12:00:00-07:00",
                end="2026-09-19T13:00:00-07:00",
                todoist_id="1",
            ),
        ]


class _Todo:
    def __init__(self) -> None:
        self.done: list[str] = []
        self.moved: list[tuple[str, str]] = []

    def complete(self, task_id: str) -> None:
        self.done.append(task_id)

    def reschedule(self, task_id: str, due_string: str) -> None:
        self.moved.append((task_id, due_string))


def test_today_lists_p1_first() -> None:
    sent: list[dict] = []
    bot = TelegramBot(token="bot", chat_id="111", sender=lambda payload: sent.append(payload))
    bot.handle_update(
        {"message": {"chat": {"id": 111}, "text": "/today"}},
        DayAgent(),
        FakeSpeech(),
    )
    text = sent[0]["text"]
    assert "<b>Today</b>" in text
    assert text.index("Pay rent") < text.index("Walk dog")
    assert "🔴" in text


def test_week_skips_task_mirrors() -> None:
    sent: list[dict] = []
    bot = TelegramBot(token="bot", chat_id="111", sender=lambda payload: sent.append(payload))
    bot.handle_update(
        {"message": {"chat": {"id": 111}, "text": "/week"}},
        DayAgent(),
        FakeSpeech(),
    )
    text = sent[0]["text"]
    assert "<b>Week</b>" in text
    assert "Pay rent" in text
    assert "Standup" in text
    assert text.count("Pay rent") == 1


def test_plan_sends_rest_to_agent() -> None:
    sent: list[dict] = []
    agent = DayAgent()
    bot = TelegramBot(token="bot", chat_id="111", sender=lambda payload: sent.append(payload))
    bot.handle_update(
        {"message": {"chat": {"id": 111}, "text": "/plan write brief"}},
        agent,
        FakeSpeech(),
    )
    assert agent.seen == ["write brief"]
    assert "planned: write brief" in sent[0]["text"]


def test_help_sends_photo(tmp_path) -> None:
    photo = tmp_path / "tito.png"
    photo.write_bytes(b"\x89PNG\r\n\x1a\nxxxx")
    sent: list[dict] = []
    bot = TelegramBot(
        token="bot",
        chat_id="111",
        sender=lambda payload: sent.append(payload),
        photo_path=photo,
    )
    bot.handle_update(
        {"message": {"chat": {"id": 111}, "text": "/start"}},
        DayAgent(),
        FakeSpeech(),
    )
    assert sent[0]["_method"] == "sendPhoto"
    assert "Tito" in sent[0]["caption"]


def test_task_done_callback_closes_task() -> None:
    todoist = _Todo()
    sent: list[dict] = []
    bot = TelegramBot(
        token="bot",
        chat_id="111",
        sender=lambda payload: sent.append(payload),
        todoist=todoist,
    )
    bot.handle_update(
        {
            "callback_query": {
                "id": "q1",
                "data": "task:done:42",
                "message": {
                    "chat": {"id": 111},
                    "message_id": 9,
                    "text": "Soon: Pay rent",
                },
            }
        },
        FakeAgent(),
        FakeSpeech(),
    )
    assert todoist.done == ["42"]
    assert any(item.get("_method") == "answerCallbackQuery" for item in sent)
    edit = next(item for item in sent if item.get("_method") == "editMessageText")
    assert "Closed" in edit["text"]
    assert edit["reply_markup"] == {"inline_keyboard": []}


def test_feedback_up_writes_store() -> None:
    store = MemoryStore()
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    sent: list[dict] = []
    bot = TelegramBot(
        token="bot",
        chat_id="111",
        sender=lambda payload: sent.append(payload),
        store=store,
        now=lambda: now,
    )
    bot.handle_update(
        {
            "callback_query": {
                "id": "q2",
                "data": "fb:up:turn9",
                "message": {"chat": {"id": 111}, "message_id": 3, "text": "ok"},
            }
        },
        FakeAgent(),
        FakeSpeech(),
    )
    assert store.feedback == [
        {"channel": "telegram", "turn": "turn9", "vote": "up", "at": now}
    ]
    assert sent[0]["_method"] == "answerCallbackQuery"
    assert sent[0]["text"] == "Noted"


def test_ensure_profile_once_a_day() -> None:
    store = MemoryStore()
    sent: list[dict] = []
    bot = TelegramBot(token="bot", chat_id="111", sender=lambda payload: sent.append(payload))
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    bot.ensure_profile(store, now)
    bot.ensure_profile(store, now)
    names = [item.get("_method") for item in sent]
    assert names.count("setMyName") == 1
    assert names.count("setMyCommands") == 1
    assert sent[0]["name"] == "Tito"
