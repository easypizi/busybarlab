from __future__ import annotations

import io
import json
from urllib.parse import urlparse

import segno

CREATION_TITLE = "Tito"
CREATION_DESCRIPTION = "Cal butler"
CREATION_THEME = "#FE5000"
CREATION_PATH = "/creation/v2/"


def icon_url_for(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if parsed.scheme and parsed.netloc and "/creation" in path:
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
    return f"{base.rstrip('/')}{CREATION_PATH}"


PACO_TITLE = "Paco"
PACO_DESCRIPTION = "Zayka notes"
PACO_PATH = "/creation/paco/v2/"


def paco_page_url(base: str) -> str:
    return f"{base.rstrip('/')}{PACO_PATH}"


def paco_icon_url(base: str) -> str:
    return f"{base.rstrip('/')}/paco.png"


def paco_payload(url: str, icon_url: str) -> dict[str, str]:
    return {
        "title": PACO_TITLE,
        "url": url,
        "description": PACO_DESCRIPTION,
        "iconUrl": icon_url,
        "themeColor": CREATION_THEME,
    }


def paco_json(url: str, icon_url: str) -> str:
    return json.dumps(paco_payload(url, icon_url), separators=(",", ":"))


def paco_qr_svg(url: str, icon_url: str) -> str:
    return segno.make(paco_json(url, icon_url), error="m").svg_inline(scale=10, border=4)


def paco_qr_png(url: str, icon_url: str) -> bytes:
    buffer = io.BytesIO()
    segno.make(paco_json(url, icon_url), error="m").save(
        buffer,
        kind="png",
        scale=10,
        border=4,
        dark="#000000",
        light="#ffffff",
    )
    return buffer.getvalue()


def creation_target_url(base: str, public: str = "") -> str:
    host = public.strip()
    if host:
        return f"{host.rstrip('/')}/"
    return creation_page_url(base)
