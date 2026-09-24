from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from toy_lair_assistant.zayka import ZaykaHit, ZaykaIndex

PACO_PREFIXES = (
    "00 Inbox",
    "10 Evergreen",
    "30 Projects",
    "40 Areas",
    "50 MOC",
    "60 Daily",
    "Home.md",
)
INBOX_NOTE = "00 Inbox/00 Inbox.md"
READ_BODY_LIMIT = 2000


class PacoVault:
    def __init__(self, root: Path, zone: ZoneInfo) -> None:
        self.root = root
        self.zone = zone
        self.index = ZaykaIndex(root, prefixes=PACO_PREFIXES)

    def search(self, query: str) -> list[ZaykaHit]:
        return self.index.search(query)[:8]

    def read_for_model(self, relative: str) -> str:
        try:
            text = self.index.read(relative)
        except (OSError, PermissionError, ValueError):
            return "blocked"
        frontmatter, body = _split_frontmatter(text)
        headings = [
            line
            for line in body.splitlines()
            if line.lstrip().startswith("#")
        ]
        excerpt = body[:READ_BODY_LIMIT]
        parts = [part for part in (frontmatter, "\n".join(headings), excerpt) if part]
        if len(body) > READ_BODY_LIMIT:
            parts.append("truncated")
        return "\n".join(parts)

    def list_inbox(self, now: datetime) -> tuple[list[dict], int]:
        local = _as_zone(now, self.zone)
        notes = []
        inbox = self.root / "00 Inbox"
        if inbox.exists():
            for path in inbox.glob("*.md"):
                rel = self.index._rel(path)
                if rel == INBOX_NOTE or not self.index.allowed(rel):
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                notes.append((path, text, _stamp(path, text, self.zone)))
        notes.sort(key=lambda item: item[2], reverse=True)
        rows = []
        for path, text, stamp in notes[:15]:
            frontmatter, _body = _split_frontmatter(text)
            rows.append(
                {
                    "title": _title(frontmatter, path.stem),
                    "age_hours": _age_hours(local, stamp),
                    "tags": _tags(frontmatter),
                }
            )
        return rows, len(notes)

    def daily_rel(self, now: datetime) -> str:
        local = _as_zone(now, self.zone)
        return f"60 Daily/{local:%Y/%m/%Y-%m-%d}.md"

    def moc_names(self) -> list[str]:
        names = []
        for path in self.index._iter_notes():
            rel = self.index._rel(path)
            if not rel.startswith("50 MOC/"):
                continue
            if path.stem == "50 MOC":
                continue
            names.append(path.stem)
        return sorted(names)

    def stems(self) -> set[str]:
        return {path.stem.casefold() for path in self.index._iter_notes()}


def _as_zone(now: datetime, zone: ZoneInfo) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=zone)
    return now.astimezone(zone)


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end < 0:
        return "", text
    frontmatter = text[: end + 4]
    body = text[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]
    return frontmatter, body


def _title(frontmatter: str, stem: str) -> str:
    for line in frontmatter.splitlines():
        if not line.startswith("title:"):
            continue
        raw = line.split(":", 1)[1].strip().strip("\"'")
        if raw:
            return raw
    return stem


def _tags(frontmatter: str) -> list[str]:
    for line in frontmatter.splitlines():
        if not line.startswith("tags:"):
            continue
        raw = line.split(":", 1)[1].strip()
        if not (raw.startswith("[") and raw.endswith("]")):
            return []
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [part.strip().strip("\"'") for part in inner.split(",") if part.strip()]
    return []


def _stamp(path: Path, text: str, zone: ZoneInfo) -> datetime:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=zone)
    except OSError:
        return _front_date(text, zone)


def _front_date(text: str, zone: ZoneInfo) -> datetime:
    _front, _body = _split_frontmatter(text)
    for line in _front.splitlines():
        if not line.startswith("date:"):
            continue
        raw = line.split(":", 1)[1].strip()
        try:
            day = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            break
        return day.replace(tzinfo=zone)
    return datetime(1970, 1, 1, tzinfo=zone)


def _age_hours(now: datetime, stamp: datetime) -> int:
    hours = int((now - stamp).total_seconds() // 3600)
    return max(0, hours)
