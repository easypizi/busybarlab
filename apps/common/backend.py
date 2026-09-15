"""Render backend interface and live BUSY Bar implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from busylib import BusyBar, converter, types

DisplaySide = Literal["front", "back"]
ElementKind = Literal["text", "image"]


@dataclass
class RenderElement:
    """One drawable element for either backend."""

    id: str
    kind: ElementKind
    x: int
    y: int
    display: DisplaySide = "front"
    text: str | None = None
    font: str = "small"
    color: str | None = None
    width: int | None = None
    scroll_rate: int | None = None
    scroll_start_delay: int | None = None
    scroll_repeat_delay: int | None = None
    path: str | None = None
    timeout: int | None = None


class DisplayBackend(ABC):
    """Common draw surface used by apps."""

    @abstractmethod
    def upload_asset(self, application_name: str, filename: str, data: bytes) -> str:
        raise NotImplementedError

    @abstractmethod
    def draw(self, application_name: str, elements: list[RenderElement]) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear(self, application_name: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class BusyBarBackend(DisplayBackend):
    """Live device backend via busylib."""

    def __init__(self, address: str = "10.0.4.20", token: str | None = None) -> None:
        kwargs: dict[str, Any] = {}
        if token:
            kwargs["token"] = token
        self._bb = BusyBar(address, **kwargs)
        self._uploaded: set[tuple[str, str]] = set()

    def upload_asset(self, application_name: str, filename: str, data: bytes) -> str:
        converted_name, payload = converter.convert_for_storage(filename, data)
        self._bb.assets_upload(
            application_name=application_name,
            filename=converted_name,
            data=payload,
        )
        self._uploaded.add((application_name, converted_name))
        return converted_name

    def draw(self, application_name: str, elements: list[RenderElement]) -> None:
        built: list[types.TextElement | types.ImageElement] = []
        for el in elements:
            display = (
                types.DisplayName.FRONT if el.display == "front" else types.DisplayName.BACK
            )
            if el.kind == "text":
                built.append(
                    types.TextElement(
                        id=el.id,
                        type="text",
                        x=el.x,
                        y=el.y,
                        display=display,
                        text=el.text or "",
                        font=el.font,  # type: ignore[arg-type]
                        color=el.color,
                        width=el.width,
                        scroll_rate=el.scroll_rate,
                        scroll_start_delay=el.scroll_start_delay,
                        scroll_repeat_delay=el.scroll_repeat_delay,
                        timeout=el.timeout,
                    )
                )
            elif el.kind == "image":
                built.append(
                    types.ImageElement(
                        id=el.id,
                        type="image",
                        x=el.x,
                        y=el.y,
                        display=display,
                        path=el.path,
                        timeout=el.timeout,
                    )
                )
        self._bb.display_draw(
            types.DisplayElements(application_name=application_name, elements=built)
        )

    def clear(self, application_name: str | None = None) -> None:
        try:
            if application_name:
                self._bb.display_clear(application_name=application_name)
                try:
                    self._bb.assets_delete(application_name=application_name)
                except Exception:
                    pass
            else:
                self._bb.display_clear()
        except Exception:
            # Device may already be gone (unplug / No route to host).
            pass

    def close(self) -> None:
        try:
            self._bb.close()
        except Exception:
            pass

    @property
    def client(self) -> BusyBar:
        return self._bb


@dataclass
class FrameBuffer:
    """In-memory RGB framebuffer used by the terminal simulator."""

    width: int
    height: int
    pixels: list[list[tuple[int, int, int]]] = field(init=False)

    def __post_init__(self) -> None:
        self.clear()

    def clear(self, color: tuple[int, int, int] = (0, 0, 0)) -> None:
        self.pixels = [[color for _ in range(self.width)] for _ in range(self.height)]

    def set_pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y][x] = color

    def blit(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        rgba_rows: list[list[tuple[int, int, int, int]]],
    ) -> None:
        for row_i, row in enumerate(rgba_rows):
            for col_i, (r, g, b, a) in enumerate(row):
                if a < 16:
                    continue
                self.set_pixel(x + col_i, y + row_i, (r, g, b))
