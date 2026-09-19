import json

import segno
from fastapi.testclient import TestClient

from toy_lair_assistant.install_qr import creation_json, creation_payload, qr_svg
from toy_lair_assistant.main import create_app
from toy_lair_assistant.settings import Settings


def _payload_from_svg(svg: str, url: str) -> dict:
    expected = segno.make(creation_json(url)).svg_inline(scale=4)
    assert svg == expected
    return json.loads(creation_json(url))


def test_creation_payload_is_rabbit_json() -> None:
    payload = creation_payload("https://example.com/creation/?token=abc")
    assert payload == {
        "title": "toy_lair",
        "url": "https://example.com/creation/?token=abc",
        "description": "Personal assistant for Todoist and Google Calendar",
        "iconUrl": "",
        "themeColor": "#FE5000",
    }


def test_qr_svg_encodes_json_not_bare_url() -> None:
    url = "https://example.com/creation/?token=abc"
    svg = qr_svg(url)
    assert "<svg" in svg
    decoded = _payload_from_svg(svg, url)
    assert decoded["title"] == "toy_lair"
    assert decoded["url"] == url
    assert decoded["themeColor"] == "#FE5000"
    assert url not in svg or '"title"' in creation_json(url)


def test_install_qr_requires_token() -> None:
    app = create_app(Settings(assistant_api_token="secret", tick_interval_seconds=0))
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
    created = "http://testserver/creation/?token=secret"
    payload = _payload_from_svg(ok.text, created)
    assert payload["url"] == created
    assert "qrserver.com" not in ok.text


def test_install_html_does_not_use_third_party_qr() -> None:
    app = create_app(Settings(assistant_api_token="secret", tick_interval_seconds=0))
    with TestClient(app) as client:
        page = client.get("/creation/install.html")
    assert page.status_code == 200
    assert "qrserver.com" not in page.text
    assert "/api/install-qr.svg" in page.text
    assert "X-Assistant-Token" in page.text
