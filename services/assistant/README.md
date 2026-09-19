# toy_lair assistant

FastAPI backend for the Rabbit R1 creation and Telegram. Hosted as Heroku app `toy-lair-assistant`.

## Local

From the repo root:

```bash
uv pip install --python .venv/bin/python -r services/assistant/requirements.txt
cp services/assistant/.env.example services/assistant/.env
# fill tokens
.venv/bin/python -m pytest services/assistant/tests -q
.venv/bin/uvicorn toy_lair_assistant.factory:app --app-dir services/assistant --reload --port 8080
```

Open `http://127.0.0.1:8080/health` and `http://127.0.0.1:8080/creation/`. R1 mic needs HTTPS, so local browser hello works, the device does not.

## Heroku

Python buildpack with `APP_BASE=services/assistant` (or deploy from that folder). Procfile starts `toy_lair_assistant.factory:app`.

Config vars: see `.env.example`. Use Basic dyno so the webhook and `/internal/tick` do not sleep. Add Heroku Postgres and set `DATABASE_URL`. Point Telegram webhook at `https://<app>/telegram/webhook`. Hit `/internal/tick` every minute (Heroku Scheduler) with `X-Assistant-Token`.

Creation install: open `https://<app>/creation/install.html` and scan the QR on the r1.

Zayka: clone `easypizi/zayka` with a read-only deploy key into `ZAYKA_DIR`. Do not copy `40 Areas/sensitive`.

## Google OAuth (once)

Create a Desktop OAuth client. Exchange a refresh token locally, then store `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`.
