"""Terminal ANSI simulator for BUSY Bar front and back displays."""

from __future__ import annotations

import io
import sys
from typing import BinaryIO

from PIL import Image, ImageDraw, ImageFont

from apps.common.backend import DisplayBackend, FrameBuffer, RenderElement
from apps.common.pixelart import image_to_rgba_rows

FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80


def _rgb_cell(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m█\x1b[0m"


def _gray_cell(v: int) -> str:
    return f"\x1b[38;2;{v};{v};{v}m█\x1b[0m"


class TerminalBackend(DisplayBackend):
    """Draws frames into stdout as colored block characters."""

    def __init__(self, out: BinaryIO | None = None, *, clear_screen: bool = True) -> None:
        self._out = out or sys.stdout.buffer
        self._clear_screen = clear_screen
        self._front = FrameBuffer(FRONT_W, FRONT_H)
        self._back = FrameBuffer(BACK_W, BACK_H)
        self._assets: dict[str, bytes] = {}
        self._text_cache: dict[tuple[str, str, str | None], Image.Image] = {}
        self.frame_count = 0

    def upload_asset(self, application_name: str, filename: str, data: bytes) -> str:
        key = f"{application_name}/{filename}"
        self._assets[key] = data
        self._assets[filename] = data
        return filename

    def draw(self, application_name: str, elements: list[RenderElement]) -> None:
        self._front.clear()
        self._back.clear()
        for el in elements:
            buf = self._front if el.display == "front" else self._back
            if el.kind == "image" and el.path:
                data = self._assets.get(el.path) or self._assets.get(
                    f"{application_name}/{el.path}"
                )
                if data is None:
                    continue
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                buf.blit(el.x, el.y, img.width, img.height, image_to_rgba_rows(img))
            elif el.kind == "text":
                self._blit_text(buf, el)
        self._render()
        self.frame_count += 1

    def _blit_text(self, buf: FrameBuffer, el: RenderElement) -> None:
        text = el.text or ""
        color = el.color or "#ffffff"
        if color.startswith("#") and len(color) >= 7:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
        else:
            r, g, b = 255, 255, 255
        # Approximate device fonts with a tiny bitmap font via default PIL font.
        cache_key = (text, el.font, color)
        img = self._text_cache.get(cache_key)
        if img is None:
            font_size = {
                "tiny": 6,
                "small": 8,
                "normal": 9,
                "condensed": 8,
                "bold": 9,
                "large": 11,
                "extra_large": 13,
                "global": 9,
            }.get(el.font, 8)
            try:
                font = ImageFont.load_default(size=font_size)
            except TypeError:
                font = ImageFont.load_default()
            # Measure then draw.
            probe = Image.new("RGBA", (1, 1))
            probe_draw = ImageDraw.Draw(probe)
            bbox = probe_draw.textbbox((0, 0), text, font=font)
            tw = max(1, bbox[2] - bbox[0])
            th = max(1, bbox[3] - bbox[1])
            img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.text((-bbox[0], -bbox[1]), text, fill=(r, g, b, 255), font=font)
            self._text_cache[cache_key] = img
        # Optional width clip for scrolling marquees: show a window.
        if el.width and img.width > el.width:
            offset = (self.frame_count * 2) % max(1, img.width + el.width)
            window = Image.new("RGBA", (el.width, img.height), (0, 0, 0, 0))
            window.paste(img, (el.width - offset, 0), img)
            img = window
        buf.blit(el.x, el.y, img.width, img.height, image_to_rgba_rows(img))

    def _render(self) -> None:
        lines: list[str] = []
        if self._clear_screen:
            lines.append("\x1b[H\x1b[2J")
        lines.append(f"FRONT {FRONT_W}x{FRONT_H}  frame={self.frame_count}")
        for row in self._front.pixels:
            lines.append("".join(_rgb_cell(*px) for px in row))
        lines.append("")
        lines.append(f"BACK {BACK_W}x{BACK_H}")
        # Downsample back display vertically for readability in terminal.
        step_y = 2
        step_x = 2
        for y in range(0, BACK_H, step_y):
            row_chars: list[str] = []
            for x in range(0, BACK_W, step_x):
                r, g, b = self._back.pixels[y][x]
                v = (r + g + b) // 3
                row_chars.append(_gray_cell(v))
            lines.append("".join(row_chars))
        lines.append("")
        payload = ("\n".join(lines) + "\n").encode("utf-8", errors="replace")
        self._out.write(payload)
        self._out.flush()

    def clear(self, application_name: str | None = None) -> None:
        self._front.clear()
        self._back.clear()
        if application_name:
            prefix = f"{application_name}/"
            self._assets = {
                k: v for k, v in self._assets.items() if not k.startswith(prefix)
            }
        self._render()

    def close(self) -> None:
        return
