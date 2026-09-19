# Flipper Zero

Handheld multi-tool. In this repo it is a **Wi-Fi remote** for Wednesday Frogs on the BUSY Bar. Scripts live in `flipper/busybar_remote/`.

Official JS docs: [engine](https://developer.flipper.net/flipperzero/doxygen/js_about_js_engine.html), [modules](https://developer.flipper.net/flipperzero/doxygen/js_using_js_modules.html), [SDK](https://developer.flipper.net/flipperzero/doxygen/js_developing_apps_using_js_sdk.html). Snapshots in [refs/](refs/).

## Hardware and limits

| Surface | Spec |
|---------|------|
| Display | 128x64 monochrome, drawn via `gui` |
| JS engine | mJS, <50k flash, <2k RAM for the engine |
| Storage | microSD. Scripts: `SD:/apps/Scripts/` |
| Radio | Sub-GHz, NFC, RFID, IR, iButton, GPIO, USB HID |
| This repo | JS only (no compiled FAP) |

mJS is not a browser. No `fetch`, no `Promise` in the official engine the way Node/browser JS works. Use `require("serial")`, `require("gui")`, `require("storage")`, `require("event_loop")`, and firmware JS modules. Load only the modules you need.

Firmware note: current scripts use official-style modules (`event_loop`, `gui/submenu`, `storage`, `serial`). They should run on official firmware and on Momentum. Momentum extras (`doesSdkSupport`, extra modules) are not used. Confirm the installed firmware before adding Momentum-only APIs.

## Role vs BUSY Bar

Flipper and the bar are both USB gadgets. They cannot talk USB-to-USB through a Mac host in this setup. Path:

1. Mac installs frogs onto the bar (USB or LAN).
2. Bar HTTP API is enabled on Wi-Fi with a password.
3. Flipper Wi-Fi Dev Board runs [FlipperHTTP](https://github.com/jblanked/FlipperHTTP).
4. `make flipper-export BAR_IP=... BAR_TOKEN=...` writes `flipper/out/`.
5. Copy `busybar_frogs.js`, `flipper_http.js`, `busybar_frogs.conf.json` to `SD:/apps/Scripts/`.

Flipper has no weekday clock in this script, so happy/sad is a manual menu choice.

## Pitfalls

- Config JSON contains the bar API password. `flipper/out/` is gitignored.
- A 409 from the bar means a BUSY/CUSTOM session holds the display.
- `eval` of `flipper_http.js` is how the script loads HTTP helpers. Keep that file next to the app on the SD card.
