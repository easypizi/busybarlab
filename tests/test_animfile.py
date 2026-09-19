"""Tests for bicycle0 encoder and frog anim bake."""

from busybar.common.animfile import decode_check, encode_anim, rle_compress, rle_decompress
from busybar.wednesday_frogs.bake import BakeConfig, bake_anim, render_frame


def test_rle_roundtrip() -> None:
    raw = bytes([1, 2, 3, 4] * 20 + [9, 9, 9, 9] * 10)
    enc = rle_compress(raw, 4)
    assert rle_decompress(enc, 4) == raw
    assert len(enc) < len(raw)


def test_encode_anim_roundtrip() -> None:
    frame_a = bytes([10, 20, 30, 255] * (72 * 16))
    frame_b = bytes([0, 0, 0, 0] * (72 * 16))
    frames = [frame_a, frame_a, frame_b]
    blob = encode_anim(frames, fps=10, width=72, height=16)
    assert blob.startswith(b"bicycle0")
    decode_check(blob, frames, width=72, height=16)


def test_bake_frogs_anim() -> None:
    cfg = BakeConfig(fps=10, frame_count=24, include_fly=True)
    blob = bake_anim(sad=False, config=cfg)
    assert blob.startswith(b"bicycle0")
    assert len(blob) > 100
    # Happy and sad frames should differ.
    frame_h = render_frame(0, sad=False, config=cfg)
    frame_s = render_frame(0, sad=True, config=cfg)
    assert frame_h != frame_s
