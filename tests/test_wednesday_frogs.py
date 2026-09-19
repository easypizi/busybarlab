"""Unit tests for Wednesday Frogs scene logic."""

from datetime import datetime

from busybar.wednesday_frogs.animation import (
    advance,
    create_scene,
    hop_offset,
    is_wednesday,
    marquee_text,
    render_elements,
    request_marquee,
)


def test_marquee_text_switches_by_day() -> None:
    assert "WEDNESDAY" in marquee_text(True)
    assert "NOT WEDNESDAY" in marquee_text(False)


def test_hop_offset_parabola() -> None:
    y0, p0 = hop_offset(0.0, 4.0)
    y_mid, p_mid = hop_offset(0.5, 4.0)
    assert y0 == 0.0
    assert y_mid > 3.0
    assert p0 == "sit"
    assert p_mid == "hop"


def test_scene_advances_and_marquees() -> None:
    scene = create_scene(frog_count=2, now=100.0, seed=1, text_interval=5.0)
    start_x = scene.frogs[0].x
    advance(scene, 0.5, now=100.5, text_interval=5.0)
    assert scene.frogs[0].x > start_x
    request_marquee(scene)
    advance(scene, 0.1, now=100.6, text_interval=5.0)
    els = render_elements(scene, now=100.6)
    assert any(e.id == "marquee" for e in els)
    assert any(e.kind == "image" and e.id.startswith("frog") for e in els)


def test_is_wednesday() -> None:
    # 2026-09-09 is Wednesday.
    assert is_wednesday(datetime(2026, 9, 9))
    assert not is_wednesday(datetime(2026, 9, 8))


def test_build_draw_payload_happy_and_sad() -> None:
    from busybar.wednesday_frogs.payload import build_draw_payload

    happy = build_draw_payload(sad=False, marquee=True)
    sad = build_draw_payload(sad=True, marquee=True)
    assert happy["application_name"] == "wednesday-frogs"
    frogs = happy["elements"][0]
    assert frogs["type"] == "animation"
    assert frogs["path"] == "frogs_happy.anim"
    assert frogs["loop"] is True
    marquee = happy["elements"][1]
    assert marquee["text"] == "IT'S WEDNESDAY MY DUDES"
    assert marquee["color"] == "#7CFC00FF"
    assert sad["elements"][0]["path"] == "frogs_sad.anim"
    assert sad["elements"][1]["text"] == "IT IS NOT WEDNESDAY MY DUDES"
    assert sad["elements"][1]["color"] == "#A0A0A0FF"


def test_build_draw_payload_without_marquee() -> None:
    from busybar.wednesday_frogs.payload import build_draw_payload

    payload = build_draw_payload(sad=False, marquee=False)
    assert [el["id"] for el in payload["elements"]] == ["frogs"]
