"""Writer for the "Your Day" sheet: tasks, idea of the day and a poem."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .editor import clean_tree

SKILL = (Path(__file__).parent / "skills" / "writer.md").read_text()
MAX_TASKS = 5

LINES = {"type": "array", "items": {"type": "string"}}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


SCHEMA = _obj(
    {
        "tasks": {
            "type": "array",
            "items": _obj({"title": {"type": "string"}, "note": {"type": "string"}, "origin": {"type": "string", "enum": ["calendar", "todoist", "mail"]}}),
        },
        "idea": _obj({"hook": {"type": "string"}, "text": {"type": "string"}}),
        "poem": LINES,
    }
)


def violations(out: dict) -> list[str]:
    bad: list[str] = []
    if len(out["poem"]) != 4:
        bad.append("poem must have exactly 4 lines")
    if len(out["tasks"]) > MAX_TASKS:
        bad.append(f"tasks must have at most {MAX_TASKS} items")
    return bad


def force_fit(out: dict) -> dict:
    """Last resort: hard-trim anything still over the limits."""
    out["poem"] = out["poem"][:4]
    out["tasks"] = out["tasks"][:MAX_TASKS]
    return out


def write(client: Any, model: str, context: dict, retries: int = 2) -> dict:
    user = json.dumps(context, ensure_ascii=False)
    out = client.chat_json(model, SKILL, user, SCHEMA, "your_day")
    for _ in range(retries):
        bad = violations(out)
        if not bad:
            break
        fix = user + "\n\nYour previous draft broke these limits. Rewrite the whole sheet and fix them:\n- " + "\n- ".join(bad) + "\n\nPrevious draft:\n" + json.dumps(out, ensure_ascii=False)
        out = client.chat_json(model, SKILL, fix, SCHEMA, "your_day")
    if violations(out):
        out = force_fit(out)
    return clean_tree(out)
