"""Black-and-white SVG charts for the front page: bar, line, timeline and a quake radar map."""

from __future__ import annotations

import math
import textwrap
from html import escape

from toy_lair_assistant.gazeta.config import LAT, LON
from toy_lair_assistant.gazeta.sources.threats import haversine_km

W, H = 600, 300
INK = "#000"
GREY = "#777"


def _svg(body: str, title: str) -> str:
    head = f'<text x="0" y="16" font-size="18" font-weight="700">{escape(title)}</text>' if title else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img">{head}{body}</svg>'


def _fmt(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 100 or float(value).is_integer() else f"{value:,.1f}"


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def bar(points: list[dict], title: str = "") -> str:
    top = 30 if title else 6
    n = len(points)
    row = (H - top - 6) / n
    peak = max(abs(p["value"]) for p in points) or 1
    label_w, value_w = 190, 70
    span = W - label_w - value_w
    parts = []
    for i, p in enumerate(points):
        y = top + i * row
        length = max(2, span * abs(p["value"]) / peak)
        parts.append(f'<text x="{label_w - 8}" y="{y + row * 0.62:.1f}" font-size="15" text-anchor="end">{escape(_clip(p["label"], 30))}</text>')
        parts.append(f'<rect x="{label_w}" y="{y + row * 0.18:.1f}" width="{length:.1f}" height="{row * 0.64:.1f}" fill="{INK}"/>')
        parts.append(f'<text x="{label_w + length + 6:.1f}" y="{y + row * 0.62:.1f}" font-size="15" font-weight="700">{_fmt(p["value"])}</text>')
    return _svg("".join(parts), title)


def line(points: list[dict], title: str = "") -> str:
    left, right, top, bottom = 40, 20, 40 if title else 20, 50
    values = [p["value"] for p in points]
    lo, hi = min(values), max(values)
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.1
    lo, hi = lo - pad, hi + pad
    n = len(points)
    xs = [left + (W - left - right) * i / max(1, n - 1) for i in range(n)]
    ys = [top + (H - top - bottom) * (1 - (v - lo) / (hi - lo)) for v in values]
    parts = [f'<line x1="{left}" y1="{H - bottom}" x2="{W - right}" y2="{H - bottom}" stroke="{INK}" stroke-width="1.5"/>']
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{H - bottom}" stroke="{INK}" stroke-width="1.5"/>')
    parts.append(f'<text x="{left - 4}" y="{top + 4}" font-size="10" text-anchor="end">{_fmt(hi)}</text>')
    parts.append(f'<text x="{left - 4}" y="{H - bottom}" font-size="10" text-anchor="end">{_fmt(lo)}</text>')
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    parts.append(f'<polyline points="{path}" fill="none" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>')
    for p, x, y in zip(points, xs, ys):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{INK}"/>')
        parts.append(f'<text x="{x:.1f}" y="{y - 9:.1f}" font-size="13" font-weight="700" text-anchor="middle">{_fmt(p["value"])}</text>')
        parts.append(f'<text x="{x:.1f}" y="{H - bottom + 16}" font-size="10" text-anchor="middle">{escape(_clip(p["label"], 12))}</text>')
    return _svg("".join(parts), title)


def timeline(points: list[dict], title: str = "") -> str:
    n = len(points)
    mid = 170 if title else 150
    left, right = 50, 50
    xs = [left + (W - left - right) * i / max(1, n - 1) for i in range(n)]
    parts = [f'<line x1="{left - 20}" y1="{mid}" x2="{W - right + 20}" y2="{mid}" stroke="{INK}" stroke-width="3"/>']
    for i, (p, x) in enumerate(zip(points, xs)):
        up = i % 2 == 0
        parts.append(f'<circle cx="{x:.1f}" cy="{mid}" r="7" fill="#fff" stroke="{INK}" stroke-width="3"/>')
        parts.append(f'<line x1="{x:.1f}" y1="{mid + (-9 if up else 9)}" x2="{x:.1f}" y2="{mid + (-34 if up else 34)}" stroke="{INK}" stroke-width="1.5"/>')
        lines = textwrap.wrap(p["label"], 22)[:4]
        base = mid - 40 - 13 * (len(lines) - 1) if up else mid + 50
        for j, text in enumerate(lines):
            parts.append(f'<text x="{x:.1f}" y="{base + 13 * j:.1f}" font-size="13" text-anchor="middle">{escape(text)}</text>')
    return _svg("".join(parts), title)


def radar(points: list[dict], title: str = "") -> str:
    """Quake radar: reader at the center, rings in km, dot radius grows with magnitude (value)."""
    cx, cy = W / 2, (H + (24 if title else 0)) / 2
    radius = (H - (44 if title else 20)) / 2
    max_km = 200
    parts = []
    for ring in (50, 100, 150):
        r = radius * ring / max_km
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="{GREY}" stroke-width="1" stroke-dasharray="3 4"/>')
        parts.append(f'<text x="{cx + r * 0.71 + 3:.1f}" y="{cy - r * 0.71 - 2:.1f}" font-size="10" fill="{GREY}">{ring} km</text>')
    parts.append(f'<path d="M{cx - 7} {cy} h14 M{cx} {cy - 7} v14" stroke="{INK}" stroke-width="2.5"/>')
    parts.append(f'<text x="{cx + 10}" y="{cy + 16}" font-size="13" font-weight="700">Burlingame</text>')
    for p in points:
        km = haversine_km(LAT, LON, p["lat"], p["lon"])
        dist = min(km, max_km)
        bearing = math.atan2((p["lon"] - LON) * math.cos(math.radians(LAT)), p["lat"] - LAT)
        r = radius * dist / max_km
        x, y = cx + r * math.sin(bearing), cy - r * math.cos(bearing)
        dot = 3 + max(0.0, p["value"]) * 2
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{dot:.1f}" fill="{INK}"/>')
        parts.append(f'<text x="{x + dot + 3:.1f}" y="{y + 4:.1f}" font-size="13" font-weight="700">{escape(_clip(p["label"], 22))}</text>')
    parts.append(f'<text x="{cx}" y="{H - 2}" font-size="10" text-anchor="middle" fill="{GREY}">N up. Dot size grows with magnitude.</text>')
    return _svg("".join(parts), title)


RENDERERS = {"bar": bar, "line": line, "timeline": timeline, "map": radar}


def render(graphic: dict) -> str:
    return RENDERERS[graphic["type"]](graphic["points"], graphic.get("title", ""))
