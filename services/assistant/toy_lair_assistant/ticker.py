from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger(__name__)


async def run_periodic(
    fn: Callable[[], Any],
    interval_seconds: float,
    sleeper: Callable[[float], Awaitable[None]] | None = None,
) -> None:
    if sleeper is None:
        import asyncio

        sleeper = asyncio.sleep
    while True:
        try:
            fn()
        except Exception:
            log.exception("periodic task failed")
        await sleeper(interval_seconds)
