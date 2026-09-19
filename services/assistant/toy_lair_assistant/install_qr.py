from __future__ import annotations

import json

import segno

CREATION_TITLE = "toy_lair"
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


def creation_url(base: str, token: str) -> str:
    return f"{base.rstrip('/')}/creation/?token={token}"


def short_install_url(base: str) -> str:
    return f"{base.rstrip('/')}/c"
