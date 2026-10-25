from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

from toy_lair_assistant.collector.models import FetchContext, RawItem

KEY_PREFIX = b"reading_list-dt-"
WINDOWS_EPOCH_OFFSET_S = 11_644_473_600
STATUS_READ = 1


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7
    raise ValueError("truncated varint")


def parse_entry(blob: bytes) -> dict[str, object]:
    """Decode ReadingListSpecifics: 1 entry_id, 2 title, 3 url, 4 created_us (Unix or Windows epoch), 5 updated_us, 6 status."""
    fields: dict[int, object] = {}
    pos = 0
    while pos < len(blob):
        tag, pos = _varint(blob, pos)
        number, wire = tag >> 3, tag & 7
        if wire == 0:
            value, pos = _varint(blob, pos)
            fields[number] = value
        elif wire == 2:
            size, pos = _varint(blob, pos)
            fields[number] = blob[pos : pos + size]
            pos += size
        elif wire == 1:
            pos += 8
        elif wire == 5:
            pos += 4
        else:
            break
    def text(num: int) -> str:
        raw = fields.get(num)
        return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else ""
    created = fields.get(4)
    stamp = ""
    if isinstance(created, int) and created > 0:
        seconds = created / 1_000_000
        if seconds > WINDOWS_EPOCH_OFFSET_S:
            seconds -= WINDOWS_EPOCH_OFFSET_S
        if seconds > 0:
            stamp = datetime.fromtimestamp(seconds, UTC).isoformat()
    status = fields.get(6)
    return {
        "url": text(3) or text(1),
        "title": text(2),
        "created": stamp,
        "status": status if isinstance(status, int) else 0,
    }


def read_entries(profile: Path) -> list[dict[str, object]]:
    import plyvel

    source = profile / "Sync Data" / "LevelDB"
    with tempfile.TemporaryDirectory(prefix="paco-rl-") as tmp:
        copy = Path(tmp) / "ldb"
        shutil.copytree(source, copy)
        (copy / "LOCK").unlink(missing_ok=True)
        db = plyvel.DB(str(copy))
        try:
            rows = [parse_entry(value) for key, value in db.iterator(prefix=KEY_PREFIX)]
        finally:
            db.close()
    return rows


class ChromeReadingList:
    name = "chrome"

    def __init__(
        self,
        profile: str | Path,
        reader: Callable[[Path], list[dict[str, object]]] = read_entries,
    ) -> None:
        self.profile = Path(profile).expanduser()
        self.reader = reader

    def fetch(self, ctx: FetchContext) -> Iterator[RawItem]:
        entries = [e for e in self.reader(self.profile) if e.get("url") and e.get("status") != STATUS_READ]
        entries.sort(key=lambda e: str(e.get("created") or ""), reverse=True)
        for entry in entries:
            url = str(entry["url"])
            if ctx.seen(url):
                continue
            yield RawItem(
                source=self.name,
                external_id=url,
                url=url,
                title=str(entry.get("title") or ""),
                captured_at=str(entry.get("created") or ""),
                fetch_page=True,
            )
