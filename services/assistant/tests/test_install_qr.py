import json

from fastapi.testclient import TestClient

from toy_lair_assistant.install_qr import (
    creation_json,
    creation_page_url,
    creation_payload,
    qr_svg,
)
from toy_lair_assistant.main import create_app
from toy_lair_assistant.settings import Settings


def test_creation_payload_is_rabbit_json() -> None:
    payload = creation_payload("https://example.com/creation/")
    assert payload == {
        "title": "toy lair",
        "url": "https://example.com/creation/",
        "description": "Assistant",
        "iconUrl": "",
        "themeColor": "#FE5000",
    }


def test_qr_svg_encodes_json_not_bare_url() -> None:
    url = "https://example.com/creation/"
    svg = qr_svg(url)
    assert "<svg" in svg
    assert svg == qr_svg(url)
    decoded = json.loads(creation_json(url))
    assert decoded["title"] == "toy lair"
    assert decoded["url"] == url
    assert decoded["themeColor"] == "#FE5000"


def test_creation_page_url() -> None:
    assert creation_page_url("https://example.com/") == "https://example.com/creation/"


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
    created = "http://testserver/creation/"
    assert qr_svg(created) == ok.text
    payload = json.loads(creation_json(created))
    assert payload["url"] == created
    assert payload["title"] == "toy lair"
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
        gone = client.get("/c")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert gone.status_code == 404


def test_install_html_does_not_use_third_party_qr() -> None:
    app = create_app(
        Settings(assistant_api_token="secret", tick_interval_seconds=0, zayka_dir="")
    )
    with TestClient(app) as client:
        page = client.get("/creation/install.html")
    assert page.status_code == 200
    assert "qrserver.com" not in page.text
    assert "/api/install-qr.svg" in page.text
    assert "X-Assistant-Token" in page.text
    assert "/api/pair/approve" in page.text
    assert "/creation/" in page.text
