"""Cursor Token Pet daemon: local collector + reporter listener + OLED draw loop."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.common.backend import BusyBarBackend, DisplayBackend
from apps.common.input_events import InputButton, InputEvent, InputEventPump
from apps.common.preflight import check_device, format_unreachable_help, is_host_unreachable
from apps.common.simulator import TerminalBackend
from apps.cursor_pet.achievements import evaluate_achievements
from apps.cursor_pet.collector import AccountRole, UsageCollector, UsageSnapshot
from apps.cursor_pet.notify import notify_events
from apps.cursor_pet.pet import APP_NAME, PetScene
from apps.cursor_pet.state import load_or_create, reroll, save_state
from apps.cursor_pet.tokens import DEFAULT_TOKENS_PATH, resolve_collectors

DEFAULT_STATE = ROOT / "data" / "pet_state.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cursor Token Pet for BUSY Bar")
    p.add_argument("--address", default="10.0.4.20")
    p.add_argument("--token", default=None, help="BUSY Bar Wi-Fi token")
    p.add_argument("--sim", action="store_true")
    p.add_argument("--fps", type=float, default=5.0)
    p.add_argument("--poll-seconds", type=float, default=300.0)
    p.add_argument("--listen", default="0.0.0.0:8765", help="Reporter HTTP bind host:port")
    p.add_argument(
        "--local-account",
        choices=["work", "personal"],
        default="personal",
        help="Fallback account if data/cursor_tokens.json is missing",
    )
    p.add_argument(
        "--tokens",
        type=Path,
        default=DEFAULT_TOKENS_PATH,
        help="Dual-account token store (export via python -m apps.cursor_pet.export_token)",
    )
    p.add_argument("--state", type=Path, default=DEFAULT_STATE)
    p.add_argument("--reroll", action="store_true")
    p.add_argument("--yes", action="store_true", help="Confirm --reroll without prompt")
    p.add_argument("--seconds", type=float, default=0.0)
    p.add_argument("--demo-feed", type=float, default=0.0, help="Simulated cents to feed once")
    p.add_argument("--demo-account", choices=["work", "personal"], default="work")
    p.add_argument("--no-collector", action="store_true")
    p.add_argument("--announce-front", action="store_true", default=True)
    p.add_argument(
        "--skip-check",
        action="store_true",
        help="Skip preflight reachability check and go straight to busylib",
    )
    return p.parse_args(argv)


class PetRuntime:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        if args.reroll:
            if not args.yes:
                answer = input("Destroy current pet and reroll? [y/N] ").strip().lower()
                if answer not in {"y", "yes"}:
                    raise SystemExit("Aborted")
            self.state = reroll(args.state)
            print(f"Genesis: {self.state.name} seed={self.state.seed}")
        else:
            self.state, created = load_or_create(args.state)
            if created:
                print(
                    f"Genesis: {self.state.name} ({self.state.temperament}) "
                    f"fav={self.state.favorite_model} bias={self.state.alignment_bias:.2f}"
                )
        self.scene = PetScene()
        self._lock = threading.Lock()
        self.remote_snapshots: dict[str, UsageSnapshot] = {}
        self.stop = False

    def apply_delta(
        self,
        account: str,
        cents: float,
        *,
        cycle_rolled: bool = False,
        model: str | None = None,
        percent_used: float = 0.0,
        today_cents: float | None = None,
        online: bool = True,
    ) -> None:
        with self._lock:
            events = self.state.feed(
                account,  # type: ignore[arg-type]
                cents,
                cycle_rolled=cycle_rolled,
                model=model,
            )
            if account == "work":
                self.state.work = {
                    "percent_used": percent_used,
                    "last_seen_at": time.time(),
                    "online": online,
                    "today_cents": today_cents
                    if today_cents is not None
                    else self.state.work.get("today_cents", 0.0),
                }
            else:
                self.state.personal = {
                    "percent_used": percent_used,
                    "last_seen_at": time.time(),
                    "online": online,
                    "today_cents": today_cents
                    if today_cents is not None
                    else self.state.personal.get("today_cents", 0.0),
                }
            if cents > 0:
                self.scene.note_food(account)
            unlocked = evaluate_achievements(self.state)
            save_state(self.state, self.args.state)
            all_events = events + [f"ACHIEVEMENT {u}" for u in unlocked]
            if all_events:
                print(" | ".join(all_events))
                notify_events(
                    all_events,
                    pet_name=self.state.name,
                    level=self.state.level,
                    branch=self.state.branch,
                )
                if self.args.announce_front:
                    self.scene.flash_announce(
                        f"{self.state.name} {all_events[-1]}"[:48]
                    )


def make_handler(runtime: PetRuntime) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/report":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                return
            account = data.get("account")
            if account not in {"work", "personal"}:
                self.send_response(400)
                self.end_headers()
                return
            snap = UsageSnapshot.from_dict(data.get("snapshot") or data)
            prev = runtime.remote_snapshots.get(account)
            from apps.cursor_pet.collector import compute_delta

            delta = compute_delta(prev, snap)
            runtime.remote_snapshots[account] = snap
            top_model = snap.models[0].model if snap.models else None
            runtime.apply_delta(
                account,
                delta.delta_cents,
                cycle_rolled=delta.cycle_rolled,
                model=top_model,
                percent_used=snap.percent_used,
                today_cents=snap.total_spend_cents,
                online=True,
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def do_GET(self) -> None:
            if self.path.rstrip("/") == "/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return
            self.send_response(404)
            self.end_headers()

    return Handler


def start_server(runtime: PetRuntime, listen: str) -> ThreadingHTTPServer:
    host, port_s = listen.rsplit(":", 1)
    server = ThreadingHTTPServer((host, int(port_s)), make_handler(runtime))
    thread = threading.Thread(target=server.serve_forever, name="pet-http", daemon=True)
    thread.start()
    return server


def _poll_one(runtime: PetRuntime, collector: UsageCollector, *, baseline: bool) -> None:
    account: AccountRole = collector.account
    try:
        delta = collector.poll()
        top = delta.snapshot.models[0].model if delta.snapshot.models else None
        cents = 0.0 if baseline else delta.delta_cents
        runtime.apply_delta(
            account,
            cents,
            cycle_rolled=False if baseline else delta.cycle_rolled,
            model=top,
            percent_used=delta.snapshot.percent_used,
            today_cents=delta.snapshot.total_spend_cents,
            online=True,
        )
        if baseline:
            print(
                f"Collector baseline {account}: "
                f"${delta.snapshot.total_spend_cents/100:.2f} / "
                f"${delta.snapshot.limit_cents/100:.2f}"
            )
        elif delta.delta_cents:
            print(f"Ate {delta.delta_cents:.1f}c from {account}")
    except Exception as exc:
        print(f"Collector {'baseline' if baseline else 'poll'} failed ({account}): {exc}")


def collector_loop(runtime: PetRuntime) -> None:
    token_map = resolve_collectors(
        tokens_path=runtime.args.tokens,
        local_account=runtime.args.local_account,  # type: ignore[arg-type]
    )
    if not token_map:
        print(
            "No Cursor tokens available. Export with:\n"
            "  python -m apps.cursor_pet.export_token --account personal --verify\n"
            "  python -m apps.cursor_pet.export_token --account work --verify"
        )
        return
    collectors = [
        UsageCollector(account, token=token) for account, token in token_map.items()
    ]
    print(f"Collecting accounts: {', '.join(token_map.keys())}")
    for collector in collectors:
        _poll_one(runtime, collector, baseline=True)
    while not runtime.stop:
        time.sleep(runtime.args.poll_seconds)
        if runtime.stop:
            break
        for collector in collectors:
            _poll_one(runtime, collector, baseline=False)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime = PetRuntime(args)
    if args.sim:
        backend: DisplayBackend = TerminalBackend(clear_screen=True)
    else:
        if not args.skip_check:
            check_device(args.address, args.token)
        backend = BusyBarBackend(address=args.address, token=args.token)
        print(f"Connected to {args.address}.")
    server = start_server(runtime, args.listen)
    print(f"Listening for reporter on http://{args.listen}/report")

    if args.demo_feed > 0:
        runtime.apply_delta(args.demo_account, args.demo_feed, model=runtime.state.favorite_model)

    collector_thread = None
    if not args.no_collector:
        collector_thread = threading.Thread(
            target=collector_loop, args=(runtime,), name="pet-collector", daemon=True
        )
        collector_thread.start()

    def on_input(event: InputEvent) -> None:
        if event.button in {InputButton.WHEEL_CW, InputButton.DOWN}:
            runtime.scene.hud.next_page()
        elif event.button in {InputButton.WHEEL_CCW, InputButton.UP}:
            runtime.scene.hud.prev_page()
        elif event.button in {InputButton.OK, InputButton.START}:
            with runtime._lock:
                runtime.state.pet_flash_until = time.time() + 3.0
                runtime.state.contentment = min(1.0, runtime.state.contentment + 0.05)
                save_state(runtime.state, args.state)

    pump = InputEventPump(None if args.sim else args.address, on_input, token=args.token)
    pump.start()

    def _stop(_s: int, _f: object) -> None:
        runtime.stop = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    frame_dt = 1.0 / max(args.fps, 1.0)
    started = time.monotonic()
    try:
        while not runtime.stop:
            now = time.monotonic()
            with runtime._lock:
                st = runtime.state
                runtime.scene.set_account_status(
                    work_percent=float(st.work.get("percent_used", 0.0)),
                    personal_percent=float(st.personal.get("percent_used", 0.0)),
                    work_online=bool(st.work.get("online", False))
                    and (time.time() - float(st.work.get("last_seen_at", 0))) < 900,
                    personal_online=bool(st.personal.get("online", False))
                    and (time.time() - float(st.personal.get("last_seen_at", 0))) < 900,
                    work_today=float(st.work.get("today_cents", 0.0)),
                    personal_today=float(st.personal.get("today_cents", 0.0)),
                )
                elements = runtime.scene.render(backend, st)
            backend.draw(APP_NAME, elements)
            if args.seconds > 0 and (time.monotonic() - started) >= args.seconds:
                break
            sleep_for = frame_dt - (time.monotonic() - now)
            if sleep_for > 0:
                time.sleep(sleep_for)
    except Exception as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        if is_host_unreachable(exc):
            print(format_unreachable_help(args.address, exc), file=sys.stderr)
        return 1
    finally:
        runtime.stop = True
        pump.stop()
        server.shutdown()
        try:
            backend.clear(APP_NAME)
        except Exception as exc:
            print(f"Cleanup clear skipped: {exc}", file=sys.stderr)
        try:
            backend.close()
        except Exception as exc:
            print(f"Cleanup close skipped: {exc}", file=sys.stderr)
        save_state(runtime.state, args.state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
