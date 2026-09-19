"""Achievement definitions and evaluation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from busybar.cursor_pet.state import PetState


@dataclass(frozen=True)
class Achievement:
    id: str
    title: str
    check: Callable[[PetState], bool]


def _has_journal(state: PetState, needle: str) -> bool:
    return any(needle.lower() in str(j.get("message", "")).lower() for j in state.journal)


ACHIEVEMENTS: list[Achievement] = [
    Achievement("first_bite", "First Bite", lambda s: s.xp > 0),
    Achievement("hundred_bucks", "Hundred Bucks", lambda s: s.xp >= 10000),
    Achievement("level_10", "Level 10", lambda s: s.level >= 10),
    Achievement("level_25", "Level 25", lambda s: s.level >= 25),
    Achievement("level_50", "Level 50", lambda s: s.level >= 50),
    Achievement("first_dark", "First Fall", lambda s: _has_journal(s, "fallen to dark")),
    Achievement("first_light", "First Light", lambda s: _has_journal(s, "redeemed to light")),
    Achievement("reach_light", "Touched Light", lambda s: s.branch == "light"),
    Achievement("reach_dark", "Touched Dark", lambda s: s.branch == "dark"),
    Achievement("metamorph_1", "First Metamorphosis", lambda s: s.tier >= 1),
    Achievement("trait_collector", "Trait Collector", lambda s: len(s.traits) >= 3),
]


def evaluate_achievements(state: PetState) -> list[str]:
    """Unlock new achievements. Returns newly unlocked titles."""
    unlocked: list[str] = []
    known = set(state.achievements)
    for ach in ACHIEVEMENTS:
        if ach.id in known:
            continue
        if ach.check(state):
            state.achievements.append(ach.id)
            unlocked.append(ach.title)
            state.journal.append(
                {
                    "kind": "achievement",
                    "message": ach.title,
                    "at": time.time(),
                    "meta": {"id": ach.id},
                }
            )
    return unlocked
