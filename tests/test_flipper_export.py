"""Tests for Flipper config export and dual-anim install."""

from __future__ import annotations

from pathlib import Path

from busybar.wednesday_frogs.flipper_export import write_flipper_config
from busybar.wednesday_frogs.install import draw_frogs, upload_both_anims


class FakeBar:
    def __init__(self) -> None:
        self.uploads: list[str] = []
        self.draws: list[object] = []
        self.cleared = False
        self.deleted = False

    def display_clear(self, application_name: str) -> None:
        self.cleared = True

    def assets_delete(self, application_name: str) -> None:
        self.deleted = True

    def assets_upload(self, application_name: str, filename: str, data: bytes) -> None:
        self.uploads.append(filename)
        assert data

    def display_draw(self, elements: object) -> None:
        self.draws.append(elements)


def test_upload_both_anims(tmp_path: Path) -> None:
    (tmp_path / "frogs_happy.anim").write_bytes(b"happy")
    (tmp_path / "frogs_sad.anim").write_bytes(b"sadxx")
    bar = FakeBar()
    upload_both_anims(bar, tmp_path)
    assert bar.uploads == ["frogs_happy.anim", "frogs_sad.anim"]


def test_draw_frogs_uses_payload() -> None:
    bar = FakeBar()
    draw_frogs(bar, sad=True, marquee=True)
    assert len(bar.draws) == 1
    payload = bar.draws[0]
    dumped = payload.model_dump()
    assert dumped["application_name"] == "wednesday-frogs"
    assert dumped["elements"][0]["path"] == "frogs_sad.anim"


def test_write_flipper_config(tmp_path: Path) -> None:
    path = write_flipper_config(
        tmp_path / "busybar_frogs.conf.json",
        bar_ip="192.168.1.50",
        token="secret",
        marquee=True,
    )
    data = path.read_text()
    assert '"base_url": "http://192.168.1.50/api"' in data
    assert '"token": "secret"' in data
    assert "frogs_happy.anim" in data
    assert "frogs_sad.anim" in data
    assert "wednesday-frogs" in data
