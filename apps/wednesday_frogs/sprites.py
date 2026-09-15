"""Pixel-art frog hop phases, fly, and tongue sprites."""

from __future__ import annotations

from apps.common.pixelart import ascii_to_png_bytes

# Palette keys: G/g green, S/s gray sad, W white eye, B black, Y tongue, R fly
FROG_SIT = [
    "........... ",
    "..GG.GG.... ",
    ".GWBGBWG... ",
    ".GGGGGGG... ",
    "..GGGGG.... ",
    "...g.g..... ",
    "........... ",
    "........... ",
    "........... ",
]

FROG_HOP = [
    "........... ",
    "..GG.GG.... ",
    ".GWBGBWG... ",
    ".GGGGGGG... ",
    "g.GGGGG.g.. ",
    "........... ",
    "........... ",
    "........... ",
    "........... ",
]

FROG_LAND = [
    "........... ",
    "..GG.GG.... ",
    ".GWBGBWG... ",
    ".GGGGGGG... ",
    "..GGGGG.... ",
    "..g...g.... ",
    "........... ",
    "........... ",
    "........... ",
]

FROG_SIT_SAD = [
    "........... ",
    "..SS.SS.... ",
    ".SsBsBs.... ",
    ".SSSSSSS... ",
    "..SSSSS.... ",
    "...s.s..... ",
    "........... ",
    "........... ",
    "........... ",
]

FROG_HOP_SAD = [
    "........... ",
    "..SS.SS.... ",
    ".SsBsBs.... ",
    ".SSSSSSS... ",
    "s.SSSSS.s.. ",
    "........... ",
    "........... ",
    "........... ",
    "........... ",
]

FROG_LAND_SAD = [
    "........... ",
    "..SS.SS.... ",
    ".SsBsBs.... ",
    ".SSSSSSS... ",
    "..SSSSS.... ",
    "..s...s.... ",
    "........... ",
    "........... ",
    "........... ",
]

FLY = [
    ".W.",
    "BRB",
    ".W.",
]

TONGUE = [
    "YYYY",
]

PHASE_NAMES = ("sit", "hop", "land")


def build_sprite_bank(*, sad: bool = False) -> dict[str, bytes]:
    """Return PNG bytes keyed by sprite name."""
    if sad:
        frogs = {
            "frog_sit.png": FROG_SIT_SAD,
            "frog_hop.png": FROG_HOP_SAD,
            "frog_land.png": FROG_LAND_SAD,
        }
    else:
        frogs = {
            "frog_sit.png": FROG_SIT,
            "frog_hop.png": FROG_HOP,
            "frog_land.png": FROG_LAND,
        }
    bank = {name: ascii_to_png_bytes(rows) for name, rows in frogs.items()}
    bank["fly.png"] = ascii_to_png_bytes(FLY)
    bank["tongue.png"] = ascii_to_png_bytes(TONGUE)
    return bank


def phase_filename(phase: str, *, sad: bool = False) -> str:
    if phase not in PHASE_NAMES:
        phase = "sit"
    return f"frog_{phase}.png"
