from __future__ import annotations

import io
import json
from urllib.parse import urlparse

import segno

CREATION_TITLE = "Tito"
CREATION_DESCRIPTION = "Cal butler"
CREATION_THEME = "#FE5000"


def icon_url_for(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if parsed.scheme and parsed.netloc and path.endswith("/creation"):
        return f"{parsed.scheme}://{parsed.netloc}/i.png"
    return f"{url.rstrip('/')}/icon.png"


def creation_payload(url: str, icon_url: str = "") -> dict[str, str]:
    return {
        "title": CREATION_TITLE,
        "url": url,
        "description": CREATION_DESCRIPTION,
        "iconUrl": icon_url or icon_url_for(url),
        "themeColor": CREATION_THEME,
    }


def creation_json(url: str) -> str:
    return json.dumps(creation_payload(url), separators=(",", ":"))


def qr_svg(url: str) -> str:
    return segno.make(creation_json(url), error="m").svg_inline(scale=10, border=4)


def qr_png(url: str) -> bytes:
    buffer = io.BytesIO()
    segno.make(creation_json(url), error="m").save(
        buffer,
        kind="png",
        scale=10,
        border=4,
        dark="#000000",
        light="#ffffff",
    )
    return buffer.getvalue()


def creation_page_url(base: str) -> str:
    return f"{base.rstrip('/')}/creation/"


def creation_target_url(base: str, public: str = "") -> str:
    host = public.strip()
    if host:
        return f"{host.rstrip('/')}/"
    return creation_page_url(base)
