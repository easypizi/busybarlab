"""Small persistent memory (used facts, recent graphics, issue counter) on top of the store."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

KEY = "gazeta:state"
KEEP_FACTS = 400
KEEP_GRAPHICS = 7


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


class GazetaState:
    def __init__(self, store: Any, now) -> None:
        self.store = store
        self.now = now

    def load(self) -> dict[str, Any]:
        data = self.store.get_plan(KEY) if self.store is not None else None
        data = dict(data or {})
        data.setdefault("facts", [])
        data.setdefault("graphics", [])
        return data

    def save(self, data: dict[str, Any]) -> None:
        if self.store is None:
            return
        data["facts"] = data["facts"][-KEEP_FACTS:]
        data["graphics"] = data["graphics"][-KEEP_GRAPHICS:]
        self.store.save_plan(KEY, data, self.now())

    def record(self, fact: str | None, graphic: str | None, day: str) -> None:
        data = self.load()
        if fact:
            data["facts"].append(fact)
        if graphic:
            data["graphics"].append({"day": day, "kind": graphic})
        self.save(data)
