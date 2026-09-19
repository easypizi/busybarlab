import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from toy_lair_assistant.clock import Clock
from toy_lair_assistant.main import create_app
from toy_lair_assistant.settings import Settings
from toy_lair_assistant.ticker import run_periodic


class FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[datetime] = []

    def tick(self, now: datetime) -> int:
        self.calls.append(now)
        return 0


def test_run_periodic_calls_tick_then_sleeps() -> None:
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    clock = Clock("America/Los_Angeles")
    clock.now = lambda: now
    scheduler = FakeScheduler()
    sleeps: list[float] = []

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 2:
            raise asyncio.CancelledError()

    async def run() -> None:
        try:
            await run_periodic(
                lambda: scheduler.tick(clock.now()),
                interval_seconds=60,
                sleeper=sleeper,
            )
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert scheduler.calls == [now, now]
    assert sleeps == [60, 60]


def test_lifespan_ticks_scheduler() -> None:
    scheduler = FakeScheduler()
    clock = Clock("America/Los_Angeles")
    now = datetime(2026, 9, 19, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    clock.now = lambda: now
    app = create_app(
        Settings(assistant_api_token="secret", tick_interval_seconds=0.05),
        clock=clock,
    )
    app.state.scheduler = scheduler
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        deadline = datetime.now().timestamp() + 2
        while not scheduler.calls and datetime.now().timestamp() < deadline:
            pass
    assert scheduler.calls
    assert scheduler.calls[0] == now
