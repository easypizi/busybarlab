# toy_lair

Monorepo for pocket hardware: [BUSY Bar](devices/busy-bar/README.md), [Flipper Zero](devices/flipper-zero/README.md), and [Rabbit R1](devices/rabbit-r1/README.md).

Device limits, APIs, and known pitfalls live in `devices/`. Personal context for agents lives in the [Zayka](docs/zayka-data-source.md) Obsidian vault (read-only).

## Layout

```
busybar/                 Python package for the LED bar (was apps/)
flipper/busybar_remote/  Flipper JS remote for Wednesday Frogs
rabbit/assistant/        Rabbit R1 creation (voice UI)
services/assistant/      FastAPI agent: Todoist, Google Calendar, Telegram
devices/                 Hardware limits and SDK notes
docs/                    Specs and Zayka access rules
deploy/launchd/          macOS agents for Cursor Token Pet
```

## Setup

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
```

BUSY Bar USB default address: `10.0.4.20`.

```bash
make                # list targets
make test           # busybar pytest
```

## Devices

| Device | Role in this repo | Start here |
|--------|-------------------|------------|
| BUSY Bar | Front 72x16 RGB + back 160x80 grey apps | [devices/busy-bar](devices/busy-bar/README.md) |
| Flipper Zero | Wi-Fi remote for the bar (not USB-to-USB) | [devices/flipper-zero](devices/flipper-zero/README.md) |
| Rabbit R1 | Voice assistant creation, 240x282 WebView | [devices/rabbit-r1](devices/rabbit-r1/README.md) |

## Projects

### Wednesday Frogs (BUSY Bar)

The mode slider cannot start this app. After you switch away, run a shortcut from the repo root.

```bash
make frogs          # install looping frogs (auto happy/sad)
make frogs-happy
make frogs-sad
make frogs-clear
make frogs-bake     # bake .anim files only
```

Extra flags: `make frogs FROGS_ARGS='--address 10.0.4.20 --token x'`.

One-shot install (recommended, no local daemon). Bake a looping `.anim`, upload once, bar plays it onboard. `make frogs` is the same as:

```bash
.venv/bin/python -m busybar.wednesday_frogs.install --bake-only
.venv/bin/python -m busybar.wednesday_frogs.install
.venv/bin/python -m busybar.wednesday_frogs.install --mode happy
.venv/bin/python -m busybar.wednesday_frogs.install --clear
```

`auto` mode: green frogs + "IT'S WEDNESDAY MY DUDES" on Wednesdays, gray/sad otherwise.

Live host animation (old FPS loop):

```bash
.venv/bin/python -m busybar.wednesday_frogs --sim --seconds 10
.venv/bin/python -m busybar.wednesday_frogs --fps 10
```

Flags: `--token`, `--text-interval`, `--frogs`, `--fps`, `--skip-check`.

If curl works but Python says "No route to host", macOS 15+ Local Network permission is per app. Enable your terminal in System Settings → Privacy & Security → Local Network, quit and reopen it. If missing from the list, run:

```bash
python3 -c "import socket; socket.create_connection(('10.0.4.20', 80), 3)"
```

then retry the install command.

### Flipper remote

The slider cannot start this app. Flipper also cannot talk to the bar over USB (both are USB devices). Use Flipper as a Wi-Fi remote after a one-time Mac install.

1. Flash [FlipperHTTP](https://github.com/jblanked/FlipperHTTP) onto the Wi-Fi Dev Board and save Wi-Fi credentials in FlipperHTTP-App.
2. On the bar: `http://10.0.4.20` → Network → HTTP API → Set password and enable. Note the bar LAN IP (Settings → Wi-Fi).
3. Once from a Mac with USB or LAN:

```bash
make frogs
make flipper-export BAR_IP=192.168.1.50 BAR_TOKEN=your-wifi-api-password
```

4. Copy `flipper/out/busybar_frogs.js`, `flipper/out/flipper_http.js`, and `flipper/out/busybar_frogs.conf.json` to `SD:/apps/Scripts/`.
5. Flipper: Apps → Scripts → `busybar_frogs`. Menu: Frogs happy, Frogs sad, Clear, Ping board.

`flipper/out/` is gitignored because it contains the API password. Flipper has no weekday clock here, so happy/sad is a manual choice. A 409 from the bar means a BUSY/CUSTOM session is holding the display.

### Cursor Token Pet (BUSY Bar)

Dual-account auth (recommended). Cursor keeps only one session per machine. Export both tokens into one local file, then the pet daemon polls work and personal itself.

On the personal machine:

```bash
.venv/bin/python -m busybar.cursor_pet.export_token --account personal --verify
```

On the work machine:

```bash
.venv/bin/python -m busybar.cursor_pet.export_token --account work --verify --out /tmp/cursor_tokens_work.json
```

Merge into one `data/cursor_tokens.json` on the pet-daemon host. The file is gitignored and saved `chmod 600`.

```bash
.venv/bin/python -m busybar.cursor_pet --address 10.0.4.20
.venv/bin/python -m busybar.cursor_pet --sim --seconds 8
```

If `data/cursor_tokens.json` has both accounts, both are polled every `--poll-seconds` (default 300). Re-export when Cursor refreshes the session and polls start failing with 401.

Fallback reporter on a second machine:

```bash
.venv/bin/python -m busybar.cursor_pet --local-account personal --address 10.0.4.20
.venv/bin/python -m busybar.cursor_pet.reporter --account work --daemon http://<pet-host>:8765
```

Demo / genesis:

```bash
.venv/bin/python -m busybar.cursor_pet --sim --no-collector --demo-feed 500 --demo-account personal --seconds 8 --reroll --yes
```

Optional Telegram: set `BUSYBAR_TG_BOT_TOKEN` and `BUSYBAR_TG_CHAT_ID`.

launchd:

```bash
LOCAL_ACCOUNT=personal BUSYBAR_ADDRESS=10.0.4.20 ./deploy/launchd/install.sh daemon
ACCOUNT=work DAEMON_URL=http://192.168.x.x:8765 ./deploy/launchd/install.sh reporter
```

### Rabbit R1 assistant

Voice-first Tito butler for Todoist + Google Calendar, with Telegram reminders. It can add and edit tasks, book meetings, and after a confirm word plan timed tasks into Todoist (mirrored to a Tito calendar). Creation UI is Talk home in `rabbit/assistant/` (hold PTT). Backend is `services/assistant/` (Heroku app `toy-lair-assistant`).

```bash
cd services/assistant
# see services/assistant/README.md
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m pytest services/assistant/tests -q
```
