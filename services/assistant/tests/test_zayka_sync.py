from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from toy_lair_assistant.paco import PacoAgent
from toy_lair_assistant.settings import Settings
from toy_lair_assistant.zayka_sync import attach_zayka, sync


class FakeAgent:
    def __init__(self) -> None:
        self.zayka = None


def test_sync_skips_when_dir_unset() -> None:
    calls: list[list[str]] = []

    def runner(cmd, cwd=None, check=False):
        calls.append(cmd)
        return None

    assert sync(Settings(zayka_dir=""), runner=runner) is None
    assert calls == []


def test_sync_pulls_existing_clone(tmp_path: Path) -> None:
    dest = tmp_path / "zayka"
    dest.mkdir()
    (dest / ".git").mkdir()
    calls: list[tuple[list[str], str]] = []

    def runner(cmd, cwd=None, check=False):
        calls.append((cmd, str(cwd)))
        return None

    path = sync(Settings(zayka_dir=str(dest)), runner=runner)
    assert path == dest
    assert calls == [(["git", "pull", "--ff-only"], str(dest))]


def test_sync_clones_when_missing(tmp_path: Path) -> None:
    dest = tmp_path / "vault" / "zayka"
    calls: list[list[str]] = []

    def runner(cmd, cwd=None, check=False):
        calls.append(cmd)
        dest.mkdir(parents=True)
        (dest / ".git").mkdir()
        return None

    path = sync(
        Settings(
            zayka_dir=str(dest),
            zayka_repo_url="https://TOKEN@github.com/easypizi/zayka.git",
        ),
        runner=runner,
    )
    assert path == dest
    assert calls == [
        [
            "git",
            "clone",
            "--depth",
            "1",
            "https://TOKEN@github.com/easypizi/zayka.git",
            str(dest),
        ]
    ]


def test_sync_keeps_existing_clone_if_pull_fails(tmp_path: Path) -> None:
    dest = tmp_path / "zayka"
    dest.mkdir()
    (dest / ".git").mkdir()

    def runner(cmd, cwd=None, check=False):
        raise RuntimeError("git unavailable")

    path = sync(Settings(zayka_dir=str(dest)), runner=runner)
    assert path == dest


def test_attach_zayka_sets_agent_index(tmp_path: Path) -> None:
    dest = tmp_path / "zayka"
    dest.mkdir()
    (dest / "Home.md").write_text("hello\n", encoding="utf-8")

    class Deps:
        settings = Settings(zayka_dir=str(dest))
        agent = FakeAgent()
        zayka = None

    attach_zayka(Deps, sync_fn=lambda settings: dest)
    assert Deps.zayka is not None
    assert Deps.agent.zayka is Deps.zayka
    assert Deps.zayka.read("Home.md") == "hello\n"


def test_attach_zayka_builds_paco_after_clone(tmp_path: Path) -> None:
    dest = tmp_path / "zayka"
    dest.mkdir()
    (dest / "Home.md").write_text("hello\n", encoding="utf-8")

    class Clock:
        def now(self) -> datetime:
            return datetime(2026, 9, 23, 12, 0, tzinfo=ZoneInfo("America/Los_Angeles"))

    class Deps:
        settings = Settings(
            zayka_dir=str(dest),
            openai_api_key="test-key",
            openai_model="gpt-4.1-mini",
            timezone="America/Los_Angeles",
            zayka_sync_enabled=False,
        )
        agent = None
        zayka = None
        paco = None
        clock = Clock()
        store = None

    attach_zayka(Deps, sync_fn=lambda settings: dest)
    assert isinstance(Deps.paco, PacoAgent)


def test_settings_skip_auto_sync_under_pytest() -> None:
    settings = Settings(zayka_dir="/tmp/zayka", zayka_sync_enabled=True)
    assert settings.zayka_should_sync() is False
