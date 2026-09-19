"""Reporter process for the second machine's Cursor account."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from busybar.cursor_pet.collector import UsageCollector


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Report Cursor usage to pet daemon")
    p.add_argument(
        "--account",
        choices=["work", "personal"],
        required=True,
        help="Account role of this machine",
    )
    p.add_argument(
        "--daemon",
        required=True,
        help="Pet daemon base URL, e.g. http://192.168.1.10:8765",
    )
    p.add_argument("--interval", type=float, default=300.0)
    p.add_argument("--once", action="store_true")
    return p.parse_args(argv)


def post_report(daemon: str, account: str, snapshot: dict) -> None:
    url = daemon.rstrip("/") + "/report"
    payload = json.dumps({"account": account, "snapshot": snapshot}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"report failed: HTTP {resp.status}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    collector = UsageCollector(args.account)  # type: ignore[arg-type]
    while True:
        try:
            delta = collector.poll()
            post_report(args.daemon, args.account, delta.snapshot.to_dict())
            print(
                f"Reported {args.account}: total=${delta.snapshot.total_spend_cents/100:.2f} "
                f"delta={delta.delta_cents:.1f}c rolled={delta.cycle_rolled}"
            )
        except Exception as exc:
            print(f"Reporter error: {exc}", file=sys.stderr)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
