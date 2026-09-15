"""Evolution rules: XP curve, tiers, branches, trait pools, model accessories."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Literal

Branch = Literal["light", "dark", "gray"]

XP_BASE = 50.0
XP_GROWTH = 1.35
LEVELS_PER_TIER = 5
LIGHT_THRESHOLD = 0.2
DARK_THRESHOLD = -0.2
FAVORITE_XP_MULT = 1.2

DARK_TRAITS = ["horns", "spikes", "shadow_aura", "fangs", "cape", "ember"]
LIGHT_TRAITS = ["halo", "wings", "glow", "crown", "sparkles", "ribbon"]
GRAY_TRAITS = ["mask", "scarf", "goggles", "antenna", "badge", "circuit"]

MODEL_ACCESSORIES = {
    "claude": "scarf",
    "gpt": "glasses",
    "composer": "bolt",
    "gemini": "stars",
    "grok": "visor",
    "auto": "gear",
}


@dataclass
class LevelProgress:
    level: int
    xp_into_level: float
    xp_to_next: float
    tier: int
    progress: float


def xp_to_next(level: int) -> float:
    return XP_BASE * (XP_GROWTH ** max(0, level))


def level_from_xp(total_xp: float) -> LevelProgress:
    level = 0
    remaining = max(0.0, total_xp)
    while True:
        need = xp_to_next(level)
        if remaining < need:
            return LevelProgress(
                level=level,
                xp_into_level=remaining,
                xp_to_next=need,
                tier=level // LEVELS_PER_TIER,
                progress=remaining / need if need else 0.0,
            )
        remaining -= need
        level += 1
        if level > 10_000:
            # Safety valve for absurd XP.
            return LevelProgress(level, 0.0, xp_to_next(level), level // LEVELS_PER_TIER, 0.0)


def branch_from_alignment(alignment: float) -> Branch:
    if alignment > LIGHT_THRESHOLD:
        return "light"
    if alignment < DARK_THRESHOLD:
        return "dark"
    return "gray"


def compute_alignment(work_cents: float, personal_cents: float, bias: float = 0.0) -> float:
    total = work_cents + personal_cents
    if total <= 0:
        return max(-1.0, min(1.0, bias))
    raw = (personal_cents - work_cents) / total
    return max(-1.0, min(1.0, raw + bias))


def trait_pool(branch: Branch) -> list[str]:
    if branch == "light":
        return LIGHT_TRAITS
    if branch == "dark":
        return DARK_TRAITS
    return GRAY_TRAITS


def pick_trait(seed: int, tier: int, branch: Branch, existing: list[str]) -> str | None:
    pool = [t for t in trait_pool(branch) if t not in existing]
    if not pool:
        # Cycle with suffix for infinite uniqueness.
        base = trait_pool(branch)[tier % len(trait_pool(branch))]
        return f"{base}_{tier}"
    rng = random.Random(f"{seed}:{tier}:{branch}")
    return rng.choice(pool)


def accessory_for_model(model: str | None) -> str | None:
    if not model:
        return None
    key = model.lower()
    for name, accessory in MODEL_ACCESSORIES.items():
        if name in key:
            return accessory
    return "badge"


def dominant_model(model_cents: dict[str, float]) -> str | None:
    if not model_cents:
        return None
    return max(model_cents.items(), key=lambda kv: kv[1])[0]


def xp_from_spend(cents: float, model: str | None, favorite_model: str) -> float:
    mult = FAVORITE_XP_MULT if model and favorite_model.lower() in model.lower() else 1.0
    return cents * mult
