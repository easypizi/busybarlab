from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from toy_lair_assistant.agent import invoke_agent
from toy_lair_assistant.auth import require_token
from toy_lair_assistant.clock import Clock
from toy_lair_assistant.install_qr import (
    creation_target_url,
    paco_icon_url,
    paco_page_url,
    paco_qr_png,
    paco_qr_svg,
    qr_png,
    qr_svg,
)
from toy_lair_assistant.pairing import Pairing, PairingFull
from toy_lair_assistant.paths import creation_dir, paco_dir
from toy_lair_assistant.settings import Settings
from toy_lair_assistant.ticker import run_periodic
from toy_lair_assistant.zayka_sync import attach_zayka
from toy_lair_assistant.zayka_token import alert_if_expired

LOG = logging.getLogger("toy_lair_assistant")


def _signed(notify: Any, who: str) -> Any:
    if notify is not None and hasattr(notify, "voice"):
        return notify.voice(who)
    return notify


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
    pairing: Pairing | None = None
    paco: Any = None


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
    pairing: Pairing | None = None,
    paco: Any = None,
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
        pairing=pairing or Pairing(settings.assistant_api_token),
        paco=paco,
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
        if (
            deps.settings.zayka_should_sync()
            and deps.settings.zayka_sync_interval_seconds > 0
        ):
            def _zayka_maintenance() -> None:
                attach_zayka(deps)
                if deps.store is None:
                    return
                import httpx

                alert_if_expired(
                    deps.settings,
                    deps.store,
                    _signed(deps.notify, "paco"),
                    deps.clock.now,
                    lambda url, headers: httpx.get(url, headers=headers, timeout=10),
                )

            tasks.append(
                asyncio.create_task(
                    run_periodic(
                        _zayka_maintenance,
                        deps.settings.zayka_sync_interval_seconds,
                    )
                )
            )
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="Tito assistant", lifespan=lifespan)
    app.state.deps = deps
    pages_origin = deps.settings.creation_origin()
    if pages_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[pages_origin],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def creation_no_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/creation"):
            response.headers["Cache-Control"] = "no-cache"
            response.headers["Permissions-Policy"] = "microphone=(self)"
        return response

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
        try:
            transcript = deps.speech.transcribe(data, audio.content_type or "audio/webm")
        except Exception as exc:
            return {"transcript": "", "reply": str(exc), "audio_base64": ""}
        try:
            result = invoke_agent(
                deps.agent, transcript, channel="r1", notify=_signed(deps.notify, "tito")
            )
        except Exception as exc:
            return {"transcript": transcript, "reply": str(exc), "audio_base64": ""}
        try:
            audio_b64 = deps.speech.speak(result.reply)
        except Exception:
            audio_b64 = ""
        return {
            "transcript": transcript,
            "reply": result.reply,
            "audio_base64": audio_b64,
        }

    @app.post("/api/client-log")
    def client_log(
        payload: dict[str, Any],
        x_assistant_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        _guard(x_assistant_token)
        event = payload.get("event")
        detail = payload.get("detail")
        print("r1 client event=%s detail=%s" % (event, detail), flush=True)
        LOG.info("r1 client event=%s detail=%s", event, detail)
        return {"ok": True}

    @app.post("/api/text")
    def text(
        payload: dict[str, Any],
        x_assistant_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _guard(x_assistant_token)
        if deps.agent is None:
            raise HTTPException(status_code=503, detail="agent is not configured")
        message = str(payload.get("text") or "").strip()
        result = invoke_agent(
            deps.agent, message, channel="r1", notify=_signed(deps.notify, "tito")
        )
        used = set(getattr(result, "used_tools", []) or [])
        action = "task" if used & {"todoist_add", "plan_apply"} else ""
        return {"reply": result.reply, "action": action}

    @app.post("/api/paco/text")
    def paco_text(
        payload: dict[str, Any],
        x_assistant_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _guard(x_assistant_token)
        if deps.paco is None:
            attach_zayka(deps)
        if deps.paco is None:
            raise HTTPException(status_code=503, detail="paco is not configured")
        message = str(payload.get("text") or "").strip()
        result = deps.paco.handle_text(message)
        return {
            "reply": result.reply,
            "peek": result.peek,
            "action": getattr(result, "action", "") or "",
        }

    @app.get("/api/paco/inbox")
    def paco_inbox(x_assistant_token: str | None = Header(default=None)) -> dict[str, Any]:
        _guard(x_assistant_token)
        if deps.paco is None:
            attach_zayka(deps)
        if deps.paco is None:
            raise HTTPException(status_code=503, detail="paco is not configured")
        return deps.paco.inbox_payload()

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
        if deps.notify is None:
            raise HTTPException(status_code=503, detail="telegram is not configured")
        if deps.paco is None:
            attach_zayka(deps)
        if deps.agent is None and deps.paco is None:
            raise HTTPException(status_code=503, detail="telegram is not configured")
        deps.notify.handle_update(update, deps.agent, deps.speech, paco=deps.paco)
        return {"ok": True}

    @app.post("/api/pair/start")
    def pair_start() -> dict[str, Any]:
        if deps.pairing is None:
            raise HTTPException(status_code=503, detail="pairing is not configured")
        try:
            return deps.pairing.start(deps.clock.now())
        except PairingFull:
            raise HTTPException(status_code=429, detail="too many pairing sessions")

    @app.post("/api/pair/approve")
    def pair_approve(
        payload: dict[str, Any],
        x_assistant_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        _guard(x_assistant_token)
        if deps.pairing is None:
            raise HTTPException(status_code=503, detail="pairing is not configured")
        code = str(payload.get("code") or "").strip()
        if not deps.pairing.approve(code, deps.clock.now()):
            raise HTTPException(status_code=404, detail="unknown pairing code")
        return {"ok": True}

    @app.get("/api/pair/claim")
    def pair_claim(secret: str = "") -> dict[str, str]:
        if deps.pairing is None:
            raise HTTPException(status_code=503, detail="pairing is not configured")
        result = deps.pairing.claim(secret, deps.clock.now())
        if result is None:
            raise HTTPException(status_code=404, detail="unknown pairing session")
        return result

    @app.get("/i.png")
    def short_icon() -> FileResponse:
        icon = creation_dir() / "icon.png"
        if not icon.exists():
            raise HTTPException(status_code=404, detail="icon is missing")
        return FileResponse(icon, media_type="image/png")

    @app.get("/tito.png")
    def tito_icon() -> FileResponse:
        icon = creation_dir() / "tito.png"
        if not icon.exists():
            raise HTTPException(status_code=404, detail="icon is missing")
        return FileResponse(icon, media_type="image/png")

    @app.get("/paco.png")
    def paco_icon() -> FileResponse:
        icon = paco_dir() / "paco.png"
        if not icon.exists():
            raise HTTPException(status_code=404, detail="icon is missing")
        return FileResponse(icon, media_type="image/png")

    @app.get("/api/paco/creation-url")
    def paco_creation_url(request: Request) -> dict[str, str]:
        base = deps.settings.public_base_url.strip() or str(request.base_url)
        return {"url": paco_page_url(base)}

    @app.get("/api/paco/install-qr.svg")
    def paco_install_qr_svg(
        request: Request,
        x_assistant_token: str | None = Header(default=None),
    ) -> Response:
        _guard(x_assistant_token)
        base = deps.settings.public_base_url.strip() or str(request.base_url)
        url = paco_page_url(base)
        return Response(content=paco_qr_svg(url, paco_icon_url(base)), media_type="image/svg+xml")

    @app.get("/api/paco/install-qr.png")
    def paco_install_qr_png(request: Request) -> Response:
        base = deps.settings.public_base_url.strip() or str(request.base_url)
        url = paco_page_url(base)
        return Response(content=paco_qr_png(url, paco_icon_url(base)), media_type="image/png")

    @app.get("/api/creation-url")
    def creation_url(request: Request) -> dict[str, str]:
        base = deps.settings.public_base_url.strip() or str(request.base_url)
        return {
            "url": creation_target_url(base, deps.settings.creation_public_url)
        }

    @app.get("/api/install-qr.svg")
    def install_qr_svg(
        request: Request,
        x_assistant_token: str | None = Header(default=None),
    ) -> Response:
        _guard(x_assistant_token)
        base = deps.settings.public_base_url.strip() or str(request.base_url)
        return Response(
            content=qr_svg(creation_target_url(base, deps.settings.creation_public_url)),
            media_type="image/svg+xml",
        )

    @app.get("/api/install-qr.png")
    def install_qr_png(request: Request) -> Response:
        base = deps.settings.public_base_url.strip() or str(request.base_url)
        return Response(
            content=qr_png(creation_target_url(base, deps.settings.creation_public_url)),
            media_type="image/png",
        )

    @app.post("/internal/tick")
    def tick(x_assistant_token: str | None = Header(default=None)) -> dict[str, Any]:
        _guard(x_assistant_token)
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler is None:
            raise HTTPException(status_code=503, detail="scheduler is not configured")
        sent = scheduler.tick(deps.clock.now())
        return {"sent": sent}

    paco_static = paco_dir()
    if paco_static.exists():
        app.mount("/creation/paco/v2", StaticFiles(directory=paco_static, html=True), name="paco-v2")
        app.mount("/creation/paco", StaticFiles(directory=paco_static, html=True), name="paco")
    static = creation_dir()
    if static.exists():
        app.mount("/creation/v2", StaticFiles(directory=static, html=True), name="creation-v2")
        app.mount("/creation", StaticFiles(directory=static, html=True), name="creation")

    return app


app = create_app()
