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
