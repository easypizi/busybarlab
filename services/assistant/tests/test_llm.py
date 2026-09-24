import json

import httpx

from toy_lair_assistant.llm import OpenAILLM


def test_complete_omits_tools_key_when_empty() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}", "tool_calls": []}}]},
        )

    llm = OpenAILLM(
        api_key="k",
        model="gpt-4.1-mini",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = llm.complete([{"role": "user", "content": "hi"}], [])
    assert "tools" not in seen["body"]
    assert result.reply == "{}"


def test_complete_includes_tools_when_named() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok", "tool_calls": []}}]},
        )

    llm = OpenAILLM(
        api_key="k",
        model="gpt-4.1-mini",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    llm.complete([{"role": "user", "content": "hi"}], ["todoist_today"])
    names = [item["function"]["name"] for item in seen["body"]["tools"]]
    assert names == ["todoist_today"]


def test_complete_uses_passed_schemas_instead_of_tito_catalog() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok", "tool_calls": []}}]},
        )

    llm = OpenAILLM(
        api_key="k",
        model="gpt-4.1-mini",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "paco_only",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    llm.complete([{"role": "user", "content": "hi"}], ["paco_only"], schemas)
    names = [item["function"]["name"] for item in seen["body"]["tools"]]
    assert names == ["paco_only"]
