import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_SERVICE_DIR / ".env", ".env"),
        extra="ignore",
    )

    assistant_api_token: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_stt_model: str = "whisper-1"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "ash"
    openai_tts_instructions: str = "relaxed Californian butler, unhurried, friendly"
    todoist_api_token: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_calendar_id: str = "primary"
    google_read_calendars: str = "all"
    google_tasks_calendar_id: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    database_url: str = ""
    zayka_dir: str = ""
    zayka_repo_url: str = "https://github.com/easypizi/zayka.git"
    timezone: str = "America/Los_Angeles"
    reminder_lead_minutes: int = 15
    briefing_hour: int = 8
    public_base_url: str = ""
    creation_public_url: str = ""
    tick_interval_seconds: float = 60
    zayka_sync_interval_seconds: float = 3600
    zayka_sync_enabled: bool = True
    plan_hours_start: int = 10
    plan_hours_end: int = 22
    plan_horizon_days: int = 7
    plan_default_minutes: int = 60
    plan_weekends: bool = True
    task_lead_minutes: int = 15
    deadline_lead_days: int = 1
    remind_label: str = "remind"
    remind_nudge_hours: int = 3
    task_sync_interval_seconds: float = 300

    def creation_origin(self) -> str:
        url = self.creation_public_url.strip()
        if not url:
            return ""
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}"

    def zayka_path(self) -> Path | None:
        if not self.zayka_dir:
            return None
        return Path(self.zayka_dir)

    def zayka_should_sync(self) -> bool:
        if not self.zayka_sync_enabled or not self.zayka_dir:
            return False
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return False
        return True
