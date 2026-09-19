"""Pet scene composition for the back OLED."""

from __future__ import annotations

import time

from busybar.common.backend import RenderElement
from busybar.cursor_pet.hud import HudController, render_hud
from busybar.cursor_pet.sprites import build_pet_png
from busybar.cursor_pet.state import PetState

APP_NAME = "cursor-pet"


class PetScene:
    def __init__(self) -> None:
        self.hud = HudController()
        self.work_food_until = 0.0
        self.personal_food_until = 0.0
        self.work_percent = 0.0
        self.personal_percent = 0.0
        self.work_online = False
        self.personal_online = False
        self.work_today = 0.0
        self.personal_today = 0.0
        self._uploaded_key: str | None = None
        self.announce: str | None = None
        self.announce_until = 0.0

    def note_food(self, account: str) -> None:
        now = time.time()
        if account == "work":
            self.work_food_until = now + 4.0
        else:
            self.personal_food_until = now + 4.0

    def set_account_status(
        self,
        *,
        work_percent: float,
        personal_percent: float,
        work_online: bool,
        personal_online: bool,
        work_today: float,
        personal_today: float,
    ) -> None:
        self.work_percent = work_percent
        self.personal_percent = personal_percent
        self.work_online = work_online
        self.personal_online = personal_online
        self.work_today = work_today
        self.personal_today = personal_today

    def flash_announce(self, text: str, seconds: float = 6.0) -> None:
        self.announce = text
        self.announce_until = time.time() + seconds

    def ensure_sprites(self, backend, state: PetState) -> str:
        fatness = min(1.0, state.cycle_eaten_cents / 5000.0)
        happy = time.time() < state.pet_flash_until
        key = f"{state.branch}:{state.tier}:{','.join(state.traits)}:{state.last_accessory}:{fatness:.2f}:{happy}"
        filename = "pet_current.png"
        if self._uploaded_key != key:
            from busybar.common.pixelart import ascii_to_png_bytes
            from busybar.cursor_pet.sprites import BOWL_P, BOWL_W, FOOD, egg

            if state.level == 0 and state.xp < 1:
                png = ascii_to_png_bytes(egg())
            else:
                png = build_pet_png(
                    state.branch,
                    state.traits,
                    state.last_accessory,
                    fatness=fatness,
                    happy=happy,
                )
            backend.upload_asset(APP_NAME, filename, png)
            backend.upload_asset(APP_NAME, "bowl_w.png", ascii_to_png_bytes(BOWL_W))
            backend.upload_asset(APP_NAME, "bowl_p.png", ascii_to_png_bytes(BOWL_P))
            backend.upload_asset(APP_NAME, "food.png", ascii_to_png_bytes(FOOD))
            self._uploaded_key = key
        return filename

    def render(self, backend, state: PetState) -> list[RenderElement]:
        pet_path = self.ensure_sprites(backend, state)
        now = time.time()
        elements: list[RenderElement] = []
        page = self.hud.active_page()

        elements.extend(
            render_hud(
                state,
                self.hud,
                work_percent=self.work_percent,
                personal_percent=self.personal_percent,
                work_online=self.work_online,
                personal_online=self.personal_online,
                work_today=self.work_today,
                personal_today=self.personal_today,
            )
        )

        if page == 0:
            elements.append(
                RenderElement(
                    id="bowl_w",
                    kind="image",
                    x=8,
                    y=40,
                    display="back",
                    path="bowl_w.png",
                )
            )
            elements.append(
                RenderElement(
                    id="bowl_p",
                    kind="image",
                    x=140,
                    y=40,
                    display="back",
                    path="bowl_p.png",
                )
            )
            if now < self.work_food_until:
                elements.append(
                    RenderElement(
                        id="food_w",
                        kind="image",
                        x=10,
                        y=34,
                        display="back",
                        path="food.png",
                    )
                )
            if now < self.personal_food_until:
                elements.append(
                    RenderElement(
                        id="food_p",
                        kind="image",
                        x=142,
                        y=34,
                        display="back",
                        path="food.png",
                    )
                )
            pet_x = 68
            if now < self.work_food_until:
                pet_x = 30
            elif now < self.personal_food_until:
                pet_x = 110
            elements.append(
                RenderElement(
                    id="pet",
                    kind="image",
                    x=pet_x,
                    y=28,
                    display="back",
                    path=pet_path,
                )
            )

            panic = max(self.work_percent, self.personal_percent)
            if panic >= 90:
                elements.append(
                    RenderElement(
                        id="panic",
                        kind="text",
                        x=40,
                        y=16,
                        display="back",
                        text="LIMIT!!",
                        font="small",
                        color="#FFFFFFFF",
                    )
                )
            elif panic >= 75:
                elements.append(
                    RenderElement(
                        id="worry",
                        kind="text",
                        x=50,
                        y=16,
                        display="back",
                        text="...",
                        font="small",
                        color="#C0C0C0FF",
                    )
                )

        if self.announce and now < self.announce_until:
            elements.append(
                RenderElement(
                    id="front_announce",
                    kind="text",
                    x=0,
                    y=4,
                    display="front",
                    text=self.announce,
                    font="small",
                    color="#7CFC00FF",
                    width=72,
                    scroll_rate=650,
                    scroll_start_delay=100,
                    scroll_repeat_delay=1200,
                    timeout=int((self.announce_until - now) * 1000),
                )
            )

        return elements
