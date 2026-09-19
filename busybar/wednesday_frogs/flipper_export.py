"""Write Flipper Zero config JSON for the Wednesday Frogs remote."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from busybar.wednesday_frogs.payload import APP_NAME, build_draw_payload

DEFAULT_OUT = ROOT / "flipper" / "out" / "busybar_frogs.conf.json"


def write_flipper_config(
    path: Path,
    *,
    bar_ip: str,
    token: str,
    marquee: bool = True,
) -> Path:
    """Write happy/sad draw payloads plus Wi-Fi API credentials."""
    config = {
        "base_url": f"http://{bar_ip.rstrip('/')}/api",
        "token": token,
        "app": APP_NAME,
        "happy": build_draw_payload(sad=False, marquee=marquee),
        "sad": build_draw_payload(sad=True, marquee=marquee),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export Flipper config for Wednesday Frogs")
    p.add_argument("--bar-ip", required=True, help="BUSY Bar LAN IP, e.g. 192.168.1.50")
    p.add_argument("--token", required=True, help="Wi-Fi HTTP API password")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--no-marquee", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = write_flipper_config(
        args.out,
        bar_ip=args.bar_ip,
        token=args.token,
        marquee=not args.no_marquee,
    )
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
