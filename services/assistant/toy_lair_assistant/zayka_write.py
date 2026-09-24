from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from toy_lair_assistant.paco_vault import PacoVault

log = logging.getLogger(__name__)

Runner = Callable[..., Any]


def git_runner(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)

INBOX_FILE = re.compile(r"^00 Inbox/\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
DAILY_FILE = re.compile(r"^60 Daily/\d{4}/\d{2}/\d{4}-\d{2}-\d{2}\.md$")

WEEKDAYS = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)
MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


@dataclass
class WriteResult:
    ok: bool
    path: str
    message: str


_AUTH_MARKERS = (
    "authentication failed",
    "invalid username or token",
    "could not read username",
    "terminal prompts disabled",
    "returned error: 401",
)


class ZaykaWrite:
    def __init__(self, root: Path, runner: Runner, zone: ZoneInfo) -> None:
        self.root = root
        self.runner = runner
        self.zone = zone
        self.last_error = ""

    def inbox_create(
        self,
        now: datetime,
        title: str,
        body: str,
        filename_hint: str,
        related: list[str] | None,
    ) -> WriteResult:
        local = _local(now, self.zone)
        rel = _inbox_rel(self.root, local, filename_hint or title)
        target = self._target(rel)
        if target is None:
            return WriteResult(False, "", "refused")
        if not self._pull():
            return self._pull_result(rel)
        rel = _inbox_rel(self.root, local, filename_hint or title)
        target = self._target(rel)
        if target is None:
            return WriteResult(False, "", "refused")
        kept = keep_related(related, PacoVault(self.root, self.zone).stems())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            fleeting_note(local, title, body, kept),
            encoding="utf-8",
        )
        return self._publish(rel, f"Capture: {title}")

    def daily_append(self, now: datetime, text: str) -> WriteResult:
        local = _local(now, self.zone)
        rel = f"60 Daily/{local:%Y/%m/%Y-%m-%d}.md"
        target = self._target(rel)
        if target is None:
            return WriteResult(False, "", "refused")
        if not self._pull():
            return self._pull_result(rel)
        target = self._target(rel)
        if target is None:
            return WriteResult(False, "", "refused")
        target.parent.mkdir(parents=True, exist_ok=True)
        block = f"## Capture {local:%H:%M}\n{text.strip()}\n"
        if target.exists():
            original = target.read_text(encoding="utf-8")
            prefix = original if original.endswith("\n") else original + "\n"
            target.write_text(prefix + block, encoding="utf-8")
        else:
            target.write_text(daily_note(local, block), encoding="utf-8")
        return self._publish(rel, f"Daily: {local:%Y-%m-%d}")

    def _target(self, rel: str) -> Path | None:
        if not allowed_write(rel):
            return None
        root = self.root.resolve()
        path = (root / rel).resolve()
        if path != root and root not in path.parents:
            return None
        return path

    def _pull(self) -> bool:
        return self._run(["git", "pull", "--ff-only"])

    def _publish(self, rel: str, message: str) -> WriteResult:
        if not self._run(["git", "add", "--", rel]):
            return self._fail(rel)
        commit = [
            "git",
            "-c",
            "user.name=Paco",
            "-c",
            "user.email=paco@toy-lair",
            "commit",
            "--only",
            "--",
            rel,
            "-m",
            message,
        ]
        if not self._run(commit):
            return self._fail(rel)
        if not self._run(["git", "push", "origin", "HEAD"]):
            return self._fail(rel)
        return WriteResult(True, rel, "wrote")

    def _pull_result(self, rel: str) -> WriteResult:
        if any(marker in self.last_error.lower() for marker in _AUTH_MARKERS):
            return WriteResult(False, rel, "token_expired")
        return WriteResult(False, rel, "pull_failed")

    def _fail(self, rel: str) -> WriteResult:
        if any(marker in self.last_error.lower() for marker in _AUTH_MARKERS):
            return WriteResult(False, rel, "token_expired")
        return WriteResult(False, rel, "push_failed")

    def _run(self, args: list[str]) -> bool:
        result = self.runner(args, cwd=self.root)
        error = f"{getattr(result, 'stderr', '') or ''} {getattr(result, 'stdout', '') or ''}"
        self.last_error = error
        ok = int(getattr(result, "returncode", 1)) == 0
        if not ok:
            redacted = re.sub(r"https://[^@\s]+@", "https://***@", error)
            log.warning("git failed cmd=%s err=%s", args[:4], redacted[:400])
        return ok


def allowed_write(relative: str) -> bool:
    norm = relative.replace("\\", "/")
    if ".." in norm.split("/"):
        return False
    if norm == "00 Inbox/00 Inbox.md":
        return False
    return bool(INBOX_FILE.match(norm) or DAILY_FILE.match(norm))


def keep_related(related: list[str] | None, stems: set[str]) -> list[str]:
    kept: list[str] = []
    seen: set[str] = set()
    for raw in related or []:
        stem = str(raw).strip()
        if stem.startswith("[[") and stem.endswith("]]"):
            stem = stem[2:-1].strip()
        key = stem.casefold()
        if not key or key not in stems or key in seen:
            continue
        kept.append(stem)
        seen.add(key)
        if len(kept) == 2:
            break
    return kept


def slug(hint: str) -> str:
    parts: list[str] = []
    for char in hint.lower():
        if "a" <= char <= "z" or "0" <= char <= "9":
            parts.append(char)
        elif parts and parts[-1] != "-":
            parts.append("-")
    text = "".join(parts).strip("-")
    return text or "capture"


def fleeting_note(local: datetime, title: str, body: str, related: list[str]) -> str:
    due = (local + timedelta(days=2)).strftime("%Y-%m-%d")
    links = "[" + ", ".join(related) + "]" if related else "[]"
    paragraph = " ".join(body.split())
    return (
        "---\n"
        f"id: {local:%Y%m%d%H%M%S}\n"
        f"title: {_yaml_quote(title)}\n"
        f"date: {local:%Y-%m-%d}\n"
        "type: fleeting\n"
        "status: draft\n"
        "tags: [to-process]\n"
        f"related: {links}\n"
        "---\n"
        "\n"
        f"{paragraph}\n"
        "\n"
        "## Next step\n"
        f"- [ ] Обработать до: {due}\n"
    )


def daily_note(local: datetime, capture: str) -> str:
    heading = f"{WEEKDAYS[local.weekday()].capitalize()}, {local.day} {MONTHS[local.month - 1]} {local.year}"
    return (
        "---\n"
        f"id: {local:%Y%m%d%H%M%S}\n"
        f"title: {_yaml_quote(local.strftime('%Y-%m-%d'))}\n"
        f"date: {local:%Y-%m-%d}\n"
        "type: daily\n"
        "status: draft\n"
        "tags: []\n"
        "related: []\n"
        "---\n"
        "\n"
        f"# {heading}\n"
        "\n"
        "## Топ 3 на сегодня\n"
        "- [ ]\n"
        "- [ ]\n"
        "- [ ]\n"
        "\n"
        "## Захваты\n"
        "-\n"
        "\n"
        "## Встречи / звонки\n"
        "\n"
        "## Рефлексия\n"
        "\n"
        "---\n"
        "*Вечером*: что из захваченного заслуживает стать [[10 Evergreen]] заметкой?\n"
        "\n"
        f"{capture}"
    )


def _inbox_rel(root: Path, local: datetime, hint: str) -> str:
    stem = slug(hint)
    date = local.strftime("%Y-%m-%d")
    folder = root / "00 Inbox"
    name = f"{date}-{stem}.md"
    if (folder / name).exists():
        number = 2
        while (folder / f"{date}-{stem}-{number}.md").exists():
            number += 1
        name = f"{date}-{stem}-{number}.md"
    return f"00 Inbox/{name}"


def _local(now: datetime, zone: ZoneInfo) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=zone)
    return now.astimezone(zone)


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
