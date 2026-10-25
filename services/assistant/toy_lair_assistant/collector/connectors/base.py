from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from toy_lair_assistant.collector.models import FetchContext, RawItem


class Connector(Protocol):
    name: str

    def fetch(self, ctx: FetchContext) -> Iterator[RawItem]: ...
