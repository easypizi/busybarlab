import logging

from fastapi.testclient import TestClient

from toy_lair_assistant.agent import AgentResult, ToolCall
from toy_lair_assistant.main import create_app
from toy_lair_assistant.settings import Settings


class FakeSpeech:
    def transcribe(self, data: bytes, mime: str) -> str:
        assert data == b"wav"
        return "add milk"

    def speak(self, text: str) -> str:
        return "YQ=="


class FakeAgent:
    def handle_text(self, text: str, channel: str = "r1") -> AgentResult:
        return AgentResult(reply="added milk", tool_calls=[])


def test_voice_requires_token() -> None:
    app = create_app(Settings(assistant_api_token="secret"), speech=FakeSpeech(), agent=FakeAgent())
    with TestClient(app) as client:
        response = client.post("/api/voice", files={"audio": ("a.wav", b"wav", "audio/wav")})
    assert response.status_code == 401


def test_voice_roundtrip() -> None:
    app = create_app(Settings(assistant_api_token="secret"), speech=FakeSpeech(), agent=FakeAgent())
    with TestClient(app) as client:
        response = client.post(
            "/api/voice",
            headers={"X-Assistant-Token": "secret"},
            files={"audio": ("a.wav", b"wav", "audio/wav")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "add milk"
    assert body["reply"] == "added milk"
    assert body["audio_base64"] == "YQ=="


class BoomSpeech:
    def transcribe(self, data: bytes, mime: str) -> str:
        raise RuntimeError("whisper down")

    def speak(self, text: str) -> str:
        return ""


class BoomAgent:
    def handle_text(self, text: str, channel: str = "r1"):
        raise RuntimeError("agent exploded")


def test_voice_surfaces_stt_error() -> None:
    app = create_app(Settings(assistant_api_token="secret"), speech=BoomSpeech(), agent=FakeAgent())
    with TestClient(app) as client:
        response = client.post(
            "/api/voice",
            headers={"X-Assistant-Token": "secret"},
            files={"audio": ("a.wav", b"wav", "audio/wav")},
        )
    assert response.status_code == 200
    assert "whisper down" in response.json()["reply"]


def test_voice_surfaces_agent_error() -> None:
    app = create_app(Settings(assistant_api_token="secret"), speech=FakeSpeech(), agent=BoomAgent())
    with TestClient(app) as client:
        response = client.post(
            "/api/voice",
            headers={"X-Assistant-Token": "secret"},
            files={"audio": ("a.wav", b"wav", "audio/wav")},
        )
    assert response.status_code == 200
    assert "agent exploded" in response.json()["reply"]


class LoggedAgent:
    def handle_text(self, text: str, channel: str = "r1") -> AgentResult:
        return AgentResult(
            reply="x" * 200,
            tool_calls=[ToolCall(name="todoist_add", arguments={"content": "milk"})],
        )


class CaptureNotify:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send_text(self, text: str) -> None:
        self.sent.append(text)


def test_voice_logs_agent_line_and_mirrors_long_reply(caplog) -> None:
    notify = CaptureNotify()
    app = create_app(
        Settings(assistant_api_token="secret"),
        speech=FakeSpeech(),
        agent=LoggedAgent(),
        notify=notify,
    )
    with caplog.at_level(logging.INFO):
        with TestClient(app) as client:
            response = client.post(
                "/api/voice",
                headers={"X-Assistant-Token": "secret"},
                files={"audio": ("a.wav", b"wav", "audio/wav")},
            )
    assert response.status_code == 200
    assert "agent channel=r1" in caplog.text
    assert "todoist_add" in caplog.text
    assert "ms=" in caplog.text
    assert notify.sent == ["x" * 200]
