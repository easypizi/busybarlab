from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger(__name__)

ALERT = "Zayka GitHub token expired. Update ZAYKA_REPO_URL."


def token_from_repo_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.password:
        return parsed.password
    username = parsed.username or ""
    if username and username not in {"git", "x-access-token"}:
        return username
    return ""


def parse_expiration(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith(" UTC"):
        text = text[: -len(" UTC")]
    if text.endswith("Z"):
        text = text[:-1]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def token_status(repo_url: str, now: datetime, getter: Any) -> str:
    token = token_from_repo_url(repo_url)
    if not token:
        return "unknown"
    try:
        response = getter(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "toy-lair-assistant",
            },
        )
    except Exception:
        log.exception("zayka token check failed")
        return "unknown"
    if getattr(response, "status_code", 0) == 401:
        return "expired"
    header = ""
    headers = getattr(response, "headers", {}) or {}
    header = str(headers.get("github-authentication-token-expiration") or "")
    if not header:
        return "ok"
    expires = parse_expiration(header)
    if expires is None:
        return "unknown"
    current = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    if current >= expires:
        return "expired"
    return "ok"


def alert_if_expired(settings: Any, store: Any, notify: Any, now: Any, getter: Any) -> None:
    if store is None:
        return
    moment = now() if callable(now) else now
    status = token_status(getattr(settings, "zayka_repo_url", ""), moment, getter)
    if status != "expired":
        return
    key = f"zayka_token:{moment.date().isoformat()}"
    if store.seen(key):
        return
    if notify is not None:
        try:
            send = getattr(notify, "send_text", None) or notify
            send(ALERT)
        except Exception:
            log.exception("zayka token alert failed")
            return
    store.mark(key)
