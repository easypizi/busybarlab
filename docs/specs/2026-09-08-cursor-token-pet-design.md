# Cursor Token Pet Design

Date: 2026-09-08

## Goal

Evolving OLED pet on BUSY Bar back display (160x80), fed by Cursor token spend from work (dark) and personal (light) accounts.

## Data

- Local Cursor SQLite: `cursorAuth/accessToken` in `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
- Dashboard API: `GetCurrentPeriodUsage`, `GetAggregatedUsageEvents` on `api2.cursor.sh`
- Verified live on this machine (personal account).

## Architecture

- Pet daemon: local collector + HTTP `/report` listener + draw loop
- Reporter on second machine POSTs snapshots every 5 minutes
- Shared `busybar/common` backends (`--sim` supported)

## Evolution

Infinite levels, metamorphosis every 5 levels, branch from 7-day alignment, trait accumulation, model accessories, genesis roll, HUD pages, achievements, Telegram optional, launchd agents.
