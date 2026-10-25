from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path("~/Library/Application Support/toy_lair").expanduser()
CONFIG_PATH = APP_DIR / "collector.json"


@dataclass
class CollectorConfig:
    vault_dir: str = "~/Documents/Zayka"
    heroku_url: str = "https://toy-lair-assistant-e9003db7d945.herokuapp.com"
    state_path: str = str(APP_DIR / "collector.db")
    timezone: str = "America/Los_Angeles"
    openai_model: str = "gpt-4.1-mini"
    openai_stt_model: str = "whisper-1"
    per_run_limit: int = 30
    instagram_user: str = ""
    gmail_user: str = ""
    gmail_query: str = "is:starred OR label:Paco OR (from:me to:me)"
    telegram_allowlist: list[str] = field(default_factory=list)
    chrome_profile: str = "~/Library/Application Support/Google/Chrome/Default"
    sources: list[str] = field(
        default_factory=lambda: ["chrome", "gmail", "telegram", "instagram", "zayka", "bot"]
    )

    @property
    def vault_path(self) -> Path:
        return Path(self.vault_dir).expanduser()


def load_config(path: Path | None = None) -> CollectorConfig:
    cfg = CollectorConfig()
    file = path or Path(os.environ.get("COLLECTOR_CONFIG", str(CONFIG_PATH)))
    if file.exists():
        data = json.loads(file.read_text(encoding="utf-8"))
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
    return cfg
