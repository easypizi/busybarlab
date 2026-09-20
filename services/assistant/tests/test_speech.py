import httpx

from toy_lair_assistant.speech import OpenAISpeech


def _speech(handler) -> OpenAISpeech:
    return OpenAISpeech(
        api_key="k",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_transcribe_uses_ogg_filename() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["files"] = request.content
        return httpx.Response(200, json={"text": "hello"})

    text = _speech(handler).transcribe(b"oggbytes", "audio/ogg;codecs=opus")
    assert text == "hello"
    assert b'filename="clip.ogg"' in seen["files"]


def test_transcribe_uses_m4a_filename_for_mp4() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["files"] = request.content
        return httpx.Response(200, json={"text": "hi"})

    text = _speech(handler).transcribe(b"mp4bytes", "audio/mp4")
    assert text == "hi"
    assert b'filename="clip.m4a"' in seen["files"]
