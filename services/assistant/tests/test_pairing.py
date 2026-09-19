from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from toy_lair_assistant.main import create_app
from toy_lair_assistant.pairing import Pairing, PairingFull
from toy_lair_assistant.settings import Settings

TZ = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 9, 19, 14, 0, tzinfo=TZ)


def test_start_returns_four_digit_code_and_secret() -> None:
    pairing = Pairing(token="secret")
    started = pairing.start(NOW)
    assert started["code"].isdigit()
    assert len(started["code"]) == 4
    assert started["secret"]
    assert started["expires_in"] == 600


def test_unknown_approve_is_false() -> None:
    pairing = Pairing(token="secret")
    assert pairing.approve("0000", NOW) is False


def test_pending_then_approved_claim_is_one_shot() -> None:
    pairing = Pairing(token="secret")
    started = pairing.start(NOW)
    pending = pairing.claim(started["secret"], NOW)
    assert pending == {"status": "pending"}
    assert pairing.approve(started["code"], NOW) is True
    first = pairing.claim(started["secret"], NOW)
    assert first == {"status": "approved", "token": "secret"}
    second = pairing.claim(started["secret"], NOW)
    assert second is None


def test_expired_session_cannot_be_approved_or_claimed() -> None:
    pairing = Pairing(token="secret", ttl_seconds=60)
    started = pairing.start(NOW)
    later = NOW + timedelta(seconds=61)
    assert pairing.approve(started["code"], later) is False
    assert pairing.claim(started["secret"], later) is None


def test_start_raises_when_live_sessions_hit_cap() -> None:
    pairing = Pairing(token="secret", max_sessions=2)
    pairing.start(NOW)
    pairing.start(NOW)
    try:
        pairing.start(NOW)
    except PairingFull:
        return
    raise AssertionError("expected PairingFull")


def test_approve_requires_token() -> None:
    app = create_app(
        Settings(
            assistant_api_token="secret",
            tick_interval_seconds=0,
            zayka_dir="",
        )
    )
    with TestClient(app) as client:
        started = client.post("/api/pair/start")
        assert started.status_code == 200
        code = started.json()["code"]
        denied = client.post("/api/pair/approve", json={"code": code})
        assert denied.status_code == 401
        ok = client.post(
            "/api/pair/approve",
            json={"code": code},
            headers={"X-Assistant-Token": "secret"},
        )
        assert ok.status_code == 200
        assert ok.json() == {"ok": True}


def test_claim_returns_token_exactly_once() -> None:
    app = create_app(
        Settings(
            assistant_api_token="secret",
            tick_interval_seconds=0,
            zayka_dir="",
        )
    )
    with TestClient(app) as client:
        started = client.post("/api/pair/start")
        body = started.json()
        pending = client.get("/api/pair/claim", params={"secret": body["secret"]})
        assert pending.status_code == 200
        assert pending.json() == {"status": "pending"}
        client.post(
            "/api/pair/approve",
            json={"code": body["code"]},
            headers={"X-Assistant-Token": "secret"},
        )
        first = client.get("/api/pair/claim", params={"secret": body["secret"]})
        assert first.status_code == 200
        assert first.json() == {"status": "approved", "token": "secret"}
        second = client.get("/api/pair/claim", params={"secret": body["secret"]})
        assert second.status_code == 404
