"""Persistent pet state with atomic saves and backup rotation."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from busybar.cursor_pet.evolution import (
    LevelProgress,
    accessory_for_model,
    branch_from_alignment,
    compute_alignment,
    dominant_model,
    level_from_xp,
    pick_trait,
    xp_from_spend,
)
from busybar.cursor_pet.genesis import GenesisResult, roll_genesis

Branch = Literal["light", "dark", "gray"]
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_PATH = ROOT / "data" / "pet_state.json"
DEFAULT_BACKUP_DIR = ROOT / "data" / "backups"
MAX_BACKUPS = 10


@dataclass
class JournalEntry:
    kind: str
    message: str
    at: float
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccountRuntime:
    last_total_spend_cents: float = 0.0
    percent_used: float = 0.0
    limit_cents: float = 0.0
    today_cents: float = 0.0
    last_seen_at: float = 0.0
    online: bool = False


@dataclass
class PetState:
    seed: int
    name: str
    temperament: str
    alignment_bias: float
    favorite_model: str
    body_pattern: str
    created_at: float
    xp: float = 0.0
    level: int = 0
    tier: int = 0
    branch: Branch = "gray"
    traits: list[str] = field(default_factory=list)
    alignment: float = 0.0
    work_window_cents: float = 0.0
    personal_window_cents: float = 0.0
    cycle_eaten_cents: float = 0.0
    contentment: float = 0.5
    achievements: list[str] = field(default_factory=list)
    journal: list[dict[str, Any]] = field(default_factory=list)
    work: dict[str, Any] = field(default_factory=dict)
    personal: dict[str, Any] = field(default_factory=dict)
    model_window: dict[str, float] = field(default_factory=dict)
    hud_page: int = 0
    metamorphosis_flash_until: float = 0.0
    pet_flash_until: float = 0.0
    last_accessory: str | None = None

    def progress(self) -> LevelProgress:
        return level_from_xp(self.xp)

    def sync_progress(self) -> list[str]:
        """Update level/tier/branch/traits. Returns event messages."""
        events: list[str] = []
        while True:
            prog = self.progress()
            if prog.level > self.level:
                self.level = prog.level
                events.append(f"LEVEL {self.level}")
            if prog.tier <= self.tier:
                break
            old_branch = self.branch
            self.alignment = compute_alignment(
                self.work_window_cents,
                self.personal_window_cents,
                self.alignment_bias,
            )
            new_branch = branch_from_alignment(self.alignment)
            if old_branch == "light" and new_branch == "dark":
                events.append("FALLEN TO DARK")
            elif old_branch == "dark" and new_branch == "light":
                events.append("REDEEMED TO LIGHT")
            self.branch = new_branch
            self.tier += 1
            if self.tier >= 1:
                trait = pick_trait(self.seed, self.tier, new_branch, self.traits)
                if trait:
                    self.traits.append(trait)
            events.append(f"METAMORPHOSIS T{self.tier} {new_branch.upper()}")
            self.metamorphosis_flash_until = time.time() + 8.0
            self.journal.append(
                {
                    "kind": "metamorphosis",
                    "message": events[-1],
                    "at": time.time(),
                    "meta": {"tier": self.tier, "branch": new_branch, "level": self.level},
                }
            )
        self.level = self.progress().level
        self.last_accessory = accessory_for_model(dominant_model(self.model_window))
        return events

    def feed(
        self,
        account: Literal["work", "personal"],
        cents: float,
        *,
        cycle_rolled: bool = False,
        model: str | None = None,
    ) -> list[str]:
        if cycle_rolled:
            self.cycle_eaten_cents = 0.0
            self.contentment = max(0.2, self.contentment * 0.5)
        if cents <= 0:
            return []
        gained = xp_from_spend(cents, model, self.favorite_model)
        self.xp += gained
        self.cycle_eaten_cents += cents
        self.contentment = min(1.0, self.contentment + min(0.15, cents / 500.0))
        if account == "work":
            self.work_window_cents += cents
        else:
            self.personal_window_cents += cents
        if model:
            self.model_window[model] = self.model_window.get(model, 0.0) + cents
        self.alignment = compute_alignment(
            self.work_window_cents,
            self.personal_window_cents,
            self.alignment_bias,
        )
        return self.sync_progress()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PetState:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def save_state(state: PetState, path: Path | None = None, backup_dir: Path | None = None) -> None:
    path = path or DEFAULT_STATE_PATH
    backup_dir = backup_dir or DEFAULT_BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, backup_dir / f"pet_state-{stamp}.json")
        backups = sorted(backup_dir.glob("pet_state-*.json"))
        for old in backups[:-MAX_BACKUPS]:
            old.unlink(missing_ok=True)
    _atomic_write(path, json.dumps(state.to_dict(), indent=2, sort_keys=True))


def load_state(path: Path | None = None) -> PetState | None:
    path = path or DEFAULT_STATE_PATH
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return PetState.from_dict(data)


def load_or_create(path: Path | None = None, *, seed: int | None = None) -> tuple[PetState, bool]:
    existing = load_state(path)
    if existing:
        return existing, False
    genesis = roll_genesis(seed)
    state = PetState(
        seed=genesis.seed,
        name=genesis.name,
        temperament=genesis.temperament,
        alignment_bias=genesis.alignment_bias,
        favorite_model=genesis.favorite_model,
        body_pattern=genesis.body_pattern,
        created_at=genesis.created_at,
        branch="gray",
        journal=[
            {
                "kind": "genesis",
                "message": f"Hatched {genesis.name}",
                "at": genesis.created_at,
                "meta": genesis.to_dict(),
            }
        ],
    )
    save_state(state, path)
    return state, True


def reroll(path: Path | None = None, *, seed: int | None = None) -> PetState:
    path = path or DEFAULT_STATE_PATH
    if path.exists():
        path.unlink()
    state, _ = load_or_create(path, seed=seed)
    return state
