from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from toy_lair_assistant.agent import AgentResult, ToolCall
from toy_lair_assistant.clients.telegram import TelegramBot
from toy_lair_assistant.library import open_library
from toy_lair_assistant.main import create_app
from toy_lair_assistant.paco import PacoAgent
from toy_lair_assistant.paco_vault import PacoVault
from toy_lair_assistant.settings import Settings
from toy_lair_assistant.store import MemoryStore
from toy_lair_assistant.zayka_write import ZaykaWrite

ZONE = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=ZONE)
AUTH = {"Authorization": "Bearer ctok"}


def _item(**over):
    base = {
        "source": "instagram",
        "external_id": "abc",
        "url": "https://www.instagram.com/p/abc/",
        "title": "Overnight oats",
        "author": "chef",
        "summary": "Oats soaked overnight with chia.",
        "kind": "recipe",
        "topics": ["breakfast"],
        "snippet": "mix oats and milk",
        "vault_path": "20 Sources/instagram/overnight-oats-aaaaaa.md",
    }
    base.update(over)
    return base


def test_store_upsert_and_search() -> None:
    lib = open_library("")
    assert lib.add_items([_item(), _item(external_id="b", title="Deadlift form", kind="workout", summary="Hinge", snippet="", topics=[])], NOW) == 2
    assert lib.add_items([_item(summary="changed")], NOW) == 1
    assert len(lib.search("oats")) == 1
    assert lib.search("oats")[0]["summary"] == "changed"
    assert [r["kind"] for r in lib.search("form", kind="workout")] == ["workout"]
    assert lib.search("oats", source="gmail") == []
    assert lib.search("breakfast")[0]["topics"] == ["breakfast"]
    assert lib.counts() == {"instagram": 2}
    assert lib.get(lib.search("oats")[0]["id"])["title"] == "Overnight oats"


def test_recent_window() -> None:
    lib = open_library("")
    lib.add_items([_item()], NOW - timedelta(days=10))
    lib.add_items([_item(external_id="new", title="Fresh")], NOW)
    assert [r["title"] for r in lib.recent(NOW, days=3)] == ["Fresh"]


def test_job_queue_lifecycle() -> None:
    lib = open_library("")
    job = lib.enqueue_job("sync", {"source": "gmail"}, NOW)
    claimed = lib.claim_jobs(NOW)
    assert claimed == [{"id": job, "kind": "sync", "payload": {"source": "gmail"}}]
    assert lib.claim_jobs(NOW) == []
    assert lib.claim_jobs(NOW + timedelta(hours=2))[0]["id"] == job
    assert lib.finish_job(job, True, "ok")
    assert lib.pending_jobs() == 0
    assert not lib.finish_job("nope", True, "")


def _client(library, notify=None, store=None) -> TestClient:
    settings = Settings(assistant_api_token="t", collector_token="ctok", tick_interval_seconds=0)
    app = create_app(settings, library=library, notify=notify, store=store)
    return TestClient(app)


def test_api_requires_collector_token() -> None:
    client = _client(open_library(""))
    assert client.post("/api/library/items", json={"items": []}).status_code == 401
    assert client.post("/api/library/items", json={"items": []}, headers={"Authorization": "Bearer x"}).status_code == 401
    assert client.get("/api/collector/jobs", headers={"X-Assistant-Token": "t"}).status_code == 401


def test_api_unconfigured_token_is_503() -> None:
    app = create_app(Settings(assistant_api_token="t", tick_interval_seconds=0), library=open_library(""))
    assert TestClient(app).get("/api/collector/jobs", headers=AUTH).status_code == 503


def test_api_ingest_and_jobs() -> None:
    lib = open_library("")
    client = _client(lib)
    assert client.post("/api/library/items", json={"items": [_item()]}, headers=AUTH).json() == {"stored": 1}
    assert client.post("/api/library/items", json={"items": "x"}, headers=AUTH).status_code == 400
    job = lib.enqueue_job("url", {"text": "https://a.b"}, NOW)
    jobs = client.get("/api/collector/jobs", headers=AUTH).json()["jobs"]
    assert jobs[0]["id"] == job
    assert client.post(f"/api/collector/jobs/{job}/done", json={"ok": True}, headers=AUTH).json() == {"ok": True}
    assert client.post("/api/collector/jobs/zzz/done", json={"ok": True}, headers=AUTH).status_code == 404


class Notify:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def voice(self, who):
        return self

    def send_text(self, text):
        self.sent.append(text)


def test_alert_is_sent_once_per_day_and_digest_recorded() -> None:
    notify = Notify()
    lib = open_library("")
    client = _client(lib, notify=notify, store=MemoryStore())
    alert = {"kind": "alert", "source": "instagram", "text": "instagram: checkpoint"}
    client.post("/api/collector/event", json=alert, headers=AUTH)
    client.post("/api/collector/event", json=alert, headers=AUTH)
    assert notify.sent == ["instagram: checkpoint"]
    digest = {"kind": "digest", "source": "collector", "text": "Library run: gmail: 2", "summary": {"counts": {"gmail": 2}}}
    client.post("/api/collector/event", json=digest, headers=AUTH)
    quiet = {"kind": "digest", "source": "collector", "text": "Library run: nothing new", "summary": {"counts": {"gmail": 0}}}
    client.post("/api/collector/event", json=quiet, headers=AUTH)
    assert notify.sent[-1] == "Library run: gmail: 2"
    assert len(notify.sent) == 2
    assert lib.last_run()["counts"] == {"gmail": 0}
    assert client.post("/api/collector/event", json={"kind": "x"}, headers=AUTH).status_code == 400


class ScriptedLLM:
    def __init__(self, scripts):
        self.scripts = list(scripts)

    def complete(self, messages, tools, schemas=None):
        self.last_tools = tools
        return self.scripts.pop(0)


def _paco(tmp_path: Path, lib, scripts) -> PacoAgent:
    writer = ZaykaWrite(tmp_path, lambda args, cwd: None, ZONE)
    return PacoAgent(ScriptedLLM(scripts), PacoVault(tmp_path, ZONE), writer, lambda: NOW, library=lib)


def test_paco_library_tools(tmp_path: Path) -> None:
    lib = open_library("")
    lib.add_items([_item()], NOW)
    agent = _paco(
        tmp_path,
        lib,
        [
            AgentResult(reply="", tool_calls=[ToolCall(name="library_search", arguments={"query": "oats"}, call_id="1")]),
            AgentResult(reply="Found oats."),
        ],
    )
    result = agent.handle_text("what oats did I save")
    assert result.reply == "Found oats."
    assert result.peek["kind"] == "hits"
    assert result.peek["items"][0]["title"] == "Overnight oats"
    assert "library_search" in agent.llm.last_tools


def test_paco_sync_and_status(tmp_path: Path) -> None:
    lib = open_library("")
    agent = _paco(tmp_path, lib, [])
    assert "Queued sync" in agent._collector_sync("gmail")
    status = agent._collector_status()
    assert "queued_jobs=1" in status and "last_run=never" in status


def test_paco_without_library_has_no_library_tools(tmp_path: Path) -> None:
    writer = ZaykaWrite(tmp_path, lambda args, cwd: None, ZONE)
    agent = PacoAgent(ScriptedLLM([]), PacoVault(tmp_path, ZONE), writer, lambda: NOW)
    assert "library_search" not in agent.tools


def _bot(lib):
    sent: list[dict] = []
    bot = TelegramBot(token="b", chat_id="1", sender=sent.append, library=lib, now=lambda: NOW)
    return bot, sent


def _msg(text, **extra):
    return {"message": {"chat": {"id": 1}, "text": text, **extra}}


def test_telegram_url_and_forward_are_queued() -> None:
    lib = open_library("")
    bot, sent = _bot(lib)
    bot.handle_update(_msg("look https://example.com/a"), None, None)
    bot.handle_update(_msg("forwarded words", forward_origin={"type": "user"}), None, None)
    jobs = lib.claim_jobs(NOW)
    assert [j["kind"] for j in jobs] == ["url", "url"]
    assert jobs[0]["payload"]["urls"] == ["https://example.com/a"]
    assert sent[0]["text"].startswith("<b>Paco</b>")


def test_telegram_sync_and_sources_commands() -> None:
    lib = open_library("")
    lib.add_items([_item()], NOW)
    bot, sent = _bot(lib)
    bot.handle_update(_msg("/sync gmail"), None, None)
    assert lib.claim_jobs(NOW)[0]["payload"] == {"source": "gmail"}
    bot.handle_update(_msg("/sources"), None, None)
    assert "instagram: 1" in sent[-1]["text"]


def test_addressed_url_still_goes_to_paco_agent() -> None:
    lib = open_library("")
    bot, _sent = _bot(lib)

    class P:
        seen = []

        def handle_text(self, text):
            self.seen.append(text)
            return AgentResult(reply="ok")

    paco = P()
    bot.handle_update(_msg("Paco, где https://example.com"), None, None, paco=paco)
    assert paco.seen == ["где https://example.com"]
    assert lib.claim_jobs(NOW) == []
