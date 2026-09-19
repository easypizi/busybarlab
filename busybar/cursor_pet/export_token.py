"""Export this machine's Cursor accessToken into data/cursor_tokens.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from busybar.cursor_pet.collector import snapshot_from_api
from busybar.cursor_pet.tokens import (
    DEFAULT_TOKENS_PATH,
    export_local_account,
    load_token_store,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Export Cursor session token from this machine into data/cursor_tokens.json. "
            "Run once on the personal machine with --account personal, once on the work "
            "machine with --account work, then copy the file to the pet-daemon host "
            "(or merge both sides into one file)."
        )
    )
    p.add_argument("--account", choices=["work", "personal"], required=True)
    p.add_argument("--out", type=Path, default=DEFAULT_TOKENS_PATH)
    p.add_argument(
        "--verify",
        action="store_true",
        help="Call GetCurrentPeriodUsage after export to confirm the token works",
    )
    p.add_argument(
        "--show",
        action="store_true",
        help="Print store summary (emails only, never full tokens)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.show and not args.account:
        pass
    stored = export_local_account(args.account, path=args.out)
    print(
        f"Saved {stored.account} token"
        f" email={stored.email or '?'}"
        f" host={stored.source_host}"
        f" -> {args.out}"
    )
    if args.verify:
        snap = snapshot_from_api(args.account, stored.access_token)
        print(
            f"Verified: ${snap.total_spend_cents/100:.2f} / "
            f"${snap.limit_cents/100:.2f} ({snap.percent_used:.1f}%)"
            f" models={len(snap.models)}"
        )
    store = load_token_store(args.out)
    print(
        "Store now has:"
        f" work={'yes' if store.work else 'no'}"
        f" personal={'yes' if store.personal else 'no'}"
    )
    if store.work and store.work.email:
        print(f"  work email: {store.work.email}")
    if store.personal and store.personal.email:
        print(f"  personal email: {store.personal.email}")
    print(
        "Security: keep data/cursor_tokens.json private (gitignored, chmod 600). "
        "Tokens expire when Cursor refreshes the session; re-export if polls start failing."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
