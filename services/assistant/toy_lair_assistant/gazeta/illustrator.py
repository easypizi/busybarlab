"""Front-page engraving through the OpenAI image API. Failure means no picture."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
STYLE = (Path(__file__).parent / "skills" / "illustrator.md").read_text().strip()


def build_prompt(scene: str) -> str:
    return f"{STYLE}\n\nScene: {scene.strip()}"


def make(client: Any, model: str, scene: str) -> str | None:
    try:
        png = client.image(model, build_prompt(scene), "1536x1024")
    except Exception as exc:
        log.warning("illustration failed: %s", exc)
        return None
    return "data:image/png;base64," + base64.b64encode(png).decode()
