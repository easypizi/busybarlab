"""Draw Tito and Paco once. Icons, cast.js, and the static mirrors come from here."""

from __future__ import annotations

import json
import shutil
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRID = 64
ICON = 512

PALETTE = [
    "#111111",
    "#e8b892",
    "#c48c68",
    "#6b3a22",
    "#8d5230",
    "#3a2418",
    "#2a2c34",
    "#16181e",
    "#f4f4f4",
    "#fe5000",
    "#c2410c",
    "#1a9b96",
    "#e25b8a",
    "#2a4a8a",
    "#8eb4ff",
    "#d7e4ee",
    "#e2c56a",
    "#8a6a28",
    "#c4322e",
    "#5c4030",
    "#f7f1e4",
    "#7d8796",
    "#e6c44a",
    "#3d6b52",
    "#2a4638",
    "#f2d7a2",
]


def blank() -> list[list[int]]:
    return [[0] * GRID for _ in range(GRID)]


def pix(buf: list[list[int]], x: int, y: int, color: int) -> None:
    if 0 <= x < GRID and 0 <= y < GRID and color:
        buf[y][x] = color


def rect(buf: list[list[int]], x: int, y: int, w: int, h: int, color: int) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            pix(buf, xx, yy, color)


def disc(buf: list[list[int]], cx: int, cy: int, rx: int, ry: int, color: int) -> None:
    for y in range(cy - ry, cy + ry + 1):
        for x in range(cx - rx, cx + rx + 1):
            if rx and ry and ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.05:
                pix(buf, x, y, color)


def stamp(buf: list[list[int]], x: int, y: int, rows: list[str], colors: dict[str, int]) -> None:
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch in colors:
                pix(buf, x + dx, y + dy, colors[ch])


def layer_from(buf: list[list[int]]) -> list[int]:
    out: list[int] = []
    for y, row in enumerate(buf):
        for x, color in enumerate(row):
            if color:
                out.extend((x, y, color))
    return out


def diff(full: list[list[int]], base: list[list[int]]) -> list[int]:
    out: list[int] = []
    for y in range(GRID):
        for x in range(GRID):
            if full[y][x] and full[y][x] != base[y][x]:
                out.extend((x, y, full[y][x]))
    return out


def clone(buf: list[list[int]]) -> list[list[int]]:
    return [row[:] for row in buf]


SKIN = {"s": 1, "S": 2}
MOUTH = {
    "shut": ["  sssss", " sSSSSSs"],
    "a": ["  kkkkk", " k8s8s8k", "  kkkkk"],
    "o": ["  kkk", " k8s8k", " ksss k", "  kkk"],
    "e": [" kkkkkk", "k8ssss8k", " kkkkkk"],
    "m": [" ssssss", " SSSSSS"],
    "con": ["  kkkk", " kssssk", "  kkkk"],
}


def mouths(origin_x: int, origin_y: int) -> dict[str, list[int]]:
    colors = {"s": 1, "S": 2, "k": 6, "8": 8}
    out = {}
    for name, rows in MOUTH.items():
        buf = blank()
        stamp(buf, origin_x, origin_y, rows, colors)
        out["mouth_" + name] = layer_from(buf)
    return out


def tito_layers() -> dict[str, list[int]]:
    body = blank()
    disc(body, 32, 54, 20, 12, 6)
    rect(body, 14, 50, 36, 14, 6)
    rect(body, 12, 58, 40, 6, 7)
    rect(body, 26, 44, 12, 16, 8)
    for i in range(12):
        pix(body, 25 - i // 4, 46 + i, 6)
        pix(body, 38 + i // 4, 46 + i, 6)
    for y in (52, 56, 60):
        pix(body, 31, y, 10)
        pix(body, 32, y, 10)
    # orange embroidery on the vest edge
    for x in range(16, 26, 2):
        pix(body, x, 52, 13)
        pix(body, 63 - x, 52, 12)
    rect(body, 28, 38, 8, 6, 2)

    head = blank()
    disc(head, 32, 24, 13, 14, 1)
    disc(head, 32, 22, 12, 12, 1)
    rect(head, 18, 22, 3, 6, 1)
    rect(head, 43, 22, 3, 6, 1)
    pix(head, 18, 24, 2)
    pix(head, 45, 24, 2)
    pix(head, 31, 30, 2)
    pix(head, 32, 30, 2)
    pix(head, 32, 31, 2)

    hair = blank()
    disc(hair, 32, 15, 13, 8, 4)
    rect(hair, 20, 12, 24, 6, 5)
    rect(hair, 22, 10, 20, 3, 4)
    rect(hair, 19, 18, 3, 6, 5)
    rect(hair, 42, 18, 3, 6, 5)

    mustache = blank()
    stamp(mustache, 26, 32, [" mm m mm", "mmmmmmmmm"], {"m": 5})

    eyes = blank()
    rect(eyes, 22, 22, 20, 6, 6)
    rect(eyes, 23, 23, 8, 4, 13)
    rect(eyes, 33, 23, 8, 4, 13)
    pix(eyes, 24, 23, 14)
    pix(eyes, 34, 23, 14)
    pix(eyes, 31, 24, 6)
    pix(eyes, 32, 24, 6)
    shut = blank()
    rect(shut, 22, 24, 9, 2, 6)
    rect(shut, 33, 24, 9, 2, 8)

    brows = blank()
    rect(brows, 22, 20, 8, 2, 5)
    rect(brows, 34, 20, 8, 2, 5)

    bow = blank()
    rect(bow, 21, 40, 8, 6, 10)
    rect(bow, 35, 40, 8, 6, 10)
    rect(bow, 22, 41, 6, 4, 9)
    rect(bow, 36, 41, 6, 4, 9)
    rect(bow, 29, 41, 6, 4, 10)
    pix(bow, 31, 42, 8)
    pix(bow, 32, 42, 8)

    calendar = blank()
    rect(calendar, 44, 46, 14, 14, 6)
    rect(calendar, 45, 47, 12, 12, 20)
    rect(calendar, 45, 47, 12, 3, 9)
    # papel picado notches
    for x in (46, 49, 52, 55):
        pix(calendar, x, 47, 13)
    pix(calendar, 47, 46, 8)
    pix(calendar, 54, 46, 8)
    for y in (52, 55):
        for x in (47, 50, 53):
            pix(calendar, x, y, 22)
            pix(calendar, x + 1, y, 22)
    lit = blank()
    rect(lit, 50, 54, 2, 2, 10)

    hand = blank()
    rect(hand, 16, 48, 4, 3, 1)
    pix(hand, 17, 47, 1)

    layers = {
        "body": layer_from(body),
        "head": layer_from(head),
        "hair": layer_from(hair),
        "mustache": layer_from(mustache),
        "eyes": layer_from(eyes),
        "eyes_shut": layer_from(shut),
        "brows": layer_from(brows),
        "bow": layer_from(bow),
        "hand": layer_from(hand),
        "prop": layer_from(calendar),
        "mark": layer_from(lit),
        "hand": layer_from(hand),
    }
    layers.update(mouths(27, 33))
    return layers


def paco_layers() -> dict[str, list[int]]:
    body = blank()
    disc(body, 30, 54, 18, 12, 24)
    rect(body, 14, 48, 32, 14, 24)
    rect(body, 12, 58, 36, 6, 24)
    # guayabera pleats
    for x in (22, 26, 34, 38):
        rect(body, x, 50, 1, 10, 11)
    rect(body, 24, 42, 12, 5, 9)
    pix(body, 27, 44, 10)
    pix(body, 32, 44, 10)
    rect(body, 26, 37, 8, 6, 2)
    # bandana
    rect(body, 24, 40, 12, 3, 18)
    pix(body, 29, 43, 10)
    pix(body, 30, 43, 13)

    head = blank()
    disc(head, 30, 24, 12, 14, 1)
    disc(head, 30, 22, 11, 12, 1)
    rect(head, 17, 22, 3, 6, 1)
    rect(head, 40, 22, 3, 6, 1)
    pix(head, 17, 24, 2)
    pix(head, 42, 24, 2)
    pix(head, 29, 30, 2)
    pix(head, 30, 30, 2)

    hair = blank()
    disc(hair, 30, 15, 12, 7, 5)
    rect(hair, 19, 13, 22, 5, 4)
    rect(hair, 22, 11, 16, 3, 5)
    rect(hair, 19, 18, 2, 4, 5)
    rect(hair, 39, 18, 2, 4, 5)

    hat = blank()
    disc(hat, 30, 11, 11, 5, 17)
    rect(hat, 14, 14, 32, 3, 16)
    rect(hat, 20, 8, 20, 4, 17)
    pix(hat, 18, 14, 19)
    pix(hat, 41, 14, 19)

    mustache = blank()
    stamp(mustache, 24, 32, [" mmmmmmm", "mmmmmmmmm"], {"m": 5})

    eyes = blank()
    rect(eyes, 20, 22, 8, 6, 6)
    rect(eyes, 31, 22, 8, 6, 6)
    rect(eyes, 21, 23, 6, 4, 15)
    rect(eyes, 32, 23, 6, 4, 15)
    pix(eyes, 22, 24, 6)
    pix(eyes, 25, 24, 6)
    pix(eyes, 33, 24, 6)
    pix(eyes, 36, 24, 6)
    pix(eyes, 28, 24, 6)
    pix(eyes, 29, 24, 6)
    shut = blank()
    rect(shut, 20, 24, 8, 2, 6)
    rect(shut, 31, 24, 8, 2, 6)

    brows = blank()
    rect(brows, 20, 20, 8, 2, 5)
    rect(brows, 31, 20, 8, 2, 5)

    pencil = blank()
    rect(pencil, 41, 10, 2, 12, 22)
    pix(pencil, 41, 9, 8)
    pix(pencil, 42, 9, 8)
    pix(pencil, 41, 22, 2)
    pix(pencil, 42, 22, 2)
    bite = blank()
    rect(bite, 33, 30, 10, 2, 22)
    pix(bite, 43, 30, 8)
    pix(bite, 33, 31, 2)

    notebook = blank()
    rect(notebook, 40, 44, 18, 16, 19)
    rect(notebook, 42, 46, 14, 12, 20)
    rect(notebook, 40, 44, 2, 16, 10)
    lines = []
    for index, y in enumerate((48, 51, 54)):
        row = blank()
        rect(row, 44, y, 10, 1, 22)
        lines.append(layer_from(row))
    # tooled corner
    pix(notebook, 54, 46, 12)
    pix(notebook, 55, 47, 13)
    mark = blank()
    pix(mark, 46, 52, 12)
    pix(mark, 47, 53, 12)
    pix(mark, 48, 52, 12)
    pix(mark, 49, 51, 12)
    pix(mark, 50, 50, 12)

    layers = {
        "body": layer_from(body),
        "head": layer_from(head),
        "hair": layer_from(hair),
        "hat": layer_from(hat),
        "mustache": layer_from(mustache),
        "eyes": layer_from(eyes),
        "eyes_shut": layer_from(shut),
        "brows": layer_from(brows),
        "pencil": layer_from(pencil),
        "pencil_bite": layer_from(bite),
        "prop": layer_from(notebook),
        "line1": lines[0],
        "line2": lines[1],
        "line3": lines[2],
        "mark": layer_from(mark),
    }
    layers.update(mouths(25, 33))
    return layers


CAST_ORDER = {
    "tito": [
        "body",
        "prop",
        "mark",
        "hand",
        "bow",
        "head",
        "hair",
        "mustache",
        "eyes",
        "brows",
        "mouth",
    ],
    "paco": [
        "body",
        "prop",
        "line1",
        "line2",
        "line3",
        "mark",
        "head",
        "hair",
        "hat",
        "pencil",
        "mustache",
        "eyes",
        "brows",
        "mouth",
    ],
}


def composite(layers: dict[str, list[int]], mouth: str = "mouth_shut") -> list[list[int]]:
    buf = blank()
    who = "tito" if "bow" in layers else "paco"
    for name in CAST_ORDER[who]:
        key = mouth if name == "mouth" else name
        if name in {"mark", "hand", "pencil_bite"}:
            continue
        if name == "pencil" and "pencil_bite" == key:
            continue
        pixels = layers.get(key)
        if not pixels:
            continue
        for i in range(0, len(pixels), 3):
            pix(buf, pixels[i], pixels[i + 1], pixels[i + 2])
    return buf


def png_bytes(buf: list[list[int]], scale: int) -> bytes:
    size = GRID * scale
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        row = buf[y // scale]
        for x in range(size):
            rgb = PALETTE[row[x // scale]]
            raw.extend(bytes.fromhex(rgb[1:]))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def cast_js(payload: dict) -> str:
    return "window.CAST = " + json.dumps(payload, separators=(",", ":")) + ";\n"


def mirror(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in src.iterdir():
        if path.is_file():
            shutil.copy2(path, dest / path.name)


def main() -> None:
    tito = tito_layers()
    paco = paco_layers()
    payload = {
        "palette": PALETTE,
        "grid": GRID,
        "scale": 2,
        "order": CAST_ORDER,
        "tito": tito,
        "paco": paco,
    }
    text = cast_js(payload)
    stage = (ROOT / "rabbit" / "cast" / "stage.js").read_text(encoding="utf-8")
    icon_scale = ICON // GRID
    tito_png = png_bytes(composite(tito), icon_scale)
    paco_png = png_bytes(composite(paco), icon_scale)
    for folder, png, icon_name in (
        (ROOT / "rabbit" / "assistant", tito_png, "tito.png"),
        (ROOT / "rabbit" / "paco", paco_png, "paco.png"),
    ):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "cast.js").write_text(text, encoding="utf-8")
        (folder / "stage.js").write_text(stage, encoding="utf-8")
        (folder / icon_name).write_bytes(png)
        (folder / "icon.png").write_bytes(png)
    mirror(ROOT / "rabbit" / "assistant", ROOT / "services" / "assistant" / "static" / "creation")
    mirror(ROOT / "rabbit" / "paco", ROOT / "services" / "assistant" / "static" / "paco")


if __name__ == "__main__":
    main()
