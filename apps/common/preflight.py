"""Preflight reachability checks for BUSY Bar over USB / LAN."""

from __future__ import annotations

import errno
import os
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path

APPLE_PYTHON = "/usr/bin/python3"

_BUNDLE_TO_APP = {
    "com.googlecode.iterm2": "iTerm",
    "com.apple.Terminal": "Terminal",
    "com.mitchellh.ghostty": "Ghostty",
    "dev.warp.Warp-Stable": "Warp",
    "dev.warp.Warp": "Warp",
    "com.github.wez.wezterm": "WezTerm",
    "com.todesktop.230313mzl4w4u92": "Cursor",
}

_TERM_PROGRAM_TO_APP = {
    "iTerm.app": "iTerm",
    "Apple_Terminal": "Terminal",
    "ghostty": "Ghostty",
    "WarpTerminal": "Warp",
    "WezTerm": "WezTerm",
    "vscode": "Cursor",
}

_UNSET = object()


def parse_host(address: str) -> str:
    """Extract host from an address that may include scheme or port."""
    return address.split("://")[-1].split("/")[0].split(":")[0]


def detect_terminal_app(env: Mapping[str, str] | None = None) -> str:
    """Name the host app that owns Local Network permission for this Python."""
    env = os.environ if env is None else env
    bundle = env.get("__CFBundleIdentifier", "")
    if bundle in _BUNDLE_TO_APP:
        return _BUNDLE_TO_APP[bundle]
    term_program = env.get("TERM_PROGRAM", "")
    if term_program in _TERM_PROGRAM_TO_APP:
        return _TERM_PROGRAM_TO_APP[term_program]
    if env.get("CURSOR_AGENT") or "CURSOR" in "".join(env.keys()):
        return "Cursor"
    if term_program:
        return term_program
    if bundle:
        return bundle
    return "this terminal app"


def apple_signed_can_reach(host: str, timeout: float = 2.0) -> bool:
    """True when Apple-signed /usr/bin/python3 can open TCP to host:80.

    Apple-signed binaries are exempt from Local Network prompts, so a
    successful probe means the bar is reachable and the failure is the
    current app's Local Network permission.
    """
    python = Path(APPLE_PYTHON)
    if not python.is_file():
        return False
    snippet = (
        "import socket; socket.create_connection(("
        f"{host!r}, 80), {timeout!r})"
    )
    try:
        completed = subprocess.run(
            [str(python), "-c", snippet],
            check=False,
            timeout=timeout + 1.5,
            capture_output=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def http_get_ipv4(host: str, path: str, token: str | None, timeout: float) -> bytes:
    """Plain IPv4 HTTP GET. Avoids urllib quirks on flaky USB RNDIS links."""
    headers = [
        f"GET {path} HTTP/1.1",
        f"Host: {host}",
        "Accept: application/json",
        "Connection: close",
    ]
    if token:
        headers.append(f"X-API-Token: {token}")
    payload = ("\r\n".join(headers) + "\r\n\r\n").encode("ascii")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, 80))
        sock.sendall(payload)
        chunks: list[bytes] = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
    finally:
        sock.close()
    raw = b"".join(chunks)
    if b"\r\n\r\n" not in raw:
        raise RuntimeError("incomplete HTTP response")
    header, body = raw.split(b"\r\n\r\n", 1)
    status_line = header.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
    if " 401" in status_line or " 403" in status_line:
        raise PermissionError(status_line)
    if " 200" not in status_line:
        raise RuntimeError(status_line)
    return body


def is_host_unreachable(exc: BaseException) -> bool:
    """True when the OS reports EHOSTUNREACH / No route to host."""
    if isinstance(exc, OSError) and exc.errno in {errno.EHOSTUNREACH, errno.ENETUNREACH}:
        return True
    text = str(exc).lower()
    return "no route to host" in text or "host is unreachable" in text


def format_unreachable_help(
    address: str,
    last_exc: BaseException | None,
    *,
    env: Mapping[str, str] | None = None,
    apple_signed_reachable: bool | object = _UNSET,
    platform: str | None = None,
) -> str:
    """Human-readable checklist for USB / Local Network failures."""
    host = parse_host(address)
    app = detect_terminal_app(env)
    lines = [
        f"Cannot reach BUSY Bar at {address} ({last_exc}).",
        "USB checklist:",
        "  1. Cable plugged into the bar and Mac",
        "  2. Bar powered on, wait ~5s after plug",
        "  3. curl http://10.0.4.20/api/status/firmware",
        "  4. curl is Apple-signed and exempt from Local Network. A working curl does not mean Python can connect.",
        "  5. Wi-Fi: --address <bar-ip> --token <password>",
        "  6. Simulator: --sim",
    ]
    os_name = sys.platform if platform is None else platform
    unreachable = last_exc is None or is_host_unreachable(last_exc)
    if os_name == "darwin" and unreachable:
        if apple_signed_reachable is _UNSET:
            apple_signed_reachable = apple_signed_can_reach(host)
        lines.extend(
            [
                "",
                f"macOS Local Network (permission is owned by {app}):",
                "  System Settings → Privacy & Security → Local Network",
                f"  Enable {app}, then quit and reopen it.",
                "  If it is missing from the list, run from that terminal:",
                f"    {APPLE_PYTHON} -c \"import socket; socket.create_connection(('{host}', 80), 3)\"",
                "  Click Allow when macOS prompts, then retry.",
                "  curl is Apple-signed and exempt from this check.",
            ]
        )
        if apple_signed_reachable is True:
            lines.append(f"  Local Network is blocked for {app}.")
    return "\n".join(lines)


def check_device(
    address: str,
    token: str | None = None,
    *,
    timeout: float = 2.0,
    attempts: int = 8,
    delay: float = 0.4,
) -> None:
    """
    Retry reachability. USB gadget routes often flap for a few seconds.

    Raises SystemExit with a readable checklist on failure.
    """
    host = parse_host(address)
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            http_get_ipv4(host, "/api/status/firmware", token, timeout)
            if i > 0:
                print(f"Reached {host} on attempt {i + 1}.")
            return
        except PermissionError as exc:
            raise SystemExit(
                f"BUSY Bar at {address} requires auth. Pass --token <wifi password>."
            ) from exc
        except Exception as exc:
            last_exc = exc
            time.sleep(delay)
    raise SystemExit(format_unreachable_help(address, last_exc))
