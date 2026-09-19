# Flipper JS engine notes

Source: https://developer.flipper.net/flipperzero/doxygen/js_about_js_engine.html (fetched 2026-09-19)

- Engine: mJS, aimed at microcontrollers.
- Budget: <50k flash, <2k RAM for the engine itself.
- Launch: Apps → Scripts, no PC compile step.
- Limitations vs browser JS: see mJS on GitHub. Do not assume ES6 modules, fetch, or large heaps.
- Modules are C/C++ FALs on the SD card. `require()` loads them into RAM. Unused modules stay unloaded.
- Official SDK npm package: `@flipperdevices/fz-sdk`. Momentum fork: `@next-flip/fz-sdk-mntm`.
- Minifier exists in the SDK. Keep it off while debugging.

Modules used by `busybar_frogs.js`: `event_loop`, `gui`, `gui/submenu`, `gui/dialog`, `gui/loading`, `storage`. `flipper_http.js` uses `serial` to talk to the Wi-Fi Dev Board.
