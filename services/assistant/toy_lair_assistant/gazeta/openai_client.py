"""Thin OpenAI clients used by the newspaper: Responses, chat JSON, images."""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx

BASE = "https://api.openai.com/v1"


class OpenAIClient:
    def __init__(self, api_key: str, http: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.http = http or httpx.Client(timeout=240)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(6):
            try:
                response = self.http.post(
                    f"{BASE}{path}",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=body,
                )
            except httpx.TransportError:
                if attempt < 5:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise
            if response.status_code in (429, 500, 502, 503) and attempt < 5:
                time.sleep(min(60, 8 * (attempt + 1)))
                continue
            if response.status_code >= 400:
                raise RuntimeError(f"OpenAI {path} {response.status_code}: {response.text[:500]}")
            return response.json()
        raise RuntimeError("unreachable")

    def respond(
        self,
        model: str,
        instructions: str,
        input: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        previous_response_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"model": model, "instructions": instructions, "input": input, "tools": tools}
        if previous_response_id:
            body["previous_response_id"] = previous_response_id
        return self._post("/responses", body)

    def chat_json(self, model: str, system: str, user: str, schema: dict[str, Any], name: str) -> dict[str, Any]:
        import json

        data = self._post(
            "/chat/completions",
            {
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
            },
        )
        return json.loads(data["choices"][0]["message"]["content"])

    def image(self, model: str, prompt: str, size: str = "1024x1024") -> bytes:
        data = self._post("/images/generations", {"model": model, "prompt": prompt, "size": size, "n": 1})
        item = data["data"][0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        response = self.http.get(item["url"])
        response.raise_for_status()
        return response.content
