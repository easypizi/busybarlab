from __future__ import annotations

import io
import json

import segno

CREATION_TITLE = "toy lair"
CREATION_DESCRIPTION = "Assistant"
CREATION_THEME = "#FE5000"


def creation_payload(url: str) -> dict[str, str]:
    return {
        "title": CREATION_TITLE,
        "url": url,
        "description": CREATION_DESCRIPTION,
        "iconUrl": "",
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
