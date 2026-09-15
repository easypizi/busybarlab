"""Tests for shared pixelart, input parsing, and preflight helpers."""

import errno

from apps.common.input_events import InputButton, parse_input_updates
from apps.common.pixelart import ascii_to_png_bytes
from apps.common import preflight
from apps.common.preflight import (
    detect_terminal_app,
    format_unreachable_help,
    is_host_unreachable,
    parse_host,
)


def test_ascii_png_roundtrip_size() -> None:
    data = ascii_to_png_bytes(["G.G", ".B.", "G.G"])
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(data) > 20


def test_parse_button_event() -> None:
    state = {
        "updates": [
            {"input": {"button_event": {"button": "ok", "action": "press"}}},
            {"input": {"wheel_event": {"delta": 1}}},
        ]
    }
    events = parse_input_updates(state)
    assert events[0].button == InputButton.OK
    assert events[1].button == InputButton.WHEEL_CW


def test_parse_host() -> None:
    assert parse_host("10.0.4.20") == "10.0.4.20"
    assert parse_host("http://10.0.4.20/api") == "10.0.4.20"


def test_is_host_unreachable() -> None:
    assert is_host_unreachable(OSError(errno.EHOSTUNREACH, "No route to host"))
    assert is_host_unreachable(RuntimeError("No route to host | POST /api/assets/upload"))
    assert not is_host_unreachable(RuntimeError("timeout"))


def test_detect_terminal_app_from_term_program_and_bundle() -> None:
    assert detect_terminal_app({"TERM_PROGRAM": "iTerm.app"}) == "iTerm"
    assert detect_terminal_app({"__CFBundleIdentifier": "com.googlecode.iterm2"}) == "iTerm"
    assert detect_terminal_app({"TERM_PROGRAM": "Apple_Terminal"}) == "Terminal"
    assert detect_terminal_app({"__CFBundleIdentifier": "com.apple.Terminal"}) == "Terminal"
    assert detect_terminal_app({"TERM_PROGRAM": "ghostty"}) == "Ghostty"
    assert detect_terminal_app({"TERM_PROGRAM": "WarpTerminal"}) == "Warp"
    assert detect_terminal_app({"__CFBundleIdentifier": "com.todesktop.230313mzl4w4u92"}) == "Cursor"
    assert detect_terminal_app({"CURSOR_AGENT": "1"}) == "Cursor"
    assert detect_terminal_app({}) == "this terminal app"


def test_format_unreachable_help_mentions_local_network() -> None:
    msg = format_unreachable_help(
        "10.0.4.20",
        OSError(errno.EHOSTUNREACH, "No route to host"),
        env={"TERM_PROGRAM": "iTerm.app"},
        apple_signed_reachable=True,
        platform="darwin",
    )
    assert "Local Network" in msg
    assert "Privacy & Security" in msg
    assert "10.0.4.20" in msg
    assert "iTerm" in msg
    assert "Local Network is blocked for iTerm" in msg
    assert "If curl works but Python fails: retry" not in msg
    assert "exempt" in msg.lower()


def test_format_unreachable_help_probes_apple_python(monkeypatch) -> None:
    called: dict[str, str] = {}

    def fake_probe(host: str, timeout: float = 2.0) -> bool:
        called["host"] = host
        return True

    monkeypatch.setattr(preflight, "apple_signed_can_reach", fake_probe)
    msg = format_unreachable_help(
        "10.0.4.20",
        OSError(errno.EHOSTUNREACH, "No route to host"),
        env={"TERM_PROGRAM": "iTerm.app"},
        platform="darwin",
    )
    assert called["host"] == "10.0.4.20"
    assert "Local Network is blocked for iTerm" in msg
