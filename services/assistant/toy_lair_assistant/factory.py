from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from toy_lair_assistant.agent import Agent
from toy_lair_assistant.clients.gcal import GoogleCalendarClient
from toy_lair_assistant.clients.telegram import TelegramBot
from toy_lair_assistant.google_alert import make_auth_alerter
from toy_lair_assistant.clients.todoist import TodoistClient
from toy_lair_assistant.clock import Clock
from toy_lair_assistant.llm import EchoLLM, OpenAILLM
from toy_lair_assistant.main import create_app
from toy_lair_assistant.scheduler import Scheduler
from toy_lair_assistant.settings import Settings
from toy_lair_assistant.speech import OpenAISpeech, SilentSpeech
from toy_lair_assistant.store import open_store
from toy_lair_assistant.zayka import ZaykaIndex


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    clock = Clock(settings.timezone)
    store = open_store(settings.database_url)
    todoist = (
        TodoistClient(settings.todoist_api_token, now=clock.now)
        if settings.todoist_api_token
        else None
    )
    calendar = None
    if settings.google_refresh_token:
        calendar = GoogleCalendarClient(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            refresh_token=settings.google_refresh_token,
            calendar_id=settings.google_calendar_id,
            now=clock.now,
            timezone=settings.timezone,
        )
    notify = None
    if settings.telegram_bot_token and settings.telegram_chat_id:
        notify = TelegramBot(settings.telegram_bot_token, settings.telegram_chat_id)
    if calendar is not None:
        calendar.on_auth_error = make_auth_alerter(
            store,
            notify.send_text if notify else (lambda text: None),
            clock.now,
        )
    zayka = None
    zayka_dir = settings.zayka_path()
    if zayka_dir and Path(zayka_dir).exists():
        zayka = ZaykaIndex(Path(zayka_dir))
    llm = OpenAILLM(settings.openai_api_key, settings.openai_model) if settings.openai_api_key else EchoLLM()
    agent = None
    if todoist and calendar:
        agent = Agent(
            todoist=todoist,
            calendar=calendar,
            llm=llm,
            now=clock.now,
            store=store,
            zayka=zayka,
        )
    speech = (
        OpenAISpeech(
            settings.openai_api_key,
            stt_model=settings.openai_stt_model,
            tts_model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
        )
        if settings.openai_api_key
        else SilentSpeech()
    )
    app = create_app(
        settings,
        clock=clock,
        todoist=todoist,
        calendar=calendar,
        speech=speech,
        agent=agent,
        store=store,
        zayka=zayka,
        notify=notify,
    )
    if agent and notify and todoist and calendar:
        app.state.scheduler = Scheduler(
            todoist=todoist,
            calendar=calendar,
            store=store,
            notify=notify.send_text,
            lead_minutes=settings.reminder_lead_minutes,
            briefing_hour=settings.briefing_hour,
            timezone=settings.timezone,
        )
    return app


app = build_app()
