import json

from fastapi.testclient import TestClient

from toy_lair_assistant.install_qr import creation_json, creation_payload, qr_svg, short_install_url
from toy_lair_assistant.main import create_app
from toy_lair_assistant.settings import Settings


def test_creation_payload_is_rabbit_json() -> None:
    payload = creation_payload("https://example.com/c")
    assert payload == {
        "title": "toy_lair",
        "url": "https://example.com/c",
        "description": "Assistant",
        "iconUrl": "",
        "themeColor": "#FE5000",
    }


def test_qr_svg_encodes_json_not_bare_url() -> None:
    url = "https://example.com/c"
    svg = qr_svg(url)
    assert "<svg" in svg
    assert svg == qr_svg(url)
    decoded = json.loads(creation_json(url))
    assert decoded["title"] == "toy_lair"
    assert decoded["url"] == url
    assert decoded["themeColor"] == "#FE5000"


def test_short_install_url() -> None:
    assert short_install_url("https://example.com/") == "https://example.com/c"


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
    created = "http://testserver/c"
    assert qr_svg(created) == ok.text
    payload = json.loads(creation_json(created))
    assert payload["url"] == created
    assert "qrserver.com" not in ok.text


def test_short_entry_redirects_with_token() -> None:
    app = create_app(
        Settings(
            assistant_api_token="secret",
            tick_interval_seconds=0,
            public_base_url="",
            zayka_dir="",
        )
    )
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/c")
    assert response.status_code in (302, 307)
    assert response.headers["location"].endswith("/creation/?token=secret")


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
