"""Clone or pull the Zayka vault into ZAYKA_DIR. Read-only. Never copies secrets."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from toy_lair_assistant.settings import Settings
from toy_lair_assistant.zayka import ZaykaIndex

log = logging.getLogger(__name__)

Runner = Callable[..., Any]


def sync(settings: Settings | None = None, runner: Runner | None = None) -> Path | None:
    settings = settings or Settings()
    run = runner or subprocess.run
    dest = settings.zayka_path()
    if dest is None:
        return None
    dest = dest.expanduser()
    if dest.exists() and (dest / ".git").exists():
        try:
            run(["git", "pull", "--ff-only"], cwd=dest, check=True)
        except Exception:
            log.exception("zayka pull failed, using existing clone")
        return dest
    if not settings.zayka_repo_url:
        return dest if dest.exists() else None
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--depth", "1", settings.zayka_repo_url, str(dest)], check=True)
    return dest


def attach_zayka(deps: Any, sync_fn: Callable[[Settings], Path | None] | None = None) -> None:
    settings = deps.settings
    if not settings.zayka_dir:
        return
    try:
        path = (sync_fn or sync)(settings)
    except Exception:
        log.exception("zayka sync failed")
        return
    if path is None or not Path(path).exists():
        return
    index = ZaykaIndex(Path(path))
    deps.zayka = index
    if getattr(deps, "agent", None) is not None:
        deps.agent.zayka = index


def main() -> int:
    path = sync()
    print(path or "ZAYKA_DIR is not set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
