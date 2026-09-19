from pathlib import Path

from toy_lair_assistant.paths import creation_dir, resolve_creation_dir


def test_local_creation_dir_prefers_repo_copy() -> None:
    path = creation_dir()
    assert (path / "index.html").exists()
    assert (path / "install.html").exists()


def test_heroku_layout_uses_bundled_static(tmp_path: Path) -> None:
    here = tmp_path / "toy_lair_assistant" / "paths.py"
    here.parent.mkdir()
    here.write_text("", encoding="utf-8")
    bundled = tmp_path / "static" / "creation"
    bundled.mkdir(parents=True)
    (bundled / "index.html").write_text("ok", encoding="utf-8")
    resolved = resolve_creation_dir(here)
    assert resolved == bundled
