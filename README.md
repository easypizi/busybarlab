# BUSY Bar Lab

Python playground for [BUSY Bar](https://docs.busy.app/) custom apps via `busylib`.

## Setup

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
```

USB default address: `10.0.4.20`.

## Wednesday Frogs

The mode slider cannot start this app. After you switch away, run a shortcut from the repo root.

```bash
make frogs          # install looping frogs (auto happy/sad)
make frogs-happy
make frogs-sad
make frogs-clear
make frogs-bake     # bake .anim files only
make               # list targets
```

Extra flags: `make frogs FROGS_ARGS='--address 10.0.4.20 --token x'`.

### One-shot install (recommended, no local daemon)

Bake a looping `.anim`, upload once, bar plays it onboard. `make frogs` is the same as:

```bash
# Bake only (no device)
.venv/bin/python -m apps.wednesday_frogs.install --bake-only

# Install over USB (Mac can disconnect after this)
.venv/bin/python -m apps.wednesday_frogs.install

# Force happy / sad, or clear
.venv/bin/python -m apps.wednesday_frogs.install --mode happy
.venv/bin/python -m apps.wednesday_frogs.install --clear
```

`auto` mode: green frogs + "IT'S WEDNESDAY MY DUDES" on Wednesdays, gray/sad otherwise.

### Live host animation (old FPS loop)

```bash
# Terminal simulator
.venv/bin/python -m apps.wednesday_frogs --sim --seconds 10

# Live device over USB
.venv/bin/python -m apps.wednesday_frogs --fps 10
```

Flags: `--token`, `--text-interval`, `--frogs`, `--fps`, `--skip-check`.

### If curl works but Python says "No route to host"

On macOS 15+, Local Network permission is per app. `curl` is allowed, but Python inherits the terminal's permission.

1. System Settings → Privacy & Security → Local Network
2. Enable your terminal (Terminal / iTerm / Ghostty / Warp), quit and reopen it
3. If missing from the list, run from that terminal:
   `python3 -c "import socket; socket.create_connection(('10.0.4.20', 80), 3)"`
   and click Allow
4. Retry `.venv/bin/python -m apps.wednesday_frogs.install`
## Cursor Token Pet

### Dual-account auth (recommended)

Cursor keeps only one session per machine. Export both tokens into one local file, then the pet daemon polls work and personal itself (no reporter required).

On the **personal** machine (this one, if logged into personal):

```bash
.venv/bin/python -m apps.cursor_pet.export_token --account personal --verify
```

On the **work** machine:

```bash
# clone/copy busybarlab, create venv, then:
.venv/bin/python -m apps.cursor_pet.export_token --account work --verify --out /tmp/cursor_tokens_work.json
```

Merge into one `data/cursor_tokens.json` on the pet-daemon host (or copy the work token block into the existing file). The file is gitignored and saved `chmod 600`.

Then run the daemon:

```bash
.venv/bin/python -m apps.cursor_pet --address 10.0.4.20
# or simulator
.venv/bin/python -m apps.cursor_pet --sim --seconds 8
```

If `data/cursor_tokens.json` has both accounts, both are polled every `--poll-seconds` (default 300).

Re-export when Cursor refreshes the session and polls start failing with 401.

### Fallback: reporter on second machine

If you prefer not to store both tokens on one disk:

```bash
.venv/bin/python -m apps.cursor_pet --local-account personal --address 10.0.4.20
# other machine:
.venv/bin/python -m apps.cursor_pet.reporter --account work --daemon http://<pet-host>:8765
```

### Demo / genesis

```bash
.venv/bin/python -m apps.cursor_pet --sim --no-collector --demo-feed 500 --demo-account personal --seconds 8 --reroll --yes
```

Optional Telegram: set `BUSYBAR_TG_BOT_TOKEN` and `BUSYBAR_TG_CHAT_ID`.

launchd:

```bash
LOCAL_ACCOUNT=personal BUSYBAR_ADDRESS=10.0.4.20 ./deploy/launchd/install.sh daemon
# reporter only if not using dual-token file:
ACCOUNT=work DAEMON_URL=http://192.168.x.x:8765 ./deploy/launchd/install.sh reporter
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```
