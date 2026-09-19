# toy_lair assistant

FastAPI backend for the Rabbit R1 creation and Telegram. Hosted as Heroku app `toy-lair-assistant` at `https://toy-lair-assistant-e9003db7d945.herokuapp.com`.

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

Creation install:

Rabbit's scanner rejects `herokuapp.com` hosts (none of the public gallery creations use it). Host the creation on GitHub Pages.

1. Repo Settings → Pages → Source: GitHub Actions. Push once so the `pages` workflow publishes `rabbit/assistant`.
2. Set `CREATION_PUBLIC_URL=https://easypizi.github.io/busybarlab/` on Heroku.
3. Open `https://<app>/creation/install.html?token=<ASSISTANT_API_TOKEN>`.
4. On the r1: Creations → add via QR, scan the QR. The page shows `/api/install-qr.png`: a square black-on-white PNG with a quiet zone. The old SVG had no background and used stroke paths, so cameras could not decode it. The payload URL is `CREATION_PUBLIC_URL` when set, otherwise `https://<app>/creation/`.
5. The creation shows a 4-digit pair code. Type it on the install page and press approve.
6. The r1 claims the token once and stores it in `creationStorage.secure`. API calls from Pages go to this Heroku app (CORS on the Pages origin).

`/api/pair/start` and `/api/pair/claim` are unauthenticated. `/api/pair/approve` requires `X-Assistant-Token`. Live pairing sessions expire after 10 minutes (max 20 at once).

Zayka: set `ZAYKA_DIR` and `ZAYKA_REPO_URL=https://<fine-grained-pat>@github.com/easypizi/zayka.git`. The vault is cloned on boot and pulled every hour. Do not index `40 Areas/sensitive`.

## Google OAuth (once)

Create a Desktop OAuth client. Keep Audience in **Testing**, add your Gmail as a test user. Do not publish: Calendar is a sensitive scope and unverified production returns 403. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`, then run `python -m toy_lair_assistant.google_auth` from `services/assistant`. Store the printed `GOOGLE_REFRESH_TOKEN`. Testing refresh tokens expire after 7 days.
