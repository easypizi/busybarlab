"""Wednesday Frogs CLI: hopping frogs + marquee on BUSY Bar front display."""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.common.backend import BusyBarBackend, DisplayBackend
from apps.common.input_events import InputButton, InputEvent, InputEventPump
from apps.common.preflight import check_device
from apps.common.simulator import TerminalBackend
from apps.wednesday_frogs.animation import (
    advance,
    create_scene,
    render_elements,
    request_marquee,
)
from apps.wednesday_frogs.sprites import build_sprite_bank

APP_NAME = "wednesday-frogs"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wednesday Frogs for BUSY Bar")
    parser.add_argument(
        "--address",
        default="10.0.4.20",
        help="BUSY Bar address (default USB 10.0.4.20)",
    )
    parser.add_argument("--token", default=None, help="Wi-Fi API password / token")
    parser.add_argument("--fps", type=float, default=10.0, help="Animation FPS")
    parser.add_argument(
        "--text-interval",
        type=float,
        default=20.0,
        help="Seconds between marquee runs",
    )
    parser.add_argument("--frogs", type=int, default=3, help="Number of frogs")
    parser.add_argument(
        "--sim",
        action="store_true",
        help="Run in terminal simulator without a device",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=0.0,
        help="Auto-exit after N seconds (0 = run until Ctrl+C)",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Skip preflight reachability check and go straight to busylib",
    )
    return parser.parse_args(argv)


def make_backend(args: argparse.Namespace) -> DisplayBackend:
    if args.sim:
        return TerminalBackend(clear_screen=True)
    if not args.skip_check:
        check_device(args.address, args.token)
    return BusyBarBackend(address=args.address, token=args.token)


def upload_sprites(backend: DisplayBackend, *, sad: bool) -> None:
    bank = build_sprite_bank(sad=sad)
    for name, data in bank.items():
        backend.upload_asset(APP_NAME, name, data)


def safe_cleanup(backend: DisplayBackend) -> None:
    try:
        backend.clear(APP_NAME)
    except Exception as exc:
        print(f"Cleanup clear skipped: {exc}", file=sys.stderr)
    try:
        backend.close()
    except Exception as exc:
        print(f"Cleanup close skipped: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    backend = make_backend(args)
    scene = create_scene(frog_count=args.frogs, text_interval=args.text_interval)
    uploaded_sad: bool | None = None
    stop = False

    def _handle_sig(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    def on_input(event: InputEvent) -> None:
        if event.button in {InputButton.OK, InputButton.START, InputButton.CUSTOM}:
            request_marquee(scene)

    pump = InputEventPump(
        None if args.sim else args.address,
        on_input,
        token=args.token,
    )
    pump.start()

    frame_dt = 1.0 / max(args.fps, 1.0)
    started = time.monotonic()
    last = started
    print(f"Connected to {args.address}. Ctrl+C to stop.")

    try:
        while not stop:
            now = time.monotonic()
            dt = now - last
            last = now
            if uploaded_sad is None or uploaded_sad != (not scene.is_wednesday):
                upload_sprites(backend, sad=not scene.is_wednesday)
                uploaded_sad = not scene.is_wednesday
            advance(scene, dt, now=now, text_interval=args.text_interval)
            backend.draw(APP_NAME, render_elements(scene, now=now))
            if args.seconds > 0 and (now - started) >= args.seconds:
                break
            sleep_for = frame_dt - (time.monotonic() - now)
            if sleep_for > 0:
                time.sleep(sleep_for)
    except Exception as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        from apps.common.preflight import format_unreachable_help, is_host_unreachable

        if is_host_unreachable(exc):
            print(format_unreachable_help(args.address, exc), file=sys.stderr)
        return 1
    finally:
        pump.stop()
        safe_cleanup(backend)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
