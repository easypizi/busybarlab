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


def test_faces_have_separate_glasses_and_authored_poses() -> None:
    module = build()
    tito = module.tito_layers()
    paco = module.paco_layers()
    for layers in (tito, paco):
        for name in ("glasses", "glasses_low", "eyes_up", "eyes_open", "eyes_shut", "eyes_half"):
            assert layers[name]
        glasses_y = [layers["glasses"][i + 1] for i in range(0, len(layers["glasses"]), 3)]
        low_y = [layers["glasses_low"][i + 1] for i in range(0, len(layers["glasses_low"]), 3)]
        assert sum(low_y) / len(low_y) > sum(glasses_y) / len(glasses_y)
    assert paco["hat_back"]
    brim_y = [paco["hat_brim"][i + 1] for i in range(0, len(paco["hat_brim"]), 3)]
    back_y = [paco["hat_back"][i + 1] for i in range(0, len(paco["hat_back"]), 3)]
    assert max(back_y) - min(back_y) > 8
    assert max(paco["hat_back"][i] for i in range(0, len(paco["hat_back"]), 3)) - min(
        paco["hat_back"][i] for i in range(0, len(paco["hat_back"]), 3)
    ) > 20
    assert min(back_y) < min(brim_y)


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
