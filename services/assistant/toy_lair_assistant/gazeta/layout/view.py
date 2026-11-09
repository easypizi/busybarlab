"""Turns pipeline outputs into the view model that paper.html renders, and shrinks it when pages overflow."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..config import SECTION_ORDER, SECTION_TITLES
from .. import charts

BODY_LIMITS = (None, 150, 120, 90, 60)
WEATHER_WORDS = 14


def _words(text: str, limit: int | None) -> str:
    """Cut to at most `limit` words on a sentence boundary. No ellipsis."""
    if limit is None:
        return text
    words = text.split()
    if len(words) <= limit:
        return text
    cut = " ".join(words[:limit])
    last = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "), cut.rfind(".\u201d "))
    if last > 0:
        return cut[: last + 1]
    return cut.rstrip(",;:") + "."


def _trim_body(paragraphs: list[str], limit: int | None) -> list[str]:
    if limit is None:
        return list(paragraphs)
    out: list[str] = []
    left = limit
    for para in paragraphs:
        n = len(para.split())
        if left <= 0:
            break
        out.append(para if n <= left else _words(para, left))
        left -= n
    return out


def _short(summary: str) -> str:
    return " ".join(summary.split()[:WEATHER_WORDS])


def _graphic(lead_graphic: dict | None, image_src: str | None) -> dict:
    g = lead_graphic or {"kind": "none"}
    if g.get("kind") == "illustration" and image_src:
        return {"kind": "illustration", "src": image_src, "caption": g.get("caption", "")}
    if g.get("kind") == "infographic" and g.get("points"):
        return {"kind": "infographic", "svg": charts.render(g), "caption": g.get("caption", "")}
    return {"kind": "none"}


def _pad_short(pad: str) -> str:
    return pad.split(",")[0][:28]


def build_view(
    *,
    now: datetime,
    issue_no: int,
    city: str,
    weather: dict | None,
    countdown: str | None,
    threats: dict,
    issue: dict,
    fact: dict | None,
    day: dict,
    launches: list[dict],
    f1: dict | None,
    image_src: str | None,
    sources_note: str = "",
    puzzles: dict | None = None,
) -> dict[str, Any]:
    lead = issue.get("lead")
    lead_view = None
    if lead:
        lead_view = {
            "kicker": lead.get("kicker") or "Lead story",
            "headline": lead["headline"],
            "standfirst": lead["standfirst"],
            "body": list(lead["body"]),
            "why": lead.get("why", ""),
            "source": lead.get("source", ""),
            "graphic": _graphic(lead.get("graphic"), image_src),
        }
    sections = []
    by_id = {s["id"]: s for s in issue.get("sections", [])}
    for sid in SECTION_ORDER:
        sec = by_id.get(sid)
        if sec and sec.get("stories"):
            sections.append({"id": sid, "title": SECTION_TITLES[sid], "stories": sec["stories"], "art": sec.get("art")})
    weather_view = None
    if weather:
        weather_view = {**weather, "short": _short(weather["summary"])}
    return {
        "date_long": now.strftime("%A, %B %-d, %Y"),
        "date_short": now.strftime("%B %-d, %Y"),
        "issue_no": issue_no,
        "city": city,
        "built_at": now.strftime("%-I:%M %p"),
        "weather": weather_view,
        "countdown": countdown,
        "threat_line": threats.get("summary", ""),
        "threat_alert": bool(threats.get("alert_active")),
        "threat_lines": list(threats.get("lines", [])),
        "lead": lead_view,
        "teasers": [
            {"headline": t["headline"], "section": SECTION_TITLES.get(t.get("section", ""), t.get("section", "")), "page": None}
            for t in issue.get("teasers", [])
        ],
        "day": {
            "num": now.day,
            "month": now.strftime("%B").upper(),
            "weekday": now.strftime("%A"),
            "year": now.year,
            "idea": day.get("idea"),
            "poem": day.get("poem", []),
            "fact": fact,
        },
        "incidents": {"lines": list(threats.get("lines", [])), "stories": list(issue.get("incidents", {}).get("stories", []))},
        "launches": [{**l, "pad_short": _pad_short(l.get("pad", ""))} for l in launches],
        "f1": f1 if f1 and (f1.get("next") or f1.get("last")) else None,
        "sections": sections,
        "sources_note": sources_note,
        "puzzles": puzzles,
        "puzzles_page": None,
        "_body_step": 0,
        "_fig_compact": 0,
    }


def apply_body_limit(view: dict) -> None:
    lead = view.get("lead")
    if not lead:
        return
    lead.setdefault("_full_body", list(lead["body"]))
    step = min(view["_body_step"], len(BODY_LIMITS) - 1)
    lead["body"] = _trim_body(lead["_full_body"], BODY_LIMITS[step])


def shrink_lead(view: dict) -> bool:
    """The lead column is too tall. Alternates shorter body and smaller picture, the illustration goes last."""
    lead = view.get("lead")
    if not lead:
        return False
    has_fig = lead["graphic"]["kind"] != "none"
    last_body = len(BODY_LIMITS) - 1
    body, fig = view["_body_step"], view["_fig_compact"]
    if body < 2:
        view["_body_step"] += 1
        apply_body_limit(view)
        return True
    if has_fig and fig < 1:
        view["_fig_compact"] = 1
        return True
    if body < 3:
        view["_body_step"] += 1
        apply_body_limit(view)
        return True
    if has_fig and fig < 2:
        view["_fig_compact"] = 2
        return True
    if body < last_body:
        view["_body_step"] += 1
        apply_body_limit(view)
        return True
    if lead["graphic"]["kind"] == "illustration":
        lead["graphic"] = {"kind": "none"}
        return True
    return False


def shrink_side(view: dict) -> bool:
    """The right column is too tall: fewer threat lines and teasers, then a shorter 'why'."""
    if len(view["threat_lines"]) > 2:
        view["threat_lines"] = view["threat_lines"][:-1]
        return True
    if len(view["teasers"]) > 2:
        view["teasers"] = view["teasers"][:-1]
        return True
    lead = view.get("lead")
    if lead and len(lead.get("why", "").split()) > 30:
        lead["why"] = _words(lead["why"], 30)
        return True
    if view["threat_lines"]:
        view["threat_lines"] = view["threat_lines"][:-1]
        return True
    if view["teasers"]:
        view["teasers"] = view["teasers"][:-1]
        return True
    return False


def shrink_extras(view: dict) -> bool:
    """The bottom band is too tall: shorter idea, then no idea."""
    day = view["day"]
    idea = day.get("idea")
    if idea and len(idea["text"].split()) > 22:
        idea["text"] = _words(idea["text"], 22)
        return True
    if idea:
        day["idea"] = None
        return True
    return False


def shrink_front(view: dict) -> bool:
    """One step smaller when the source of the overflow is unknown. Returns False when nothing is left."""
    return shrink_extras(view) or shrink_lead(view) or shrink_side(view)


def shrink_puzzles(view: dict) -> bool:
    puzzles = view.get("puzzles")
    if not puzzles:
        return False
    for key in ("onthisday", "yesterday", "chess"):
        if puzzles.get(key):
            puzzles[key] = [] if key == "onthisday" else None
            return True
    return False


def cap_flow(view: dict) -> bool:
    """Drop the last story of the longest rubric. Returns False when nothing is left."""
    sections = [s for s in view["sections"] if s["stories"]]
    if not sections:
        return False
    for _ in range(2):
        longest = max((s for s in sections if s["stories"]), key=lambda s: len(s["stories"]), default=None)
        if longest:
            longest["stories"].pop()
    view["sections"] = [s for s in view["sections"] if s["stories"]]
    return True


_norm = re.compile(r"[^a-z0-9]+")


def norm(text: str) -> str:
    return _norm.sub("", text.lower())
