from __future__ import annotations

import os
import subprocess

SERVICE = "toy_lair_collector"


def get_secret(name: str) -> str:
    env = os.environ.get(f"COLLECTOR_{name.upper()}")
    if env:
        return env
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def set_secret(name: str, value: str) -> None:
    subprocess.run(
        ["security", "add-generic-password", "-U", "-s", SERVICE, "-a", name, "-w", value],
        check=True,
        capture_output=True,
        text=True,
    )
