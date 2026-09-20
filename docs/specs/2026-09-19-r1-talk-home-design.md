# R1 Talk home

Date: 2026-09-19

Replaces the phase 0 "today list is the screen" idea. Voice is the product. The list is a peek.

## Screen (240x282)

- Title `toy lair`, status, today count, last reply, rec circle.
- Hint: `hold PTT talk · wheel today`.
- `#peek` is hidden until the wheel or a PTT click. Click no longer completes tasks.
- Pairing code stays on first launch. Token is written to secure, plain, and local storage after the Flutter bridge appears.

## Voice

1. `longPressStart` requests `getUserMedia` and starts `MediaRecorder`.
2. `longPressEnd` sends `POST /api/voice`.
3. If the WebView blocks mic on PTT, `#tap-gate` says `tap once for mic`. One tap arms the session.
4. STT or agent errors come back as a one-line `reply`. Status 200, not a blank screen.

## Agent

System prompt includes date, time, timezone, and today's tasks/events as `t1`/`e1`. The model uses those indexes. The server maps them to real ids.

Tool calls loop up to 3 rounds. Last 6 user/assistant turns per channel (`r1`, `telegram`) live 15 minutes in the store.

Delete event (and more than one complete in one turn) needs a confirm word: yes, confirm, да, ok.

## Hardware

| Input | Action |
|-------|--------|
| Hold PTT | Record, release to send |
| PTT click | Toggle today peek |
| Wheel | Open peek, then move the selection |

See also [2026-09-19-r1-assistant-phase0-design.md](2026-09-19-r1-assistant-phase0-design.md). Phase 2 "sideClick completes a task" is obsolete.
