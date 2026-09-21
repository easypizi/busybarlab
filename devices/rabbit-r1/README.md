# Rabbit R1

Pocket AI companion. In this repo it is the voice front-end for the personal assistant (`rabbit/assistant/` + `services/assistant/`).

Official: [what is r1](https://www.rabbit.tech/support/article/what-is-rabbit-r1), [creations](https://www.rabbit.tech/support/article/how-to-use-r1-creations), [creations-sdk](https://github.com/rabbit-hmi-oss/creations-sdk). Snapshots in [refs/](refs/).

## Hardware and limits

| Surface | Spec |
|---------|------|
| SoC | MediaTek Helio P35 (MT6765), 8x Cortex-A53 @ 2.3 GHz, PowerVR GE8320 |
| RAM / storage | 4 GB / 128 GB, no microSD |
| OS | AOSP 13 |
| Display | 2.88" TFT touch, 60 Hz |
| Creation viewport | **240 x 282** CSS pixels, portrait WebView |
| Battery | 1000 mAh Li-Po, non-removable |
| Audio | 2 W speaker, dual mic |
| Radio | Wi-Fi 2.4 + 5 GHz, 4G LTE (no 5G), Bluetooth 5.0 |
| Camera | 8 MP rotating "eye", 1080p24 |
| Size / weight | 78 x 78 x 13 mm, 115 g |
| Inputs | touch, scroll wheel, side PTT |

Internet is required. Unlocked nano-SIM or phone hotspot works.

## Creations runtime

A creation is a **static HTTPS website** in a Flutter WebView.

Allowed:

- HTML/CSS/JS, Canvas 2D
- `window` events: `scrollUp`, `scrollDown`, `sideClick`, `longPressStart`, `longPressEnd`
- `CreationVoiceHandler.postMessage("start"|"stop")` for native STT (no `getUserMedia`)
- `window.onPluginMessage` for `{type: "sttStarted"}` then `{type: "sttEnded", transcript}`
- `window.creationStorage.plain` / `.secure` (values must be Base64)
- `PluginMessageHandler.postMessage` → `window.onPluginMessage` (Rabbit LLM / TTS, no our tools)
- `closeWebView.postMessage("")`

Not allowed / unreliable:

- WebGL
- `getUserMedia` in this WebView (hangs, no prompt, no error)
- inline `onclick` on dynamically injected HTML
- `touchstart` + `preventDefault` on `document.body` (breaks the on-screen keyboard)
- more than one creation at a time
- intern-generated creations cannot host a backend (our creation is self-hosted)

Install: host the site, open `install.html`, scan the QR from Creations → add via QR.

`PluginMessageHandler` with `useLLM: false` and `wantsR1Response: true` speaks our reply through the R1 speaker. `useLLM: true` would route to Rabbit's LLM, which has no Todoist/GCal tools. Tito talks to **our** FastAPI instead.

## Assistant constraints that follow from this

- Serve the creation from the same Heroku app (`https://…`) so pairing + API are same-origin.
- Voice: hold PTT → `CreationVoiceHandler` → `sttEnded` transcript → `POST /api/text` → speak reply via `PluginMessageHandler`. No WebRTC, no tap gate.
- No push into a creation. Proactive reminders go to Telegram.
- Touch targets should stay near 44 px. Dark high-contrast UI, accent `#FE5000`, 512px creation icon. No WebGL animations. PTT pulse uses `transform` and `opacity` only.

## Repo map

- UI: `rabbit/assistant/`
- Backend: `services/assistant/`
- Design: `docs/specs/2026-09-19-r1-assistant-phase0-design.md`
