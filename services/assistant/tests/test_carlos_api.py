import json

from fastapi.testclient import TestClient

from toy_lair_assistant.carlos import CarlosResult
from toy_lair_assistant.install_qr import carlos_icon_url, carlos_json, carlos_page_url, carlos_qr_png, carlos_qr_svg
from toy_lair_assistant.main import create_app
from toy_lair_assistant.settings import Settings
from toy_lair_assistant.store import MemoryStore


class FakeCarlos:
    def __init__(self) -> None:
        self.seen: list[tuple[str, dict]] = []
        self.store = MemoryStore()

    def log(self, text: str, card: dict) -> CarlosResult:
        self.seen.append((text, card))
        entry = {
            "date": card["date"],
            "sessionId": card["sessionId"],
            "status": "done",
            "back": "ok",
            "items": [],
            "raw": text,
        }
        return CarlosResult(ok=True, reply="Записал.", entry=entry, line="сделано · спина в порядке", action="logged")

    def last(self, log_date: str):
        if log_date == "2026-09-22":
            return {"date": log_date, "status": "done", "back": "ok", "items": [], "raw": "сделал"}
        return None


def _app(carlos=None):
    return create_app(
        Settings(
            assistant_api_token="secret",
            tick_interval_seconds=0,
            zayka_dir="",
            zayka_sync_enabled=False,
        ),
        carlos=carlos,
    )


def test_carlos_log_requires_token() -> None:
    app = _app(FakeCarlos())
    with TestClient(app) as client:
        denied = client.post("/api/carlos/log", json={"text": "сделал", "date": "2026-09-22"})
    assert denied.status_code == 401


def test_carlos_log_and_read() -> None:
    carlos = FakeCarlos()
    app = _app(carlos)
    headers = {"X-Assistant-Token": "secret"}
    body = {
        "text": "сделал",
        "date": "2026-09-22",
        "sessionId": "module-strike",
        "title": "Модуль",
        "exercises": ["Блок 1. Strike"],
    }
    with TestClient(app) as client:
        saved = client.post("/api/carlos/log", headers=headers, json=body)
        loaded = client.get("/api/carlos/log", headers=headers, params={"date": "2026-09-22"})
        missing = client.get("/api/carlos/log", headers=headers, params={"date": "2026-09-23"})
    assert saved.status_code == 200
    assert saved.json()["ok"] is True
    assert saved.json()["action"] == "logged"
    assert carlos.seen[0][0] == "сделал"
    assert carlos.seen[0][1]["exercises"] == ["Блок 1. Strike"]
    assert loaded.json()["line"] == "сделано · спина в порядке"
    assert missing.json()["entry"] is None


def test_carlos_log_is_503_without_an_agent() -> None:
    app = _app(None)
    with TestClient(app) as client:
        denied = client.post(
            "/api/carlos/log",
            headers={"X-Assistant-Token": "secret"},
            json={"text": "сделал", "date": "2026-09-22"},
        )
    assert denied.status_code == 503


def test_carlos_qr_points_at_carlos_only() -> None:
    app = create_app(
        Settings(
            assistant_api_token="secret",
            tick_interval_seconds=0,
            zayka_dir="",
            public_base_url="https://heroku.example",
            creation_public_url="https://easypizi.github.io/toy_lair/",
        )
    )
    with TestClient(app) as client:
        url = client.get("/api/carlos/creation-url")
        png = client.get("/api/carlos/install-qr.png")
        denied = client.get("/api/carlos/install-qr.svg")
        svg = client.get("/api/carlos/install-qr.svg", headers={"X-Assistant-Token": "secret"})
        page = client.get("/creation/carlos/index.html")
        script = client.get("/creation/carlos/app.js")
        icon = client.get("/carlos.png")
        install = client.get("/creation/carlos/install.html")
    assert url.json()["url"] == "https://heroku.example/creation/carlos/v2/"
    target = carlos_page_url("https://heroku.example")
    icon_url = carlos_icon_url("https://heroku.example")
    payload = json.loads(carlos_json(target, icon_url))
    assert payload["title"] == "Carlos"
    assert payload["url"].endswith("/creation/carlos/v2/")
    assert "/creation/paco/" not in payload["url"]
    assert payload["url"] != "https://heroku.example/creation/v2/"
    assert png.status_code == 200
    assert png.content == carlos_qr_png(target, icon_url)
    assert denied.status_code == 401
    assert svg.text == carlos_qr_svg(target, icon_url)
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-cache"
    assert "240" in page.text and "282" in page.text
    assert "Carlos" in page.text
    assert "hold PTT · wheel day" in page.text
    assert "CreationVoiceHandler" in script.text
    assert "wantsR1Response" in script.text
    assert "getUserMedia" not in script.text
    assert "webgl" not in script.text
    assert "/api/carlos/log" in script.text
    assert 'event: "carlos "' in script.text
    assert icon.status_code == 200
    assert icon.content[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(icon.content[16:20], "big")
    height = int.from_bytes(icon.content[20:24], "big")
    assert (width, height) == (512, 512)
    assert "Install Carlos" in install.text
    assert "/api/carlos/install-qr.png" in install.text
