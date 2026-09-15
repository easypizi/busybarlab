"""HUD strip and multi-page overlays for the back OLED."""

from __future__ import annotations

import time
from typing import Any

from apps.common.backend import RenderElement
from apps.cursor_pet.state import PetState

BACK_W = 160
HUD_H = 12
PAGE_COUNT = 4
PAGE_TIMEOUT = 20.0


def branch_glyph(branch: str) -> str:
    return {"light": "*", "dark": "!", "gray": "."}.get(branch, ".")


def xp_bar(progress: float, width: int = 20) -> str:
    filled = int(max(0.0, min(1.0, progress)) * width)
    return "#" * filled + "-" * (width - filled)


def limit_bar(percent: float, width: int = 12) -> str:
    filled = int(max(0.0, min(100.0, percent)) / 100.0 * width)
    return "=" * filled + "." * (width - filled)


def alignment_slider(alignment: float, width: int = 21) -> str:
    pos = int((alignment + 1.0) / 2.0 * (width - 1))
    chars = ["-"] * width
    mid = width // 2
    chars[mid] = "|"
    chars[max(0, min(width - 1, pos))] = "O"
    return "D" + "".join(chars) + "L"


class HudController:
    def __init__(self) -> None:
        self.page = 0
        self.page_until = 0.0

    def next_page(self) -> None:
        self.page = (self.page + 1) % PAGE_COUNT
        self.page_until = time.time() + PAGE_TIMEOUT

    def prev_page(self) -> None:
        self.page = (self.page - 1) % PAGE_COUNT
        self.page_until = time.time() + PAGE_TIMEOUT

    def active_page(self) -> int:
        if self.page != 0 and time.time() > self.page_until:
            self.page = 0
        return self.page


def render_hud(
    state: PetState,
    hud: HudController,
    *,
    work_percent: float,
    personal_percent: float,
    work_online: bool,
    personal_online: bool,
    work_today: float,
    personal_today: float,
) -> list[RenderElement]:
    page = hud.active_page()
    prog = state.progress()
    elements: list[RenderElement] = []

    top = f"{state.name[:8]} L{state.level}{branch_glyph(state.branch)} {xp_bar(prog.progress, 14)}"
    elements.append(
        RenderElement(
            id="hud_top",
            kind="text",
            x=1,
            y=1,
            display="back",
            text=top[:40],
            font="tiny",
            color="#E0E0E0FF",
            width=BACK_W - 2,
        )
    )

    bottom = (
        f"W{limit_bar(work_percent, 8)}"
        f"{'' if work_online else '?'}"
        f" {alignment_slider(state.alignment, 11)} "
        f"P{limit_bar(personal_percent, 8)}"
        f"{'' if personal_online else '?'}"
    )
    elements.append(
        RenderElement(
            id="hud_bottom",
            kind="text",
            x=1,
            y=68,
            display="back",
            text=bottom[:42],
            font="tiny",
            color="#B0B0B0FF",
            width=BACK_W - 2,
        )
    )

    if page == 1:
        elements.append(
            RenderElement(
                id="page",
                kind="text",
                x=4,
                y=20,
                display="back",
                text=f"TODAY W ${work_today/100:.2f}  P ${personal_today/100:.2f}",
                font="small",
                color="#FFFFFFFF",
                width=BACK_W - 8,
            )
        )
    elif page == 2:
        models = sorted(state.model_window.items(), key=lambda kv: kv[1], reverse=True)[:4]
        lines = ["MODELS"] + [f"{m[:10]} {c/100:.2f}" for m, c in models]
        if len(lines) == 1:
            lines.append("none")
        elements.append(
            RenderElement(
                id="page",
                kind="text",
                x=4,
                y=18,
                display="back",
                text=" | ".join(lines)[:48],
                font="tiny",
                color="#FFFFFFFF",
                width=BACK_W - 8,
            )
        )
    elif page == 3:
        recent = state.journal[-3:] if state.journal else []
        text = "LOG " + " / ".join(str(j.get("message", ""))[:18] for j in recent)
        if state.achievements:
            text += f"  ACH:{len(state.achievements)}"
        elements.append(
            RenderElement(
                id="page",
                kind="text",
                x=4,
                y=20,
                display="back",
                text=text[:50],
                font="tiny",
                color="#FFFFFFFF",
                width=BACK_W - 8,
            )
        )

    return elements
