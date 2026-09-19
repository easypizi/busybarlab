from urllib.parse import parse_qs, urlparse

import httpx

from toy_lair_assistant.google_auth import (
    CALENDAR_SCOPE,
    TOKEN_URL,
    authorize_url,
    exchange_code,
)


def test_authorize_url_asks_offline_calendar_access() -> None:
    url = authorize_url(
        client_id="cid.apps.googleusercontent.com",
        redirect_uri="http://127.0.0.1:8765/",
        state="abc",
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "accounts.google.com"
    assert query["client_id"] == ["cid.apps.googleusercontent.com"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8765/"]
    assert query["response_type"] == ["code"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["state"] == ["abc"]
    assert CALENDAR_SCOPE in query["scope"][0]


def test_exchange_code_returns_refresh_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == TOKEN_URL
        seen.update(dict(parse_qs(request.content.decode("utf-8"))))
        return httpx.Response(
            200,
            json={"refresh_token": "refresh-1", "access_token": "acc"},
        )

    token = exchange_code(
        client_id="cid",
        client_secret="sec",
        code="auth-code",
        redirect_uri="http://127.0.0.1:8765/",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert token == "refresh-1"
    assert seen["code"] == ["auth-code"]
    assert seen["grant_type"] == ["authorization_code"]
    assert seen["client_secret"] == ["sec"]
