"""Shared render backends, pixel-art helpers, and input event utilities."""

from apps.common.backend import BusyBarBackend, DisplayBackend, RenderElement
from apps.common.pixelart import ascii_to_png_bytes
from apps.common.preflight import check_device
from apps.common.simulator import TerminalBackend

__all__ = [
    "BusyBarBackend",
    "DisplayBackend",
    "RenderElement",
    "TerminalBackend",
    "ascii_to_png_bytes",
    "check_device",
]