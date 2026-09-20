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

from toy_lair_assistant.agent import AgentResult as _AgentResult
from toy_lair_assistant.clients.telegram import to_html
from toy_lair_assistant.day_plan import DayPlanner
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


class _PlanLLM:
    def complete(self, messages, tools):
        return _AgentResult(
            reply='{"scheduled":[{"ref":"t1","start":"13:00","minutes":60,"why":"slot"}],"anytime":[]}',
            tool_calls=[],
        )


class _PlanTodoist:
    def __init__(self) -> None:
        self.updates: list[tuple[str, dict]] = []

    def today(self):
        return [
            Task(
                id="call",
                content="Позвонить маме",
                due_date="2026-09-20",
                due_time="2026-09-20T12:00:00-07:00",
                duration_minutes=30,
                priority=4,
            ),
            Task(id="market", content="Рынок", due_date="2026-09-20"),
        ]

    def update(self, task_id: str, **fields) -> None:
        self.updates.append((task_id, fields))


class _EmptyCal:
    def events_in_range(self, start, end):
        return []


class _Sync:
    def __init__(self) -> None:
        self.ran: list = []

    def run(self, now) -> None:
        self.ran.append(now)


def _day_bot(sent, todoist=None, store=None, sync=None):
    todoist = todoist or _PlanTodoist()
    store = store or MemoryStore()
    planner = DayPlanner(
        todoist=todoist,
        calendar=_EmptyCal(),
        llm=_PlanLLM(),
        settings=type(
            "S",
            (),
            {
                "timezone": "America/Los_Angeles",
                "plan_hours_start": 10,
                "plan_hours_end": 22,
                "plan_horizon_days": 7,
                "plan_default_minutes": 60,
                "plan_weekends": True,
            },
        )(),
        store=store,
        task_sync=sync,
    )
    now = datetime(2026, 9, 20, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    bot = TelegramBot(
        token="bot",
        chat_id="111",
        sender=lambda payload: sent.append(payload),
        store=store,
        todoist=todoist,
        now=lambda: now,
        day_planner=planner,
        task_sync=sync,
    )
    return bot, todoist, planner


def test_today_sends_schedule_with_apply() -> None:
    sent: list[dict] = []
    bot, _, _ = _day_bot(sent)
    bot.handle_update(
        {"message": {"chat": {"id": 111}, "text": "/today"}},
        DayAgent(),
        FakeSpeech(),
    )
    text = sent[0]["text"]
    assert "<b>Today</b>" in text
    assert "<b>Schedule</b>" in text
    assert "~" in text
    assert "Рынок" in text
    buttons = sent[0]["reply_markup"]["inline_keyboard"][0]
    assert buttons[0]["text"] == "✅ Apply plan"
    assert buttons[0]["callback_data"].startswith("plan:apply:")
    assert buttons[1]["text"] == "🔁 Reshuffle"
    assert buttons[1]["callback_data"] == "plan:redo"


def test_plan_apply_callback_updates_and_edits() -> None:
    sent: list[dict] = []
    sync = _Sync()
    bot, todoist, planner = _day_bot(sent, sync=sync)
    bot.handle_update(
        {"message": {"chat": {"id": 111}, "text": "/today"}},
        DayAgent(),
        FakeSpeech(),
    )
    apply_data = sent[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    sent.clear()
    bot.handle_update(
        {
            "callback_query": {
                "id": "q3",
                "data": apply_data,
                "message": {
                    "chat": {"id": 111},
                    "message_id": 4,
                    "text": "Today schedule",
                },
            }
        },
        DayAgent(),
        FakeSpeech(),
    )
    assert [item[0] for item in todoist.updates] == ["market"]
    assert sync.ran
    edit = next(item for item in sent if item.get("_method") == "editMessageText")
    assert "Applied 1 slots." in edit["text"]
    assert edit["reply_markup"] == {"inline_keyboard": []}
    assert planner.store.get_plan(apply_data.split(":")[-1]) is not None


def test_plan_redo_sends_new_plan() -> None:
    sent: list[dict] = []
    bot, _, _ = _day_bot(sent)
    bot.handle_update(
        {"message": {"chat": {"id": 111}, "text": "/today"}},
        DayAgent(),
        FakeSpeech(),
    )
    sent.clear()
    bot.handle_update(
        {
            "callback_query": {
                "id": "q4",
                "data": "plan:redo",
                "message": {"chat": {"id": 111}, "message_id": 5, "text": "old"},
            }
        },
        DayAgent(),
        FakeSpeech(),
    )
    fresh = next(item for item in sent if item.get("text") and "Schedule" in item.get("text", ""))
    assert "✅ Apply plan" in fresh["reply_markup"]["inline_keyboard"][0][0]["text"]


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
