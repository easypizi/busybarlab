from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from toy_lair_assistant.collector.models import FetchContext, RawItem
from toy_lair_assistant.collector.vault_layout import is_blocked
from toy_lair_assistant.paco_vault import _split_frontmatter, _title
from toy_lair_assistant.zayka import ZaykaIndex

INDEX_PREFIXES = ("10 Evergreen", "20 Sources", "30 Projects", "40 Areas", "50 MOC", "Home.md")
SNIPPET = 300


class ZaykaNotes:
    """Indexes vault notes into the library. Never writes to the vault."""

    name = "zayka"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.index = ZaykaIndex(root, prefixes=INDEX_PREFIXES)

    def fetch(self, ctx: FetchContext) -> Iterator[RawItem]:
        for path in sorted(self.root.rglob("*.md")):
            rel = path.relative_to(self.root).as_posix()
            if is_blocked(rel) or not self.index.allowed(rel):
                continue
            if rel.startswith("20 Sources/") and path.parent.name in {"instagram", "telegram", "gmail", "chrome", "bot"}:
                continue
            version = int(path.stat().st_mtime)
            ext = f"{rel}@{version}"
            if ctx.seen(ext):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            front, body = _split_frontmatter(text)
            yield RawItem(
                source=self.name,
                external_id=ext,
                url="",
                title=_title(front, path.stem),
                text=" ".join(body.split())[:SNIPPET],
                extra={"indexed_only": True, "rel": rel, "stable_id": rel},
            )
