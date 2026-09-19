from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ALLOWED_PREFIXES = (
    "10 Evergreen",
    "30 Projects",
    "40 Areas",
    "50 MOC",
    "Home.md",
)
BLOCKED_PARTS = (
    "40 Areas/sensitive",
    ".obsidian",
    ".smart-env",
    ".git",
    "Presentations",
)


@dataclass
class ZaykaHit:
    path: str
    title: str
    snippet: str


class ZaykaIndex:
    def __init__(self, root: Path) -> None:
        self.root = root

    def search(self, query: str) -> list[ZaykaHit]:
        needle = query.lower().strip()
        hits: list[ZaykaHit] = []
        if not needle:
            return hits
        for path in self._iter_notes():
            text = path.read_text(encoding="utf-8", errors="replace")
            if needle not in text.lower() and needle not in path.name.lower():
                continue
            rel = self._rel(path)
            hits.append(
                ZaykaHit(
                    path=rel,
                    title=path.stem,
                    snippet=_snippet(text, needle),
                )
            )
        return hits

    def read(self, relative: str) -> str:
        if not self.allowed(relative):
            raise PermissionError(f"blocked path: {relative}")
        path = (self.root / relative).resolve()
        if self.root.resolve() not in path.parents and path != self.root.resolve():
            raise PermissionError(f"blocked path: {relative}")
        if not self.allowed(str(path.relative_to(self.root))):
            raise PermissionError(f"blocked path: {relative}")
        return path.read_text(encoding="utf-8")

    def allowed(self, relative: str) -> bool:
        norm = relative.replace("\\", "/")
        if any(part in norm for part in BLOCKED_PARTS):
            return False
        if norm == "Home.md":
            return True
        return any(norm == prefix or norm.startswith(prefix + "/") for prefix in ALLOWED_PREFIXES)

    def _iter_notes(self) -> list[Path]:
        notes: list[Path] = []
        if not self.root.exists():
            return notes
        for path in self.root.rglob("*.md"):
            rel = self._rel(path)
            if self.allowed(rel):
                notes.append(path)
        return notes

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.root)).replace("\\", "/")


def _snippet(text: str, needle: str) -> str:
    lower = text.lower()
    idx = lower.find(needle)
    if idx < 0:
        return text.strip().splitlines()[0][:160] if text.strip() else ""
    start = max(0, idx - 40)
    end = min(len(text), idx + 80)
    return " ".join(text[start:end].split())
