from datetime import datetime
from zoneinfo import ZoneInfo


class Clock:
    def __init__(self, timezone: str = "America/Los_Angeles") -> None:
        self.timezone = timezone

    def now(self) -> datetime:
        return datetime.now(ZoneInfo(self.timezone))
