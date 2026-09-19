"""ASCII pixel maps to PNG bytes via Pillow."""

from __future__ import annotations

import io
from typing import Mapping

from PIL import Image

DEFAULT_PALETTE: dict[str, tuple[int, int, int, int]] = {
    ".": (0, 0, 0, 0),
    " ": (0, 0, 0, 0),
    "G": (46, 184, 64, 255),
    "g": (30, 120, 42, 255),
    "W": (255, 255, 255, 255),
    "B": (20, 20, 20, 255),
    "Y": (240, 210, 40, 255),
    "R": (220, 40, 40, 255),
    "P": (200, 80, 180, 255),
    "O": (230, 140, 40, 255),
    "C": (80, 180, 220, 255),
    "S": (140, 140, 140, 255),
    "s": (90, 90, 90, 255),
    "L": (180, 220, 180, 255),
    "D": (60, 60, 70, 255),
    "H": (200, 200, 210, 255),
    "1": (16, 16, 16, 255),
    "2": (48, 48, 48, 255),
    "3": (80, 80, 80, 255),
    "4": (112, 112, 112, 255),
    "5": (144, 144, 144, 255),
    "6": (176, 176, 176, 255),
    "7": (208, 208, 208, 255),
    "8": (240, 240, 240, 255),
}


def ascii_to_image(
    rows: list[str],
    palette: Mapping[str, tuple[int, int, int, int]] | None = None,
) -> Image.Image:
    """Convert ASCII art rows into an RGBA Pillow image."""
    if not rows:
        raise ValueError("rows must not be empty")
    width = max(len(row) for row in rows)
    height = len(rows)
    colors = dict(DEFAULT_PALETTE)
    if palette:
        colors.update(palette)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = img.load()
    assert pixels is not None
    for y, row in enumerate(rows):
        for x, ch in enumerate(row.ljust(width)):
            pixels[x, y] = colors.get(ch, (0, 0, 0, 0))
    return img


def ascii_to_png_bytes(
    rows: list[str],
    palette: Mapping[str, tuple[int, int, int, int]] | None = None,
) -> bytes:
    """Encode ASCII art as PNG bytes."""
    img = ascii_to_image(rows, palette)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def image_to_rgba_rows(img: Image.Image) -> list[list[tuple[int, int, int, int]]]:
    """Flatten an image into RGBA rows for the terminal simulator blit."""
    rgba = img.convert("RGBA")
    width, height = rgba.size
    data = list(rgba.getdata())
    rows: list[list[tuple[int, int, int, int]]] = []
    for y in range(height):
        start = y * width
        rows.append([tuple(data[start + x]) for x in range(width)])  # type: ignore[misc]
    return rows
