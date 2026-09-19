"""Clone or pull the Zayka vault into ZAYKA_DIR. Read-only. Never copies secrets."""

from __future__ import annotations

import subprocess
from pathlib import Path

from toy_lair_assistant.settings import Settings


def sync(settings: Settings | None = None) -> Path | None:
    settings = settings or Settings()
    dest = settings.zayka_path()
    if dest is None:
        return None
    dest = dest.expanduser()
    if dest.exists() and (dest / ".git").exists():
        subprocess.run(["git", "pull", "--ff-only"], cwd=dest, check=True)
        return dest
    if not settings.zayka_repo_url:
        return dest if dest.exists() else None
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", settings.zayka_repo_url, str(dest)], check=True)
    return dest


def main() -> int:
    path = sync()
    print(path or "ZAYKA_DIR is not set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
