import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from toy_lair_assistant.agent import AgentResult
from toy_lair_assistant.collector.config import CollectorConfig
from toy_lair_assistant.collector.connectors.bot_inbox import BotInbox
from toy_lair_assistant.collector.connectors.chrome_reading_list import ChromeReadingList, parse_entry
from toy_lair_assistant.collector.connectors.gmail_imap import GmailImap
from toy_lair_assistant.collector.connectors.instagram import InstagramSaved
from toy_lair_assistant.collector.connectors.telegram_user import TelegramUser, extract_urls
from toy_lair_assistant.collector.connectors.zayka_notes import ZaykaNotes
from toy_lair_assistant.collector.enrich import Classifier, Enricher, html_to_text
from toy_lair_assistant.collector.models import (
    ConnectorAuthError,
    Enriched,
    FetchContext,
    RawItem,
    canonical_url,
)
from toy_lair_assistant.collector.pipeline import Pipeline, to_payload
from toy_lair_assistant.collector.runner import Runner
from toy_lair_assistant.collector.state import CollectorState
from toy_lair_assistant.collector.vault_layout import (
    VaultWriter,
    allowed_create,
    allowed_link_target,
    is_blocked,
)

ZONE = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=ZONE)
DIARY = "\u0414\u043d\u0435\u0432\u043d\u0438\u043a"


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / "30 Projects").mkdir()
    (root / "30 Projects" / "HireScope.md").write_text("# HireScope\nmine\n", encoding="utf-8")
    (root / "40 Areas" / "sensitive").mkdir(parents=True)
    (root / "40 Areas" / "sensitive" / "secret.md").write_text("secret", encoding="utf-8")
    (root / "50 MOC").mkdir()
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


def writer(root: Path, push: bool = False) -> VaultWriter:
    return VaultWriter(root, ZONE, CollectorState(), push=push)


def item(n: int = 1, **over) -> RawItem:
    base = dict(source="chrome", external_id=f"https://x.test/{n}", url=f"https://x.test/{n}", title=f"Pasta {n}")
    base.update(over)
    return RawItem(**base)


class FakeLLM:
    def __init__(self, payload: dict | str | None = None) -> None:
        self.payload = payload if payload is not None else {
            "kind": "recipe", "topics": ["food"], "summary": "A pasta.", "related": ["HireScope", "Ghost"],
        }
        self.calls = 0

    def complete(self, messages, tools, schemas=None):
        self.calls += 1
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return AgentResult(reply=text)


class FakeIngest:
    def __init__(self, fail: bool = False) -> None:
        self.items: list[dict] = []
        self.events: list[tuple] = []
        self.fail = fail
        self.job_list: list[dict] = []
        self.done_calls: list[tuple] = []

    def push_items(self, items):
        if self.fail:
            raise RuntimeError("down")
        self.items.extend(items)

    def event(self, kind, source, text, summary=None):
        self.events.append((kind, source, text))

    def jobs(self):
        return self.job_list

    def done(self, job_id, ok, message=""):
        self.done_calls.append((job_id, ok))


class StaticConnector:
    def __init__(self, name: str, items: list[RawItem], error: Exception | None = None) -> None:
        self.name = name
        self.items = items
        self.error = error

    def fetch(self, ctx):
        yield from self.items
        if self.error:
            raise self.error


def pipeline(root: Path, ingest: FakeIngest, llm: FakeLLM | None = None, push: bool = False, limit: int = 30):
    state = CollectorState()
    vw = VaultWriter(root, ZONE, state, push=push)
    pipe = Pipeline(state, Enricher(http=None), Classifier(llm or FakeLLM()), vw, ingest, limit)
    return pipe, state, vw


# paths

def test_blocked_and_allowed_paths() -> None:
    assert is_blocked("40 Areas/sensitive/x.md")
    assert is_blocked(f"60 Daily/{DIARY}/2026.md")
    assert is_blocked(".obsidian/app.json") and is_blocked("Presentations/a.md") and is_blocked("a/../b.md")
    assert not is_blocked("40 Areas/health.md")
    assert allowed_create("20 Sources/instagram/pasta-abc123.md")
    assert allowed_create("50 MOC/MOC-Recipe.md")
    assert not allowed_create("10 Evergreen/pasta.md")
    assert not allowed_create("20 Sources/zayka/x.md")
    assert not allowed_create("00 Inbox/2026-10-24-x.md")
    assert allowed_link_target("30 Projects/HireScope.md")
    assert not allowed_link_target("40 Areas/sensitive/secret.md")
    assert not allowed_link_target("00 Inbox/x.md") and not allowed_link_target("60 Daily/2026/10/x.md")


# writer

def test_add_writes_source_note_with_frontmatter(vault: Path) -> None:
    w = writer(vault)
    rel = w.add(item(), Enriched(kind="recipe", topics=["food"], summary="A pasta.", transcript="line1\nline2"))
    text = (vault / rel).read_text(encoding="utf-8")
    assert rel.startswith("20 Sources/chrome/pasta-1-")
    assert "type: source\nstatus: draft\ntags: [to-process]" in text
    assert 'source: "https://x.test/1"' in text
    assert "> line1\n> line2" in text
    assert w.add(item(), Enriched(kind="recipe")) == rel


def test_private_item_text_is_not_quoted(vault: Path) -> None:
    w = writer(vault)
    rel = w.add(item(private=True, text="secret body"), Enriched(summary="s"))
    assert "secret body" not in (vault / rel).read_text(encoding="utf-8")


def test_related_only_to_existing_and_backlink_block_keeps_user_text(vault: Path) -> None:
    w = writer(vault)
    rel = w.add(item(), Enriched(related=["HireScope", "Ghost"]))
    note = (vault / rel).read_text(encoding="utf-8")
    assert "related: [HireScope]" in note and "Ghost" not in note
    project = (vault / "30 Projects" / "HireScope.md").read_text(encoding="utf-8")
    assert project.startswith("# HireScope\nmine\n")
    assert project.count("<!-- paco:links -->") == 1 and "[[pasta-1-" in project
    w.add(item(2), Enriched(related=["HireScope"]))
    project = (vault / "30 Projects" / "HireScope.md").read_text(encoding="utf-8")
    assert project.count("<!-- paco:links -->") == 1 and project.count("[[pasta-") == 2


def test_never_links_into_sensitive(vault: Path) -> None:
    (vault / "40 Areas" / "sensitive" / "Vault.md").write_text("x", encoding="utf-8")
    w = writer(vault)
    w.add(item(), Enriched(related=["Vault", "secret"]))
    assert (vault / "40 Areas" / "sensitive" / "secret.md").read_text(encoding="utf-8") == "secret"
    assert (vault / "40 Areas" / "sensitive" / "Vault.md").read_text(encoding="utf-8") == "x"


def test_moc_created_at_three_items_and_replaced_not_duplicated(vault: Path) -> None:
    w = writer(vault)
    for n in (1, 2):
        w.add(item(n), Enriched(kind="recipe"))
    w.update_collections()
    assert not (vault / "50 MOC" / "MOC-Recipe.md").exists()
    w.add(item(3), Enriched(kind="recipe"))
    w.update_collections()
    moc = (vault / "50 MOC" / "MOC-Recipe.md").read_text(encoding="utf-8")
    assert moc.count("[[pasta-") == 3 and "type: moc" in moc
    w.add(item(4), Enriched(kind="recipe"))
    w.update_collections()
    moc = (vault / "50 MOC" / "MOC-Recipe.md").read_text(encoding="utf-8")
    assert moc.count("[[pasta-") == 4 and moc.count("<!-- paco:links -->") == 1
    assert w.grown_mocs


def test_one_commit_per_run_by_paco(vault: Path) -> None:
    w = writer(vault, push=False)
    w.push = True
    calls: list[list[str]] = []

    def runner(args, cwd):
        calls.append(args)
        if args[:2] == ["git", "push"] or args[:2] == ["git", "pull"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True)

    w.runner = runner
    assert w.begin()
    w.add(item(), Enriched(related=["HireScope"]))
    w.add(item(2), Enriched())
    assert w.commit_run("2 items")
    log = git(vault, "log", "--format=%an|%s").splitlines()
    assert log[0] == "Paco|Library: 2 items" and len(log) == 2
    assert git(vault, "status", "--porcelain") == ""
    assert any(c[:2] == ["git", "push"] for c in calls)


def test_commit_does_not_sweep_in_user_changes(vault: Path) -> None:
    (vault / "30 Projects" / "HireScope.md").write_text("# edited by me\n", encoding="utf-8")
    w = writer(vault)
    w.push = True
    w.runner = lambda args, cwd: (
        subprocess.CompletedProcess(args, 0, "", "") if args[1] in {"push", "pull"}
        else subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    )
    w.begin()
    w.add(item(), Enriched())
    assert w.commit_run("1 items")
    assert git(vault, "status", "--porcelain").startswith(" M ")
    assert "edited by me" not in git(vault, "show", "HEAD")


# pipeline

def test_pipeline_end_to_end_and_dedupe(vault: Path) -> None:
    ingest = FakeIngest()
    pipe, state, _vw = pipeline(vault, ingest)
    conn = StaticConnector("chrome", [item(1), item(1, external_id="other-id", url="https://www.x.test/1/?utm_source=a")])
    report = pipe.run([conn])
    assert report.counts == {"chrome": 1}
    assert len(ingest.items) == 1 and ingest.items[0]["kind"] == "recipe"
    assert state.pending_pushes() == []
    again = pipe.run([StaticConnector("chrome", [item(1)])])
    assert again.counts == {"chrome": 0} and len(ingest.items) == 1


def test_connector_failure_is_isolated(vault: Path) -> None:
    ingest = FakeIngest()
    pipe, state, _ = pipeline(vault, ingest)
    bad = StaticConnector("instagram", [item(5, source="instagram", external_id="s")], ConnectorAuthError("checkpoint"))
    crash = StaticConnector("gmail", [], RuntimeError("boom"))
    good = StaticConnector("chrome", [item(1)])
    report = pipe.run([bad, crash, good])
    assert report.errors["instagram"] == "checkpoint"
    assert "RuntimeError" in report.errors["gmail"]
    assert report.counts == {"instagram": 1, "gmail": 0, "chrome": 1}
    assert len(ingest.items) == 2


def test_push_failure_is_retried_next_run(vault: Path) -> None:
    ingest = FakeIngest(fail=True)
    pipe, state, _ = pipeline(vault, ingest)
    report = pipe.run([StaticConnector("chrome", [item(1)])])
    assert "push" in report.errors and len(state.pending_pushes()) == 1
    ingest.fail = False
    pipe.run([])
    assert len(ingest.items) == 1 and state.pending_pushes() == []


def test_commit_failure_leaves_items_unmarked(vault: Path) -> None:
    ingest = FakeIngest()
    pipe, state, vw = pipeline(vault, ingest, push=True)
    vw.runner = lambda args, cwd: subprocess.CompletedProcess(args, 1 if args[1] == "push" else 0, "", "nope")
    vw.runner = lambda args, cwd: (
        subprocess.CompletedProcess(args, 1, "", "push rejected") if args[1] == "push"
        else subprocess.CompletedProcess(args, 0, "", "") if args[1] in {"pull", "add", "commit"}
        else subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    )
    report = pipe.run([StaticConnector("chrome", [item(1)])])
    assert not report.commit_ok and ingest.items == []
    assert not state.is_done("chrome:https://x.test/1")


def test_pull_failure_aborts_run(vault: Path) -> None:
    ingest = FakeIngest()
    pipe, _state, vw = pipeline(vault, ingest, push=True)
    vw.runner = lambda args, cwd: subprocess.CompletedProcess(args, 1, "", "not fast-forward")
    report = pipe.run([StaticConnector("chrome", [item(1)])])
    assert "vault" in report.errors and report.total == 0


def test_limit_caps_items_per_connector(vault: Path) -> None:
    ingest = FakeIngest()
    pipe, _s, _v = pipeline(vault, ingest, limit=2)
    report = pipe.run([StaticConnector("chrome", [item(n) for n in range(5)])])
    assert report.counts == {"chrome": 2}


def test_payload_hides_private_snippet() -> None:
    from toy_lair_assistant.collector.models import Processed

    mail = Processed(RawItem("gmail", "m1", "u", title="Invoice", text="card 1234", private=True), Enriched(summary="bill"))
    assert to_payload(mail)["snippet"] == ""
    note = Processed(RawItem("chrome", "c", "u", text="hello"), Enriched())
    assert to_payload(note)["snippet"] == "hello"


def test_classifier_parses_fenced_json_and_falls_back() -> None:
    fenced = Classifier(FakeLLM('```json\n{"kind": "workout", "topics": ["a"], "summary": "s"}\n```'))
    out = fenced.classify(item(), "", "", [])
    assert out.kind == "workout" and out.summary == "s"
    junk = Classifier(FakeLLM("no json here")).classify(item(text="body"), "", "", [])
    assert junk.kind == "other" and junk.summary == "body"
    bad_kind = Classifier(FakeLLM({"kind": "weird"})).classify(item(), "", "", [])
    assert bad_kind.kind == "other"


def test_enricher_transcribes_and_survives_failures() -> None:
    calls = []
    enricher = Enricher(transcribe=lambda data, mime: calls.append((data, mime)) or "spoken", http=None)
    video = item(audio=lambda: b"aud")
    assert enricher.enrich(video) == ("spoken", "") and calls == [(b"aud", "audio/mp4")]

    def boom():
        raise RuntimeError("x")

    assert Enricher(transcribe=lambda d, m: "t", http=None).enrich(item(audio=boom)) == ("", "")


def test_html_to_text_skips_scripts() -> None:
    assert html_to_text("<html><head><title>t</title></head><body><script>x()</script><p>Hi</p> there</body></html>") == "Hi there"


def test_canonical_url_strips_tracking() -> None:
    assert canonical_url("https://www.A.com/p/?utm_source=x&id=2#frag") == "https://a.com/p?id=2"


# connectors

def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(num: int, value) -> bytes:
    if isinstance(value, int):
        return _varint(num << 3) + _varint(value)
    data = value.encode() if isinstance(value, str) else value
    return _varint(num << 3 | 2) + _varint(len(data)) + data


def test_chrome_parse_entry_matches_real_layout() -> None:
    url = "https://alan.norbauer.com/articles/browser-debugging-tricks"
    created = (1_700_000_000 + 11_644_473_600) * 1_000_000
    blob = _field(1, url) + _field(2, "Tricks \u0442\u0435\u0441\u0442") + _field(3, url) + _field(4, created) + _field(5, created) + _field(6, 0)
    entry = parse_entry(blob)
    assert entry["url"] == url and entry["title"] == "Tricks \u0442\u0435\u0441\u0442"
    assert entry["created"].startswith("2023-11-14") and entry["status"] == 0
    unix = _field(3, url) + _field(4, 1_700_000_000 * 1_000_000)
    assert parse_entry(unix)["created"].startswith("2023-11-14")


def test_chrome_connector_skips_read_and_seen() -> None:
    rows = [
        {"url": "https://a.test", "title": "A", "created": "2026-01-02T00:00:00+00:00", "status": 0},
        {"url": "https://b.test", "title": "B", "created": "2026-01-01T00:00:00+00:00", "status": 1},
        {"url": "https://c.test", "title": "C", "created": "2026-01-03T00:00:00+00:00", "status": 2},
    ]
    conn = ChromeReadingList("/nowhere", reader=lambda p: rows)
    ctx = FetchContext(lambda ext: ext == "https://c.test", 30, {})
    assert [i.title for i in conn.fetch(ctx)] == ["A"]


MAIL = (
    b"Message-ID: <m1@x>\r\nFrom: Bob <bob@x.test>\r\nSubject: Trip plan\r\nDate: Sat, 24 Oct 2026 10:00:00 -0700\r\n"
    b"Content-Type: text/plain\r\n\r\nSee https://trip.test/plan for details.\r\n"
)


class FakeImap:
    def __init__(self, login_error: bool = False) -> None:
        self.login_error = login_error
        self.logged_out = False

    def login(self, user, password):
        import imaplib

        if self.login_error:
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    def select(self, box, readonly=False):
        return "OK", [b"1"]

    def uid(self, cmd, *args):
        if cmd == "SEARCH":
            assert args[0] == "X-GM-RAW"
            return "OK", [b"1 2"]
        uid, spec = args
        if "HEADER" in spec:
            mid = b"<m1@x>" if uid == b"1" else b"<m2@x>"
            return "OK", [(b"1 (BODY[HEADER.FIELDS (MESSAGE-ID)]", b"Message-ID: " + mid + b"\r\n\r\n"), b")"]
        return "OK", [(b"1 (BODY[]", MAIL), b")"]

    def logout(self):
        self.logged_out = True


def test_gmail_fetch_is_private_and_skips_seen() -> None:
    fake = FakeImap()
    conn = GmailImap("me@x", "pw", "is:starred", connect=lambda: fake)
    items = list(conn.fetch(FetchContext(lambda ext: ext == "<m2@x>", 30, {})))
    assert len(items) == 1
    mail = items[0]
    assert mail.private and mail.title == "Trip plan" and "bob@x.test" in mail.author
    assert mail.extra["links"] == ["https://trip.test/plan"]
    assert "rfc822msgid:m1%40x" in mail.url and mail.captured_at.startswith("2026-10-24")
    assert fake.logged_out


def test_gmail_bad_password_is_auth_error() -> None:
    conn = GmailImap("me@x", "bad", "q", connect=lambda: FakeImap(login_error=True))
    with pytest.raises(ConnectorAuthError):
        list(conn.fetch(FetchContext(lambda e: False, 30, {})))


class _Msg:
    def __init__(self, mid, text, fwd=False, urls=()):
        self.id = mid
        self.message = text
        self.fwd_from = object() if fwd else None
        self.entities = [type("E", (), {"url": u})() for u in urls]
        self.date = NOW


class FakeTg:
    def __init__(self, authorized=True):
        self.authorized = authorized
        self.requested = []

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def is_user_authorized(self):
        return self.authorized

    async def get_entity(self, chat):
        return type("Ent", (), {"id": 77, "title": "Links"})()

    async def iter_messages(self, entity, min_id=0, limit=0):
        self.requested.append(min_id)
        for msg in [_Msg(9, "hi there"), _Msg(8, "read https://a.test/x now"), _Msg(7, "fwd", fwd=True), _Msg(6, "t", urls=["https://hid.test"])]:
            if msg.id > min_id:
                yield msg


def test_extract_urls_dedupes() -> None:
    assert extract_urls("go https://a.test and https://a.test", ["https://a.test"]) == ["https://a.test"]


def test_telegram_collects_links_and_forwards_and_stages_cursor() -> None:
    client = FakeTg()
    conn = TelegramUser(1, "h", "s", ["-100"], client_factory=lambda: client)
    ctx = FetchContext(lambda ext: False, 30, {"telegram:77": "6"})
    items = list(conn.fetch(ctx))
    assert [i.external_id for i in items] == ["77:8", "77:7"]
    assert items[0].url == "https://a.test/x" and items[1].url == "https://t.me/c/77/7"
    assert ctx.staged == {"telegram:77": "9"} and client.requested == [6]


def test_telegram_unauthorized_and_empty_allowlist() -> None:
    conn = TelegramUser(1, "h", "s", ["x"], client_factory=lambda: FakeTg(authorized=False))
    with pytest.raises(ConnectorAuthError):
        list(conn.fetch(FetchContext(lambda e: False, 30, {})))
    assert list(TelegramUser(1, "h", "s", []).fetch(FetchContext(lambda e: False, 30, {}))) == []


class _Post:
    def __init__(self, code, video=False):
        self.shortcode = code
        self.caption = f"Caption {code}\nmore"
        self.owner_username = "chef"
        self.is_video = video
        self.video_url = f"https://cdn.test/{code}.mp4" if video else None
        self.date_utc = datetime(2026, 10, 1)


class _Profile:
    def get_saved_posts(self):
        yield _Post("a", video=True)
        yield _Post("b")
        yield _Post("c")


class _Loader:
    def __init__(self, error=None):
        self.error = error
        self.loaded = None

    def load_session(self, user, data):
        if self.error:
            raise self.error
        self.loaded = (user, data)

    context = object()


def test_instagram_throttles_limits_and_builds_audio(monkeypatch) -> None:
    import toy_lair_assistant.collector.connectors.instagram as ig

    monkeypatch.setattr(ig, "_profile", lambda loader, user: _Profile())
    sleeps: list[float] = []
    conn = InstagramSaved("me", json.dumps({"k": "v"}), loader_factory=_Loader, sleep=sleeps.append, pause_seconds=2)
    items = list(conn.fetch(FetchContext(lambda ext: ext == "b", 2, {})))
    assert [i.external_id for i in items] == ["a", "c"]
    assert items[0].audio is not None and items[1].audio is None
    assert items[0].title == "Caption a" and items[0].url == "https://www.instagram.com/p/a/"
    assert sleeps == [2]


def test_instagram_stops_on_checkpoint_and_missing_session(monkeypatch) -> None:
    class LoginRequiredException(Exception):
        pass

    with pytest.raises(ConnectorAuthError):
        list(InstagramSaved("me", "", loader_factory=_Loader).fetch(FetchContext(lambda e: False, 5, {})))
    conn = InstagramSaved("me", "{}", loader_factory=lambda: _Loader(LoginRequiredException("checkpoint")), sleep=lambda s: None)
    with pytest.raises(ConnectorAuthError):
        list(conn.fetch(FetchContext(lambda e: False, 5, {})))


def test_instagram_audio_extracts_via_ffmpeg_without_keeping_media() -> None:
    from toy_lair_assistant.collector.connectors.instagram import extract_audio

    seen: list[list[str]] = []

    def runner(args, **kw):
        seen.append(args)
        Path(args[-1]).write_bytes(b"audio")
        return subprocess.CompletedProcess(args, 0)

    assert extract_audio("https://cdn.test/a.mp4", runner) == b"audio"
    assert seen[0][0] == "ffmpeg" and "-vn" in seen[0]
    with pytest.raises(RuntimeError):
        extract_audio("u", lambda args, **kw: subprocess.CompletedProcess(args, 1))


def test_zayka_notes_index_only_allowed_and_never_own_sources(vault: Path) -> None:
    (vault / "20 Sources" / "chrome").mkdir(parents=True)
    (vault / "20 Sources" / "chrome" / "mine.md").write_text("x", encoding="utf-8")
    (vault / "00 Inbox").mkdir()
    (vault / "00 Inbox" / "a.md").write_text("x", encoding="utf-8")
    conn = ZaykaNotes(vault)
    items = list(conn.fetch(FetchContext(lambda e: False, 30, {})))
    assert sorted(i.extra["stable_id"] for i in items) == ["30 Projects/HireScope.md"]
    assert all(i.extra["indexed_only"] for i in items)


def test_indexed_only_items_are_not_written_to_vault(vault: Path) -> None:
    ingest = FakeIngest()
    llm = FakeLLM()
    pipe, _s, _v = pipeline(vault, ingest, llm)
    pipe.run([ZaykaNotes(vault)])
    assert llm.calls == 0
    assert ingest.items[0]["external_id"] == "30 Projects/HireScope.md"
    assert ingest.items[0]["vault_path"] == "30 Projects/HireScope.md"
    assert git(vault, "status", "--porcelain") == ""


def test_bot_inbox_turns_jobs_into_items() -> None:
    bot = BotInbox()
    bot.feed([{"id": "j1", "kind": "url", "payload": {"text": "nice\nhttps://a.test", "urls": ["https://a.test"]}}, {"id": "j2", "kind": "sync"}])
    items = list(bot.fetch(FetchContext(lambda e: False, 30, {})))
    assert len(items) == 1 and items[0].url == "https://a.test" and items[0].fetch_page
    bot.feed([{"id": "j3", "kind": "url", "payload": {"text": "just words"}}])
    assert list(bot.fetch(FetchContext(lambda e: False, 30, {})))[0].url == "bot:j3"


# runner

def _runner(vault: Path, ingest: FakeIngest, now: datetime, items=None):
    pipe, state, _ = pipeline(vault, ingest)
    bot = BotInbox()
    cfg = CollectorConfig(per_run_limit=30, sources=["chrome", "bot"])
    conns = {"chrome": StaticConnector("chrome", items or []), "bot": bot}
    return Runner(cfg, pipe, conns, bot, ingest, state, lambda: now), state


def test_runner_digest_alerts_and_due_logic(vault: Path) -> None:
    ingest = FakeIngest()
    runner, state = _runner(vault, ingest, NOW, [item(1)])
    assert runner.due()
    runner.run()
    assert ingest.events[-1][0] == "digest" and "chrome: 1" in ingest.events[-1][2]
    assert not runner.due()
    runner.now = lambda: NOW + timedelta(hours=25)
    assert runner.due()
    runner.now = lambda: (NOW + timedelta(days=1)).replace(hour=2)
    assert not runner.due()
    state.set_cursors({"backlog": "1"})
    runner.now = lambda: NOW + timedelta(hours=3)
    assert runner.due()


def test_runner_alerts_on_connector_error(vault: Path) -> None:
    ingest = FakeIngest()
    pipe, state, _ = pipeline(vault, ingest)
    bot = BotInbox()
    cfg = CollectorConfig(sources=["instagram"])
    bad = StaticConnector("instagram", [], ConnectorAuthError("checkpoint"))
    runner = Runner(cfg, pipe, {"instagram": bad, "bot": bot}, bot, ingest, state, lambda: NOW)
    runner.run()
    assert ("alert", "instagram", "instagram: checkpoint") in ingest.events


def test_runner_poll_serves_url_and_sync_jobs(vault: Path) -> None:
    ingest = FakeIngest()
    runner, state = _runner(vault, ingest, NOW, [item(9)])
    state.set_cursors({"last_full_run": NOW.isoformat(), "backlog": "0"})
    ingest.job_list = [{"id": "u1", "kind": "url", "payload": {"text": "https://z.test/page", "urls": ["https://z.test/page"]}}]
    assert runner.poll() == 1
    assert ingest.done_calls == [("u1", True)]
    assert any(i["source"] == "bot" for i in ingest.items)
    ingest.job_list = [{"id": "s1", "kind": "sync", "payload": {"source": "chrome"}}]
    assert runner.poll() == 1
    assert ingest.done_calls[-1] == ("s1", True)
    assert any(i["source"] == "chrome" for i in ingest.items)


def test_state_cursor_roundtrip_and_library(tmp_path: Path) -> None:
    state = CollectorState(tmp_path / "s" / "c.db")
    state.set_cursors({"a": "1"})
    state.add_library("k", "recipe", "T", "p.md")
    assert state.cursors() == {"a": "1"} and state.library_by_kind("recipe") == [("T", "p.md")]
    assert CollectorState(tmp_path / "s" / "c.db").cursors() == {"a": "1"}
