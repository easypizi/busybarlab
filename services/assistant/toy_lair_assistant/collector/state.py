from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class CollectorState:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path) if str(path) == ":memory:" else str(Path(path).expanduser()))
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS done (key TEXT PRIMARY KEY, url_key TEXT, at TEXT);
            CREATE INDEX IF NOT EXISTS done_url ON done(url_key);
            CREATE TABLE IF NOT EXISTS cursors (name TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS push_queue (key TEXT PRIMARY KEY, payload TEXT);
            CREATE TABLE IF NOT EXISTS library (
                key TEXT PRIMARY KEY, kind TEXT, title TEXT, rel_path TEXT
            );
            CREATE TABLE IF NOT EXISTS runs (at TEXT, source TEXT, ok INTEGER, note TEXT);
            """
        )
        self.conn.commit()

    def is_done(self, key: str, url_key: str = "") -> bool:
        row = self.conn.execute("SELECT 1 FROM done WHERE key = ?", (key,)).fetchone()
        if row:
            return True
        if url_key:
            return (
                self.conn.execute("SELECT 1 FROM done WHERE url_key = ?", (url_key,)).fetchone()
                is not None
            )
        return False

    def mark_done(self, key: str, url_key: str = "") -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO done(key, url_key, at) VALUES (?, ?, ?)",
            (key, url_key, datetime.now(UTC).isoformat()),
        )
        self.conn.commit()

    def cursors(self) -> dict[str, str]:
        return {r[0]: r[1] for r in self.conn.execute("SELECT name, value FROM cursors")}

    def set_cursors(self, values: dict[str, str]) -> None:
        for name, value in values.items():
            self.conn.execute(
                "INSERT OR REPLACE INTO cursors(name, value) VALUES (?, ?)", (name, value)
            )
        self.conn.commit()

    def queue_push(self, key: str, payload: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO push_queue(key, payload) VALUES (?, ?)",
            (key, json.dumps(payload)),
        )
        self.conn.commit()

    def pending_pushes(self) -> list[tuple[str, dict[str, Any]]]:
        rows = self.conn.execute("SELECT key, payload FROM push_queue ORDER BY rowid").fetchall()
        return [(r[0], json.loads(r[1])) for r in rows]

    def clear_push(self, keys: list[str]) -> None:
        for key in keys:
            self.conn.execute("DELETE FROM push_queue WHERE key = ?", (key,))
        self.conn.commit()

    def add_library(self, key: str, kind: str, title: str, rel_path: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO library(key, kind, title, rel_path) VALUES (?, ?, ?, ?)",
            (key, kind, title, rel_path),
        )
        self.conn.commit()

    def library_by_kind(self, kind: str) -> list[tuple[str, str]]:
        rows = self.conn.execute(
            "SELECT title, rel_path FROM library WHERE kind = ? ORDER BY rel_path", (kind,)
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def log_run(self, source: str, ok: bool, note: str = "") -> None:
        self.conn.execute(
            "INSERT INTO runs(at, source, ok, note) VALUES (?, ?, ?, ?)",
            (datetime.now(UTC).isoformat(), source, 1 if ok else 0, note[:500]),
        )
        self.conn.commit()
