# Wednesday Frogs Design

Date: 2026-09-08

## Goal

Python app that drives a BUSY Bar front LED matrix (72x16) with hopping frogs and a periodic marquee: "IT'S WEDNESDAY MY DUDES".

## Decisions

- Runtime: host Python script via `busylib`, USB default `10.0.4.20`, optional Wi-Fi token.
- Front display only. Manual launch. No audio. No Wednesday auto-start daemon.
- Element-based rendering: frog phase PNGs uploaded once, coordinates updated each tick. Native text scroll for the marquee.
- Shared `busybar/common` backends: live `BusyBarBackend` and `TerminalBackend` (`--sim`).
- Non-Wednesday mode: gray sad frogs + "IT IS NOT WEDNESDAY MY DUDES".
- Button press (OK/START/CUSTOM) triggers marquee immediately.
- Occasional fly + tongue catch animation. Random frog speed/size variation.

## Scene

- 2-3 frogs hop left to right with phase-shifted parabolic arcs, wrap around.
- Marquee every ~20s (CLI `--text-interval`).
- Target ~10 FPS (`--fps`).
- Ctrl+C clears `wednesday-frogs` display + assets.

## Files

- `busybar/common/`: backends, pixelart, input WebSocket pump
- `busybar/wednesday_frogs/sprites.py`, `animation.py`, `main.py`

## Out of scope here

Cursor Token Pet is a separate app that reuses `busybar/common`.
