import json

from fastapi.testclient import TestClient

import segno

from toy_lair_assistant.install_qr import (
    creation_json,
    creation_page_url,
    creation_payload,
    creation_target_url,
    qr_png,
    qr_svg,
)
from toy_lair_assistant.main import create_app
from toy_lair_assistant.settings import Settings


def test_creation_payload_is_rabbit_json() -> None:
    payload = creation_payload("https://example.com/creation/")
    assert payload == {
        "title": "Tito",
        "url": "https://example.com/creation/",
        "description": "Cal butler",
        "iconUrl": "https://example.com/i.png",
        "themeColor": "#FE5000",
    }


def test_creation_payload_icon_url_is_absolute() -> None:
    payload = creation_payload(
        "https://example.com/creation/",
        "https://example.com/creation/icon.png",
    )
    assert payload["iconUrl"].startswith("https://")
    assert payload["iconUrl"].endswith("/creation/icon.png")


def test_creation_qr_stays_version_10_or_less() -> None:
    url = "https://toy-lair-assistant-e9003db7d945.herokuapp.com/creation/v2/"
    code = segno.make(creation_json(url), error="m")
    assert code.version <= 10


def test_v2_payload_uses_short_icon() -> None:
    payload = creation_payload(
        "https://toy-lair-assistant-e9003db7d945.herokuapp.com/creation/v2/"
    )
    assert payload["url"].endswith("/creation/v2/")
    assert payload["iconUrl"].endswith("/i.png")


def test_qr_svg_encodes_json_not_bare_url() -> None:
    url = "https://example.com/creation/"
    svg = qr_svg(url)
    assert "<svg" in svg
    assert svg == qr_svg(url)
    decoded = json.loads(creation_json(url))
    assert decoded["title"] == "Tito"
    assert decoded["url"] == url
    assert decoded["themeColor"] == "#FE5000"


def test_qr_png_is_opaque_square_bitmap() -> None:
    raw = qr_png("https://example.com/creation/")
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert raw[12:16] == b"IHDR"
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    color_type = raw[25]
    assert width == height
    assert width >= 200
    assert color_type in (0, 2, 3)


def test_creation_page_url() -> None:
    assert creation_page_url("https://example.com/") == "https://example.com/creation/v2/"


def test_creation_target_url_prefers_public_host() -> None:
    assert (
        creation_target_url("https://heroku.example/", "https://easypizi.github.io/toy_lair")
        == "https://easypizi.github.io/toy_lair/"
    )
    assert creation_target_url("https://heroku.example/", "") == "https://heroku.example/creation/v2/"


def test_install_qr_requires_token() -> None:
    app = create_app(
        Settings(
            assistant_api_token="secret",
            tick_interval_seconds=0,
            public_base_url="",
            zayka_dir="",
        )
    )
    with TestClient(app) as client:
        denied = client.get("/api/install-qr.svg")
        assert denied.status_code == 401
        ok = client.get(
            "/api/install-qr.svg",
            headers={"X-Assistant-Token": "secret"},
        )
    assert ok.status_code == 200
    assert "image/svg+xml" in ok.headers["content-type"]
    assert "<svg" in ok.text
    created = "http://testserver/creation/v2/"
    assert qr_svg(created) == ok.text
    payload = json.loads(creation_json(created))
    assert payload["url"] == created
    assert payload["title"] == "Tito"
    assert "qrserver.com" not in ok.text


def test_creation_is_direct_html_and_short_path_is_gone() -> None:
    app = create_app(
        Settings(
            assistant_api_token="secret",
            tick_interval_seconds=0,
            public_base_url="",
            zayka_dir="",
        )
    )
    with TestClient(app, follow_redirects=False) as client:
        page = client.get("/creation/")
        bust = client.get("/creation/v2/")
        gone = client.get("/c")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert bust.status_code == 200
    assert "text/html" in bust.headers["content-type"]
    assert "hold PTT or circle" in bust.text
    assert gone.status_code == 404


def test_install_html_does_not_use_third_party_qr() -> None:
    app = create_app(
        Settings(assistant_api_token="secret", tick_interval_seconds=0, zayka_dir="")
    )
    with TestClient(app) as client:
        page = client.get("/creation/install.html")
    assert page.status_code == 200
    assert "qrserver.com" not in page.text
    assert "qr-code-styling" not in page.text
    assert "/api/install-qr.png" in page.text
    assert "X-Assistant-Token" in page.text
    assert "/api/pair/approve" in page.text
    assert "/api/creation-url" in page.text
    assert "Install Tito" in page.text
    assert "tito.png" in page.text
    assert "image-rendering: pixelated" in page.text


def test_install_qr_png_is_public() -> None:
    app = create_app(
        Settings(
            assistant_api_token="secret",
            tick_interval_seconds=0,
            public_base_url="",
            zayka_dir="",
        )
    )
    with TestClient(app) as client:
        ok = client.get("/api/install-qr.png")
    assert ok.status_code == 200
    assert "image/png" in ok.headers["content-type"]
    assert ok.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert ok.content == qr_png("http://testserver/creation/v2/")
