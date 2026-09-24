from datetime import datetime
from zoneinfo import ZoneInfo

from toy_lair_assistant.settings import Settings
from toy_lair_assistant.store import MemoryStore
from toy_lair_assistant.zayka_token import alert_if_expired, token_from_repo_url, token_status

NOW = datetime(2026, 11, 22, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
URL = "https://github_pat_test@github.com/easypizi/zayka.git"


class Response:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


def test_token_is_taken_from_the_repo_url() -> None:
    assert token_from_repo_url(URL) == "github_pat_test"
    assert token_from_repo_url("https://me:github_pat_other@github.com/easypizi/zayka.git") == (
        "github_pat_other"
    )


def test_expired_header_alerts_once_per_day() -> None:
    sent: list[str] = []
    store = MemoryStore()
    seen: dict[str, str] = {}

    def getter(url: str, headers: dict[str, str]) -> Response:
        seen["auth"] = headers["Authorization"]
        return Response(200, {"github-authentication-token-expiration": "2026-11-22 00:00:00 UTC"})

    settings = Settings(zayka_repo_url=URL)
    alert_if_expired(settings, store, sent.append, lambda: NOW, getter)
    alert_if_expired(settings, store, sent.append, lambda: NOW, getter)
    assert sent == ["Zayka GitHub token expired. Update ZAYKA_REPO_URL."]
    assert seen["auth"] == "Bearer github_pat_test"
    assert "github_pat_test" not in sent[0]


def test_future_expiration_does_not_alert() -> None:
    sent: list[str] = []

    def getter(url: str, headers: dict[str, str]) -> Response:
        return Response(200, {"github-authentication-token-expiration": "2027-01-21 00:00:00 UTC"})

    alert_if_expired(Settings(zayka_repo_url=URL), MemoryStore(), sent.append, lambda: NOW, getter)
    assert sent == []


def test_unauthorized_token_alerts() -> None:
    sent: list[str] = []

    def getter(url: str, headers: dict[str, str]) -> Response:
        return Response(401)

    alert_if_expired(Settings(zayka_repo_url=URL), MemoryStore(), sent.append, lambda: NOW, getter)
    assert sent == ["Zayka GitHub token expired. Update ZAYKA_REPO_URL."]


def test_token_without_expiration_header_stays_quiet() -> None:
    assert token_status(URL, NOW, lambda url, headers: Response(200)) == "ok"
