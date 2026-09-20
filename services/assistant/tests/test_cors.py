from fastapi.testclient import TestClient

from toy_lair_assistant.main import create_app
from toy_lair_assistant.settings import Settings


def test_pair_start_allows_pages_origin() -> None:
    app = create_app(
        Settings(
            assistant_api_token="secret",
            tick_interval_seconds=0,
            zayka_dir="",
            creation_public_url="https://easypizi.github.io/toy_lair/",
        )
    )
    with TestClient(app) as client:
        res = client.options(
            "/api/pair/start",
            headers={
                "Origin": "https://easypizi.github.io",
                "Access-Control-Request-Method": "POST",
            },
        )
        info = client.get("/api/creation-url")
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://easypizi.github.io"
    assert info.status_code == 200
    assert info.json()["url"] == "https://easypizi.github.io/toy_lair/"
