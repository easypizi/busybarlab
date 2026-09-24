import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from toy_lair_assistant.zayka_write import ZaykaWrite, allowed_write

ZONE = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 9, 22, 15, 4, tzinfo=ZONE)


def _writer(tmp_path: Path, fail: str = "") -> tuple[ZaykaWrite, list[list[str]]]:
    calls: list[list[str]] = []

    def runner(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        code = 1 if fail and args[:2] == ["git", fail] else 0
        if fail == "pull" and args[:3] == ["git", "pull", "--ff-only"]:
            code = 1
        if fail == "push" and args == ["git", "push"]:
            code = 1
        return subprocess.CompletedProcess(args, code)

    (tmp_path / "10 Evergreen").mkdir()
    (tmp_path / "10 Evergreen" / "atomic-notes.md").write_text("idea\n", encoding="utf-8")
    return ZaykaWrite(tmp_path, runner, ZONE), calls


def test_inbox_create_writes_fleeting_template(tmp_path: Path) -> None:
    writer, calls = _writer(tmp_path)
    result = writer.inbox_create(
        NOW,
        "Hire Scope",
        "A short thought",
        "hire scope idea",
        ["nope", "atomic-notes"],
    )
    assert result.message == "wrote"
    path = tmp_path / "00 Inbox" / "2026-09-22-hire-scope-idea.md"
    text = path.read_text(encoding="utf-8")
    assert "type: fleeting" in text
    assert "tags: [to-process]" in text
    assert "related: [atomic-notes]" in text
    assert "nope" not in text
    assert "## Related" not in text
    assert "Обработать до: 2026-09-24" in text
    assert "A short thought" in text
    assert ["git", "push"] in calls
    add = next(args for args in calls if args[:2] == ["git", "add"])
    assert add == ["git", "add", "--", "00 Inbox/2026-09-22-hire-scope-idea.md"]
    commit = next(args for args in calls if "commit" in args)
    assert commit[1:5] == ["-c", "user.name=Paco", "-c", "user.email=paco@toy-lair"]
    assert "--only" in commit
    assert commit.count("00 Inbox/2026-09-22-hire-scope-idea.md") == 1
    assert "config" not in commit


def test_empty_hint_and_cyrillic_become_ascii_slug(tmp_path: Path) -> None:
    writer, _calls = _writer(tmp_path)
    empty = writer.inbox_create(NOW, "Мысль", "text", "", [])
    assert empty.path.endswith("2026-09-22-capture.md")
    cyr = writer.inbox_create(NOW, "Focus", "text", "мысль focus", [])
    assert cyr.path.endswith("2026-09-22-focus.md")
    note = (tmp_path / "00 Inbox" / "2026-09-22-capture.md").read_text(encoding="utf-8")
    assert 'title: "Мысль"' in note


def test_name_collision_uses_suffix(tmp_path: Path) -> None:
    writer, _calls = _writer(tmp_path)
    first = writer.inbox_create(NOW, "Idea", "one", "idea", [])
    second = writer.inbox_create(NOW, "Idea", "two", "idea", [])
    assert first.path.endswith("2026-09-22-idea.md")
    assert second.path.endswith("2026-09-22-idea-2.md")


def test_missing_daily_uses_template_then_capture(tmp_path: Path) -> None:
    writer, _calls = _writer(tmp_path)
    result = writer.daily_append(NOW, "evening thought")
    assert result.message == "wrote"
    text = (tmp_path / "60 Daily" / "2026" / "09" / "2026-09-22.md").read_text(encoding="utf-8")
    assert "# Вторник, 22 сентября 2026" in text
    assert "## Топ 3 на сегодня" in text
    assert text.endswith("## Capture 15:04\nevening thought\n")


def test_existing_daily_appends_without_rewriting(tmp_path: Path) -> None:
    writer, _calls = _writer(tmp_path)
    path = tmp_path / "60 Daily" / "2026" / "09" / "2026-09-22.md"
    path.parent.mkdir(parents=True)
    original = "# already here\n"
    path.write_text(original, encoding="utf-8")
    writer.daily_append(NOW, "more")
    text = path.read_text(encoding="utf-8")
    assert text.startswith(original)
    assert text.endswith("## Capture 15:04\nmore\n")


def test_old_diary_path_is_not_a_write_target(tmp_path: Path) -> None:
    assert not allowed_write("60 Daily/Дневник/22.09.2026.md")
    assert not allowed_write("60 Daily/brainteasers.md")
    assert not allowed_write("60 Daily/60 Daily.md")
    assert not allowed_write("00 Inbox/00 Inbox.md")
    writer, calls = _writer(tmp_path)
    writer.daily_append(NOW, "note")
    assert not (tmp_path / "60 Daily" / "Дневник").exists()
    assert calls


def test_pull_failure_writes_nothing_and_does_not_push(tmp_path: Path) -> None:
    writer, calls = _writer(tmp_path, fail="pull")
    result = writer.inbox_create(NOW, "Idea", "text", "idea", [])
    assert result.message == "pull_failed"
    assert not (tmp_path / "00 Inbox" / "2026-09-22-idea.md").exists()
    assert not any(args == ["git", "push"] for args in calls)


def test_push_failure_does_not_report_wrote(tmp_path: Path) -> None:
    writer, calls = _writer(tmp_path, fail="push")
    result = writer.inbox_create(NOW, "Idea", "text", "idea", [])
    assert result.message == "push_failed"
    assert result.ok is False
    assert ["git", "push"] in calls
