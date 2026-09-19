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
    openai_tts_voice: str = "alloy"
    todoist_api_token: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_calendar_id: str = "primary"
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
