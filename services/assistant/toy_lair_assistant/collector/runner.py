from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from toy_lair_assistant.collector.config import CollectorConfig
from toy_lair_assistant.collector.connectors.bot_inbox import BotInbox
from toy_lair_assistant.collector.pipeline import Pipeline, RunReport

log = logging.getLogger(__name__)

BACKLOG_INTERVAL = timedelta(hours=2)
DAILY_INTERVAL = timedelta(hours=24)
DAILY_HOUR = 4
LAST_FULL = "last_full_run"
BACKLOG = "backlog"


def digest_text(report: RunReport) -> str:
    parts = [f"{name}: {count}" for name, count in report.counts.items() if count]
    text = "Library run: " + (", ".join(parts) if parts else "nothing new")
    if report.grown_mocs:
        text += ". Collections: " + ", ".join(m.rsplit("/", 1)[-1][:-3] for m in report.grown_mocs)
    return text


class Runner:
    def __init__(
        self,
        cfg: CollectorConfig,
        pipeline: Pipeline,
        connectors: dict[str, Any],
        bot: BotInbox,
        ingest: Any,
        state: Any,
        now: Callable[[], datetime],
    ) -> None:
        self.cfg = cfg
        self.pipeline = pipeline
        self.connectors = connectors
        self.bot = bot
        self.ingest = ingest
        self.state = state
        self.now = now

    def run(self, names: list[str] | None = None, full: bool = True) -> RunReport:
        wanted = names or [n for n in self.cfg.sources if n in self.connectors]
        selected = [self.connectors[n] for n in wanted if n in self.connectors]
        report = self.pipeline.run(selected)
        for source, message in report.errors.items():
            self._safe(lambda s=source, m=message: self.ingest.event("alert", s, f"{s}: {m}"))
        self._safe(
            lambda: self.ingest.event(
                "digest",
                "collector",
                digest_text(report),
                {"counts": report.counts, "errors": list(report.errors), "at": self.now().isoformat()},
            )
        )
        if full:
            backlog = any(c >= self.cfg.per_run_limit for c in report.counts.values())
            self.state.set_cursors({LAST_FULL: self.now().isoformat(), BACKLOG: "1" if backlog else "0"})
        return report

    def due(self) -> bool:
        cursors = self.state.cursors()
        last = cursors.get(LAST_FULL)
        if not last:
            return True
        elapsed = self.now() - datetime.fromisoformat(last)
        if cursors.get(BACKLOG) == "1" and elapsed >= BACKLOG_INTERVAL:
            return True
        return elapsed >= DAILY_INTERVAL and self.now().hour >= DAILY_HOUR

    def poll(self) -> int:
        """One tick: serve queued jobs, then run the schedule if it is due."""
        handled = 0
        try:
            jobs = self.ingest.jobs()
        except Exception as exc:
            log.warning("job poll failed: %s", exc)
            jobs = []
        urls = [j for j in jobs if j.get("kind") == "url"]
        syncs = [j for j in jobs if j.get("kind") == "sync"]
        if urls:
            self.bot.feed(urls)
            report = self.run(["bot"], full=False)
            ok = "bot" not in report.errors and report.commit_ok
            for job in urls:
                self._safe(lambda j=job: self.ingest.done(str(j["id"]), ok, "queued item processed"))
                handled += 1
        for job in syncs:
            source = str((job.get("payload") or {}).get("source") or "")
            report = self.run([source] if source in self.connectors else None)
            self._safe(lambda j=job, r=report: self.ingest.done(str(j["id"]), not r.errors, "sync finished"))
            handled += 1
        if not syncs and self.due():
            self.run()
        return handled

    @staticmethod
    def _safe(call: Callable[[], Any]) -> None:
        try:
            call()
        except Exception as exc:
            log.warning("collector side call failed: %s", exc)
