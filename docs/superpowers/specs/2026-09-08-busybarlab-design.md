# Wednesday Frogs + Cursor Token Pet Design

Date: 2026-09-08

## Overview

Two BUSY Bar lab apps sharing `busybar/common` render backends.

1. **Wednesday Frogs** — front 72x16 RGB hopping frogs + marquee.
2. **Cursor Token Pet** — back 160x80 OLED evolving pet fed by Cursor token spend from work (dark) and personal (light) accounts.

## Common layer

- `DisplayBackend` interface with `BusyBarBackend` (busylib) and `TerminalBackend` (`--sim`).
- ASCII pixel maps to PNG via Pillow.
- Async status WebSocket input pump for buttons and wheel.

## Wednesday Frogs

See `docs/specs/2026-09-08-wednesday-frogs-design.md`.

## Cursor Token Pet

### Character

Hybrid glutton + budget guard. Eats spend deltas, fattens within a billing cycle, panics near account limits (75% / 90%).

### Evolution

- Alignment (7-day window): `(personal - work) / (personal + work)` in [-1, +1].
- Infinite levels: `xp_to_next(level) = base * growth^level`.
- Metamorphosis every 5 levels. Branch from alignment: light (>0.2), dark (<-0.2), gray otherwise. Branch locked for the tier, re-evaluated next metamorphosis (redemption/fall).
- Drawn base bodies for early tiers. From tier 5+, accumulate deterministic traits from branch pools (seeded).
- Dominant model over 7 days adds an accessory.

### Genesis

First launch rolls seed-derived: name, temperament, innate alignment bias, favorite model (x1.2 XP), body pattern. `--reroll` with confirmation.

### HUD

Top strip: name, LVL, branch glyph, XP bar, favorite model. Bottom: work/personal limit gauges + alignment slider. Wheel pages: pet, today spend, model mix, evolution/achievements log. Button pets the creature.

### Data

Undocumented Cursor dashboard API (`GetCurrentPeriodUsage`, `GetAggregatedUsageEvents`) with bearer token from local Cursor SQLite. Local collector on pet host machine. Reporter on the other machine POSTs JSON over LAN every 5 minutes.

### Reliability

Atomic saves + backup rotation. Billing-cycle rollover detection (spend decrease). launchd agents. Optional Telegram notifications for metamorphosis and achievements.
