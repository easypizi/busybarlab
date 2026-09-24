import importlib.util
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def build():
    path = ROOT / "rabbit" / "cast" / "build.py"
    spec = importlib.util.spec_from_file_location("cast_build", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shift_moves_y_not_x() -> None:
    module = build()
    assert module.shift([4, 7, 2], 0, 5) == [4, 12, 2]
    assert module.shift([4, 7, 2], 3, 0) == [7, 7, 2]


def _triples(layers: dict, name: str) -> list[tuple[int, int, int]]:
    pixels = layers[name]
    return [(pixels[i], pixels[i + 1], pixels[i + 2]) for i in range(0, len(pixels), 3)]


def _ys(layers: dict, name: str) -> list[int]:
    pixels = layers[name]
    return [pixels[i + 1] for i in range(0, len(pixels), 3)]


def _xs(layers: dict, name: str) -> list[int]:
    pixels = layers[name]
    return [pixels[i] for i in range(0, len(pixels), 3)]


def test_faces_have_separate_glasses_and_authored_poses() -> None:
    module = build()
    tito = module.tito_layers()
    paco = module.paco_layers()
    for name in ("glasses", "glasses_low", "eyes_up", "eyes_open", "eyes_shut", "eyes_half"):
        assert tito[name]
    assert "glasses" not in paco
    assert "glasses_low" not in paco
    assert "glasses" not in module.CAST_ORDER["paco"]
    assert "glasses_low" not in module.CAST_ORDER["paco"]
    glasses_y = _ys(tito, "glasses")
    low_y = _ys(tito, "glasses_low")
    assert sum(low_y) / len(low_y) > sum(glasses_y) / len(glasses_y)
    assert paco["hat_back"]
    brim_y = [paco["hat_brim"][i + 1] for i in range(0, len(paco["hat_brim"]), 3)]
    back_y = [paco["hat_back"][i + 1] for i in range(0, len(paco["hat_back"]), 3)]
    assert max(back_y) - min(back_y) > 8
    assert max(paco["hat_back"][i] for i in range(0, len(paco["hat_back"]), 3)) - min(
        paco["hat_back"][i] for i in range(0, len(paco["hat_back"]), 3)
    ) > 20
    assert min(back_y) < min(brim_y)


def _cells(layers: dict, name: str) -> set[tuple[int, int]]:
    pixels = layers[name]
    return {(pixels[i], pixels[i + 1]) for i in range(0, len(pixels), 3)}


def _span(cells: set[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs = [x for x, _ in cells]
    ys = [y for _, y in cells]
    return min(xs), max(xs), min(ys), max(ys)


def test_hat_sits_on_the_head() -> None:
    paco = build().paco_layers()
    head = _cells(paco, "head")
    hair = _cells(paco, "hair")
    brim = _cells(paco, "hat_brim")
    crown = _cells(paco, "hat_crown")
    band = _cells(paco, "hat_band")
    back = _cells(paco, "hat_back")
    worn = crown | band | brim
    _, _, head_top, _ = _span(head)
    brim_left, brim_right, brim_top, brim_bottom = _span(brim)
    crown_left, crown_right, _, _ = _span(crown)
    assert brim_bottom + 2 >= head_top
    assert not any(y < brim_top and crown_left <= x <= crown_right for x, y in hair)
    worn_box = _span(worn)
    back_box = _span(back)
    assert abs((worn_box[1] - worn_box[0]) - (back_box[1] - back_box[0])) <= 2
    assert abs((worn_box[3] - worn_box[2]) - (back_box[3] - back_box[2])) <= 2
    assert brim_right - brim_left < 52


def test_face_rows_do_not_collide() -> None:
    module = build()
    tito = module.tito_layers()
    paco = module.paco_layers()

    def cells(layers: dict, name: str) -> set[tuple[int, int]]:
        pixels = layers[name]
        return {(pixels[i], pixels[i + 1]) for i in range(0, len(pixels), 3)}

    def span_y(layers: dict, name: str) -> tuple[int, int]:
        ys = _ys(layers, name)
        return min(ys), max(ys)

    for layers, rig in ((tito, module.TITO), (paco, module.PACO)):
        brow_top, brow_bottom = span_y(layers, "brows")
        eye_top, _eye_bottom = span_y(layers, "eyes_open")
        mustache_top, _mustache_bottom = span_y(layers, "mustache")
        _mouth_top, mouth_bottom = span_y(layers, "mouth_shut")
        assert cells(layers, "brows").isdisjoint(cells(layers, "hair"))
        assert brow_bottom < eye_top
        assert eye_top > rig.brow_y
        assert mustache_top > rig.nose_y + 2
        assert mouth_bottom <= rig.chin_y - 2
        assert cells(layers, "mouth_shut").isdisjoint(cells(layers, "body"))
        assert cells(layers, "mouth_a").isdisjoint(cells(layers, "body"))
        widths = []
        tops = []
        for kind in ("open", "half", "shut", "up", "side_l", "side_r"):
            name = "eyes_" + kind
            xs = _xs(layers, name)
            widths.append(max(xs) - min(xs))
            tops.append(min(_ys(layers, name)))
        assert len(set(widths)) == 1
        assert len(set(tops)) == 1

    eye = cells(tito, "eyes_open")
    frame = cells(tito, "glasses")
    low = cells(tito, "glasses_low")
    assert eye.isdisjoint(frame)
    assert low.isdisjoint(cells(tito, "mustache"))
    assert low.isdisjoint(cells(tito, "mouth_shut"))
    assert set(_ys(tito, "eyes_open")) & set(_ys(tito, "glasses_low"))
    window = {(x, y) for x, y in eye}
    assert window
    ear = {(x, y) for x, y in cells(tito, "head") if x <= 34 or x >= 61}
    assert any(abs(gx - hx) <= 1 and abs(gy - hy) <= 1 for gx, gy in frame for hx, hy in ear)

    assert cells(paco, "brows").isdisjoint(cells(paco, "hat_brim"))
    mouth_left, mouth_right = min(_xs(paco, "mouth_shut")), max(_xs(paco, "mouth_shut"))
    mustache_left, mustache_right = min(_xs(paco, "mustache")), max(_xs(paco, "mustache"))
    assert mustache_left <= mouth_left - 3
    assert mustache_right >= mouth_right + 3
    assert max(_ys(paco, "mustache")) > max(_ys(paco, "mouth_shut"))
    assert cells(paco, "mouth_shut").isdisjoint(cells(paco, "mustache"))
    whites = 0
    full_shade = False
    for y in range(min(_ys(paco, "eyes_open")), max(_ys(paco, "eyes_open")) + 1):
        row = [color for x, yy, color in _triples(paco, "eyes_open") if yy == y and x < 48]
        if not row:
            continue
        if 8 in row:
            whites += 1
        if len(row) >= 6 and all(color == 2 for color in row):
            full_shade = True
    assert whites >= 4
    assert not full_shade

    head_left, head_right = min(_xs(tito, "head")), max(_xs(tito, "head"))
    hair_left, hair_right = min(_xs(tito, "hair")), max(_xs(tito, "hair"))
    assert hair_left >= head_left - 2
    assert hair_right <= head_right + 2
    leg_rows = {}
    for x, y, _color in _triples(tito, "mustache"):
        leg_rows.setdefault(y, []).append(x)
    mouth_top = min(_ys(tito, "mouth_shut"))
    for y, xs in leg_rows.items():
        if y < mouth_top:
            continue
        left = min(xs)
        assert sum(1 for x in xs if x <= left + 2) >= 2
    brow_top = min(_ys(tito, "brows"))
    forehead = {
        (x, y)
        for x, y, color in _triples(tito, "head")
        if color == 1 and y < brow_top and 44 <= x <= 51
    }
    hair_cells = cells(tito, "hair")
    assert any((x, y) not in hair_cells for x, y in forehead)


def test_pencil_does_not_cross_the_brim() -> None:
    module = build()
    paco = module.paco_layers()

    def cells(name: str) -> set[tuple[int, int]]:
        pixels = paco[name]
        return {(pixels[i], pixels[i + 1]) for i in range(0, len(pixels), 3)}

    brim = cells("hat_brim")
    assert cells("pencil_ear").isdisjoint(brim)
    assert cells("pencil_touch").isdisjoint(brim)


def test_idle_icon_is_512() -> None:
    module = build()
    data = module.payload()
    png = module.png_bytes(module.composite(data["tito"], module.IDLE["tito"]), 5, 16)
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (512, 512)


def test_stage_reads_attach_and_clock() -> None:
    text = (ROOT / "rabbit" / "cast" / "stage.js").read_text(encoding="utf-8")
    assert "cast.attach" in text
    assert "options.clock" in text
    assert "glasses_low" in text
    assert "hat_back" in text
    assert "mouth_mid" in text
    assert "webgl" not in text
