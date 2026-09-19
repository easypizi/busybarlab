"""One-shot install: bake frogs .anim, upload to BUSY Bar, start looping onboard.

After this exits, the bar keeps playing the animation without a host process.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from busylib import BusyBar, types

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from busybar.common.preflight import check_device
from busybar.wednesday_frogs.animation import is_wednesday
from busybar.wednesday_frogs.bake import BakeConfig, bake_anim
from busybar.wednesday_frogs.payload import APP_NAME, HAPPY_ANIM, SAD_ANIM, build_draw_payload

DEFAULT_OUT = ROOT / "data" / "anims"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Install looping Wednesday Frogs animation onto BUSY Bar"
    )
    p.add_argument("--address", default="10.0.4.20")
    p.add_argument("--token", default=None, help="Wi-Fi API password / token")
    p.add_argument("--skip-check", action="store_true")
    p.add_argument(
        "--bake-only",
        action="store_true",
        help="Only write .anim files under data/anims, do not talk to the bar",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Directory for baked .anim files",
    )
    p.add_argument(
        "--mode",
        choices=["auto", "happy", "sad"],
        default="auto",
        help="auto = Wednesday happy / other days sad",
    )
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--frames", type=int, default=48)
    p.add_argument("--no-marquee", action="store_true")
    p.add_argument("--no-fly", action="store_true")
    p.add_argument(
        "--clear",
        action="store_true",
        help="Only clear wednesday-frogs from the bar and exit",
    )
    return p.parse_args(argv)


def resolve_sad(mode: str) -> bool:
    if mode == "happy":
        return False
    if mode == "sad":
        return True
    return not is_wednesday()


def bake_to_disk(args: argparse.Namespace) -> tuple[Path, bool]:
    sad = resolve_sad(args.mode)
    cfg = BakeConfig(
        fps=args.fps,
        frame_count=args.frames,
        include_fly=not args.no_fly,
    )
    name = "frogs_sad.anim" if sad else "frogs_happy.anim"
    blob = bake_anim(sad=sad, config=cfg)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / name
    path.write_bytes(blob)
    # Always bake the other variant too for later swaps.
    other = bake_anim(sad=not sad, config=cfg)
    other_name = "frogs_happy.anim" if sad else "frogs_sad.anim"
    (args.out / other_name).write_bytes(other)
    print(f"Baked {path} ({len(blob)} bytes, sad={sad})")
    print(f"Baked {args.out / other_name} ({len(other)} bytes)")
    return path, sad


def upload_both_anims(bb: object, anim_dir: Path) -> None:
    """Upload happy and sad .anim so Flipper can switch without the Mac."""
    for name in (HAPPY_ANIM, SAD_ANIM):
        path = anim_dir / name
        bb.assets_upload(
            application_name=APP_NAME,
            filename=name,
            data=path.read_bytes(),
        )


def draw_frogs(bb: object, *, sad: bool, marquee: bool) -> None:
    payload = build_draw_payload(sad=sad, marquee=marquee)
    bb.display_draw(types.DisplayElements.model_validate(payload))


def install_on_bar(args: argparse.Namespace, anim_path: Path, *, sad: bool) -> None:
    if not args.skip_check:
        check_device(args.address, args.token)
    kwargs = {}
    if args.token:
        kwargs["token"] = args.token
    with BusyBar(args.address, **kwargs) as bb:
        # Clear previous draw so a playing .anim file handle is released.
        try:
            bb.display_clear(application_name=APP_NAME)
        except Exception:
            pass
        try:
            bb.assets_delete(application_name=APP_NAME)
        except Exception:
            pass

        upload_both_anims(bb, anim_path.parent)
        draw_frogs(bb, sad=sad, marquee=not args.no_marquee)
        filename = SAD_ANIM if sad else HAPPY_ANIM
    print(
        f"Installed on {args.address}: {filename} looping"
        f" ({'sad' if sad else 'happy'}, "
        f"{'Wed' if datetime.now().weekday() == 2 else 'not Wed'})."
    )
    print("You can unplug the Mac script. The bar keeps playing until cleared.")


def clear_bar(args: argparse.Namespace) -> None:
    if not args.skip_check:
        check_device(args.address, args.token)
    kwargs = {}
    if args.token:
        kwargs["token"] = args.token
    with BusyBar(args.address, **kwargs) as bb:
        bb.display_clear(application_name=APP_NAME)
        try:
            bb.assets_delete(application_name=APP_NAME)
        except Exception:
            pass
    print(f"Cleared {APP_NAME} from {args.address}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.clear:
        clear_bar(args)
        return 0
    anim_path, sad = bake_to_disk(args)
    if args.bake_only:
        return 0
    install_on_bar(args, anim_path, sad=sad)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
