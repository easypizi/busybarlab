from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from toy_lair_assistant.models import Reminder


class MemoryStore:
    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.reminders: dict[str, Reminder] = {}
        self.turns: list[dict[str, Any]] = []
        self.feedback: list[dict[str, Any]] = []

    def seen(self, key: str) -> bool:
        return key in self.keys

    def mark(self, key: str) -> None:
        self.keys.add(key)

    def add_reminder(self, reminder_id: str, fire_at: datetime, text: str) -> None:
        self.reminders[reminder_id] = Reminder(
            id=reminder_id,
            fire_at=fire_at.isoformat(),
            text=text,
            sent=False,
        )

    def due_reminders(self, now: datetime) -> list[Reminder]:
        due: list[Reminder] = []
        for reminder in self.reminders.values():
            if reminder.sent:
                continue
            if datetime.fromisoformat(reminder.fire_at) <= now:
                due.append(reminder)
        return due

    def mark_sent(self, reminder_id: str) -> None:
        reminder = self.reminders.get(reminder_id)
        if reminder:
            reminder.sent = True

    def add_turn(self, channel: str, role: str, content: str, at: datetime) -> None:
        self.turns.append(
            {"channel": channel, "role": role, "content": content, "at": at}
        )

    def recent_turns(
        self,
        channel: str,
        now: datetime,
        limit: int = 6,
        ttl_minutes: int = 15,
    ) -> list[dict[str, str]]:
        cutoff = now - timedelta(minutes=ttl_minutes)
        kept = [
            turn
            for turn in self.turns
            if turn["channel"] == channel and turn["at"] >= cutoff
        ]
        return [
            {"role": str(turn["role"]), "content": str(turn["content"])}
            for turn in kept[-limit:]
        ]

    def add_feedback(self, channel: str, turn_id: str, vote: str, at: datetime) -> None:
        self.feedback.append(
            {"channel": channel, "turn": turn_id, "vote": vote, "at": at}
        )


class SqliteStore:
    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS keys (key TEXT PRIMARY KEY, created_at TEXT)"
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                fire_at TEXT,
                text TEXT,
                sent INTEGER
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT,
                role TEXT,
                content TEXT,
                created_at TEXT
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT,
                turn TEXT,
                vote TEXT,
                created_at TEXT
            )"""
        )
        self.conn.commit()

    def seen(self, key: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM keys WHERE key = ?", (key,)).fetchone()
        return row is not None

    def mark(self, key: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO keys(key, created_at) VALUES (?, ?)",
            (key, datetime.now(UTC).isoformat()),
        )
        self.conn.commit()

    def add_reminder(self, reminder_id: str, fire_at: datetime, text: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO reminders(id, fire_at, text, sent) VALUES (?, ?, ?, 0)",
            (reminder_id, fire_at.isoformat(), text),
        )
        self.conn.commit()

    def due_reminders(self, now: datetime) -> list[Reminder]:
        rows = self.conn.execute(
            "SELECT id, fire_at, text, sent FROM reminders WHERE sent = 0 AND fire_at <= ?",
            (now.isoformat(),),
        ).fetchall()
        return [Reminder(id=r[0], fire_at=r[1], text=r[2], sent=bool(r[3])) for r in rows]

    def mark_sent(self, reminder_id: str) -> None:
        self.conn.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
        self.conn.commit()

    def add_turn(self, channel: str, role: str, content: str, at: datetime) -> None:
        self.conn.execute(
            "INSERT INTO turns(channel, role, content, created_at) VALUES (?, ?, ?, ?)",
            (channel, role, content, at.isoformat()),
        )
        self.conn.commit()

    def recent_turns(
        self,
        channel: str,
        now: datetime,
        limit: int = 6,
        ttl_minutes: int = 15,
    ) -> list[dict[str, str]]:
        cutoff = (now - timedelta(minutes=ttl_minutes)).isoformat()
        rows = self.conn.execute(
            """SELECT role, content FROM turns
               WHERE channel = ? AND created_at >= ?
               ORDER BY id ASC""",
            (channel, cutoff),
        ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows[-limit:]]

    def add_feedback(self, channel: str, turn_id: str, vote: str, at: datetime) -> None:
        self.conn.execute(
            "INSERT INTO feedback(channel, turn, vote, created_at) VALUES (?, ?, ?, ?)",
            (channel, turn_id, vote, at.isoformat()),
        )
        self.conn.commit()


def open_store(database_url: str) -> Any:
    if not database_url:
        return MemoryStore()
    if database_url.startswith("sqlite"):
        path = database_url.split("///", 1)[-1] or ":memory:"
        return SqliteStore(path)
    if database_url.startswith("postgres"):
        return PostgresStore(database_url)
    return SqliteStore(database_url)


class PostgresStore:
    def __init__(self, url: str) -> None:
        import psycopg

        self.conn = psycopg.connect(url)
        with self.conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS keys (key TEXT PRIMARY KEY, created_at TEXT)"
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    fire_at TEXT,
                    text TEXT,
                    sent INTEGER
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS turns (
                    id SERIAL PRIMARY KEY,
                    channel TEXT,
                    role TEXT,
                    content TEXT,
                    created_at TEXT
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS feedback (
                    id SERIAL PRIMARY KEY,
                    channel TEXT,
                    turn TEXT,
                    vote TEXT,
                    created_at TEXT
                )"""
            )
        self.conn.commit()

    def seen(self, key: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM keys WHERE key = %s", (key,))
            return cur.fetchone() is not None

    def mark(self, key: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO keys(key, created_at) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (key, datetime.now(UTC).isoformat()),
            )
        self.conn.commit()

    def add_reminder(self, reminder_id: str, fire_at: datetime, text: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO reminders(id, fire_at, text, sent)
                   VALUES (%s, %s, %s, 0)
                   ON CONFLICT (id) DO UPDATE SET fire_at = EXCLUDED.fire_at, text = EXCLUDED.text""",
                (reminder_id, fire_at.isoformat(), text),
            )
        self.conn.commit()

    def due_reminders(self, now: datetime) -> list[Reminder]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, fire_at, text, sent FROM reminders WHERE sent = 0 AND fire_at <= %s",
                (now.isoformat(),),
            )
            rows = cur.fetchall()
        return [Reminder(id=r[0], fire_at=r[1], text=r[2], sent=bool(r[3])) for r in rows]

    def mark_sent(self, reminder_id: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute("UPDATE reminders SET sent = 1 WHERE id = %s", (reminder_id,))
        self.conn.commit()

    def add_turn(self, channel: str, role: str, content: str, at: datetime) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO turns(channel, role, content, created_at) VALUES (%s, %s, %s, %s)",
                (channel, role, content, at.isoformat()),
            )
        self.conn.commit()

    def recent_turns(
        self,
        channel: str,
        now: datetime,
        limit: int = 6,
        ttl_minutes: int = 15,
    ) -> list[dict[str, str]]:
        cutoff = (now - timedelta(minutes=ttl_minutes)).isoformat()
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT role, content FROM turns
                   WHERE channel = %s AND created_at >= %s
                   ORDER BY id ASC""",
                (channel, cutoff),
            )
            rows = cur.fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows[-limit:]]

    def add_feedback(self, channel: str, turn_id: str, vote: str, at: datetime) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO feedback(channel, turn, vote, created_at) VALUES (%s, %s, %s, %s)",
                (channel, turn_id, vote, at.isoformat()),
            )
        self.conn.commit()
