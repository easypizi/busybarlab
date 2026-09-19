from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from toy_lair_assistant.auth import require_token
from toy_lair_assistant.clock import Clock
from toy_lair_assistant.install_qr import creation_url, qr_svg
from toy_lair_assistant.paths import creation_dir
from toy_lair_assistant.settings import Settings
from toy_lair_assistant.ticker import run_periodic
from toy_lair_assistant.zayka_sync import attach_zayka


@dataclass
class AppDeps:
    settings: Settings
    clock: Clock
    todoist: Any = None
    calendar: Any = None
    speech: Any = None
    agent: Any = None
    store: Any = None
    zayka: Any = None
    notify: Any = None


def create_app(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    todoist: Any = None,
    calendar: Any = None,
    speech: Any = None,
    agent: Any = None,
    store: Any = None,
    zayka: Any = None,
    notify: Any = None,
) -> FastAPI:
    settings = settings or Settings()
    deps = AppDeps(
        settings=settings,
        clock=clock or Clock(settings.timezone),
        todoist=todoist,
        calendar=calendar,
        speech=speech,
        agent=agent,
        store=store,
        zayka=zayka,
        notify=notify,
    )
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks: list[asyncio.Task[None]] = []
        if deps.settings.tick_interval_seconds > 0:

            def _tick() -> None:
                scheduler = getattr(app.state, "scheduler", None)
                if scheduler is None:
                    return
                scheduler.tick(deps.clock.now())

            tasks.append(
                asyncio.create_task(
                    run_periodic(_tick, deps.settings.tick_interval_seconds)
                )
            )
        if deps.settings.zayka_dir and deps.settings.zayka_sync_interval_seconds > 0:
            tasks.append(
                asyncio.create_task(
                    run_periodic(
                        lambda: attach_zayka(deps),
                        deps.settings.zayka_sync_interval_seconds,
                    )
                )
            )
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="toy_lair assistant", lifespan=lifespan)
    app.state.deps = deps

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    def _guard(token: str | None) -> None:
        require_token(deps.settings, token)

    @app.get("/api/today")
    def today(x_assistant_token: str | None = Header(default=None)) -> dict[str, Any]:
        _guard(x_assistant_token)
        if deps.agent is None:
            raise HTTPException(status_code=503, detail="agent is not configured")
        return deps.agent.today_payload(deps.clock.now())

    @app.post("/api/voice")
    async def voice(
        x_assistant_token: str | None = Header(default=None),
        audio: UploadFile = File(...),
    ) -> dict[str, Any]:
        _guard(x_assistant_token)
        if deps.speech is None or deps.agent is None:
            raise HTTPException(status_code=503, detail="voice is not configured")
        data = await audio.read()
        transcript = deps.speech.transcribe(data, audio.content_type or "audio/webm")
        result = deps.agent.handle_text(transcript, channel="r1")
        audio_b64 = deps.speech.speak(result.reply)
        return {
            "transcript": transcript,
            "reply": result.reply,
            "audio_base64": audio_b64,
        }

    @app.post("/api/text")
    def text(
        payload: dict[str, Any],
        x_assistant_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _guard(x_assistant_token)
        if deps.agent is None:
            raise HTTPException(status_code=503, detail="agent is not configured")
        message = str(payload.get("text") or "").strip()
        result = deps.agent.handle_text(message, channel="r1")
        return {"reply": result.reply}

    @app.post("/api/tasks/{task_id}/complete")
    def complete_task(
        task_id: str,
        x_assistant_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _guard(x_assistant_token)
        if deps.todoist is None:
            raise HTTPException(status_code=503, detail="todoist is not configured")
        deps.todoist.complete(task_id)
        return {"ok": True, "id": task_id}

    @app.post("/telegram/webhook")
    def telegram_webhook(update: dict[str, Any]) -> dict[str, bool]:
        if deps.agent is None or deps.notify is None:
            raise HTTPException(status_code=503, detail="telegram is not configured")
        deps.notify.handle_update(update, deps.agent, deps.speech)
        return {"ok": True}

    @app.get("/api/install-qr.svg")
    def install_qr_svg(
        request: Request,
        x_assistant_token: str | None = Header(default=None),
    ) -> Response:
        _guard(x_assistant_token)
        base = deps.settings.public_base_url.strip() or str(request.base_url)
        url = creation_url(base, deps.settings.assistant_api_token)
        return Response(content=qr_svg(url), media_type="image/svg+xml")

    @app.post("/internal/tick")
    def tick(x_assistant_token: str | None = Header(default=None)) -> dict[str, Any]:
        _guard(x_assistant_token)
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler is None:
            raise HTTPException(status_code=503, detail="scheduler is not configured")
        sent = scheduler.tick(deps.clock.now())
        return {"sent": sent}

    static = creation_dir()
    if static.exists():
        app.mount("/creation", StaticFiles(directory=static, html=True), name="creation")

    return app


app = create_app()
