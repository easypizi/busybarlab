"""Draw Tito and Paco once, on a real 96 grid. Icons, cast.js, and the static mirrors come from here."""

from __future__ import annotations

import json
import shutil
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRID = 96
AXIS = 48
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

HEAD_NAMES = {
    "hand_bow",
    "bow",
    "head",
    "hair",
    "mustache",
    "mustache_open",
    "eyes_open",
    "eyes_half",
    "eyes_shut",
    "eyes_up",
    "eyes_side_l",
    "eyes_side_r",
    "glasses",
    "glasses_low",
    "glint",
    "brows",
    "brows_up",
    "brows_knit",
    "mouth_shut",
    "mouth_a",
    "mouth_o",
    "mouth_e",
    "mouth_m",
    "mouth_con",
    "mouth_mid",
    "hat_crown",
    "hat_band",
    "hat_brim",
    "hat_back",
    "pencil_ear",
    "pencil_touch",
    "pencil_bite",
}


def blank() -> list[list[int]]:
    return [[0] * GRID for _ in range(GRID)]


def pix(buf: list[list[int]], x: int, y: int, color: int) -> None:
    if 0 <= x < GRID and 0 <= y < GRID and color:
        buf[y][x] = color


def erase(buf: list[list[int]], x: int, y: int, w: int, h: int) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if 0 <= xx < GRID and 0 <= yy < GRID:
                buf[yy][xx] = 0


def rect(buf: list[list[int]], x: int, y: int, w: int, h: int, color: int) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            pix(buf, xx, yy, color)


def sym_rect(buf: list[list[int]], x: int, y: int, w: int, h: int, color: int) -> None:
    rect(buf, x, y, w, h, color)
    mx = (GRID - 1) - (x + w - 1)
    if mx != x:
        rect(buf, mx, y, w, h, color)


def disc(buf: list[list[int]], cx: float, cy: float, rx: float, ry: float, color: int) -> None:
    for y in range(GRID):
        for x in range(GRID):
            dx = (x + 0.5 - cx) / rx
            dy = (y + 0.5 - cy) / ry
            if dx * dx + dy * dy <= 1:
                pix(buf, x, y, color)


def stamp(buf: list[list[int]], x: int, y: int, rows: list[str], colors: dict[str, int]) -> None:
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch in colors:
                pix(buf, x + dx, y + dy, colors[ch])


def stamp_even(buf: list[list[int]], top: int, rows: list[str], colors: dict[str, int]) -> None:
    for dy, row in enumerate(rows):
        if len(row) % 2:
            raise ValueError("stamp width must be even: " + row)
        stamp(buf, AXIS - len(row) // 2, top + dy, [row], colors)


def stamp_axis(buf: list[list[int]], top: int, rows: list[str], colors: dict[str, int]) -> None:
    for row in rows:
        if row != row[::-1]:
            raise ValueError("stamp must be a palindrome: " + row)
    stamp_even(buf, top, rows, colors)


def shift(pixels: list[int], dx: int, dy: int) -> list[int]:
    out: list[int] = []
    for i in range(0, len(pixels), 3):
        out.extend((pixels[i] + dx, pixels[i + 1] + dy, pixels[i + 2]))
    return out


def layer_from(buf: list[list[int]]) -> list[int]:
    out: list[int] = []
    for y, row in enumerate(buf):
        for x, color in enumerate(row):
            if color:
                out.extend((x, y, color))
    return out


def assert_sym(buf: list[list[int]], name: str) -> None:
    for y, row in enumerate(buf):
        for x in range(GRID // 2):
            mirror = GRID - 1 - x
            if row[x] != row[mirror]:
                raise ValueError(f"{name} asymmetric at {x},{y}")


SKIN = {"s": 1, "S": 2, "w": 8, "i": 3, "p": 7, "k": 6, "m": 5, "h": 25}


def _eyes(kind: str) -> list[str]:
    bridge = "ssssssss"
    if kind == "open":
        eye = "wwwwww wwiiww wippiw wwiiww wwwwww".split()
    elif kind == "half":
        eye = "ssssss ssssss kkkkkk wippiw wwwwww".split()
    elif kind == "shut":
        eye = "ssssss ssssss ssssss kkkkkk ssssss".split()
    elif kind == "up":
        eye = "wwwwww wippiw wwwwww wwwwww wwwwww".split()
    elif kind == "side_l":
        eye_l = "wwwwww wwiiww wpiiiw wwiiww wwwwww".split()
        eye_r = "wwwwww wwiiww wiiipw wwiiww wwwwww".split()
        return [eye_l[i] + bridge + eye_r[i] for i in range(5)]
    elif kind == "side_r":
        eye_l = "wwwwww wwiiww wiiipw wwiiww wwwwww".split()
        eye_r = "wwwwww wwiiww wpiiiw wwiiww wwwwww".split()
        return [eye_l[i] + bridge + eye_r[i] for i in range(5)]
    else:
        raise ValueError(kind)
    return [eye[i] + bridge + eye[i] for i in range(5)]


def eyes_layer(kind: str, drop: int = 0) -> list[int]:
    buf = blank()
    rows = _eyes(kind)
    top = 36 + drop
    if kind in {"side_l", "side_r"}:
        stamp_even(buf, top, rows, SKIN)
    else:
        stamp_axis(buf, top, rows, SKIN)
        assert_sym(buf, "eyes_" + kind)
    return layer_from(buf)


def brows_layer(kind: str, drop: int = 0) -> list[int]:
    buf = blank()
    if kind == "up":
        sym_rect(buf, 38, 29 + drop, 6, 2, 5)
    elif kind == "knit":
        sym_rect(buf, 42, 32 + drop, 5, 2, 5)
        pix(buf, 41, 31 + drop, 5)
        pix(buf, 54, 31 + drop, 5)
        pix(buf, 46, 34 + drop, 5)
        pix(buf, 49, 34 + drop, 5)
    else:
        sym_rect(buf, 38, 32 + drop, 6, 2, 5)
    assert_sym(buf, "brows_" + kind)
    return layer_from(buf)


def mustache_layer(open_shape: bool, drop: int = 0) -> list[int]:
    buf = blank()
    top = (48 if open_shape else 50) + drop
    rows = [
        " mmmmmmmmmmmmmm ",
        "mm            mm",
        "mm            mm",
        "mmm          mmm",
    ]
    if open_shape:
        rows = [
            "mmmmmmmmmmmmmmmm",
            "mm            mm",
            " mmm        mmm ",
        ]
    stamp_axis(buf, top, rows, {"m": 5})
    assert_sym(buf, "mustache")
    return layer_from(buf)


def mouth_layer(kind: str, drop: int = 0) -> list[int]:
    rows = {
        "shut": ["  ssssss  ", " ssssssss ", "  SSSSSS  "],
        "mid": ["   ssss   ", "  k8ss8k  ", "   ssss   "],
        "a": ["  kkkkkk  ", " k8s88s8k ", "  kkkkkk  "],
        "o": ["   kkkk   ", "  k8ss8k  ", "  kssssk  ", "   kkkk   "],
        "e": [" kkkkkkkk ", "k8ssssss8k", " kkkkkkkk "],
        "m": [" ssssssss ", " SSSSSSSS "],
        "con": ["  kkkkkk  ", " kssssssk ", "  kkkkkk  "],
    }[kind]
    buf = blank()
    stamp_axis(buf, 56 + drop, rows, {"s": 1, "S": 2, "k": 6, "8": 8})
    assert_sym(buf, "mouth_" + kind)
    return layer_from(buf)


def _lens(buf: list[list[int]], x: int, y: int, tint: int) -> None:
    """Frame with an open window so the eye layer stays visible."""
    rect(buf, x, y, 8, 7, 6)
    erase(buf, x + 1, y + 1, 6, 5)
    rect(buf, x + 1, y + 1, 6, 1, tint)
    rect(buf, x + 1, y + 5, 6, 1, tint)


def glasses_layer(low: bool, drop: int = 0, round_frame: bool = False) -> list[int]:
    buf = blank()
    y = (42 if low else 35) + drop
    tint = 15 if round_frame else 13
    _lens(buf, 36, y, tint)
    _lens(buf, 52, y, tint)
    pix(buf, 39, y + 2, 14)
    pix(buf, 56, y + 2, 14)
    if not round_frame:
        rect(buf, 44, y + 2, 8, 2, 6)
    else:
        rect(buf, 44, y + 3, 8, 1, 6)
        for corner_y in (y, y + 6):
            erase(buf, 36, corner_y, 1, 1)
            erase(buf, 43, corner_y, 1, 1)
            erase(buf, 52, corner_y, 1, 1)
            erase(buf, 59, corner_y, 1, 1)
    sym_rect(buf, 30, y + 2, 6, 2, 6)
    if low:
        sym_rect(buf, 32, y - 4, 2, 4, 6)
    assert_sym(buf, "glasses")
    return layer_from(buf)


def face_base(cy: float, rx: float, ry: float) -> tuple[list[list[int]], list[list[int]]]:
    head = blank()
    disc(head, AXIS, cy, rx, ry, 1)
    disc(head, AXIS, cy + 6, rx - 4, ry - 6, 25)
    sym_rect(head, 30, int(cy) - 2, 4, 8, 1)
    pix(head, 47, int(cy) + 2, 2)
    pix(head, 48, int(cy) + 2, 2)
    pix(head, 47, int(cy) + 4, 2)
    pix(head, 48, int(cy) + 4, 2)
    hair = blank()
    disc(hair, AXIS, cy - 12, rx, 9, 4)
    disc(hair, AXIS, cy - 14, rx - 2, 6, 3)
    sym_rect(hair, 32, int(cy) - 8, 3, 8, 5)
    assert_sym(head, "head")
    assert_sym(hair, "hair")
    return head, hair


def tito_layers() -> dict[str, list[int]]:
    head, hair = face_base(42, 17, 16)
    body = blank()
    disc(body, AXIS, 78, 22, 16, 6)
    rect(body, 28, 70, 40, 26, 6)
    rect(body, 26, 88, 44, 8, 7)
    rect(body, 44, 64, 8, 16, 8)
    for y in (74, 80, 86):
        pix(body, 47, y, 10)
        pix(body, 48, y, 10)
    for dx in range(0, 10, 2):
        pix(body, 40 - dx, 76, 11)
        pix(body, 55 + dx, 76, 11)
        pix(body, 40 - dx, 78, 12)
        pix(body, 55 + dx, 78, 12)

    bow = blank()
    sym_rect(bow, 34, 58, 8, 8, 10)
    sym_rect(bow, 35, 59, 6, 6, 9)
    rect(bow, 46, 60, 4, 4, 10)
    pix(bow, 47, 61, 8)
    pix(bow, 48, 61, 8)
    assert_sym(bow, "bow")

    hand_bow = blank()
    rect(hand_bow, 34, 60, 5, 4, 1)
    pix(hand_bow, 35, 59, 1)
    pix(hand_bow, 38, 63, 2)

    hand_tick = blank()
    rect(hand_tick, 64, 44, 6, 5, 1)
    pix(hand_tick, 69, 45, 1)
    pix(hand_tick, 69, 46, 2)
    pix(hand_tick, 65, 43, 1)

    def page(curl: int, lit: bool) -> list[int]:
        buf = blank()
        rect(buf, 70, 36, 20, 24, 6)
        rect(buf, 72, 38, 16, 20, 20)
        rect(buf, 72, 38, 16, 4, 9)
        for x in (73, 76, 79, 82, 85):
            pix(buf, x, 38, 13)
        pix(buf, 74, 37, 8)
        pix(buf, 84, 37, 8)
        if curl == 0:
            for y in (46, 50, 54):
                for x in (74, 78, 82):
                    pix(buf, x, y, 22)
                    pix(buf, x + 1, y, 22)
        elif curl == 1:
            rect(buf, 82, 42, 6, 16, 8)
            rect(buf, 84, 44, 4, 12, 21)
            for y in (46, 50):
                pix(buf, 74, y, 22)
                pix(buf, 75, y, 22)
                pix(buf, 78, y, 22)
        else:
            rect(buf, 72, 42, 4, 16, 8)
            for y in (46, 50, 54):
                pix(buf, 80, y, 22)
                pix(buf, 84, y, 22)
        if lit:
            rect(buf, 78, 49, 3, 3, 10)
        return layer_from(buf)

    glint = blank()
    rect(glint, 39, 37, 2, 2, 14)

    layers = {
        "body": layer_from(body),
        "head": layer_from(head),
        "hair": layer_from(hair),
        "bow": layer_from(bow),
        "hand_bow": layer_from(hand_bow),
        "hand_tick": layer_from(hand_tick),
        "cal_0": page(0, False),
        "cal_1": page(1, False),
        "cal_2": page(2, False),
        "cal_lit": page(0, True),
        "glint": layer_from(glint),
        "mustache": mustache_layer(False),
        "mustache_open": mustache_layer(True),
        "glasses": glasses_layer(False),
        "glasses_low": glasses_layer(True),
        "brows": brows_layer("rest"),
        "brows_up": brows_layer("up"),
        "brows_knit": brows_layer("knit"),
    }
    for kind in ("open", "half", "shut", "up", "side_l", "side_r"):
        layers["eyes_" + kind] = eyes_layer(kind)
    for kind in ("shut", "mid", "a", "o", "e", "m", "con"):
        layers["mouth_" + kind] = mouth_layer(kind)
    return layers


def paco_layers() -> dict[str, list[int]]:
    drop = 2
    head, hair = face_base(46, 15, 14)
    body = blank()
    disc(body, AXIS, 80, 20, 14, 23)
    rect(body, 30, 68, 36, 28, 23)
    rect(body, 28, 90, 40, 6, 24)
    for x in (38, 42, 53, 57):
        rect(body, x, 74, 1, 14, 11)
    rect(body, 44, 70, 8, 6, 9)
    pix(body, 46, 72, 10)
    pix(body, 49, 72, 10)
    # Bandana sits on the neck, above the shirt.
    rect(body, 40, 60, 16, 4, 18)
    pix(body, 46, 64, 10)
    pix(body, 49, 64, 12)
    pix(body, 47, 64, 8)
    pix(body, 48, 64, 8)

    hat_crown = blank()
    disc(hat_crown, AXIS, 12, 12, 8, 16)
    disc(hat_crown, AXIS, 10, 8, 5, 17)
    assert_sym(hat_crown, "crown")
    hat_band = blank()
    rect(hat_band, 36, 16, 24, 4, 19)
    rect(hat_band, 36, 16, 24, 1, 17)
    assert_sym(hat_band, "band")
    hat_brim = blank()
    disc(hat_brim, AXIS, 22, 26, 5, 16)
    rect(hat_brim, 22, 24, 52, 2, 17)
    assert_sym(hat_brim, "brim")

    hat_back = blank()
    disc(hat_back, AXIS, 20, 10, 6, 16)
    disc(hat_back, AXIS, 18, 6, 4, 17)
    rect(hat_back, 38, 22, 20, 3, 19)
    disc(hat_back, AXIS, 26, 16, 3, 16)
    rect(hat_back, 34, 27, 28, 1, 17)
    assert_sym(hat_back, "hat_back")

    def pencil_at(x: int, y: int, w: int, h: int, tip_x: int, tip_y: int) -> list[int]:
        buf = blank()
        rect(buf, x, y, w, h, 22)
        pix(buf, tip_x, tip_y, 8)
        return layer_from(buf)

    pencil_ear = blank()
    rect(pencil_ear, 60, 14, 16, 3, 22)
    pix(pencil_ear, 76, 14, 8)
    pix(pencil_ear, 76, 15, 8)
    pix(pencil_ear, 60, 16, 2)
    pencil_touch = blank()
    rect(pencil_touch, 60, 14, 16, 3, 22)
    pix(pencil_touch, 76, 14, 8)
    rect(pencil_touch, 70, 17, 4, 1, 1)

    bite = blank()
    rect(bite, 50, 57, 12, 2, 22)
    pix(bite, 62, 57, 8)
    pix(bite, 50, 58, 2)

    def writing(angle: int) -> list[int]:
        buf = blank()
        if angle == 0:
            rect(buf, 74, 50, 12, 2, 22)
            pix(buf, 86, 50, 8)
            rect(buf, 70, 49, 5, 4, 1)
        elif angle == 1:
            for i in range(8):
                pix(buf, 76 + i, 46 + i, 22)
                pix(buf, 77 + i, 46 + i, 22)
            pix(buf, 84, 54, 8)
            rect(buf, 72, 44, 5, 4, 1)
        else:
            for i in range(8):
                pix(buf, 80, 46 + i, 22)
                pix(buf, 81, 46 + i, 22)
            pix(buf, 80, 54, 8)
            rect(buf, 77, 44, 6, 4, 1)
        return layer_from(buf)

    notebook = blank()
    rect(notebook, 68, 46, 22, 26, 19)
    rect(notebook, 70, 48, 18, 22, 20)
    rect(notebook, 68, 46, 3, 26, 10)
    pix(notebook, 84, 50, 12)
    pix(notebook, 86, 52, 13)

    def rule(y: int) -> list[int]:
        buf = blank()
        rect(buf, 74, y, 12, 1, 21)
        return layer_from(buf)

    def check(step: int) -> list[int]:
        buf = blank()
        pix(buf, 76, 58, 12)
        if step >= 1:
            pix(buf, 77, 59, 12)
            pix(buf, 78, 60, 12)
        if step >= 2:
            pix(buf, 79, 59, 12)
            pix(buf, 80, 58, 12)
            pix(buf, 81, 57, 12)
        return layer_from(buf)

    layers = {
        "body": layer_from(body),
        "head": layer_from(head),
        "hair": layer_from(hair),
        "hat_crown": layer_from(hat_crown),
        "hat_band": layer_from(hat_band),
        "hat_brim": layer_from(hat_brim),
        "hat_back": layer_from(hat_back),
        "pencil_ear": layer_from(pencil_ear),
        "pencil_touch": layer_from(pencil_touch),
        "pencil_bite": layer_from(bite),
        "pencil_write_0": writing(0),
        "pencil_write_1": writing(1),
        "pencil_write_2": writing(2),
        "notebook": layer_from(notebook),
        "line1": rule(52),
        "line2": rule(56),
        "line3": rule(60),
        "mark_0": check(0),
        "mark_1": check(1),
        "mark_2": check(2),
        "mustache": mustache_layer(False, drop),
        "mustache_open": mustache_layer(True, drop),
        "glasses": glasses_layer(False, drop, round_frame=True),
        "glasses_low": glasses_layer(True, drop, round_frame=True),
        "brows": brows_layer("rest", drop),
        "brows_up": brows_layer("up", drop),
        "brows_knit": brows_layer("knit", drop),
    }
    for kind in ("open", "half", "shut", "up", "side_l", "side_r"):
        layers["eyes_" + kind] = eyes_layer(kind, drop)
    for kind in ("shut", "mid", "a", "o", "e", "m", "con"):
        layers["mouth_" + kind] = mouth_layer(kind, drop)
    return layers


CAST_ORDER = {
    "tito": [
        "body",
        "cal_0",
        "cal_1",
        "cal_2",
        "cal_lit",
        "hand_tick",
        "hand_bow",
        "bow",
        "head",
        "hair",
        "mustache",
        "mustache_open",
        "eyes_open",
        "eyes_half",
        "eyes_shut",
        "eyes_up",
        "eyes_side_l",
        "eyes_side_r",
        "glasses",
        "glasses_low",
        "glint",
        "brows",
        "brows_up",
        "brows_knit",
        "mouth_shut",
        "mouth_mid",
        "mouth_a",
        "mouth_o",
        "mouth_e",
        "mouth_m",
        "mouth_con",
    ],
    "paco": [
        "body",
        "notebook",
        "line1",
        "line2",
        "line3",
        "mark_0",
        "mark_1",
        "mark_2",
        "pencil_write_0",
        "pencil_write_1",
        "pencil_write_2",
        "head",
        "hair",
        "hat_crown",
        "hat_band",
        "hat_brim",
        "hat_back",
        "pencil_ear",
        "pencil_touch",
        "pencil_bite",
        "mustache",
        "mustache_open",
        "eyes_open",
        "eyes_half",
        "eyes_shut",
        "eyes_up",
        "eyes_side_l",
        "eyes_side_r",
        "glasses",
        "glasses_low",
        "brows",
        "brows_up",
        "brows_knit",
        "mouth_shut",
        "mouth_mid",
        "mouth_a",
        "mouth_o",
        "mouth_e",
        "mouth_m",
        "mouth_con",
    ],
}

IDLE = {
    "tito": [
        "body",
        "cal_0",
        "bow",
        "head",
        "hair",
        "mustache",
        "eyes_open",
        "glasses",
        "brows",
        "mouth_shut",
    ],
    "paco": [
        "body",
        "notebook",
        "head",
        "hair",
        "hat_crown",
        "hat_band",
        "hat_brim",
        "pencil_ear",
        "mustache",
        "eyes_open",
        "glasses",
        "brows",
        "mouth_shut",
    ],
}


def attach_map(who: str) -> dict[str, str]:
    return {name: "head" if name in HEAD_NAMES else "body" for name in CAST_ORDER[who]}


def composite(layers: dict[str, list[int]], names: list[str]) -> list[list[int]]:
    buf = [[0] * GRID for _ in range(GRID)]
    for name in names:
        pixels = layers.get(name)
        if not pixels:
            continue
        for i in range(0, len(pixels), 3):
            x, y, color = pixels[i], pixels[i + 1], pixels[i + 2]
            if 0 <= x < GRID and 0 <= y < GRID and color:
                buf[y][x] = color
    return buf


def png_bytes(buf: list[list[int]], scale: int, pad: int = 0) -> bytes:
    inner = len(buf) * scale
    size = inner + pad * 2
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            if x < pad or y < pad or x >= size - pad or y >= size - pad:
                rgb = PALETTE[0]
            else:
                rgb = PALETTE[buf[(y - pad) // scale][(x - pad) // scale]]
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


def payload() -> dict:
    tito = tito_layers()
    paco = paco_layers()
    for who, layers in (("tito", tito), ("paco", paco)):
        missing = [name for name in layers if name not in CAST_ORDER[who]]
        extra = [name for name in CAST_ORDER[who] if name not in layers]
        if missing or extra:
            raise ValueError(f"{who} order mismatch missing={missing} extra={extra}")
    return {
        "palette": PALETTE,
        "grid": GRID,
        "scale": 2,
        "order": CAST_ORDER,
        "attach": {"tito": attach_map("tito"), "paco": attach_map("paco")},
        "idle": IDLE,
        "tito": tito,
        "paco": paco,
    }


def main() -> None:
    data = payload()
    text = cast_js(data)
    stage = (ROOT / "rabbit" / "cast" / "stage.js").read_text(encoding="utf-8")
    tito_png = png_bytes(composite(data["tito"], IDLE["tito"]), 5, 16)
    paco_png = png_bytes(composite(data["paco"], IDLE["paco"]), 5, 16)
    if len(tito_png) < 8 or ICON != 512:
        raise ValueError("icon render failed")
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


def write_sheet(path: Path) -> None:
    data = payload()
    poses = {
        "tito": [
            ("idle", IDLE["tito"]),
            ("blink", ["body", "cal_0", "bow", "head", "hair", "mustache", "eyes_shut", "glasses", "brows", "mouth_shut"]),
            ("listen", ["body", "cal_0", "bow", "head", "hair", "mustache", "eyes_open", "glasses", "glint", "brows_up", "mouth_shut"]),
            ("think", ["body", "cal_1", "bow", "head", "hair", "mustache", "eyes_up", "glasses_low", "brows", "mouth_shut"]),
            ("speak", ["body", "cal_0", "hand_tick", "bow", "head", "hair", "mustache_open", "eyes_open", "glasses", "brows", "mouth_a"]),
            ("action", ["body", "cal_lit", "bow", "head", "hair", "mustache", "eyes_open", "glasses", "brows", "mouth_shut"]),
        ],
        "paco": [
            ("idle", IDLE["paco"]),
            ("blink", ["body", "notebook", "head", "hair", "hat_crown", "hat_band", "hat_brim", "pencil_ear", "mustache", "eyes_shut", "glasses", "brows", "mouth_shut"]),
            ("listen", ["body", "notebook", "line1", "line2", "pencil_write_1", "head", "hair", "hat_crown", "hat_band", "hat_brim", "mustache", "eyes_open", "glasses", "brows_up", "mouth_shut"]),
            ("think", ["body", "notebook", "head", "hair", "hat_back", "pencil_bite", "mustache", "eyes_up", "glasses", "brows_knit", "mouth_shut"]),
            ("speak", ["body", "notebook", "head", "hair", "hat_crown", "hat_band", "hat_brim", "pencil_ear", "mustache_open", "eyes_open", "glasses", "brows", "mouth_o"]),
            ("action", ["body", "notebook", "mark_2", "head", "hair", "hat_crown", "hat_band", "hat_brim", "pencil_ear", "mustache", "eyes_open", "glasses", "brows", "mouth_shut"]),
        ],
    }
    cell = GRID
    cols = 6
    sheet = [[0] * (cols * cell) for _ in range(2 * cell)]
    for row, who in enumerate(("tito", "paco")):
        for col, (_label, names) in enumerate(poses[who]):
            buf = composite(data[who], names)
            for y in range(cell):
                for x in range(cell):
                    sheet[row * cell + y][col * cell + x] = buf[y][x]
    path.write_bytes(png_bytes(sheet, 4, 0))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sheet":
        write_sheet(Path(sys.argv[2]))
    else:
        main()
