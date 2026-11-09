"""Writer for the "Your Day" sheet: tasks, idea, poem and a four-panel roast comic."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

SKILL = (Path(__file__).parent / "skills" / "writer.md").read_text()
LINE_MAX = 16
CAPTION_MAX = 60
PROP_MAX = 8

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
        "comic": _obj(
            {
                "p1": _obj({"you": LINES, "printer": LINES}),
                "p2": _obj({"caption": {"type": "string"}, "speech": LINES}),
                "p3": _obj({"caption": {"type": "string"}, "speech": LINES, "prop": {"type": "string"}}),
                "p4": _obj({"caption": {"type": "string"}, "speech": LINES}),
            }
        ),
    }
)


def violations(out: dict) -> list[str]:
    bad: list[str] = []
    comic = out["comic"]

    def bubble(name: str, lines: list[str]) -> None:
        if not 1 <= len(lines) <= 2:
            bad.append(f"{name} must have 1 or 2 lines, has {len(lines)}")
        for line in lines:
            if len(line) > LINE_MAX:
                bad.append(f'{name} line "{line}" is {len(line)} characters, max {LINE_MAX}')

    bubble("p1.you", comic["p1"]["you"])
    bubble("p1.printer", comic["p1"]["printer"])
    for key in ("p2", "p3", "p4"):
        bubble(f"{key}.speech", comic[key]["speech"])
        if len(comic[key]["caption"]) > CAPTION_MAX:
            bad.append(f"{key}.caption is {len(comic[key]['caption'])} characters, max {CAPTION_MAX}")
    if len(comic["p3"]["prop"]) > PROP_MAX:
        bad.append(f"p3.prop is longer than {PROP_MAX} characters")
    if len(out["poem"]) != 4:
        bad.append("poem must have exactly 4 lines")
    if not 0 <= len(out["tasks"]) <= 5:
        bad.append("tasks must have at most 5 items")
    return bad


DEFAULT_COMIC = {
    "p1": {"you": ["Print me a", "good morning"], "printer": ["Define good."]},
    "p2": {"caption": "Meanwhile, at 6:58 AM", "speech": ["Five more", "minutes."]},
    "p3": {"caption": "The alarm arrives", "speech": ["It says", "I'm late."], "prop": "7:00 AM"},
    "p4": {"caption": "Productivity curve", "speech": ["Trending", "down."]},
}


def _trim_line(line: str) -> str:
    if len(line) <= LINE_MAX:
        return line
    cut = line[:LINE_MAX]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut


def force_fit(out: dict) -> dict:
    """Last resort: hard-trim anything still over the limits."""
    comic = out["comic"]
    for bubble in (comic["p1"]["you"], comic["p1"]["printer"], comic["p2"]["speech"], comic["p3"]["speech"], comic["p4"]["speech"]):
        bubble[:] = [_trim_line(line) for line in bubble[:2]]
    for key in ("p2", "p3", "p4"):
        comic[key]["caption"] = comic[key]["caption"][:CAPTION_MAX].rsplit(" ", 1)[0] if len(comic[key]["caption"]) > CAPTION_MAX else comic[key]["caption"]
    comic["p3"]["prop"] = comic["p3"]["prop"][:PROP_MAX]
    out["poem"] = out["poem"][:4]
    out["tasks"] = out["tasks"][:5]
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
        comic_bad = [v for v in violations(out) if v.startswith("p")]
        if comic_bad:
            out["comic"] = copy.deepcopy(DEFAULT_COMIC)
        out = force_fit(out)
    return out
