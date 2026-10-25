from __future__ import annotations

from typing import Any

import httpx


class IngestClient:
    def __init__(self, base_url: str, token: str, http: httpx.Client | None = None) -> None:
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.http = http or httpx.Client(timeout=30)

    def push_items(self, items: list[dict[str, Any]]) -> None:
        for start in range(0, len(items), 50):
            response = self.http.post(
                f"{self.base}/api/library/items",
                headers=self.headers,
                json={"items": items[start : start + 50]},
            )
            response.raise_for_status()

    def jobs(self) -> list[dict[str, Any]]:
        response = self.http.get(f"{self.base}/api/collector/jobs", headers=self.headers)
        response.raise_for_status()
        return list(response.json().get("jobs") or [])

    def done(self, job_id: str, ok: bool, message: str = "") -> None:
        response = self.http.post(
            f"{self.base}/api/collector/jobs/{job_id}/done",
            headers=self.headers,
            json={"ok": ok, "message": message},
        )
        response.raise_for_status()

    def event(self, kind: str, source: str, text: str, summary: dict[str, Any] | None = None) -> None:
        response = self.http.post(
            f"{self.base}/api/collector/event",
            headers=self.headers,
            json={"kind": kind, "source": source, "text": text, "summary": summary or {}},
        )
        response.raise_for_status()
