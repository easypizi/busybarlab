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
        self.on_api_error = None

    def _raise(self, response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if self.on_api_error is not None and (status in (401, 429) or status >= 500):
                from toy_lair_assistant.openai_alert import openai_detail

                self.on_api_error(status, openai_detail(exc.response))
            raise

    def transcribe(self, data: bytes, mime: str) -> str:
        files = {"file": (_clip_name(mime), data, mime or "application/octet-stream")}
        response = self.http.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            data={"model": self.stt_model},
            files=files,
        )
        self._raise(response)
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
        self._raise(response)
        return base64.b64encode(response.content).decode("ascii")


def _clip_name(mime: str) -> str:
    lower = (mime or "").lower()
    if "ogg" in lower:
        return "clip.ogg"
    if "mp4" in lower or "m4a" in lower:
        return "clip.m4a"
    if "webm" in lower:
        return "clip.webm"
    return "clip.wav"


class SilentSpeech(Speech):
    def transcribe(self, data: bytes, mime: str) -> str:
        return ""

    def speak(self, text: str) -> str:
        return ""
