from pathlib import Path

import pytest


def test_stage_js_is_shared() -> None:
    service_dir = Path(__file__).resolve().parents[1]
    root = service_dir.parents[1]
    left = (root / "rabbit" / "assistant" / "stage.js").read_bytes()
    right = (root / "rabbit" / "paco" / "stage.js").read_bytes()
    carlos = (root / "rabbit" / "carlos" / "stage.js").read_bytes()
    assert left == right == carlos
    assert b"webgl" not in left
    assert b"SPEECH_CPS" in left


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


def test_carlos_static_copy_matches_rabbit() -> None:
    service_dir = Path(__file__).resolve().parents[1]
    static = service_dir / "static" / "carlos"
    repo_root = service_dir.parents[1]
    source = repo_root / "rabbit" / "carlos"
    if not (source / "index.html").exists() or not (static / "index.html").exists():
        pytest.skip("repo layout is absent")
    names = sorted(path.name for path in source.iterdir() if path.is_file())
    assert names
    for name in names:
        left = (source / name).read_bytes()
        right = (static / name).read_bytes()
        assert left == right, name
