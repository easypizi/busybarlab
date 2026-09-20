from datetime import datetime
from zoneinfo import ZoneInfo

from toy_lair_assistant.google_alert import make_auth_alerter
from toy_lair_assistant.store import MemoryStore


def test_google_auth_alert_dedupes_per_day() -> None:
    sent: list[str] = []
    store = MemoryStore()
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    alert = make_auth_alerter(store, sent.append, lambda: now)
    alert()
    alert()
    assert len(sent) == 1
    assert "google_auth" in sent[0].lower() or "calendar" in sent[0].lower()
    assert "google_auth" in str(store.keys) or store.seen("google_auth:2026-09-19")
