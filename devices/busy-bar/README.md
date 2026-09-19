# BUSY Bar

Programmable dual-display desk bar. In this repo it runs Wednesday Frogs (front RGB) and Cursor Token Pet (back OLED).

Official docs: [tech specs](https://docs.busy.app/bar/tech-specs), [HTTP API](https://docs.busy.app/bar/dev/http-api), [busylib](https://pypi.org/project/busylib/). Local firmware docs: `http://10.0.4.20/docs` when the bar is on USB. Offline snapshots live in [refs/](refs/).

## Hardware and limits

| Surface | Spec |
|---------|------|
| Front | 72x16 RGB LED matrix, 60 Hz, 158.4 x 35.2 mm, pitch 2.2 mm |
| Back | 160x80 monochrome OLED, 16 greys, 1.54", SSD1320 |
| MCU | STM32U595 (Cortex-M33 @ 160 MHz), 2 MB flash, 2.5 MB SRAM |
| Wireless MCU | SiWx917, Wi-Fi 6 **2.4 GHz only**, BLE 5.4 |
| Storage | 8 GB eMMC |
| Speaker | mono, 0.8 W |
| Battery | 3250 mAh 18650 |
| USB-C | virtual LAN + charging, USB 2.0 FS (12 Mbit/s) |
| Size / weight | 55.2 x 168.6 x 40.8 mm, 250 g |
| Inputs | start/pause, mode slider, scroll wheel, back |

- Asset upload cap: 255 KB per file (`POST /api/assets/upload`).
- Elements drawn outside 72x16 (front) or 160x80 (back) are simply invisible.
- `busylib>=2.1` is the Python client used here (`busybar/common/backend.py`).
- HTTP 409: a BUSY/CUSTOM session owns the display. Clear that session first.

## Network and auth

| Path | Base URL | Auth |
|------|----------|------|
| USB | `http://10.0.4.20/api` | none |
| Wi-Fi LAN | `http://<bar-lan-ip>/api` | header `X-API-Token` (password set in Network → HTTP API) |
| Cloud | `https://api.busy.app/busybar` | `Authorization: Bearer <account token>` |

Wi-Fi HTTP API is off by default. Enable it from the USB web UI at `http://10.0.4.20`.

Capabilities used here: `display/draw`, `assets/upload`, `assets/delete`, `display/clear`, WebSocket input events (buttons, wheel). Also available: audio, timer/BUSY mode, files, firmware, Matter.

## Repo map

- Package: `busybar/` (`common`, `wednesday_frogs`, `cursor_pet`)
- Flipper remote: `flipper/busybar_remote/`
- Specs: `docs/specs/2026-09-08-wednesday-frogs-design.md`, `docs/specs/2026-09-08-cursor-token-pet-design.md`

## Pitfalls from this repo

- macOS 15+ Local Network permission is **per app**. `curl` can reach `10.0.4.20` while the terminal's Python cannot. Enable the terminal (or Cursor) under System Settings → Privacy & Security → Local Network.
- The mode slider cannot launch custom Python apps. Install via USB/LAN, then disconnect.
- Flipper cannot talk to the bar over USB (both are USB devices). Use FlipperHTTP over Wi-Fi after a one-time Mac install.
- `make flipper-export` writes `flipper/out/` with the Wi-Fi API password. That directory is gitignored.

## OpenAPI snapshot

The bar was not on USB when this note was written (`http://10.0.4.20/docs` timed out). Re-fetch when it is plugged in:

```bash
curl -fsS http://10.0.4.20/docs/openapi.json -o devices/busy-bar/refs/openapi.json
```

Public reference: `https://api.busy.app/busybar/docs` (pick firmware version).
