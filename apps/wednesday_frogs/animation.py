"""Scene logic for hopping frogs, fly events, and marquee schedule."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from apps.common.backend import RenderElement
from apps.wednesday_frogs.sprites import PHASE_NAMES, phase_filename

FRONT_W = 72
FRONT_H = 16
FROG_W = 12
FROG_H = 9
GROUND_Y = 7


@dataclass
class Frog:
    id: str
    x: float
    phase_t: float
    speed: float
    hop_height: float
    hop_period: float


@dataclass
class FlyEvent:
    x: float
    y: float
    vx: float
    target_frog: str
    tongue_frames: int = 0
    done: bool = False


@dataclass
class SceneState:
    frogs: list[Frog] = field(default_factory=list)
    fly: FlyEvent | None = None
    marquee_until: float = 0.0
    next_marquee_at: float = 0.0
    next_fly_at: float = 0.0
    is_wednesday: bool = True
    force_marquee: bool = False
    tick: int = 0


def is_wednesday(now: datetime | None = None) -> bool:
    dt = now or datetime.now()
    return dt.weekday() == 2


def marquee_text(wednesday: bool) -> str:
    if wednesday:
        return "IT'S WEDNESDAY MY DUDES"
    return "IT IS NOT WEDNESDAY MY DUDES"


def create_scene(
    frog_count: int = 3,
    *,
    now: float | None = None,
    seed: int | None = None,
    text_interval: float = 20.0,
) -> SceneState:
    rng = random.Random(seed)
    t = now if now is not None else time.monotonic()
    frogs: list[Frog] = []
    for i in range(frog_count):
        frogs.append(
            Frog(
                id=f"frog{i}",
                x=float(-FROG_W - i * 18 - rng.randint(0, 8)),
                phase_t=rng.random(),
                speed=rng.uniform(0.55, 0.95),
                hop_height=rng.uniform(3.5, 5.0),
                hop_period=rng.uniform(0.9, 1.4),
            )
        )
    return SceneState(
        frogs=frogs,
        next_marquee_at=t + text_interval,
        next_fly_at=t + rng.uniform(8.0, 16.0),
        is_wednesday=is_wednesday(),
    )


def hop_offset(phase_t: float, height: float) -> tuple[float, Literal["sit", "hop", "land"]]:
    """Parabolic hop. phase_t in [0, 1)."""
    p = phase_t % 1.0
    y = -4.0 * height * p * (p - 1.0)
    if p < 0.15:
        phase: Literal["sit", "hop", "land"] = "sit"
    elif p < 0.75:
        phase = "hop"
    else:
        phase = "land"
    return y, phase


def request_marquee(scene: SceneState) -> None:
    scene.force_marquee = True


def advance(
    scene: SceneState,
    dt: float,
    *,
    now: float | None = None,
    text_interval: float = 20.0,
    marquee_duration: float = 6.0,
    fly_chance_window: tuple[float, float] = (10.0, 22.0),
) -> None:
    t = now if now is not None else time.monotonic()
    scene.tick += 1
    scene.is_wednesday = is_wednesday()

    for frog in scene.frogs:
        frog.x += frog.speed * dt * 12.0
        frog.phase_t = (frog.phase_t + dt / frog.hop_period) % 1.0
        if frog.x > FRONT_W + 4:
            frog.x = float(-FROG_W - random.randint(0, 10))
            frog.phase_t = random.random()

    if scene.force_marquee or t >= scene.next_marquee_at:
        scene.marquee_until = t + marquee_duration
        scene.next_marquee_at = t + text_interval
        scene.force_marquee = False

    if scene.fly is None and t >= scene.next_fly_at:
        target = min(scene.frogs, key=lambda f: abs(f.x - FRONT_W / 2))
        scene.fly = FlyEvent(
            x=float(FRONT_W + 4),
            y=2.0,
            vx=-1.4,
            target_frog=target.id,
        )

    if scene.fly and not scene.fly.done:
        fly = scene.fly
        target = next((f for f in scene.frogs if f.id == fly.target_frog), scene.frogs[0])
        ty_off, _ = hop_offset(target.phase_t, target.hop_height)
        target_y = GROUND_Y + ty_off
        if fly.tongue_frames > 0:
            fly.tongue_frames -= 1
            if fly.tongue_frames <= 0:
                fly.done = True
                scene.fly = None
                scene.next_fly_at = t + random.uniform(*fly_chance_window)
        else:
            fly.x += fly.vx
            # Home toward frog mouth.
            fly.y += (target_y - fly.y) * 0.08
            if abs(fly.x - (target.x + 6)) < 3 and abs(fly.y - target_y) < 3:
                fly.tongue_frames = 4
            if fly.x < -6:
                fly.done = True
                scene.fly = None
                scene.next_fly_at = t + random.uniform(*fly_chance_window)


def render_elements(scene: SceneState, *, now: float | None = None) -> list[RenderElement]:
    t = now if now is not None else time.monotonic()
    sad = not scene.is_wednesday
    elements: list[RenderElement] = []

    for frog in scene.frogs:
        y_off, phase = hop_offset(frog.phase_t, frog.hop_height)
        y = int(round(GROUND_Y + y_off))
        x = int(round(frog.x))
        elements.append(
            RenderElement(
                id=frog.id,
                kind="image",
                x=x,
                y=max(0, min(FRONT_H - FROG_H, y)),
                display="front",
                path=phase_filename(phase, sad=sad),
            )
        )

    if scene.fly and not scene.fly.done:
        fly = scene.fly
        if fly.tongue_frames > 0:
            target = next((f for f in scene.frogs if f.id == fly.target_frog), scene.frogs[0])
            elements.append(
                RenderElement(
                    id="tongue",
                    kind="image",
                    x=int(round(target.x + 8)),
                    y=int(round(GROUND_Y + hop_offset(target.phase_t, target.hop_height)[0] + 2)),
                    display="front",
                    path="tongue.png",
                )
            )
        else:
            elements.append(
                RenderElement(
                    id="fly",
                    kind="image",
                    x=int(round(fly.x)),
                    y=int(round(fly.y)),
                    display="front",
                    path="fly.png",
                )
            )

    if t < scene.marquee_until:
        color = "#7CFC00FF" if scene.is_wednesday else "#A0A0A0FF"
        elements.append(
            RenderElement(
                id="marquee",
                kind="text",
                x=0,
                y=0,
                display="front",
                text=marquee_text(scene.is_wednesday),
                font="small",
                color=color,
                width=FRONT_W,
                scroll_rate=700,
                scroll_start_delay=200,
                scroll_repeat_delay=1500,
            )
        )

    return elements


def expected_phase_at(phase_t: float) -> str:
    _, phase = hop_offset(phase_t, 4.0)
    assert phase in PHASE_NAMES
    return phase
