"""First-launch genesis: seed-derived name, temperament, and starting traits."""

from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass
from typing import Literal

Temperament = Literal["sleepy", "hyper", "stoic"]
Branch = Literal["light", "dark", "gray"]

PREFIXES = [
    "Aza", "Lumi", "Nyx", "Sol", "Vex", "Ora", "Kai", "Mira", "Zeno", "Pixa",
    "Echo", "Bolt", "Nox", "Faye", "Rune",
]
SUFFIXES = [
    "zel", "io", "ara", "on", "ix", "elle", "ius", "a", "or", "yn", "ette", "um",
]
MODELS = ["claude", "gpt", "composer", "gemini", "grok", "auto"]
TEMPERAMENTS: list[Temperament] = ["sleepy", "hyper", "stoic"]
PATTERNS = ["spots", "stripes", "swirl", "plain", "stars"]


@dataclass
class GenesisResult:
    seed: int
    name: str
    temperament: Temperament
    alignment_bias: float
    favorite_model: str
    body_pattern: str
    created_at: float

    def to_dict(self) -> dict:
        return asdict(self)


def generate_name(rng: random.Random) -> str:
    return rng.choice(PREFIXES) + rng.choice(SUFFIXES)


def roll_genesis(seed: int | None = None) -> GenesisResult:
    seed_value = seed if seed is not None else random.SystemRandom().randint(1, 2**31 - 1)
    rng = random.Random(seed_value)
    return GenesisResult(
        seed=seed_value,
        name=generate_name(rng),
        temperament=rng.choice(TEMPERAMENTS),
        alignment_bias=rng.uniform(-0.1, 0.1),
        favorite_model=rng.choice(MODELS),
        body_pattern=rng.choice(PATTERNS),
        created_at=time.time(),
    )
