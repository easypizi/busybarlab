from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from toy_lair_assistant.collector.models import (
    Enriched,
    ConnectorAuthError,
    FetchContext,
    Processed,
    RawItem,
    url_hash,
)

log = logging.getLogger(__name__)
SNIPPET_LIMIT = 400


@dataclass
class RunReport:
    counts: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    grown_mocs: list[str] = field(default_factory=list)
    commit_ok: bool = True

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def to_payload(done: Processed) -> dict[str, Any]:
    item, enriched = done.item, done.enriched
    snippet = "" if item.private else (enriched.transcript or item.text or enriched.page_text)[:SNIPPET_LIMIT]
    return {
        "source": item.source,
        "external_id": item.extra.get("stable_id", item.external_id),
        "url": item.url,
        "title": item.title or item.url,
        "author": item.author,
        "summary": enriched.summary,
        "kind": enriched.kind,
        "topics": enriched.topics,
        "snippet": snippet,
        "vault_path": done.vault_path,
        "captured_at": item.captured_at,
    }


class Pipeline:
    def __init__(self, state: Any, enricher: Any, classifier: Any, vault: Any, ingest: Any, limit: int = 30) -> None:
        self.state = state
        self.enricher = enricher
        self.classifier = classifier
        self.vault = vault
        self.ingest = ingest
        self.limit = limit

    def is_seen(self, key: str, url: str = "") -> bool:
        return self.state.is_done(key, url_hash(url) if url else "")

    def run(self, connectors: Iterable[Any]) -> RunReport:
        report = RunReport()
        if not self.vault.begin():
            report.commit_ok = False
            report.errors["vault"] = "git pull failed: " + self.vault.last_error[:200]
            self.state.log_run("vault", False, report.errors["vault"])
            self._flush_pending(report)
            return report
        titles = self.vault.note_titles()
        stems = self.vault.stem_map()
        processed: list[Processed] = []
        staged: dict[str, str] = {}
        for connector in connectors:
            name = connector.name
            ctx = FetchContext(
                seen=lambda ext, name=name: self.state.is_done(f"{name}:{ext}"),
                limit=self.limit,
                cursors=self.state.cursors(),
            )
            count = 0
            try:
                for item in connector.fetch(ctx):
                    if self.is_seen(item.key, item.url) or any(
                        p.item.key == item.key
                        or (item.url and p.item.url and url_hash(p.item.url) == url_hash(item.url))
                        for p in processed
                    ):
                        continue
                    processed.append(self._process(item, titles, stems))
                    count += 1
                    if count >= self.limit:
                        break
            except ConnectorAuthError as exc:
                report.errors[name] = str(exc)
                self.state.log_run(name, False, str(exc))
            except Exception as exc:
                log.exception("connector failed name=%s", name)
                report.errors[name] = f"{type(exc).__name__}: {exc}"
                self.state.log_run(name, False, report.errors[name])
            else:
                self.state.log_run(name, True, f"{count} new")
            report.counts[name] = count
            staged.update(ctx.staged)
        self.vault.update_collections()
        report.grown_mocs = list(self.vault.grown_mocs)
        if processed and not self.vault.commit_run(f"{len(processed)} items"):
            report.commit_ok = False
            report.errors["vault"] = "git commit or push failed: " + self.vault.last_error[:200]
            self.state.log_run("vault", False, report.errors["vault"])
            return report
        for done in processed:
            self.state.mark_done(done.item.key, url_hash(done.item.url) if done.item.url else "")
            self.state.queue_push(done.item.key, to_payload(done))
        self.state.set_cursors(staged)
        self._flush_pending(report)
        return report

    def _process(self, item: RawItem, titles: list[str], stems: dict[str, str]) -> Processed:
        if item.extra.get("indexed_only"):
            enriched = Enriched(kind="note", summary=item.text[:300])
            return Processed(item=item, enriched=enriched, vault_path=str(item.extra.get("rel", "")))
        transcript, page = self.enricher.enrich(item)
        enriched = self.classifier.classify(item, transcript, page, titles)
        path = self.vault.add(item, enriched, stems)
        return Processed(item=item, enriched=enriched, vault_path=path)

    def _flush_pending(self, report: RunReport) -> None:
        pending = self.state.pending_pushes()
        if not pending:
            return
        try:
            self.ingest.push_items([payload for _key, payload in pending])
        except Exception as exc:
            log.warning("push failed, will retry: %s", exc)
            report.errors["push"] = f"{type(exc).__name__}"
            return
        self.state.clear_push([key for key, _payload in pending])
