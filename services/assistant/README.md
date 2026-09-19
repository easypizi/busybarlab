# toy_lair assistant

FastAPI backend for the Rabbit R1 creation and Telegram. Hosted as Heroku app `toy-lair-assistant`.

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

Config vars: see `.env.example`. Use Basic dyno so the webhook and the in-process ticker do not sleep. Add Heroku Postgres (`DATABASE_URL`). The app ticks every 60 seconds in process. `/internal/tick` is only for a manual check.

Creation install: open `https://<app>/creation/install.html?token=<ASSISTANT_API_TOKEN>` and scan the QR on the r1. The QR is generated on this server (`/api/install-qr.svg`).

Zayka: set `ZAYKA_DIR` and `ZAYKA_REPO_URL=https://<fine-grained-pat>@github.com/easypizi/zayka.git`. The vault is cloned on boot and pulled every hour. Do not index `40 Areas/sensitive`.

## Google OAuth (once)

Create a Desktop OAuth client. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`, then run `python -m toy_lair_assistant.google_auth` from `services/assistant`. Store the printed `GOOGLE_REFRESH_TOKEN`. Publish the OAuth consent screen (Testing refresh tokens expire after 7 days).
