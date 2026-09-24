import json

from fastapi.testclient import TestClient

from toy_lair_assistant.agent import AgentResult
from toy_lair_assistant.factory import build_app
from toy_lair_assistant.install_qr import (
    paco_icon_url,
    paco_json,
    paco_page_url,
    paco_qr_png,
    paco_qr_svg,
)
from toy_lair_assistant.main import create_app
from toy_lair_assistant.paco import PacoAgent, PacoResult
from toy_lair_assistant.settings import Settings


class FakeTito:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def handle_text(self, text: str, channel: str = "r1") -> AgentResult:
        self.seen.append(text)
        return AgentResult(reply="tito")


class FakePaco:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def handle_text(self, text: str) -> PacoResult:
        self.seen.append(text)
        return PacoResult(reply="paco", peek={"kind": "inbox", "items": [], "count": 2})

    def inbox_payload(self) -> dict:
        return {
            "kind": "inbox",
            "items": [{"title": "Idea", "age_hours": 1, "tags": ["to-process"]}],
            "count": 3,
        }


def _app(tito: FakeTito, paco: FakePaco):
    return create_app(
        Settings(
            assistant_api_token="secret",
            tick_interval_seconds=0,
            zayka_dir="",
            zayka_sync_enabled=False,
        ),
        agent=tito,
        paco=paco,
    )


def test_paco_text_requires_token() -> None:
    app = _app(FakeTito(), FakePaco())
    with TestClient(app) as client:
        denied = client.post("/api/paco/text", json={"text": "hi"})
    assert denied.status_code == 401


def test_paco_text_and_inbox(tmp_path=None) -> None:
    tito = FakeTito()
    paco = FakePaco()
    app = _app(tito, paco)
    headers = {"X-Assistant-Token": "secret"}
    with TestClient(app) as client:
        text = client.post("/api/paco/text", headers=headers, json={"text": "запиши"})
        inbox = client.get("/api/paco/inbox", headers=headers)
        tito_text = client.post("/api/text", headers=headers, json={"text": "today"})
    assert text.status_code == 200
    assert text.json()["reply"] == "paco"
    assert text.json()["peek"]["kind"] == "inbox"
    assert inbox.json()["items"][0]["title"] == "Idea"
    assert paco.seen == ["запиши"]
    assert tito.seen == ["today"]


def test_text_routes_do_not_cross() -> None:
    tito = FakeTito()
    paco = FakePaco()
    app = _app(tito, paco)
    headers = {"X-Assistant-Token": "secret"}
    with TestClient(app) as client:
        client.post("/api/text", headers=headers, json={"text": "calendar"})
        client.post("/api/paco/text", headers=headers, json={"text": "note"})
    assert tito.seen == ["calendar"]
    assert paco.seen == ["note"]


def test_paco_qr_ignores_creation_public_url() -> None:
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
        url = client.get("/api/paco/creation-url")
        png = client.get("/api/paco/install-qr.png")
        denied = client.get("/api/paco/install-qr.svg")
        svg = client.get(
            "/api/paco/install-qr.svg",
            headers={"X-Assistant-Token": "secret"},
        )
    assert url.json()["url"] == "https://heroku.example/creation/paco/v2/"
    page = paco_page_url("https://heroku.example")
    icon = paco_icon_url("https://heroku.example")
    assert png.content == paco_qr_png(page, icon)
    assert denied.status_code == 401
    assert svg.text == paco_qr_svg(page, icon)
    assert json.loads(paco_json(page, icon))["title"] == "Paco"
    assert png.status_code == 200


def test_paco_creation_is_voice_home() -> None:
    app = create_app(
        Settings(assistant_api_token="secret", tick_interval_seconds=0, zayka_dir="")
    )
    with TestClient(app) as client:
        page = client.get("/creation/paco/index.html")
        script = client.get("/creation/paco/app.js")
        icon = client.get("/paco.png")
        install = client.get("/creation/paco/install.html")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-cache"
    assert "240" in page.text and "282" in page.text
    assert "> Paco</h1>" in page.text or "> Paco<" in page.text
    assert "hold PTT · wheel inbox" in page.text
    assert "CreationVoiceHandler" in script.text
    assert "wantsR1Response" in script.text
    assert "getUserMedia" not in script.text
    assert 'id="stage"' in page.text
    assert 'id="dialog"' in page.text
    assert 'id="rec"' not in page.text
    assert "webgl" not in script.text
    assert "/api/paco/text" in script.text
    assert "/api/paco/inbox" in script.text
    assert 'event: "paco "' in script.text
    assert icon.status_code == 200
    assert icon.content[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(icon.content[16:20], "big")
    height = int.from_bytes(icon.content[20:24], "big")
    assert (width, height) == (512, 512)
    assert "Install Paco" in install.text
    assert "/api/paco/install-qr.png" in install.text


def test_tito_text_reports_a_task_action() -> None:
    class TaskTito(FakeTito):
        def handle_text(self, text: str, channel: str = "r1") -> AgentResult:
            return AgentResult(reply="added", used_tools=["todoist_add"])

    app = _app(TaskTito(), FakePaco())
    with TestClient(app) as client:
        response = client.post(
            "/api/text",
            headers={"X-Assistant-Token": "secret"},
            json={"text": "add milk"},
        )
    assert response.status_code == 200
    assert response.json()["action"] == "task"


def test_factory_builds_paco_without_todoist(tmp_path) -> None:
    (tmp_path / "Home.md").write_text("home\n", encoding="utf-8")
    app = build_app(
        Settings(
            assistant_api_token="secret",
            openai_api_key="test-key",
            openai_model="gpt-4.1-mini",
            zayka_dir=str(tmp_path),
            zayka_sync_enabled=False,
            tick_interval_seconds=0,
            todoist_api_token="",
            google_refresh_token="",
            telegram_bot_token="",
            database_url="",
        )
    )
    assert isinstance(app.state.deps.paco, PacoAgent)
    assert app.state.deps.agent is None
