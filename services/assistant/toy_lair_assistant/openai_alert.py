from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any


def make_openai_alerter(
    store: Any,
    notify: Callable[[str], None],
    now: Callable[[], datetime],
) -> Callable[[int, str], None]:
    def alert(status: int, detail: str) -> None:
        key = f"openai_api:{now().date().isoformat()}"
        if store.seen(key):
            return
        extra = f" {detail}".rstrip() if detail else ""
        notify(f"OpenAI is refusing requests ({status}{extra}). Check the balance.")
        store.mark(key)

    return alert


OPENAI_REPLY = "OpenAI is not answering. Try again later."


def openai_failure(status: int) -> bool:
    return status in (401, 429) or status >= 500


def openai_detail(response: Any) -> str:
    try:
        body = response.json()
    except Exception:
        return ""
    if not isinstance(body, dict):
        return ""
    error = body.get("error") or {}
    if not isinstance(error, dict):
        return ""
    return str(error.get("code") or error.get("type") or "")
