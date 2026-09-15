"""Optional Telegram notifications for metamorphoses and achievements."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str

    @classmethod
    def from_env(cls) -> TelegramConfig | None:
        token = os.environ.get("BUSYBAR_TG_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("BUSYBAR_TG_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return None
        return cls(bot_token=token, chat_id=chat_id)


def send_message(config: TelegramConfig, text: str) -> bool:
    url = f"https://api.telegram.org/bot{config.bot_token}/sendMessage"
    payload = {"chat_id": config.chat_id, "text": text, "disable_web_page_preview": True}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def notify_events(events: list[str], *, pet_name: str, level: int, branch: str) -> None:
    config = TelegramConfig.from_env()
    if not config or not events:
        return
    body = f"{pet_name} LVL {level} [{branch.upper()}]\n" + "\n".join(f"- {e}" for e in events)
    send_message(config, body)
