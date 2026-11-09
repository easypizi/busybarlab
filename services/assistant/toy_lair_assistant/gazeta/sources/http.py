from __future__ import annotations

from typing import Any

import httpx

from toy_lair_assistant.gazeta.config import USER_AGENT


def client() -> httpx.Client:
    return httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def get_json(http: httpx.Client, url: str, params: dict[str, Any] | None = None) -> Any:
    response = http.get(url, params=params)
    response.raise_for_status()
    return response.json()
