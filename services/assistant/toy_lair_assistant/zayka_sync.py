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
    _attach_paco(deps, Path(path))


def _attach_paco(deps: Any, path: Path) -> None:
    if getattr(deps, "paco", None) is not None:
        return
    settings = deps.settings
    if not settings.openai_api_key or getattr(deps, "clock", None) is None:
        return
    from zoneinfo import ZoneInfo

    from toy_lair_assistant.llm import OpenAILLM
    from toy_lair_assistant.paco import PacoAgent
    from toy_lair_assistant.paco_vault import PacoVault
    from toy_lair_assistant.zayka_write import ZaykaWrite, git_runner

    zone = ZoneInfo(settings.timezone)
    root = path.expanduser()
    deps.paco = PacoAgent(
        llm=OpenAILLM(settings.openai_api_key, settings.openai_model),
        vault=PacoVault(root, zone),
        writer=ZaykaWrite(root, git_runner, zone),
        now=deps.clock.now,
        store=getattr(deps, "store", None),
        notify=getattr(deps, "notify", None),
    )


def main() -> int:
    path = sync()
    print(path or "ZAYKA_DIR is not set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
