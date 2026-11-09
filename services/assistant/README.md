# Tito assistant

Tito is a laid-back Californian butler for Todoist and Google Calendar. FastAPI backend for the Rabbit R1 creation and Telegram. Hosted as Heroku app `toy-lair-assistant` at `https://toy-lair-assistant-e9003db7d945.herokuapp.com`.

## Local

From the repo root:

```bash
uv pip install --python .venv/bin/python -r services/assistant/requirements.txt
cp services/assistant/.env.example services/assistant/.env
# fill tokens
.venv/bin/python -m toy_lair_assistant.google_auth --app-dir services/assistant
# or: cd services/assistant && ../../.venv/bin/python -m toy_lair_assistant.google_auth
make test-assistant
.venv/bin/uvicorn toy_lair_assistant.factory:app --app-dir services/assistant --reload --port 8080
```

Open `http://127.0.0.1:8080/health` and `http://127.0.0.1:8080/creation/`. R1 mic needs HTTPS, so local browser hello works, the device does not.

## Heroku

Python 3.12 via `.python-version`. Buildpacks: `lstoll/heroku-buildpack-monorepo` then `heroku/python`, with `APP_BASE=services/assistant`. Procfile starts `toy_lair_assistant.factory:app`.

Config vars: see `.env.example`. Use Basic dyno so the webhook and the in-process ticker do not sleep. Add Heroku Postgres (`DATABASE_URL`). The app ticks every 60 seconds in process. `/internal/tick` is only for a manual check. `/creation/*` is served with `Cache-Control: no-cache`, so after a deploy close and reopen Tito. The install QR points at `/creation/v2/` so a stuck WebView cache can be broken by one rescan.

Creation install (Heroku is the main path):

1. Open `https://<app>/creation/install.html?token=<ASSISTANT_API_TOKEN>`.
2. On the r1: Creations → add via QR. Scan `/api/install-qr.png` (black-on-white PNG with a quiet zone). The payload URL is `https://<app>/creation/v2/` unless `CREATION_PUBLIC_URL` is set. `iconUrl` is `https://<app>/i.png` (same file as `/creation/icon.png`).
3. The creation shows a 4-digit pair code. Type it on the install page and press approve.
4. The r1 stores the token in `creationStorage.secure` (and plain/local as fallback). After pairing, the screen is Talk home: hold PTT or the orange circle to talk, wheel opens today's peek. Mic, recorder, and clip steps go to `POST /api/client-log` (Heroku logs as `r1 client event=`). Long replies shrink and scroll with the wheel. Planning hours default to 10:00–22:00 including weekends (`PLAN_*` in `.env.example`). R1 speaks one or two sentences. A long schedule answer sends a card to Telegram instead of the spoken paragraph.

The Telegram bot is Ostanovka, one chat for Tito and Paco. Each agent signs the first line of its own messages. Address Tito with `Tito, ...`, `/tito`, `/today`, `/week`, `/plan`, or by replying to a Tito message. Address Paco with `Paco, ...`, `/paco`, or by replying to a Paco message. A message with no name gets Tito / Paco buttons. `/today` and the 8:00 briefing are a day schedule. Timed tasks and events sit on the timeline. Untimed tasks get a suggested slot (`~`) or land in Anytime. Recurring rituals without a time go to Anytime. `/week` groups by day and puts recurring items under Rituals. `/plan` takes one task per line, proposes times with a 15-minute buffer, a 30-minute break after 3 hours, a 4-hour load cap, and weekday work hours 09:00–17:00 (sport and errands after 17:00). Apply writes matched Todoist tasks or creates the missing ones. `🔁 Reshuffle` and `📅 Tomorrow` rebuild the same list. Nothing is written without Apply. Agent replies about a day or week get the same card. Short replies still get 👍👎. Task reminders get Done / +1h / Tomorrow. Bot API cannot set the avatar. In @BotFather run `/setuserpic` and upload `rabbit/cast/ostanovka.png`.

Carlos is a third creation on the same app: the day card for the Survivor Body cycle. Install it from `https://<app>/creation/carlos/install.html?token=<ASSISTANT_API_TOKEN>`. The QR payload is `https://<app>/creation/carlos/v2/` and the icon is `https://<app>/carlos.png`. Hold PTT logs the session through `POST /api/carlos/log`. The OpenAI key stays on the server. Rows live in `workout_logs`.

Paco is a second creation on the same app for the Zayka vault. Install it from `https://<app>/creation/paco/install.html?token=<ASSISTANT_API_TOKEN>`. The QR payload is `https://<app>/creation/paco/v2/` and the icon is `https://<app>/paco.png`. `CREATION_PUBLIC_URL` does not change that URL. Hold PTT uses the r1's own speech. `POST /api/paco/text` does not call Whisper or `gpt-4o-mini-tts`. Paco can add a fleeting note under `00 Inbox/` or append today's daily note, then `git push`. That push needs a write-capable `ZAYKA_REPO_URL`. This repo does not rotate the live deploy key.

Tito never deletes Todoist tasks. Close or reschedule them. Timed tasks sync one way into a Google calendar named `Tito` (`TASK_SYNC_INTERVAL_SECONDS`, override with `GOOGLE_TASKS_CALENDAR_ID`). Free slots and `/today` read every selected calendar (`GOOGLE_READ_CALENDARS=all`). Task mirrors stay out of the catalog. Reminders use due time (`TASK_LEAD_MINUTES`), deadline (`DEADLINE_LEAD_DAYS`), and the `remind` label (`REMIND_NUDGE_HOURS`).

GitHub Pages is optional, if you want a non-herokuapp.com origin. The `pages` workflow publishes `rabbit/assistant`. Then set `CREATION_PUBLIC_URL=https://easypizi.github.io/toy_lair/` and CORS allows that origin.

`/api/pair/start` and `/api/pair/claim` are unauthenticated. `/api/pair/approve` requires `X-Assistant-Token`. Live pairing sessions expire after 10 minutes (max 20 at once).

Zayka: set `ZAYKA_DIR`, `ZAYKA_SYNC_ENABLED=true`, and `ZAYKA_REPO_URL=https://<fine-grained-pat>@github.com/easypizi/zayka.git`. The vault is cloned on boot and pulled every hour. Tests skip that pull. Do not index `40 Areas/sensitive`. Paco pushes notes, so that token needs write access to `easypizi/zayka`. When the token expires, Telegram gets one message that day: `Zayka GitHub token expired. Update ZAYKA_REPO_URL.` A failed save on the r1 says the same thing. A failed push also sends the note text to Telegram, because the dyno clone does not survive a restart. The local vault updates through the `app.toy_lair.zayka-pull` LaunchAgent (`deploy/launchd/install.sh zayka-pull`). macOS blocks `/bin/bash` from `~/Documents`, so that installer builds a signed helper and the agent runs the pull through it.

## Ivanity Fair

Daily English B/W A4 newspaper. Built at 07:00 PT (`GAZETA_HOUR`) and on `/gazeta`, sent to Ostanovka as a PDF and to Gmail. With `GAZETA_PRINTER_EMAIL` set (an HP ePrint address), the PDF in Ostanovka gets a 🖨 Print button that mails it to the printer. Needs `OPENAI_API_KEY` and `TODOIST_API_TOKEN`. Email needs `GMAIL_USER` and `GMAIL_APP_PASSWORD` (also used for the inbox read). `GAZETA_MODEL` defaults to `OPENAI_MODEL`, use a stronger model for the editor. Manual run without delivery: `python -m toy_lair_assistant.gazeta --out issue.pdf`. Layout preview without any API: `PYTHONPATH=. python -c "from toy_lair_assistant.gazeta.layout import sample, render; open('p.pdf','wb').write(render.render(sample.sample_view())[0])"`.

Rendering uses Playwright Chromium. After `pip install -r requirements.txt` run `playwright install chromium`. On Heroku (stack heroku-24) the `Aptfile` carries the Chromium libraries and `bin/post_compile` installs Chromium into the slug. Set config var `PLAYWRIGHT_BROWSERS_PATH=0` so runtime finds it, plus `GMAIL_USER`, `GMAIL_APP_PASSWORD` and `GAZETA_MODEL`. Dyno is Basic (512 MB), watch for R14 on the first run.

## Google OAuth (once)

Create a Desktop OAuth client. Keep Audience in **Testing**, add your Gmail as a test user. Do not publish: Calendar is a sensitive scope and unverified production returns 403. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`, then run `python -m toy_lair_assistant.google_auth` from `services/assistant`. Store the printed `GOOGLE_REFRESH_TOKEN`. Testing refresh tokens expire after 7 days. When they die, Telegram gets one `Calendar auth expired` message that day.

## Library and collector

Paco searches a personal library: saved Instagram posts, Telegram links, starred Gmail, the Chrome reading list, links sent to the bot, and Zayka notes. Heroku keeps the index (`library_items`, `collector_jobs` in Postgres). A collector on the Mac fetches and enriches, writes notes to Zayka, and pushes rows. Sessions and passwords stay in the Mac Keychain. The Mac opens no inbound port.

Heroku: set `COLLECTOR_TOKEN` (long random string). `/api/library/items`, `/api/collector/jobs`, `/api/collector/jobs/{id}/done`, `/api/collector/event` take `Authorization: Bearer <COLLECTOR_TOKEN>`. Alerts reach Telegram once per day per source.

Mac setup, from the repo root:

```bash
uv pip install --python .venv/bin/python -r services/assistant/requirements-collector.txt
brew install ffmpeg
cd services/assistant
../../.venv/bin/python -m toy_lair_assistant.collector auth openai_api_key
../../.venv/bin/python -m toy_lair_assistant.collector auth collector_token
../../.venv/bin/python -m toy_lair_assistant.collector auth gmail_app_password
../../.venv/bin/python -m toy_lair_assistant.collector auth instagram
../../.venv/bin/python -m toy_lair_assistant.collector auth telegram
```

Config goes in `~/Library/Application Support/toy_lair/collector.json`: `gmail_user`, `instagram_user`, `telegram_allowlist` (chat ids or usernames), optional `gmail_query`, `per_run_limit`, `vault_dir`, `chrome_profile`, `heroku_url`. Sources without credentials are skipped. Then `collector run` for one pass, `collector backfill` to drain a backlog, and `deploy/launchd/install.sh collector` for the agent. The agent runs `poll` every 5 minutes: it serves queued jobs (`/sync`, links sent to the bot), then runs the full pass once a day after 04:00 local, or every 2 hours while a backlog remains. A sleeping Mac catches up on wake.

Telegram: `/sync [source]`, `/sources`. Send a link or forward a post with no name and Paco files it. Instagram uses a session (not an official API), caps each run at `per_run_limit` posts, pauses between posts, and stops without retrying on a checkpoint. Telegram reading uses your user session through Telethon, only for chats in the allowlist. Chrome Read Later is read from a copy of `Default/Sync Data/LevelDB`.
