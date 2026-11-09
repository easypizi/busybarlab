import email
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from toy_lair_assistant.clients.telegram import TelegramBot
from toy_lair_assistant.gazeta import delivery, job as job_mod
from toy_lair_assistant.gazeta.editor import EditorError, EditorResult
from toy_lair_assistant.gazeta.layout import sample
from toy_lair_assistant.models import CalendarEvent, Task
from toy_lair_assistant.scheduler import Scheduler
from toy_lair_assistant.settings import Settings
from toy_lair_assistant.store import MemoryStore

ZONE = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 9, 7, 5, tzinfo=ZONE)


class Clock:
    def now(self):
        return NOW


class Todoist:
    def open_tasks(self):
        return [
            Task(id="1", content="Pay rent", due_date="2026-11-09", project="Home"),
            Task(id="2", content="Anna Ivanova", due_date="2026-11-14", due_string="every year", project="Friends & Family"),
        ]


class Cal:
    def events_in_range(self, start, end):
        return [CalendarEvent(id="e", title="Dentist", start="2026-11-09T11:00:00-08:00", end="2026-11-09T12:00:00-08:00")]


class Client:
    def __init__(self):
        self.calls = []

    def chat_json(self, model, system, user, schema, name):
        self.calls.append(("chat_json", json.loads(user)))
        return {
            "tasks": [{"title": "Pay rent", "note": "Todoist, due today", "origin": "todoist"}],
            "idea": {"hook": "Hook.", "text": "Text."},
            "poem": ["a", "b", "c", "d"],
            "comic": sample.sample_view()["day"]["comic"],
        }

    def image(self, model, prompt, size):
        return b"\x89PNG"


def make_settings(**kw):
    base = dict(openai_api_key="k", gmail_user="me@gmail.com", gmail_app_password="pw", gazeta_start_date="2026-11-01")
    base.update(kw)
    return Settings(_env_file=None, **base)


@pytest.fixture
def patched(monkeypatch):
    sv = sample.sample_view()
    issue = {
        "lead": {**sample.sample_view()["lead"], "kicker": "x", "headline": "Lead", "standfirst": "s", "body": ["b"], "url": "https://a/1", "source": "A", "graphic": {"kind": "none"}},
        "teasers": [],
        "sections": [{"id": "space", "stories": [{"headline": "H", "summary": "S", "url": "https://a/2", "source": "B", "published": ""}]}],
        "incidents": {"stories": [{"headline": "I", "summary": "S", "url": "https://a/3", "source": "C", "published": "", "where": "San Mateo"}]},
    }

    class FakeEditor:
        fail = False

        def __init__(self, *a, **k):
            pass

        def run(self, context, pool, used):
            if FakeEditor.fail:
                raise EditorError("boom")
            return EditorResult(issue, {"text": "Fact.", "source_url": "https://f", "source_name": "F"}, [], 3)

    monkeypatch.setattr(job_mod, "Editor", FakeEditor)
    seen_args = []
    monkeypatch.setattr(job_mod.weather_src, "fetch", lambda *a: seen_args.append(a) or {"now_c": 13, "high": "16°C", "low": "10°C", "summary": "Fog.", "sunrise": "6:40 AM", "sunset": "4:56 PM", "daylight": "10 h", "rain_pct": 0})
    monkeypatch.setattr(job_mod.threats_src, "fetch", lambda *a: {"summary": "Quiet.", "lines": ["l"], "alert_active": False})
    monkeypatch.setattr(job_mod.launches_src, "fetch", lambda *a: [])
    monkeypatch.setattr(job_mod.f1_src, "fetch", lambda *a: {"next": None, "last": None, "standings": []})
    monkeypatch.setattr(job_mod.feeds, "fetch_all", lambda *a: {"space": [{"title": "t"}]})
    FakeEditor.weather_args = seen_args
    return FakeEditor


def build(settings=None, **kw):
    sent = []
    bot = TelegramBot(token="t", chat_id="1", sender=lambda p: sent.append(p))
    emails = []
    renders = []

    def render(view, pages):
        renders.append(view)
        return b"%PDF-fake", {"pages": 4, "trims": []}

    job = job_mod.GazetaJob(
        settings=settings or make_settings(),
        clock=Clock(),
        store=MemoryStore(),
        todoist=Todoist(),
        calendar=Cal(),
        notify=bot,
        client=Client(),
        fetch_mail=lambda u, p: [{"subject": "Sign form", "from": "a", "date": "", "snippet": ""}],
        send_email=lambda *a: emails.append(a),
        render_pdf=render,
        **kw,
    )
    return job, sent, emails, renders


def test_run_delivers_to_telegram_and_email(patched):
    job, sent, emails, renders = build()
    result = job.run()
    assert result["pages"] == 4 and result["filename"] == "IVANencial-Times-2026-11-09.pdf"
    doc = [p for p in sent if p.get("_method") == "sendDocument"][0]
    assert doc["_document"] == b"%PDF-fake" and "4 pages" in doc["caption"]
    links = [p for p in sent if "Sources" in p.get("text", "")][0]
    assert "https://a/1" in links["text"] and links["disable_web_page_preview"] is True
    assert emails and emails[0][2] == "me@gmail.com"
    assert renders[0]["issue_no"] == 9
    assert "Veterans" in renders[0]["countdown"]


def test_writer_gets_real_inputs(patched):
    job, *_ = build()
    job.run()
    assert patched.weather_args[0][1] == "2026-11-09"
    ctx = job.client.calls[0][1]
    assert ctx["tasks"][0]["content"] == "Pay rent"
    assert ctx["calendar_today"][0]["title"] == "Dentist"
    assert ctx["mail_last_48h"][0]["subject"] == "Sign form"


def test_editor_failure_falls_back_to_curated_fact(patched):
    patched.fail = True
    try:
        job, _, _, renders = build()
        job.run()
    finally:
        patched.fail = False
    assert renders[0]["lead"] is None
    assert renders[0]["day"]["fact"]["source_name"] == "Wikipedia"


def test_email_failure_is_reported_not_raised(patched):
    job, sent, _, _ = build()

    def boom(*a):
        raise RuntimeError("smtp down")

    job.send_email = boom
    job.run()
    assert any("Email: smtp down" in p.get("text", "") for p in sent)


def test_no_email_without_credentials(patched):
    job, _, emails, _ = build(make_settings(gmail_user="", gmail_app_password=""))
    job.run()
    assert emails == []


def test_start_is_single_flight(patched):
    job, *_ = build()
    job._running = True
    assert job.start() is False


def test_scheduler_runs_once_per_morning_with_retry_cap():
    started = []

    class G:
        def start(self, on_demand=False):
            started.append(on_demand)
            return True

    store = MemoryStore()
    sched = Scheduler(
        todoist=type("T", (), {"open_tasks": lambda self: []})(),
        calendar=type("C", (), {"events_in_range": lambda self, a, b: []})(),
        store=store,
        notify=lambda text: None,
        settings=make_settings(),
        gazeta=G(),
    )
    early = NOW.replace(hour=6)
    assert sched._gazeta(early) == 0
    for _ in range(5):
        sched._gazeta(NOW)
    assert len(started) == 3
    store.mark("gazeta:done:2026-11-10")
    assert sched._gazeta(NOW.replace(day=10)) == 0
    assert sched._gazeta(NOW.replace(hour=13, day=11)) == 0


def test_gazeta_command_starts_job_and_rejects_double():
    sent = []
    calls = []

    class G:
        def start(self, on_demand=False):
            calls.append(on_demand)
            return len(calls) == 1

    bot = TelegramBot(token="t", chat_id="1", sender=lambda p: sent.append(p), gazeta=G())
    update = {"message": {"chat": {"id": 1}, "text": "/gazeta"}}
    bot.handle_update(update, None, None)
    bot.handle_update(update, None, None)
    assert calls == [True, True]
    assert "Going to press" in sent[0]["text"] and "already" in sent[1]["text"]


def test_gazeta_command_without_job():
    sent = []
    bot = TelegramBot(token="t", chat_id="1", sender=lambda p: sent.append(p))
    bot.handle_update({"message": {"chat": {"id": 1}, "text": "/gazeta"}}, None, None)
    assert "not set up" in sent[0]["text"]


def test_email_message_has_pdf_attachment():
    msg = delivery.build_message("a@x", "b@x", "Subj", "Body", b"%PDF-1", "p.pdf")
    parsed = email.message_from_bytes(msg.as_bytes())
    parts = list(parsed.walk())
    assert any(p.get_content_type() == "application/pdf" and p.get_filename() == "p.pdf" for p in parts)


def test_send_pdf_logs_in_and_sends():
    log = []

    class Smtp:
        def __init__(self, host, port, timeout):
            log.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            log.append(("login", u, p))

        def send_message(self, msg):
            log.append(("send", msg["To"]))

    delivery.send_pdf("me@gmail.com", "pw", "", "S", "B", b"x", "f.pdf", connect=Smtp)
    assert log == [("connect", "smtp.gmail.com", 465), ("login", "me@gmail.com", "pw"), ("send", "me@gmail.com")]


def test_document_has_print_button_when_printer_set(patched):
    job, sent, _, _ = build(make_settings(gazeta_printer_email="printer@hpeprint.com"))
    job.run()
    doc = [p for p in sent if p.get("_method") == "sendDocument"][0]
    assert json.loads(doc["reply_markup"]) == {"inline_keyboard": [[{"text": "🖨 Print", "callback_data": "gazeta:print"}]]}


def test_no_print_button_without_printer(patched):
    job, sent, _, _ = build()
    job.run()
    doc = [p for p in sent if p.get("_method") == "sendDocument"][0]
    assert "reply_markup" not in doc


def test_print_pdf_mails_printer_with_empty_body(patched):
    job, _, emails, _ = build(make_settings(gazeta_printer_email="printer@hpeprint.com"))
    job.print_pdf(b"%PDF", "IVANencial-Times-2026-11-09.pdf")
    user, password, to, subject, body, pdf, name = emails[0]
    assert to == "printer@hpeprint.com" and body == "" and pdf == b"%PDF"


def test_print_button_downloads_document_and_prints():
    sent, printed, downloads = [], [], []

    class G:
        def print_pdf(self, pdf, name):
            printed.append((pdf, name))

    bot = TelegramBot(token="t", chat_id="1", sender=lambda p: sent.append(p), downloader=lambda fid: downloads.append(fid) or b"%PDF", gazeta=G())
    query = {"id": "q", "data": "gazeta:print", "message": {"chat": {"id": 1}, "document": {"file_id": "F1", "file_name": "paper.pdf"}}}
    bot.handle_update({"callback_query": query}, None, None)
    assert downloads == ["F1"] and printed == [(b"%PDF", "paper.pdf")]
    assert "Sent to the printer" in sent[-1]["text"]


def test_print_failure_is_reported():
    sent = []

    class G:
        def print_pdf(self, pdf, name):
            raise RuntimeError("smtp down")

    bot = TelegramBot(token="t", chat_id="1", sender=lambda p: sent.append(p), downloader=lambda fid: b"%PDF", gazeta=G())
    query = {"id": "q", "data": "gazeta:print", "message": {"chat": {"id": 1}, "document": {"file_id": "F1"}}}
    bot.handle_update({"callback_query": query}, None, None)
    assert "smtp down" in sent[-1]["text"]


def test_email_without_body_has_only_the_pdf():
    msg = delivery.build_message("a@x", "b@x", "S", "", b"%PDF-1", "p.pdf")
    assert [p.get_content_type() for p in msg.walk()] == ["multipart/mixed", "application/pdf"]


def test_desk_sections_and_code_made_teasers_reach_the_view(patched, monkeypatch):
    seen = {}

    class FakeDesk:
        def __init__(self, *a, **k):
            pass

        def run(self, pool, urls, titles):
            seen["urls"], seen["titles"] = urls, titles
            story = {"headline": "Desk story", "summary": "S", "url": "https://d/1", "source": "D", "published": ""}
            return [{"id": "space", "title": "Space", "stories": [story]}, {"id": "f1", "title": "Formula 1", "stories": [story]}]

    monkeypatch.setattr(job_mod, "Desk", FakeDesk)
    job, _, _, renders = build()
    job.run()
    view = renders[0]
    assert [s["id"] for s in view["sections"]] == ["space", "f1"]
    assert [t["headline"] for t in view["teasers"]] == ["Desk story", "Desk story"]
    assert "https://a/1" in seen["urls"] and "https://a/3" in seen["urls"] and "Lead" in seen["titles"]


def test_desk_crash_still_prints_lead_and_incidents(patched, monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            pass

        def run(self, *a):
            raise RuntimeError("desk down")

    monkeypatch.setattr(job_mod, "Desk", Boom)
    job, _, _, renders = build()
    job.run()
    assert renders[0]["sections"] == [] and renders[0]["lead"]["headline"] == "Lead"
    assert renders[0]["incidents"]["stories"]


def test_day_sheet_has_no_comic(patched):
    job, _, _, renders = build()
    job.run()
    assert "comic" not in renders[0]["day"]
