from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from toy_lair_assistant.models import Reminder

DRAFT_TTL = timedelta(hours=12)


class MemoryStore:
    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.reminders: dict[str, Reminder] = {}
        self.turns: list[dict[str, Any]] = []
        self.feedback: list[dict[str, Any]] = []
        self.plans: dict[str, dict[str, Any]] = {}
        self.drafts: dict[str, dict[str, Any]] = {}
        self.workout_logs: list[dict[str, Any]] = []

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

    def save_plan(self, plan_id: str, payload: dict[str, Any], at: datetime) -> None:
        self.plans[plan_id] = {"payload": payload, "created_at": at}

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        row = self.plans.get(plan_id)
        if row is None:
            return None
        return row["payload"]

    def save_draft(self, channel: str, payload: dict[str, Any], at: datetime) -> None:
        self.drafts[channel] = {"payload": payload, "updated_at": at}

    def get_draft(self, channel: str, now: datetime) -> dict[str, Any] | None:
        row = self.drafts.get(channel)
        if row is None or not _draft_fresh(row["updated_at"], now):
            return None
        payload = row["payload"]
        return payload if isinstance(payload, dict) else None

    def clear_draft(self, channel: str) -> None:
        self.drafts.pop(channel, None)

    def append_workout_log(self, log_date: str, payload: dict[str, Any], at: datetime) -> None:
        self.workout_logs.append({"log_date": log_date, "payload": payload, "at": at})

    def last_workout_log(self, log_date: str) -> dict[str, Any] | None:
        for row in reversed(self.workout_logs):
            if row["log_date"] == log_date:
                payload = row["payload"]
                return payload if isinstance(payload, dict) else None
        return None

    def replace_last_workout_log(
        self, log_date: str, payload: dict[str, Any], at: datetime
    ) -> bool:
        for row in reversed(self.workout_logs):
            if row["log_date"] == log_date:
                row["payload"] = payload
                row["at"] = at
                return True
        return False


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
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY,
                payload TEXT,
                created_at TEXT
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS drafts (
                channel TEXT PRIMARY KEY,
                payload TEXT,
                updated_at TEXT
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS workout_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT,
                payload TEXT,
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

    def save_plan(self, plan_id: str, payload: dict[str, Any], at: datetime) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO plans(id, payload, created_at) VALUES (?, ?, ?)",
            (plan_id, json.dumps(payload), at.isoformat()),
        )
        self.conn.commit()

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload FROM plans WHERE id = ?", (plan_id,)
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        return data if isinstance(data, dict) else None

    def save_draft(self, channel: str, payload: dict[str, Any], at: datetime) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO drafts(channel, payload, updated_at) VALUES (?, ?, ?)",
            (channel, json.dumps(payload), at.isoformat()),
        )
        self.conn.commit()

    def get_draft(self, channel: str, now: datetime) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload, updated_at FROM drafts WHERE channel = ?",
            (channel,),
        ).fetchone()
        if row is None or not _draft_fresh(row[1], now):
            return None
        data = json.loads(row[0])
        return data if isinstance(data, dict) else None

    def clear_draft(self, channel: str) -> None:
        self.conn.execute("DELETE FROM drafts WHERE channel = ?", (channel,))
        self.conn.commit()

    def append_workout_log(self, log_date: str, payload: dict[str, Any], at: datetime) -> None:
        self.conn.execute(
            "INSERT INTO workout_logs(log_date, payload, created_at) VALUES (?, ?, ?)",
            (log_date, json.dumps(payload), at.isoformat()),
        )
        self.conn.commit()

    def last_workout_log(self, log_date: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload FROM workout_logs WHERE log_date = ? ORDER BY id DESC LIMIT 1",
            (log_date,),
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        return data if isinstance(data, dict) else None

    def replace_last_workout_log(
        self, log_date: str, payload: dict[str, Any], at: datetime
    ) -> bool:
        row = self.conn.execute(
            "SELECT id FROM workout_logs WHERE log_date = ? ORDER BY id DESC LIMIT 1",
            (log_date,),
        ).fetchone()
        if row is None:
            return False
        self.conn.execute(
            "UPDATE workout_logs SET payload = ?, created_at = ? WHERE id = ?",
            (json.dumps(payload), at.isoformat(), row[0]),
        )
        self.conn.commit()
        return True


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
            cur.execute(
                """CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    payload TEXT,
                    created_at TEXT
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS drafts (
                    channel TEXT PRIMARY KEY,
                    payload TEXT,
                    updated_at TEXT
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS workout_logs (
                    id SERIAL PRIMARY KEY,
                    log_date TEXT,
                    payload TEXT,
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

    def save_plan(self, plan_id: str, payload: dict[str, Any], at: datetime) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO plans(id, payload, created_at)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload,
                   created_at = EXCLUDED.created_at""",
                (plan_id, json.dumps(payload), at.isoformat()),
            )
        self.conn.commit()

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT payload FROM plans WHERE id = %s", (plan_id,))
            row = cur.fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        return data if isinstance(data, dict) else None

    def save_draft(self, channel: str, payload: dict[str, Any], at: datetime) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO drafts(channel, payload, updated_at)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (channel) DO UPDATE SET payload = EXCLUDED.payload,
                   updated_at = EXCLUDED.updated_at""",
                (channel, json.dumps(payload), at.isoformat()),
            )
        self.conn.commit()

    def get_draft(self, channel: str, now: datetime) -> dict[str, Any] | None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT payload, updated_at FROM drafts WHERE channel = %s",
                (channel,),
            )
            row = cur.fetchone()
        if row is None or not _draft_fresh(row[1], now):
            return None
        data = json.loads(row[0])
        return data if isinstance(data, dict) else None

    def clear_draft(self, channel: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM drafts WHERE channel = %s", (channel,))
        self.conn.commit()

    def append_workout_log(self, log_date: str, payload: dict[str, Any], at: datetime) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workout_logs(log_date, payload, created_at) VALUES (%s, %s, %s)",
                (log_date, json.dumps(payload), at.isoformat()),
            )
        self.conn.commit()

    def last_workout_log(self, log_date: str) -> dict[str, Any] | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT payload FROM workout_logs
                   WHERE log_date = %s ORDER BY id DESC LIMIT 1""",
                (log_date,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        return data if isinstance(data, dict) else None

    def replace_last_workout_log(
        self, log_date: str, payload: dict[str, Any], at: datetime
    ) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT id FROM workout_logs
                   WHERE log_date = %s ORDER BY id DESC LIMIT 1""",
                (log_date,),
            )
            row = cur.fetchone()
            if row is None:
                return False
            cur.execute(
                "UPDATE workout_logs SET payload = %s, created_at = %s WHERE id = %s",
                (json.dumps(payload), at.isoformat(), row[0]),
            )
        self.conn.commit()
        return True


def _draft_fresh(updated_at: datetime | str, now: datetime) -> bool:
    stamp = updated_at if isinstance(updated_at, datetime) else datetime.fromisoformat(updated_at)
    if stamp.tzinfo is None and now.tzinfo is not None:
        stamp = stamp.replace(tzinfo=now.tzinfo)
    current = now
    if current.tzinfo is None and stamp.tzinfo is not None:
        current = current.replace(tzinfo=stamp.tzinfo)
    return current - stamp <= DRAFT_TTL
