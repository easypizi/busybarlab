from pathlib import Path

import pytest


def test_creation_static_copy_matches_rabbit() -> None:
    service_dir = Path(__file__).resolve().parents[1]
    static = service_dir / "static" / "creation"
    repo_root = service_dir.parents[1]
    source = repo_root / "rabbit" / "assistant"
    if not (source / "index.html").exists() or not (static / "index.html").exists():
        pytest.skip("repo layout is absent")
    names = sorted(path.name for path in source.iterdir() if path.is_file())
    assert names
    for name in names:
        left = (source / name).read_bytes()
        right = (static / name).read_bytes()
        assert left == right, name


def test_paco_static_copy_matches_rabbit() -> None:
    service_dir = Path(__file__).resolve().parents[1]
    static = service_dir / "static" / "paco"
    repo_root = service_dir.parents[1]
    source = repo_root / "rabbit" / "paco"
    if not (source / "index.html").exists() or not (static / "index.html").exists():
        pytest.skip("repo layout is absent")
    names = sorted(path.name for path in source.iterdir() if path.is_file())
    assert names
    for name in names:
        left = (source / name).read_bytes()
        right = (static / name).read_bytes()
        assert left == right, name
