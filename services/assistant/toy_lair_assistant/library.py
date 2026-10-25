from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

DOC = "(coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(topics,'') || ' ' || coalesce(author,'') || ' ' || coalesce(snippet,''))"
ITEM_COLUMNS = (
    "id, source, external_id, url, title, author, summary, kind, topics, snippet, vault_path, captured_at, added_at"
)
JOB_TTL = timedelta(hours=1)


def item_id(source: str, external_id: str) -> str:
    return hashlib.sha1(f"{source}:{external_id}".encode()).hexdigest()[:12]


class LibraryStore:
    """Item index and collector job queue. SQLite for local runs, Postgres on Heroku."""

    def __init__(self, conn: Any, dialect: str) -> None:
        self.conn = conn
        self.pg = dialect == "postgres"
        self.lock = threading.RLock()
        self._create()

    def _q(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.pg else sql

    def _exec(self, sql: str, params: tuple = ()) -> list[tuple]:
        with self.lock:
            if self.pg:
                with self.conn.cursor() as cur:
                    cur.execute(self._q(sql), params)
                    rows = cur.fetchall() if cur.description else []
                self.conn.commit()
                return rows
            cur = self.conn.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
            self.conn.commit()
            return rows

    def _create(self) -> None:
        self._exec(
            """CREATE TABLE IF NOT EXISTS library_items (
                id TEXT PRIMARY KEY, source TEXT, external_id TEXT, url TEXT, title TEXT,
                author TEXT, summary TEXT, kind TEXT, topics TEXT, snippet TEXT,
                vault_path TEXT, captured_at TEXT, added_at TEXT)"""
        )
        self._exec(
            """CREATE TABLE IF NOT EXISTS collector_jobs (
                id TEXT PRIMARY KEY, kind TEXT, payload TEXT, status TEXT,
                message TEXT, created_at TEXT, claimed_at TEXT)"""
        )
        self._exec("CREATE TABLE IF NOT EXISTS collector_runs (at TEXT, summary TEXT)")

    # items
    def add_items(self, items: list[dict[str, Any]], now: datetime) -> int:
        count = 0
        for raw in items:
            source = str(raw.get("source") or "").strip()
            external = str(raw.get("external_id") or "").strip()
            if not source or not external:
                continue
            topics = json.dumps([str(t) for t in (raw.get("topics") or [])], ensure_ascii=False)
            values = (
                item_id(source, external), source, external, str(raw.get("url") or ""),
                str(raw.get("title") or "")[:300], str(raw.get("author") or "")[:200],
                str(raw.get("summary") or "")[:1000], str(raw.get("kind") or "other"), topics,
                str(raw.get("snippet") or "")[:500], str(raw.get("vault_path") or ""),
                str(raw.get("captured_at") or ""), now.astimezone(UTC).isoformat(),
            )
            self._exec(
                f"""INSERT INTO library_items({ITEM_COLUMNS}) VALUES ({",".join("?" * 13)})
                    ON CONFLICT (id) DO UPDATE SET url = excluded.url, title = excluded.title,
                    author = excluded.author, summary = excluded.summary, kind = excluded.kind,
                    topics = excluded.topics, snippet = excluded.snippet,
                    vault_path = excluded.vault_path, captured_at = excluded.captured_at""",
                values,
            )
            count += 1
        return count

    def search(
        self, query: str, source: str = "", kind: str = "", limit: int = 8
    ) -> list[dict[str, Any]]:
        words = [w.lower() for w in query.split() if w.strip()][:6]
        where: list[str] = []
        params: list[Any] = []
        for word in words:
            clause = f"lower({DOC}) LIKE ?"
            params.append(f"%{word}%")
            if self.pg:
                clause = (
                    f"({clause} OR to_tsvector('russian', {DOC}) @@ plainto_tsquery('russian', ?)"
                    f" OR to_tsvector('english', {DOC}) @@ plainto_tsquery('english', ?))"
                )
                params += [word, word]
            where.append(clause)
        if source:
            where.append("source = ?")
            params.append(source)
        if kind:
            where.append("kind = ?")
            params.append(kind)
        sql = f"SELECT {ITEM_COLUMNS} FROM library_items"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY added_at DESC LIMIT ?"
        params.append(max(1, min(limit, 25)))
        return [_item(r) for r in self._exec(sql, tuple(params))]

    def recent(self, now: datetime, source: str = "", days: int = 7, limit: int = 10) -> list[dict[str, Any]]:
        cutoff = (now - timedelta(days=days)).astimezone(UTC).isoformat()
        sql = f"SELECT {ITEM_COLUMNS} FROM library_items WHERE added_at >= ?"
        params: list[Any] = [cutoff]
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY added_at DESC LIMIT ?"
        params.append(max(1, min(limit, 25)))
        return [_item(r) for r in self._exec(sql, tuple(params))]

    def get(self, ident: str) -> dict[str, Any] | None:
        rows = self._exec(f"SELECT {ITEM_COLUMNS} FROM library_items WHERE id = ?", (ident,))
        return _item(rows[0]) if rows else None

    def counts(self) -> dict[str, int]:
        rows = self._exec("SELECT source, count(*) FROM library_items GROUP BY source")
        return {str(r[0]): int(r[1]) for r in rows}

    # jobs
    def enqueue_job(self, kind: str, payload: dict[str, Any], now: datetime) -> str:
        job_id = uuid.uuid4().hex[:10]
        self._exec(
            "INSERT INTO collector_jobs(id, kind, payload, status, message, created_at, claimed_at)"
            " VALUES (?, ?, ?, 'pending', '', ?, '')",
            (job_id, kind, json.dumps(payload, ensure_ascii=False), now.astimezone(UTC).isoformat()),
        )
        return job_id

    def claim_jobs(self, now: datetime, limit: int = 20) -> list[dict[str, Any]]:
        stale = (now - JOB_TTL).astimezone(UTC).isoformat()
        rows = self._exec(
            "SELECT id, kind, payload FROM collector_jobs WHERE status = 'pending'"
            " OR (status = 'claimed' AND claimed_at < ?) ORDER BY created_at LIMIT ?",
            (stale, limit),
        )
        jobs = []
        for job_id, kind, payload in rows:
            self._exec(
                "UPDATE collector_jobs SET status = 'claimed', claimed_at = ? WHERE id = ?",
                (now.astimezone(UTC).isoformat(), job_id),
            )
            jobs.append({"id": job_id, "kind": kind, "payload": json.loads(payload or "{}")})
        return jobs

    def finish_job(self, job_id: str, ok: bool, message: str) -> bool:
        rows = self._exec("SELECT 1 FROM collector_jobs WHERE id = ?", (job_id,))
        if not rows:
            return False
        self._exec(
            "UPDATE collector_jobs SET status = ?, message = ? WHERE id = ?",
            ("done" if ok else "failed", message[:300], job_id),
        )
        return True

    def pending_jobs(self) -> int:
        rows = self._exec("SELECT count(*) FROM collector_jobs WHERE status IN ('pending', 'claimed')")
        return int(rows[0][0]) if rows else 0

    # runs
    def record_run(self, summary: dict[str, Any], now: datetime) -> None:
        self._exec(
            "INSERT INTO collector_runs(at, summary) VALUES (?, ?)",
            (now.astimezone(UTC).isoformat(), json.dumps(summary, ensure_ascii=False)),
        )

    def last_run(self) -> dict[str, Any] | None:
        rows = self._exec("SELECT at, summary FROM collector_runs ORDER BY at DESC LIMIT 1")
        if not rows:
            return None
        return {"at": rows[0][0], **json.loads(rows[0][1] or "{}")}


def _item(row: tuple) -> dict[str, Any]:
    keys = [c.strip() for c in ITEM_COLUMNS.split(",")]
    data = dict(zip(keys, row, strict=True))
    try:
        data["topics"] = json.loads(data.get("topics") or "[]")
    except json.JSONDecodeError:
        data["topics"] = []
    return data


def open_library(database_url: str) -> LibraryStore:
    if database_url.startswith("postgres"):
        import psycopg

        return LibraryStore(psycopg.connect(database_url), "postgres")
    path = ":memory:"
    if database_url.startswith("sqlite"):
        path = database_url.split("///", 1)[-1] or ":memory:"
    conn = sqlite3.connect(path, check_same_thread=False)
    return LibraryStore(conn, "sqlite")
