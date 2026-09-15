"""Pixel sprites for Cursor Token Pet (grayscale-friendly for OLED)."""

from __future__ import annotations

from apps.common.pixelart import ascii_to_png_bytes

# Grayscale digits 1-8 used for OLED-friendly art.


def egg() -> list[str]:
    return [
        "......4444......",
        "....44666644....",
        "...4668888664...",
        "..4688....8864..",
        "..468......864..",
        "..468......864..",
        "...4688..8864...",
        "....46666664....",
        ".....444444.....",
    ]


def body(branch: str, fat: int = 0) -> list[str]:
    """Basic body; fat 0-2 widens belly."""
    pad = "." * fat
    if branch == "dark":
        return [
            f"....{pad}2222{pad}....",
            f"...{pad}244442{pad}...",
            f"..{pad}24188142{pad}..",
            f"..{pad}24444442{pad}..",
            f"...{pad}244442{pad}...",
            f"....{pad}2..2{pad}....",
        ]
    if branch == "light":
        return [
            f"....{pad}7777{pad}....",
            f"...{pad}788887{pad}...",
            f"..{pad}78122187{pad}..",
            f"..{pad}78888887{pad}..",
            f"...{pad}788887{pad}...",
            f"....{pad}7..7{pad}....",
        ]
    return [
        f"....{pad}5555{pad}....",
        f"...{pad}566665{pad}...",
        f"..{pad}56122165{pad}..",
        f"..{pad}56666665{pad}..",
        f"...{pad}566665{pad}...",
        f"....{pad}5..5{pad}....",
    ]


TRAIT_LAYERS: dict[str, list[str]] = {
    "horns": [
        "2..2............",
        ".22.............",
    ],
    "spikes": [
        "................",
        ".2.2.2..........",
    ],
    "shadow_aura": [
        "1111............",
        "1..............1",
    ],
    "fangs": [
        "................",
        "......8.8.......",
    ],
    "cape": [
        "................",
        "2..............2",
    ],
    "ember": [
        "................",
        "....3..3........",
    ],
    "halo": [
        "....8888........",
        "................",
    ],
    "wings": [
        "7......7........",
        ".77..77.........",
    ],
    "glow": [
        "88888888........",
        "................",
    ],
    "crown": [
        "..8.8.8.........",
        ".8888888........",
    ],
    "sparkles": [
        "8...8...8.......",
        "................",
    ],
    "ribbon": [
        "................",
        "....888.........",
    ],
    "mask": [
        "................",
        "...555555.......",
    ],
    "scarf": [
        "................",
        "....666.........",
    ],
    "goggles": [
        "................",
        "...6.66.6.......",
    ],
    "antenna": [
        "...8............",
        "...8............",
    ],
    "badge": [
        "................",
        "..........8.....",
    ],
    "circuit": [
        "5.5.5.5.........",
        "................",
    ],
}

ACCESSORIES: dict[str, list[str]] = {
    "scarf": ["....666.........", "................"],
    "glasses": ["...8.88.8.......", "................"],
    "bolt": ["......8.........", ".....888........"],
    "stars": ["8...8...8.......", "................"],
    "visor": ["...888888.......", "................"],
    "gear": [".....8.8........", "....88888......."],
    "badge": ["..........8.....", "................"],
}

BOWL_W = [
    "66666",
    "6...6",
    "66666",
]
BOWL_P = [
    "88888",
    "8...8",
    "88888",
]
FOOD = [
    "777",
    "777",
]


def build_pet_png(
    branch: str,
    traits: list[str],
    accessory: str | None,
    *,
    fatness: float = 0.0,
    happy: bool = False,
) -> bytes:
    fat = 0 if fatness < 0.33 else 1 if fatness < 0.66 else 2
    rows = body(branch, fat=fat)
    # Overlay first two rows of traits/accessories above body.
    overlays: list[list[str]] = []
    for trait in traits[-4:]:
        base = trait.split("_")[0]
        if base in TRAIT_LAYERS:
            overlays.append(TRAIT_LAYERS[base])
    if accessory and accessory in ACCESSORIES:
        overlays.append(ACCESSORIES[accessory])
    canvas_w = max(len(r) for r in rows)
    height = 2 + len(rows)
    canvas = [["." for _ in range(canvas_w)] for _ in range(height)]
    for oy, overlay in enumerate(overlays[:2]):
        for y, row in enumerate(overlay):
            for x, ch in enumerate(row):
                if ch != "." and x < canvas_w and oy + y < height:
                    canvas[oy + y][x] = ch
    body_y = 2
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != "." and x < canvas_w:
                canvas[body_y + y][x] = ch
    if happy and body_y + 2 < height:
        # Tiny smile.
        mid = canvas_w // 2
        if mid + 1 < canvas_w:
            canvas[body_y + 2][mid] = "8"
    ascii_rows = ["".join(r) for r in canvas]
    return ascii_to_png_bytes(ascii_rows)


def sprite_bank() -> dict[str, bytes]:
    bank = {
        "egg.png": ascii_to_png_bytes(egg()),
        "bowl_w.png": ascii_to_png_bytes(BOWL_W),
        "bowl_p.png": ascii_to_png_bytes(BOWL_P),
        "food.png": ascii_to_png_bytes(FOOD),
    }
    for branch in ("light", "dark", "gray"):
        bank[f"body_{branch}.png"] = build_pet_png(branch, [], None)
    return bank
