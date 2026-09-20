# R1 Assistant Phase 0 Design

Date: 2026-09-19

## Goal

Prove the Rabbit R1 creation can reach our backend over HTTPS, receive hardware events, and obtain a microphone, before any Todoist or Calendar logic.

Later phases reuse this skeleton. They do not replace the hosting path.

## Pieces

- FastAPI app in `services/assistant/` (Heroku app name `toy-lair-assistant`).
- Creation files in `rabbit/assistant/`, served at `/creation/`.
- `GET /health` → `{"status":"ok"}`.
- Shared secret header `X-Assistant-Token` on `/api/*` (not on `/health` or `/creation/*`).

## Creation hello screen

Viewport 240x282, dark UI.

1. Show connection state: token present, `/health` ok, last hardware event.
2. First tap on the screen requests `getUserMedia({audio:true})`.
3. `longPressStart` starts `MediaRecorder`. `longPressEnd` stops and `POST /api/voice`.
4. Log `scrollUp`, `scrollDown`, `sideClick` on screen.

This is the risk gate: Flutter WebView, HTTPS mic, PTT, codec. If a codec fails, the hello screen reports the `MediaRecorder` MIME it actually got.

## Voice v1

Hold PTT → audio blob → `POST /api/voice` (multipart) → STT → agent → `{transcript, reply, audio_base64}`. WebView plays the audio. No WebRTC in v1.

## Hosting

One Heroku Basic dyno serves the creation and the API so the origin is HTTPS. Procfile:

```
web: uvicorn toy_lair_assistant.main:app --host 0.0.0.0 --port ${PORT}
```

Python 3.12. Config vars only, no secrets in git.

## Out of scope for the hello gate (implemented in later phases, same app)

- Phase 1: Todoist v1 + Google Calendar clients, Telegram text bot, agent tools.
- Phase 2: Today list UI. Superseded by Talk home: [2026-09-19-r1-talk-home-design.md](2026-09-19-r1-talk-home-design.md). Wheel opens a peek. `sideClick` does not complete a task.
- Phase 3: Scheduler, reminder dedup, morning briefing to Telegram.
- Phase 4: Read-only Zayka search/read.

## Test plan

- `GET /health` is 200.
- `GET /creation/index.html` is 200 and mentions 240x282.
- `POST /api/voice` without token is 401.
- `POST /api/voice` with token and a fake speech backend returns transcript + reply.
