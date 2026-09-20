from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any


def make_auth_alerter(
    store: Any,
    notify: Callable[[str], None],
    now: Callable[[], datetime],
) -> Callable[[], None]:
    def alert() -> None:
        key = f"google_auth:{now().date().isoformat()}"
        if store.seen(key):
            return
        notify("Calendar auth expired. Run python -m toy_lair_assistant.google_auth")
        store.mark(key)

    return alert
