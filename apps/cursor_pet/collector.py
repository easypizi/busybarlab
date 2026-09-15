"""Read Cursor auth from local SQLite and poll dashboard usage APIs."""

from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

AccountRole = Literal["work", "personal"]

DEFAULT_DB = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Cursor"
    / "User"
    / "globalStorage"
    / "state.vscdb"
)
DASHBOARD_BASE = "https://api2.cursor.sh/aiserver.v1.DashboardService"


@dataclass
class ModelSpend:
    model: str
    total_cents: float
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class UsageSnapshot:
    account: AccountRole
    total_spend_cents: float
    included_spend_cents: float
    limit_cents: float
    remaining_cents: float
    percent_used: float
    models: list[ModelSpend] = field(default_factory=list)
    fetched_at: float = field(default_factory=time.time)
    billing_cycle_start: str | None = None
    billing_cycle_end: str | None = None
    raw_plan: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "total_spend_cents": self.total_spend_cents,
            "included_spend_cents": self.included_spend_cents,
            "limit_cents": self.limit_cents,
            "remaining_cents": self.remaining_cents,
            "percent_used": self.percent_used,
            "models": [
                {
                    "model": m.model,
                    "total_cents": m.total_cents,
                    "input_tokens": m.input_tokens,
                    "output_tokens": m.output_tokens,
                }
                for m in self.models
            ],
            "fetched_at": self.fetched_at,
            "billing_cycle_start": self.billing_cycle_start,
            "billing_cycle_end": self.billing_cycle_end,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UsageSnapshot:
        models = [
            ModelSpend(
                model=str(m.get("model", "unknown")),
                total_cents=float(m.get("total_cents", 0)),
                input_tokens=int(m.get("input_tokens", 0)),
                output_tokens=int(m.get("output_tokens", 0)),
            )
            for m in data.get("models", [])
        ]
        return cls(
            account=data.get("account", "personal"),  # type: ignore[arg-type]
            total_spend_cents=float(data.get("total_spend_cents", 0)),
            included_spend_cents=float(data.get("included_spend_cents", 0)),
            limit_cents=float(data.get("limit_cents", 0)),
            remaining_cents=float(data.get("remaining_cents", 0)),
            percent_used=float(data.get("percent_used", 0)),
            models=models,
            fetched_at=float(data.get("fetched_at", time.time())),
            billing_cycle_start=data.get("billing_cycle_start"),
            billing_cycle_end=data.get("billing_cycle_end"),
        )


def read_access_token(db_path: Path | None = None) -> str:
    path = db_path or DEFAULT_DB
    if not path.exists():
        raise FileNotFoundError(f"Cursor state DB not found: {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT value FROM ItemTable WHERE key=?",
            ("cursorAuth/accessToken",),
        ).fetchone()
    finally:
        con.close()
    if not row or not row[0]:
        raise RuntimeError("cursorAuth/accessToken missing from Cursor state DB")
    return str(row[0])


def _post_json(token: str, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        f"{DASHBOARD_BASE}/{method}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"{method} failed HTTP {exc.code}: {detail}") from exc


def fetch_period_usage(token: str) -> dict[str, Any]:
    return _post_json(token, "GetCurrentPeriodUsage")


def fetch_aggregated_models(token: str) -> list[ModelSpend]:
    data = _post_json(token, "GetAggregatedUsageEvents")
    models: list[ModelSpend] = []
    for row in data.get("aggregations") or []:
        if not isinstance(row, dict):
            continue
        models.append(
            ModelSpend(
                model=str(row.get("modelIntent") or row.get("model") or "unknown"),
                total_cents=float(row.get("totalCents") or row.get("total_cents") or 0),
                input_tokens=int(row.get("inputTokens") or 0),
                output_tokens=int(row.get("outputTokens") or 0),
            )
        )
    models.sort(key=lambda m: m.total_cents, reverse=True)
    return models


def snapshot_from_api(account: AccountRole, token: str) -> UsageSnapshot:
    data = fetch_period_usage(token)
    plan = data.get("planUsage") or {}
    total = float(plan.get("totalSpend") or 0)
    included = float(plan.get("includedSpend") or 0)
    limit = float(plan.get("limit") or 0)
    remaining = float(plan.get("remaining") or max(0.0, limit - total))
    percent = float(plan.get("totalPercentUsed") or (100.0 * total / limit if limit else 0.0))
    models = fetch_aggregated_models(token)
    return UsageSnapshot(
        account=account,
        total_spend_cents=total,
        included_spend_cents=included,
        limit_cents=limit,
        remaining_cents=remaining,
        percent_used=percent,
        models=models,
        billing_cycle_start=data.get("billingCycleStart"),
        billing_cycle_end=data.get("billingCycleEnd"),
        raw_plan=plan if isinstance(plan, dict) else {},
    )


@dataclass
class SpendDelta:
    account: AccountRole
    delta_cents: float
    cycle_rolled: bool
    snapshot: UsageSnapshot


def compute_delta(previous: UsageSnapshot | None, current: UsageSnapshot) -> SpendDelta:
    """Positive spend delta with billing-cycle rollover detection."""
    if previous is None:
        return SpendDelta(account=current.account, delta_cents=0.0, cycle_rolled=False, snapshot=current)
    if current.total_spend_cents + 1.0 < previous.total_spend_cents:
        # New billing cycle: do not feed negative food.
        return SpendDelta(
            account=current.account,
            delta_cents=max(0.0, current.total_spend_cents),
            cycle_rolled=True,
            snapshot=current,
        )
    return SpendDelta(
        account=current.account,
        delta_cents=max(0.0, current.total_spend_cents - previous.total_spend_cents),
        cycle_rolled=False,
        snapshot=current,
    )


class UsageCollector:
    """Local collector that reads this machine's Cursor session."""

    def __init__(
        self,
        account: AccountRole,
        *,
        db_path: Path | None = None,
        token: str | None = None,
    ) -> None:
        self.account = account
        self.db_path = db_path
        self._token = token
        self._last: UsageSnapshot | None = None

    def _token_value(self) -> str:
        if self._token:
            return self._token
        return read_access_token(self.db_path)

    def poll(self) -> SpendDelta:
        snap = snapshot_from_api(self.account, self._token_value())
        delta = compute_delta(self._last, snap)
        self._last = snap
        return delta

    def set_baseline(self, snap: UsageSnapshot) -> None:
        self._last = snap
