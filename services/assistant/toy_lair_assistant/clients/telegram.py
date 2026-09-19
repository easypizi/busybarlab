from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx


class TelegramBot:
    def __init__(
        self,
        token: str,
        chat_id: str,
        sender: Callable[[dict], None] | None = None,
        downloader: Callable[[str], bytes] | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        self.token = token
        self.chat_id = str(chat_id)
        self.http = http or httpx.Client(timeout=30)
        self._owns_http = http is None
        self.sender = sender or self._send
        self.downloader = downloader or self._download_voice

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def allowed(self, chat_id: Any) -> bool:
        return str(chat_id) == self.chat_id

    def send_text(self, text: str) -> None:
        self.sender({"chat_id": self.chat_id, "text": text})

    def handle_update(self, update: dict, agent: Any, speech: Any) -> None:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        if not self.allowed(chat.get("id")):
            return
        text = (message.get("text") or "").strip()
        if not text and message.get("voice"):
            file_id = message["voice"]["file_id"]
            audio = self.downloader(file_id)
            text = speech.transcribe(audio, "audio/ogg")
        if not text:
            return
        result = agent.handle_text(text, channel="telegram")
        self.send_text(result.reply)

    def _send(self, payload: dict) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.http.post(url, json=payload).raise_for_status()

    def _download_voice(self, file_id: str) -> bytes:
        meta = self.http.get(
            f"https://api.telegram.org/bot{self.token}/getFile",
            params={"file_id": file_id},
        )
        meta.raise_for_status()
        path = meta.json()["result"]["file_path"]
        data = self.http.get(f"https://api.telegram.org/file/bot{self.token}/{path}")
        data.raise_for_status()
        return data.content
