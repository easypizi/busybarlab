"""Bake Wednesday Frogs scene into a looping .anim for onboard playback."""

from __future__ import annotations

from dataclasses import dataclass

from busybar.common.animfile import decode_check, encode_anim
from busybar.common.pixelart import DEFAULT_PALETTE
from busybar.wednesday_frogs.animation import hop_offset
from busybar.wednesday_frogs.sprites import (
    FLY,
    FROG_HOP,
    FROG_HOP_SAD,
    FROG_LAND,
    FROG_LAND_SAD,
    FROG_SIT,
    FROG_SIT_SAD,
    TONGUE,
)

FRONT_W = 72
FRONT_H = 16
GROUND_Y = 7
FROG_W = 12


@dataclass(frozen=True)
class BakeConfig:
    fps: int = 12
    frame_count: int = 48
    frog_count: int = 3
    spacing: int = 24
    hop_height: float = 4.2
    hop_period_frames: int = 14
    include_fly: bool = True


def _rows_to_rgba(rows: list[str]) -> list[list[tuple[int, int, int, int]]]:
    width = max(len(r) for r in rows)
    out: list[list[tuple[int, int, int, int]]] = []
    for row in rows:
        padded = row.ljust(width)
        out.append([DEFAULT_PALETTE.get(ch, (0, 0, 0, 0)) for ch in padded])
    return out


def _blit(
    canvas: bytearray,
    rgba_rows: list[list[tuple[int, int, int, int]]],
    x0: int,
    y0: int,
    *,
    width: int = FRONT_W,
    height: int = FRONT_H,
) -> None:
    for dy, row in enumerate(rgba_rows):
        y = y0 + dy
        if y < 0 or y >= height:
            continue
        for dx, (r, g, b, a) in enumerate(row):
            if a < 16:
                continue
            x = x0 + dx
            if x < 0 or x >= width:
                continue
            i = (y * width + x) * 4
            # Device format is BGRA8888.
            canvas[i : i + 4] = bytes((b, g, r, 255))


def _frog_rows(phase: str, *, sad: bool) -> list[str]:
    if sad:
        return {"sit": FROG_SIT_SAD, "hop": FROG_HOP_SAD, "land": FROG_LAND_SAD}[phase]
    return {"sit": FROG_SIT, "hop": FROG_HOP, "land": FROG_LAND}[phase]


def render_frame(
    frame_idx: int,
    *,
    sad: bool,
    config: BakeConfig,
) -> bytes:
    """One 72x16 BGRA frame of hopping frogs (seamless when idx wraps)."""
    canvas = bytearray(FRONT_W * FRONT_H * 4)  # transparent/black
    period = config.frog_count * config.spacing
    # Move exactly `spacing` pixels over the full loop so the formation repeats.
    scroll = (frame_idx * config.spacing) / config.frame_count

    for frog_i in range(config.frog_count):
        x = (frog_i * config.spacing + scroll) % period
        x_draw = int(round(x)) - FROG_W

        phase_t = (
            (frame_idx / config.hop_period_frames) + frog_i * (1.0 / config.frog_count)
        ) % 1.0
        y_off, phase = hop_offset(phase_t, config.hop_height)
        y = int(round(GROUND_Y + y_off))
        rows = _frog_rows(phase, sad=sad)
        rgba = _rows_to_rgba(rows)
        y_clamped = max(0, min(FRONT_H - len(rows), y))
        _blit(canvas, rgba, x_draw, y_clamped)
        # Second blit when the sprite wraps past the right edge.
        _blit(canvas, rgba, x_draw - period, y_clamped)
        _blit(canvas, rgba, x_draw + period, y_clamped)

    if config.include_fly:
        # Fly crosses once per loop; tongue flash near mid-loop.
        fly_x = FRONT_W + 2 - int(round((frame_idx / config.frame_count) * (FRONT_W + 10)))
        fly_y = 2 + (frame_idx % 5) // 2
        mid = config.frame_count // 2
        if abs(frame_idx - mid) <= 1:
            _blit(canvas, _rows_to_rgba(TONGUE), max(0, fly_x), fly_y + 1)
        else:
            _blit(canvas, _rows_to_rgba(FLY), fly_x, fly_y)

    return bytes(canvas)


def bake_anim(*, sad: bool = False, config: BakeConfig | None = None) -> bytes:
    cfg = config or BakeConfig()
    frames = [render_frame(i, sad=sad, config=cfg) for i in range(cfg.frame_count)]
    blob = encode_anim(frames, fps=cfg.fps, width=FRONT_W, height=FRONT_H)
    decode_check(blob, frames, width=FRONT_W, height=FRONT_H)
    return blob


def bake_both(config: BakeConfig | None = None) -> dict[str, bytes]:
    cfg = config or BakeConfig()
    return {
        "frogs_happy.anim": bake_anim(sad=False, config=cfg),
        "frogs_sad.anim": bake_anim(sad=True, config=cfg),
    }
