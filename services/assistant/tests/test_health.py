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
    assert "cache-control" not in response.headers


def test_creation_index_is_r1_sized() -> None:
    app = create_app(Settings(assistant_api_token="secret"))
    with TestClient(app) as client:
        response = client.get("/creation/index.html")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    body = response.text
    assert "240" in body
    assert "282" in body
    assert 'id="pair"' in body
    script = client.get("/creation/app.js")
    assert script.status_code == 200
    assert script.headers["cache-control"] == "no-cache"
    assert "herokuapp.com" in script.text
    assert "/api/pair/start" in script.text
    assert "waitForBridge" in script.text
    assert "creationStorage.plain" in script.text
    assert "paired via secure" in script.text
    assert "storage: local" in script.text
    assert "storage failed" in script.text
    assert 'id="hint"' in body
    assert "hold PTT or circle" in body
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
    assert 'rel="icon"' in body
    assert "icon.png" in body
    assert "> Tito</h1>" in body or "> Tito<" in body
    assert "<title>Tito</title>" in body
    css = client.get("/creation/styles.css")
    assert css.status_code == 200
    assert "#FE5000" in css.text
    assert "@keyframes" in css.text
    assert "64px" in css.text
    assert "#reply.long" in css.text
    script = client.get("/creation/app.js")
    assert "setReply" in script.text
    assert "scrollReply" in script.text
    assert "client-log" in script.text
    assert "audio/ogg" in script.text
    assert "touchend" in script.text
    assert "start(250)" in script.text
    assert "mic timeout" in script.text
    assert "stop timeout" in script.text
    assert "empty clip" in script.text
    icon = client.get("/creation/icon.png")
    assert icon.status_code == 200
    assert icon.content[:8] == b"\x89PNG\r\n\x1a\n"
    short = client.get("/i.png")
    assert short.status_code == 200
    assert short.content == icon.content
    tito = client.get("/creation/tito.png")
    assert tito.status_code == 200
    assert tito.content[:8] == b"\x89PNG\r\n\x1a\n"
    via_root = client.get("/tito.png")
    assert via_root.status_code == 200
    assert via_root.content == tito.content
    width = int.from_bytes(tito.content[16:20], "big")
    height = int.from_bytes(tito.content[20:24], "big")
    assert width == 512
    assert height == 512
