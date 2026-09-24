import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from toy_lair_assistant.paco_vault import PacoVault
from toy_lair_assistant.zayka import ZaykaIndex

ZONE = ZoneInfo("America/Los_Angeles")


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "00 Inbox").mkdir()
    (tmp_path / "10 Evergreen").mkdir()
    (tmp_path / "40 Areas" / "sensitive").mkdir(parents=True)
    (tmp_path / "50 MOC").mkdir()
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "Presentations").mkdir()
    (tmp_path / "40 Areas" / "sensitive" / "secrets.md").write_text(
        "passport number 123\n",
        encoding="utf-8",
    )
    (tmp_path / ".obsidian" / "app.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "Presentations" / "deck.html").write_text("deck\n", encoding="utf-8")
    (tmp_path / "50 MOC" / "MOC-Frontend.md").write_text("# Frontend\n", encoding="utf-8")
    (tmp_path / "50 MOC" / "50 MOC.md").write_text("# MOC\n", encoding="utf-8")
    return tmp_path


def test_blocked_paths_are_not_readable(tmp_path: Path) -> None:
    vault = PacoVault(_vault(tmp_path), ZONE)
    assert vault.read_for_model("40 Areas/sensitive/secrets.md") == "blocked"
    assert vault.read_for_model(".obsidian/app.json") == "blocked"
    assert vault.read_for_model("Presentations/deck.html") == "blocked"
    assert vault.read_for_model("../outside.md") == "blocked"
    assert vault.read_for_model("00 Inbox/../../40 Areas/sensitive/secrets.md") == "blocked"


def test_search_skips_sensitive_and_caps_hits(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    evergreen = root / "10 Evergreen"
    for index in range(9):
        (evergreen / f"alpha-{index}.md").write_text("alpha word\n", encoding="utf-8")
    vault = PacoVault(root, ZONE)
    assert vault.search("passport") == []
    assert len(vault.search("alpha")) == 8


def test_inbox_lists_fifteen_newest_and_skips_folder_note(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    inbox = root / "00 Inbox"
    base = datetime(2026, 9, 22, 12, 0, tzinfo=ZONE)
    (inbox / "00 Inbox.md").write_text("# Inbox\n", encoding="utf-8")
    os.utime(inbox / "00 Inbox.md", _ts(base + timedelta(hours=19)))
    for index in range(1, 17):
        path = inbox / f"note-{index:02d}.md"
        path.write_text(
            f"---\ntitle: Note {index}\ntags: [to-process]\n---\n\nbody\n",
            encoding="utf-8",
        )
        os.utime(path, _ts(base + timedelta(hours=index)))
    vault = PacoVault(root, ZONE)
    items, count = vault.list_inbox(base + timedelta(hours=20))
    assert count == 16
    assert len(items) == 15
    assert items[0]["title"] == "Note 16"
    assert items[0]["age_hours"] == 4
    assert items[0]["tags"] == ["to-process"]
    assert all(item["title"] != "00 Inbox" for item in items)
    assert not ZaykaIndex(root).allowed("00 Inbox/note-01.md")


def test_read_for_model_truncates_body_and_keeps_late_heading(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    body = ("a" * 2500) + "\n# Late Heading\nTAILMARKER"
    (root / "10 Evergreen" / "long.md").write_text(
        "---\ntitle: Long\n---\n\n# Early\n\n" + body,
        encoding="utf-8",
    )
    text = PacoVault(root, ZONE).read_for_model("10 Evergreen/long.md")
    assert text.startswith("---")
    assert "# Late Heading" in text
    assert "TAILMARKER" not in text
    assert text.endswith("truncated")


def test_daily_path_and_moc_names(tmp_path: Path) -> None:
    vault = PacoVault(_vault(tmp_path), ZONE)
    now = datetime(2026, 9, 22, 15, 4, tzinfo=ZONE)
    assert vault.daily_rel(now) == "60 Daily/2026/09/2026-09-22.md"
    assert vault.moc_names() == ["MOC-Frontend"]
    assert "secrets" not in vault.stems()
    assert "moc-frontend" in vault.stems()


def _ts(moment: datetime) -> tuple[float, float]:
    stamp = moment.timestamp()
    return (stamp, stamp)
