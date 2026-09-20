# R1 WebView quirks

Sources: rabbit-hmi-oss/creations-sdk plugin-demo, ShayneP/rabbit-r1-livekit-skill (2026).

- Viewport: 240x282, fixed.
- HTTPS required for microphone.
- No WebGL. Canvas 2D only.
- First mic access often needs a screen tap. Prefer requesting `getUserMedia` on `longPressStart`. If that fails, show a one-time tap gate, then PTT can record.
- `longPressStart` / `longPressEnd` on the side button are the PTT pair.
- `setMicrophoneEnabled()` is unreliable. Use `getUserMedia` then, if using WebRTC later, `publishTrack()`.
- Touch: bind `touchstart` on `document.body` and call `preventDefault()`.
- Storage values must be Base64. Secure store is hardware-encrypted (Android M+). Isolated per plugin id.
- Community voice apps tunnel HTTP to HTTPS (tunnelmole, Cloudflare, or a real host). Heroku provides HTTPS.
