from pathlib import Path

from fastapi.testclient import TestClient

from toy_lair_assistant.main import create_app
from toy_lair_assistant.settings import Settings


def test_procfile_pins_single_worker() -> None:
    text = (Path(__file__).resolve().parents[1] / "Procfile").read_text()
    assert "--workers 1" in text


def test_health_ok() -> None:
    app = create_app(Settings(assistant_api_token="secret"))
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_creation_index_is_r1_sized() -> None:
    app = create_app(Settings(assistant_api_token="secret"))
    with TestClient(app) as client:
        response = client.get("/creation/index.html")
    assert response.status_code == 200
    body = response.text
    assert "240" in body
    assert "282" in body
    assert 'id="pair"' in body
    script = client.get("/creation/app.js")
    assert script.status_code == 200
    assert "herokuapp.com" in script.text
    assert "/api/pair/start" in script.text
    assert "waitForBridge" in script.text
    assert "creationStorage.plain" in script.text
    assert "paired via secure" in script.text
    assert "storage: local" in script.text
    assert "storage failed" in script.text
    assert 'id="hint"' in body
    assert "hold PTT talk" in body
    assert "wheel today" in body
    assert "PTT click done" not in body
    assert "wheel select" not in body
    assert 'id="rec"' in body
    assert 'id="count"' in body
    assert 'id="tap-gate"' in body
    assert 'id="peek"' in body
    assert "recWanted" in script.text
    assert "enableMic" in script.text
    assert "tap once for mic" in script.text
    assert "completeSelected" not in script.text
    assert "togglePeek" in script.text
