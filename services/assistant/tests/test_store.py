from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from toy_lair_assistant.store import MemoryStore, SqliteStore


def test_memory_turns_keep_last_six_within_ttl() -> None:
    store = MemoryStore()
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    for i in range(8):
        store.add_turn("r1", "user", f"u{i}", now - timedelta(minutes=1))
        store.add_turn("r1", "assistant", f"a{i}", now - timedelta(minutes=1))
    store.add_turn("r1", "user", "old", now - timedelta(minutes=20))
    turns = store.recent_turns("r1", now, limit=6, ttl_minutes=15)
    contents = [t["content"] for t in turns]
    assert "old" not in contents
    assert contents[-6:] == ["u5", "a5", "u6", "a6", "u7", "a7"]
    assert all(t["role"] in ("user", "assistant") for t in turns)


def test_sqlite_turns_roundtrip(tmp_path) -> None:
    store = SqliteStore(str(tmp_path / "mem.db"))
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    store.add_turn("telegram", "user", "hi", now)
    store.add_turn("telegram", "assistant", "hello", now)
    store.add_turn("r1", "user", "other", now)
    turns = store.recent_turns("telegram", now)
    assert [(t["role"], t["content"]) for t in turns] == [
        ("user", "hi"),
        ("assistant", "hello"),
    ]


def test_memory_and_sqlite_save_plan(tmp_path) -> None:
    now = datetime(2026, 9, 20, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    payload = {"plan_id": "abcd1234", "suggested": [{"task_id": "t1"}]}
    memory = MemoryStore()
    memory.save_plan("abcd1234", payload, now)
    assert memory.get_plan("abcd1234") == payload
    assert memory.get_plan("missing") is None
    sqlite = SqliteStore(str(tmp_path / "plans.db"))
    sqlite.save_plan("abcd1234", payload, now)
    assert sqlite.get_plan("abcd1234") == payload
    assert sqlite.get_plan("missing") is None


def test_workout_log_appends_and_corrects(tmp_path) -> None:
    now = datetime(2026, 9, 22, 18, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    first = {"date": "2026-09-22", "status": "done", "raw": "сделал"}
    second = {"date": "2026-09-22", "status": "partial", "raw": "исправь"}
    other = {"date": "2026-09-23", "status": "skipped", "raw": "пропуск"}
    stores = (MemoryStore(), SqliteStore(str(tmp_path / "logs.db")))
    for store in stores:
        assert store.last_workout_log("2026-09-22") is None
        assert store.replace_last_workout_log("2026-09-22", second, now) is False
        store.append_workout_log("2026-09-22", first, now)
        store.append_workout_log("2026-09-22", second, now)
        assert store.last_workout_log("2026-09-22") == second
        store.append_workout_log("2026-09-23", other, now)
        assert store.replace_last_workout_log("2026-09-22", first, now) is True
        assert store.last_workout_log("2026-09-22") == first
        assert store.last_workout_log("2026-09-23") == other
        same_day = store.workout_logs_between("2026-09-22", "2026-09-22")
        assert same_day[-1] == first
        assert len(store.workout_logs_between("2026-09-22", "2026-09-23")) == 3


def test_draft_roundtrip_and_twelve_hour_expiry(tmp_path) -> None:
    now = datetime(2026, 9, 22, 15, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    payload = {"title": "Hire", "body": "first", "filename_hint": "", "related": []}
    for store in (MemoryStore(), SqliteStore(str(tmp_path / "drafts.db"))):
        assert store.get_draft("r1-paco", now) is None
        store.save_draft("r1-paco", payload, now)
        assert store.get_draft("r1-paco", now + timedelta(hours=12)) == payload
        assert store.get_draft("r1-paco", now + timedelta(hours=12, seconds=1)) is None
        store.save_draft("r1-paco", payload, now)
        store.clear_draft("r1-paco")
        assert store.get_draft("r1-paco", now) is None
