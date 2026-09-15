"""Tests for Cursor Token Pet evolution, state, collector math, genesis."""

from __future__ import annotations

import json
from pathlib import Path

from apps.cursor_pet.achievements import evaluate_achievements
from apps.cursor_pet.collector import UsageSnapshot, compute_delta
from apps.cursor_pet.evolution import (
    branch_from_alignment,
    compute_alignment,
    level_from_xp,
    pick_trait,
    xp_to_next,
)
from apps.cursor_pet.genesis import roll_genesis
from apps.cursor_pet.state import PetState, load_or_create, reroll, save_state


def test_genesis_deterministic() -> None:
    a = roll_genesis(42)
    b = roll_genesis(42)
    assert a.name == b.name
    assert a.favorite_model == b.favorite_model
    assert a.temperament == b.temperament


def test_xp_curve_and_infinite_levels() -> None:
    assert xp_to_next(0) == 50.0
    assert xp_to_next(1) > xp_to_next(0)
    prog = level_from_xp(0)
    assert prog.level == 0
    # Feed enough XP to cross multiple tiers.
    total = 0.0
    for _ in range(40):
        total += xp_to_next(level_from_xp(total).level)
    prog = level_from_xp(total)
    assert prog.level >= 30
    assert prog.tier == prog.level // 5


def test_alignment_and_branches() -> None:
    assert compute_alignment(100, 0) == -1.0
    assert compute_alignment(0, 100) == 1.0
    assert branch_from_alignment(0.5) == "light"
    assert branch_from_alignment(-0.5) == "dark"
    assert branch_from_alignment(0.0) == "gray"


def test_billing_cycle_rollover_delta() -> None:
    prev = UsageSnapshot(
        account="work",
        total_spend_cents=9000,
        included_spend_cents=9000,
        limit_cents=40000,
        remaining_cents=31000,
        percent_used=22.5,
    )
    current = UsageSnapshot(
        account="work",
        total_spend_cents=100,
        included_spend_cents=100,
        limit_cents=40000,
        remaining_cents=39900,
        percent_used=0.25,
    )
    delta = compute_delta(prev, current)
    assert delta.cycle_rolled is True
    assert delta.delta_cents == 100.0


def test_feed_metamorphosis_and_traits(tmp_path: Path) -> None:
    state = PetState(
        seed=7,
        name="Testo",
        temperament="stoic",
        alignment_bias=0.0,
        favorite_model="claude",
        body_pattern="spots",
        created_at=0.0,
    )
    # Heavy personal spend -> light branch on first metamorphosis.
    events: list[str] = []
    # Need enough XP to reach level 5 (tier 1).
    while state.tier < 1:
        events.extend(state.feed("personal", 200.0, model="claude"))
    assert state.tier >= 1
    assert state.branch == "light"
    assert any("METAMORPHOSIS" in e for e in events)
    assert state.traits

    # Later dark spend can cause a fall on next tier.
    start_tier = state.tier
    while state.tier < start_tier + 1:
        state.feed("work", 500.0, model="gpt")
    assert state.branch in {"dark", "gray", "light"}

    unlocked = evaluate_achievements(state)
    assert "First Bite" in unlocked or "first_bite" in state.achievements


def test_atomic_save_and_reroll(tmp_path: Path) -> None:
    path = tmp_path / "pet_state.json"
    backups = tmp_path / "backups"
    state, created = load_or_create(path, seed=99)
    assert created
    state.feed("personal", 10)
    save_state(state, path, backups)
    assert path.exists()
    reloaded, created2 = load_or_create(path)
    assert created2 is False
    assert reloaded.name == state.name
    assert reloaded.xp == state.xp
    new_state = reroll(path, seed=100)
    assert new_state.seed == 100
    assert json.loads(path.read_text())["seed"] == 100


def test_trait_pick_deterministic() -> None:
    a = pick_trait(1, 5, "dark", [])
    b = pick_trait(1, 5, "dark", [])
    assert a == b
    assert a is not None
