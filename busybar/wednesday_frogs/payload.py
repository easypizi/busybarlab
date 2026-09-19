"""Shared /api/display/draw payload for Python install and Flipper remote."""

from __future__ import annotations

from busybar.wednesday_frogs.animation import marquee_text

APP_NAME = "wednesday-frogs"
HAPPY_ANIM = "frogs_happy.anim"
SAD_ANIM = "frogs_sad.anim"


def build_draw_payload(*, sad: bool, marquee: bool = True) -> dict:
    """JSON-ready body for POST /api/display/draw."""
    filename = SAD_ANIM if sad else HAPPY_ANIM
    elements: list[dict] = [
        {
            "id": "frogs",
            "type": "animation",
            "x": 0,
            "y": 0,
            "display": "front",
            "path": filename,
            "loop": True,
        }
    ]
    if marquee:
        wednesday = not sad
        elements.append(
            {
                "id": "marquee",
                "type": "text",
                "x": 0,
                "y": 0,
                "display": "front",
                "text": marquee_text(wednesday),
                "font": "small",
                "color": "#7CFC00FF" if wednesday else "#A0A0A0FF",
                "width": 72,
                "scroll_rate": 700,
                "scroll_start_delay": 400,
                "scroll_repeat_delay": 2500,
            }
        )
    return {"application_name": APP_NAME, "elements": elements}
