"""BUSY Bar .anim encoder (firmware 'bicycle0' format).

Independent implementation of the documented RLE + section layout used by
the device anim player. Frames are BGRA8888, little-endian structs.
"""

from __future__ import annotations

import struct
from typing import Sequence

MAX_BLOCKS = 127
COLOR_FORMAT_BGRA8888 = 2
ENCODING_RAW = 0
ENCODING_RLE = 1


def rle_compress(data: bytes, blk: int = 4) -> bytes:
    """Encode to the firmware RLE stream (literal / repeat opcodes)."""
    blocks = [data[i : i + blk] for i in range(0, len(data), blk)]
    out = bytearray()
    literals: list[bytes] = []

    def flush() -> None:
        for j in range(0, len(literals), MAX_BLOCKS):
            chunk = literals[j : j + MAX_BLOCKS]
            out.append(0x80 | len(chunk))
            out.extend(b"".join(chunk))
        literals.clear()

    i, n = 0, len(blocks)
    while i < n:
        run = 1
        while run < MAX_BLOCKS and i + run < n and blocks[i + run] == blocks[i]:
            run += 1
        if run >= 3:
            flush()
            out.append(run)
            out.extend(blocks[i])
        else:
            literals.extend(blocks[i : i + run])
        i += run
    flush()
    return bytes(out)


def rle_decompress(data: bytes, blk: int = 4) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        op = data[i]
        n = op & 0x7F
        i += 1
        if op & 0x80:
            out += data[i : i + n * blk]
            i += n * blk
        else:
            out += data[i : i + blk] * n
            i += blk
    return bytes(out)


def encode_anim(
    display_frames: Sequence[bytes],
    *,
    fps: int = 12,
    width: int = 72,
    height: int = 16,
    section_name: str = "default",
) -> bytes:
    """Encode BGRA8888 frames into a .anim blob with one named section."""
    if not display_frames:
        raise ValueError("display_frames must not be empty")
    frame_bytes = width * height * 4
    for idx, frame in enumerate(display_frames):
        if len(frame) != frame_bytes:
            raise ValueError(
                f"frame {idx} has {len(frame)} bytes, expected {frame_bytes}"
            )

    # Collapse identical consecutive frames into duration counts (max 255).
    file_frames: list[tuple[bytes, int]] = []
    for frame in display_frames:
        if file_frames and file_frames[-1][0] == frame and file_frames[-1][1] < 255:
            prev, dur = file_frames[-1]
            file_frames[-1] = (prev, dur + 1)
        else:
            file_frames.append((frame, 1))

    frames_blob = bytearray()
    max_len = 0
    for raw, duration in file_frames:
        rle = rle_compress(raw, 4)
        if len(rle) < len(raw):
            encoding, data = ENCODING_RLE, rle
        else:
            encoding, data = ENCODING_RAW, raw
        if len(data) > 0xFFFF:
            raise ValueError("frame payload exceeds 65535 bytes")
        max_len = max(max_len, len(data))
        frames_blob += struct.pack("<BBH", encoding, duration, len(data))
        frames_blob += data

    name = section_name.encode("ascii") + b"\x00"
    header_size = 36
    sections_len = 4 + 4 + 4 + 1 + len(name)
    section = (
        struct.pack(
            "<IIIB",
            0,
            len(display_frames) - 1,
            header_size + sections_len,
            file_frames[0][1],
        )
        + name
    )

    header = struct.pack(
        "<8sBBBBBHxIIIII",
        b"bicycle0",
        0,
        width,
        height,
        COLOR_FORMAT_BGRA8888,
        fps,
        max_len,
        len(section),
        len(frames_blob),
        1,
        len(file_frames),
        len(display_frames),
    )
    if len(header) != header_size:
        raise RuntimeError(f"header size {len(header)} != {header_size}")
    return bytes(header + section + frames_blob)


def decode_check(
    blob: bytes,
    display_frames: Sequence[bytes],
    *,
    width: int = 72,
    height: int = 16,
) -> None:
    """Round-trip sanity check. Raises AssertionError on mismatch."""
    (
        sig,
        _flags,
        fw,
        fh,
        fmt,
        _fps,
        _max_len,
        s_len,
        _f_len,
        _s_cnt,
        ff_cnt,
        df_cnt,
    ) = struct.unpack("<8sBBBBBHxIIIII", blob[:36])
    assert sig == b"bicycle0"
    assert (fw, fh, fmt) == (width, height, COLOR_FORMAT_BGRA8888)
    assert df_cnt == len(display_frames)
    off = 36 + s_len
    out: list[bytes] = []
    for _ in range(ff_cnt):
        enc, dur, ln = struct.unpack("<BBH", blob[off : off + 4])
        off += 4
        data = blob[off : off + ln]
        off += ln
        raw = rle_decompress(data, 4) if enc == ENCODING_RLE else data
        assert len(raw) == width * height * 4
        out.extend([raw] * dur)
    assert out == list(display_frames), "roundtrip mismatch"
