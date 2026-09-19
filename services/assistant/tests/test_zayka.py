from pathlib import Path

from toy_lair_assistant.zayka import ZaykaIndex


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "30 Projects").mkdir()
    (tmp_path / "40 Areas" / "sensitive").mkdir(parents=True)
    (tmp_path / "40 Areas" / "personal").mkdir()
    (tmp_path / "10 Evergreen").mkdir()
    (tmp_path / "30 Projects" / "hirescope.md").write_text(
        "---\ntitle: HireScope\n---\n\nHiring product for founders.\n",
        encoding="utf-8",
    )
    (tmp_path / "40 Areas" / "personal" / "life-plan.md").write_text(
        "House and health goals.\n",
        encoding="utf-8",
    )
    (tmp_path / "40 Areas" / "sensitive" / "secrets.md").write_text(
        "passport number 123\n",
        encoding="utf-8",
    )
    (tmp_path / "10 Evergreen" / "atomic-notes.md").write_text(
        "One note is one idea.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_search_and_read(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    index = ZaykaIndex(vault)
    hits = index.search("hiring")
    paths = [hit.path for hit in hits]
    assert any(p.endswith("hirescope.md") for p in paths)
    assert not any("sensitive" in p for p in paths)
    note = index.read("30 Projects/hirescope.md")
    assert "Hiring product" in note
    try:
        index.read("40 Areas/sensitive/secrets.md")
    except PermissionError:
        return
    raise AssertionError("sensitive note must be blocked")
