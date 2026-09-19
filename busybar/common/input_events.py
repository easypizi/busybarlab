"""Subscribe to BUSY Bar button and wheel events over the status WebSocket."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

ButtonHandler = Callable[["InputEvent"], None]


class InputAction(str, Enum):
    PRESS = "press"
    RELEASE = "release"
    HOLD = "hold"
    UNKNOWN = "unknown"


class InputButton(str, Enum):
    OK = "ok"
    BACK = "back"
    START = "start"
    UP = "up"
    DOWN = "down"
    BUSY = "busy"
    CUSTOM = "custom"
    WHEEL_CW = "wheel_cw"
    WHEEL_CCW = "wheel_ccw"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class InputEvent:
    button: InputButton
    action: InputAction
    raw: dict[str, Any]


def _map_button(raw: dict[str, Any]) -> InputButton:
    name = str(raw.get("button") or raw.get("key") or raw.get("name") or "").lower()
    mapping = {
        "ok": InputButton.OK,
        "back": InputButton.BACK,
        "start": InputButton.START,
        "up": InputButton.UP,
        "down": InputButton.DOWN,
        "busy": InputButton.BUSY,
        "custom": InputButton.CUSTOM,
        "wheel_cw": InputButton.WHEEL_CW,
        "wheel_ccw": InputButton.WHEEL_CCW,
        "scroll_up": InputButton.WHEEL_CCW,
        "scroll_down": InputButton.WHEEL_CW,
        "0": InputButton.OK,
        "1": InputButton.BACK,
        "2": InputButton.START,
        "3": InputButton.UP,
        "4": InputButton.DOWN,
    }
    if name in mapping:
        return mapping[name]
    # Numeric protobuf enums sometimes arrive as ints.
    button_id = raw.get("button")
    if isinstance(button_id, int):
        return {
            0: InputButton.OK,
            1: InputButton.BACK,
            2: InputButton.START,
            3: InputButton.UP,
            4: InputButton.DOWN,
        }.get(button_id, InputButton.UNKNOWN)
    return InputButton.UNKNOWN


def _map_action(raw: dict[str, Any]) -> InputAction:
    name = str(raw.get("action") or raw.get("type") or "").lower()
    if name in {"press", "down", "0"}:
        return InputAction.PRESS
    if name in {"release", "up", "1"}:
        return InputAction.RELEASE
    if name in {"hold", "2"}:
        return InputAction.HOLD
    action_id = raw.get("action")
    if isinstance(action_id, int):
        return {0: InputAction.PRESS, 1: InputAction.RELEASE, 2: InputAction.HOLD}.get(
            action_id, InputAction.UNKNOWN
        )
    return InputAction.UNKNOWN


def parse_input_updates(state: dict[str, Any]) -> list[InputEvent]:
    """Extract input events from a decoded /api/status/ws state dict."""
    events: list[InputEvent] = []
    updates = state.get("updates") or []
    if not isinstance(updates, list):
        return events
    for update in updates:
        if not isinstance(update, dict):
            continue
        input_block = update.get("input")
        if not isinstance(input_block, dict):
            continue
        button_event = input_block.get("button_event") or input_block.get("buttonEvent")
        if isinstance(button_event, dict):
            events.append(
                InputEvent(
                    button=_map_button(button_event),
                    action=_map_action(button_event),
                    raw=button_event,
                )
            )
        wheel = input_block.get("wheel_event") or input_block.get("scroll_event")
        if isinstance(wheel, dict):
            delta = wheel.get("delta") or wheel.get("steps") or 0
            try:
                delta_i = int(delta)
            except (TypeError, ValueError):
                delta_i = 0
            if delta_i > 0:
                events.append(
                    InputEvent(
                        button=InputButton.WHEEL_CW,
                        action=InputAction.PRESS,
                        raw=wheel,
                    )
                )
            elif delta_i < 0:
                events.append(
                    InputEvent(
                        button=InputButton.WHEEL_CCW,
                        action=InputAction.PRESS,
                        raw=wheel,
                    )
                )
    return events


class InputEventPump:
    """
    Background async pump that forwards device input to a sync callback.

    Uses AsyncBusyBar.stream_status_ws. Safe no-op when address is None (sim mode).
    """

    def __init__(
        self,
        address: str | None,
        handler: ButtonHandler,
        *,
        token: str | None = None,
    ) -> None:
        self._address = address
        self._handler = handler
        self._token = token
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if not self._address:
            return
        self._thread = threading.Thread(target=self._run, name="busybar-input", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        try:
            asyncio.run(self._async_loop())
        except Exception:
            # Input is best-effort: apps keep running without it.
            return

    async def _async_loop(self) -> None:
        from busylib import AsyncBusyBar

        kwargs: dict[str, Any] = {}
        if self._token:
            kwargs["token"] = self._token
        assert self._address is not None
        async with AsyncBusyBar(self._address, **kwargs) as bb:
            async for message in bb.stream_status_ws():
                if self._stop.is_set():
                    break
                if not isinstance(message, dict):
                    continue
                for event in parse_input_updates(message):
                    if event.action in {InputAction.PRESS, InputAction.UNKNOWN}:
                        try:
                            self._handler(event)
                        except Exception:
                            continue
