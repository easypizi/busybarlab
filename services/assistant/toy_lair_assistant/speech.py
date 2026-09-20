from __future__ import annotations

import base64

import httpx


class Speech:
    def transcribe(self, data: bytes, mime: str) -> str:
        raise NotImplementedError

    def speak(self, text: str) -> str:
        raise NotImplementedError


class OpenAISpeech(Speech):
    def __init__(
        self,
        api_key: str,
        stt_model: str = "whisper-1",
        tts_model: str = "gpt-4o-mini-tts",
        voice: str = "ash",
        instructions: str = "",
        http: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.stt_model = stt_model
        self.tts_model = tts_model
        self.voice = voice
        self.instructions = instructions
        self.http = http or httpx.Client(timeout=60)

    def transcribe(self, data: bytes, mime: str) -> str:
        ext = "webm" if "webm" in mime else "wav"
        files = {"file": (f"clip.{ext}", data, mime or "application/octet-stream")}
        response = self.http.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            data={"model": self.stt_model},
            files=files,
        )
        response.raise_for_status()
        return str(response.json().get("text") or "").strip()

    def speak(self, text: str) -> str:
        response = self.http.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.tts_model,
                "voice": self.voice,
                "input": text,
                **({"instructions": self.instructions} if self.instructions else {}),
            },
        )
        response.raise_for_status()
        return base64.b64encode(response.content).decode("ascii")


class SilentSpeech(Speech):
    def transcribe(self, data: bytes, mime: str) -> str:
        return ""

    def speak(self, text: str) -> str:
        return ""
