"""Desktop OAuth loopback flow. Prints GOOGLE_REFRESH_TOKEN."""

from __future__ import annotations

import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from toy_lair_assistant.settings import Settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": CALENDAR_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"{AUTH_URL}?{query}"


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    http: httpx.Client | None = None,
) -> str:
    client = http or httpx.Client(timeout=30)
    owns = http is None
    try:
        response = client.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        token = response.json().get("refresh_token")
        if not token:
            raise RuntimeError("Google did not return a refresh_token. Re-consent with prompt=consent.")
        return str(token)
    finally:
        if owns:
            client.close()


def _wait_for_code(host: str, port: int, expected_state: str) -> str:
    result: dict[str, str] = {}
    ready = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            state = (query.get("state") or [""])[0]
            code = (query.get("code") or [""])[0]
            if state != expected_state or not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"OAuth failed. Close this tab.")
                return
            result["code"] = code
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Google Calendar connected. You can close this tab.")
            ready.set()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if not ready.wait(timeout=180):
        server.shutdown()
        raise TimeoutError("Timed out waiting for Google OAuth redirect")
    server.shutdown()
    thread.join(timeout=2)
    return result["code"]


def main() -> int:
    settings = Settings()
    if not settings.google_client_id or not settings.google_client_secret:
        print("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first.")
        return 1
    host = "127.0.0.1"
    port = 8765
    redirect_uri = f"http://{host}:{port}/"
    state = secrets.token_urlsafe(16)
    url = authorize_url(settings.google_client_id, redirect_uri, state)
    print(f"Open this URL if the browser does not appear:\n{url}")
    webbrowser.open(url)
    code = _wait_for_code(host, port, state)
    token = exchange_code(
        settings.google_client_id,
        settings.google_client_secret,
        code,
        redirect_uri,
    )
    print(f"GOOGLE_REFRESH_TOKEN={token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
