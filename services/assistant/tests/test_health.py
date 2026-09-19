from fastapi.testclient import TestClient

from toy_lair_assistant.main import create_app
from toy_lair_assistant.settings import Settings


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
