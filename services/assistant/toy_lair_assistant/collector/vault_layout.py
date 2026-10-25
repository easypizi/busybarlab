from __future__ import annotations

import re
import subprocess
import unicodedata
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from toy_lair_assistant.collector.models import Enriched, RawItem, item_hash
from toy_lair_assistant.zayka_write import slug

Runner = Callable[..., Any]

DIARY = "\u0414\u043d\u0435\u0432\u043d\u0438\u043a"
BLOCKED_PARTS = (
    ("40 Areas", "sensitive"),
    ("60 Daily", DIARY),
)
BLOCKED_NAMES = {".obsidian", ".git", ".smart-env", "Presentations"}
SOURCE_RE = re.compile(
    r"^20 Sources/(instagram|telegram|gmail|chrome|bot)/[a-z0-9]+(?:-[a-z0-9]+)*\.md$"
)
MOC_RE = re.compile(r"^50 MOC/MOC-[A-Za-z0-9]+\.md$")
LINK_PREFIXES = ("10 Evergreen/", "30 Projects/", "40 Areas/", "50 MOC/")
LINKS_OPEN = "<!-- paco:links -->"
LINKS_CLOSE = "<!-- /paco:links -->"
TRANSCRIPT_LIMIT = 3000
MOC_MIN_ITEMS = 3


def _norm(rel: str) -> list[str]:
    return [unicodedata.normalize("NFC", p) for p in rel.replace("\\", "/").split("/")]


def is_blocked(rel: str) -> bool:
    parts = _norm(rel)
    if ".." in parts or any(p in BLOCKED_NAMES for p in parts):
        return True
    for blocked in BLOCKED_PARTS:
        if tuple(parts[: len(blocked)]) == blocked:
            return True
    return False


def allowed_create(rel: str) -> bool:
    norm = "/".join(_norm(rel))
    if is_blocked(norm):
        return False
    return bool(SOURCE_RE.match(norm) or MOC_RE.match(norm))


def allowed_link_target(rel: str) -> bool:
    norm = "/".join(_norm(rel))
    if is_blocked(norm) or not norm.endswith(".md"):
        return False
    return norm.startswith(LINK_PREFIXES)


def git_runner(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)


class VaultWriter:
    def __init__(
        self,
        root: Path,
        zone: ZoneInfo,
        state: Any,
        runner: Runner = git_runner,
        push: bool = True,
    ) -> None:
        self.root = root
        self.zone = zone
        self.state = state
        self.runner = runner
        self.push = push
        self.touched: list[str] = []
        self._touched_kinds: set[str] = set()
        self.last_error = ""
        self.grown_mocs: list[str] = []

    # git helpers
    def _run(self, args: list[str]) -> bool:
        result = self.runner(args, cwd=self.root)
        self.last_error = f"{getattr(result, 'stderr', '') or ''}{getattr(result, 'stdout', '') or ''}"
        return int(getattr(result, "returncode", 1)) == 0

    def begin(self) -> bool:
        self.touched = []
        self._touched_kinds = set()
        self.grown_mocs = []
        if not self.push:
            return True
        return self._run(["git", "pull", "--ff-only"])

    # vault scanning
    def stem_map(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for path in sorted(self.root.rglob("*.md")):
            rel = path.relative_to(self.root).as_posix()
            if is_blocked(rel):
                continue
            found.setdefault(unicodedata.normalize("NFC", path.stem).casefold(), rel)
        return found

    def note_titles(self, limit: int = 300) -> list[str]:
        names = [Path(rel).stem for rel in self.stem_map().values() if not rel.startswith("20 Sources/")]
        return names[:limit]

    # writes
    def add(self, item: RawItem, enriched: Enriched, stems: dict[str, str] | None = None) -> str:
        local = self._local(item.captured_at)
        stem = f"{slug(item.title or item.url or item.external_id)[:48].strip('-') or 'item'}-{item_hash(item.source, item.external_id)[:6]}"
        rel = f"20 Sources/{item.source}/{stem}.md"
        if not allowed_create(rel):
            raise ValueError(f"blocked path {rel}")
        target = self.root / rel
        known = stems if stems is not None else self.stem_map()
        related = [n for n in enriched.related if n.casefold() in known][:3]
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_source(local, item, enriched, related), encoding="utf-8")
        self.touched.append(rel)
        self._touched_kinds.add(enriched.kind)
        self.state.add_library(item.key, enriched.kind, item.title or item.url, rel)
        for name in related:
            self._link_back(known[name.casefold()], stem, item.title or stem)
        return rel

    def _link_back(self, rel: str, stem: str, title: str) -> None:
        if not allowed_link_target(rel):
            return
        path = self.root / rel
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
        line = f"- [[{stem}|{_one_line(title)}]]"
        if line in text:
            return
        new = _with_block(text, line, replace=False)
        path.write_text(new, encoding="utf-8")
        self.touched.append(rel)

    def update_collections(self) -> None:
        for kind in sorted(self._touched_kinds):
            rows = self.state.library_by_kind(kind)
            if len(rows) < MOC_MIN_ITEMS:
                continue
            rel = f"50 MOC/MOC-{kind.capitalize()}.md"
            if not allowed_create(rel):
                continue
            path = self.root / rel
            body = "\n".join(
                f"- [[{Path(p).stem}|{_one_line(t)}]]" for t, p in rows
            )
            existed = path.exists()
            if existed:
                new = _with_block(path.read_text(encoding="utf-8"), body, replace=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                now = datetime.now(self.zone)
                new = render_moc(now, kind, body)
            if not existed or new != path.read_text(encoding="utf-8"):
                path.write_text(new, encoding="utf-8")
                self.touched.append(rel)
                self.grown_mocs.append(rel)

    def commit_run(self, label: str) -> bool:
        paths = sorted(set(self.touched))
        if not paths:
            return True
        if not self.push:
            return True
        if not self._run(["git", "add", "--", *paths]):
            return False
        commit = [
            "git", "-c", "user.name=Paco", "-c", "user.email=paco@toy-lair",
            "commit", "--only", "-m", f"Library: {label}", "--", *paths,
        ]
        if not self._run(commit):
            return False
        return self._run(["git", "push", "origin", "HEAD"])

    def _local(self, stamp: str) -> datetime:
        if stamp:
            try:
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                return parsed.astimezone(self.zone) if parsed.tzinfo else parsed.replace(tzinfo=self.zone)
            except ValueError:
                pass
        return datetime.now(self.zone)


def _one_line(text: str) -> str:
    return " ".join(text.replace("|", "/").replace("[", "(").replace("]", ")").split())[:120]


def _with_block(text: str, lines: str, replace: bool) -> str:
    if LINKS_OPEN in text and LINKS_CLOSE in text:
        head, rest = text.split(LINKS_OPEN, 1)
        inner, tail = rest.split(LINKS_CLOSE, 1)
        if replace:
            inner_new = f"\n{lines}\n"
        else:
            inner_new = inner.rstrip("\n") + f"\n{lines}\n"
        return f"{head}{LINKS_OPEN}{inner_new}{LINKS_CLOSE}{tail}"
    sep = "" if text.endswith("\n") else "\n"
    return f"{text}{sep}\n{LINKS_OPEN}\n{lines}\n{LINKS_CLOSE}\n"


def _yaml(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_source(local: datetime, item: RawItem, enriched: Enriched, related: list[str]) -> str:
    links = "[" + ", ".join(related) + "]" if related else "[]"
    title = _one_line(item.title or item.url or item.external_id)
    lines = [
        "---",
        f"id: {local:%Y%m%d%H%M%S}",
        f"title: {_yaml(title)}",
        f"date: {local:%Y-%m-%d}",
        "type: source",
        "status: draft",
        "tags: [to-process]",
        f"related: {links}",
        f"source: {_yaml(item.url)}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    meta = [f"Kind: {enriched.kind}", f"From: {item.source}"]
    if item.author:
        meta.append(f"Author: {item.author}")
    lines.append(" | ".join(meta))
    lines.append("")
    if enriched.summary:
        lines += [enriched.summary.strip(), ""]
    if enriched.topics:
        lines += ["Topics: " + ", ".join(enriched.topics), ""]
    quote = enriched.transcript or ("" if item.private else item.text)
    if quote.strip():
        lines.append("## Excerpt")
        for row in quote.strip()[:TRANSCRIPT_LIMIT].splitlines():
            lines.append(f"> {row}" if row.strip() else ">")
        lines.append("")
    return "\n".join(lines)


def render_moc(local: datetime, kind: str, body: str) -> str:
    return (
        "---\n"
        f"id: {local:%Y%m%d%H%M%S}\n"
        f"title: {_yaml('MOC ' + kind.capitalize())}\n"
        f"date: {local:%Y-%m-%d}\n"
        "type: moc\n"
        "status: draft\n"
        "tags: []\n"
        "related: []\n"
        "---\n"
        "\n"
        f"# MOC {kind.capitalize()}\n"
        "\n"
        f"{LINKS_OPEN}\n{body}\n{LINKS_CLOSE}\n"
    )
