from toy_lair_assistant.clients.telegram import TelegramBot


class FakeAgent:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def handle_text(self, text: str, channel: str = "telegram"):
        self.seen.append(text)
        return type("R", (), {"reply": "done: " + text})()


class FakeSpeech:
    def transcribe(self, data: bytes, mime: str) -> str:
        return "voice task"

    def speak(self, text: str) -> str:
        return "YQ=="


def test_ignores_unknown_chat() -> None:
    sent: list[dict] = []
    bot = TelegramBot(
        token="bot",
        chat_id="111",
        sender=lambda payload: sent.append(payload),
    )
    bot.handle_update(
        {"message": {"chat": {"id": 999}, "text": "hi"}},
        FakeAgent(),
        FakeSpeech(),
    )
    assert sent == []


def test_text_from_allowed_chat_goes_to_agent() -> None:
    sent: list[dict] = []
    agent = FakeAgent()
    bot = TelegramBot(
        token="bot",
        chat_id="111",
        sender=lambda payload: sent.append(payload),
    )
    bot.handle_update(
        {"message": {"chat": {"id": 111}, "text": "add milk"}},
        agent,
        FakeSpeech(),
    )
    assert agent.seen == ["add milk"]
    assert sent[0]["chat_id"] == "111"
    assert sent[0]["text"] == "done: add milk"


def test_voice_is_transcribed() -> None:
    sent: list[dict] = []
    agent = FakeAgent()
    bot = TelegramBot(
        token="bot",
        chat_id="111",
        sender=lambda payload: sent.append(payload),
        downloader=lambda file_id: b"ogg",
    )
    bot.handle_update(
        {"message": {"chat": {"id": 111}, "voice": {"file_id": "f1"}}},
        agent,
        FakeSpeech(),
    )
    assert agent.seen == ["voice task"]
    assert "done: voice task" in sent[0]["text"]
