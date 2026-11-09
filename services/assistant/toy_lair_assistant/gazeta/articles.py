"""Article download shared by the editor tools and the section desk."""

from __future__ import annotations

import httpx

from toy_lair_assistant.collector.enrich import html_to_text

ARTICLE_LIMIT = 4000


def fetch_article(http: httpx.Client, url: str) -> tuple[str, str]:
    """Return (final_url, text). Raises on any HTTP or transport error."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must be http(s)")
    response = http.get(url)
    response.raise_for_status()
    kind = response.headers.get("content-type", "")
    text = html_to_text(response.text) if "html" in kind else response.text
    return str(response.url), text[:ARTICLE_LIMIT]
