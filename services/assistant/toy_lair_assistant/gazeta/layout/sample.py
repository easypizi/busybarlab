"""Static sample data to preview the layout without any network or model calls."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from . import view as V

NOW = datetime(2026, 11, 9, 7, 0, tzinfo=ZoneInfo("America/Los_Angeles"))

LOREM = (
    "Engineers at the company said the new system cut the time between a customer request and a finished result from hours to minutes, "
    "and that early partners had already moved their daily work onto it. The announcement came with a public price list, which analysts "
    "called aggressive. Competitors have not yet answered, though two of them are expected to ship rival tools within weeks. "
)


def _story(n: int, source: str, extra: str = "") -> dict:
    return {
        "headline": f"Sample headline number {n} about something that happened {extra}".strip(),
        "summary": "A short summary of what happened and why it matters to a reader in the Bay Area. " + ("It runs a little long to test wrapping. " if n % 2 else ""),
        "url": f"https://example.com/{n}",
        "source": source,
        "published": "2026-11-09T05:00:00+00:00",
    }


def sample_view(stories_per_section: int = 3, body_paragraphs: int = 4) -> dict:
    issue = {
        "lead": {
            "kicker": "Applied AI",
            "headline": "A Bay Area lab ships an agent that does a day of paperwork before lunch",
            "standfirst": "The tool is priced per task, not per seat, and the first customers are already cancelling their old subscriptions.",
            "body": [LOREM * 2 for _ in range(body_paragraphs)],
            "why": "If you build with agents this week, the pricing model changes which prototypes are worth finishing.",
            "source": "Example Wire",
            "url": "https://example.com/lead",
            "published": "2026-11-09T05:00:00+00:00",
            "graphic": {
                "kind": "infographic",
                "type": "bar",
                "title": "Price per task, USD",
                "caption": "Price per completed task, by vendor.",
                "points": [
                    {"label": "New agent", "value": 0.4, "source": "https://example.com/p1"},
                    {"label": "Vendor B", "value": 1.1, "source": "https://example.com/p2"},
                    {"label": "Vendor C", "value": 2.3, "source": "https://example.com/p3"},
                ],
            },
        },
        "teasers": [
            {"headline": "Sample headline number 1 about something that happened", "section": "space"},
            {"headline": "Sample headline number 4 about something that happened", "section": "f1"},
            {"headline": "Sample headline number 7 about something that happened", "section": "bay_area"},
        ],
        "sections": [],
        "incidents": {
            "stories": [
                {**_story(100 + i, "SF Chronicle"), "where": "San Mateo", "status": "reported overnight"}
                for i in range(4)
            ]
        },
    }
    n = 0
    from ..config import SECTION_ORDER

    for sid in SECTION_ORDER:
        stories = []
        for _ in range(stories_per_section):
            n += 1
            stories.append(_story(n, "Example Source"))
        issue["sections"].append({"id": sid, "stories": stories})
    day = {
        "tasks": [{"title": f"Task {i}", "note": "from Todoist, due today"} for i in range(1, 6)],
        "idea": {"hook": "Build a tiny tool for the thing you do twice a week.", "text": "Pick one repeated chore, time it for a week, then spend one evening automating the worst ten minutes of it."},
        "poem": ["The fog rolls in at seven,", "the printer hums along,", "your day is mostly planned,", "the rest is just a song."],
    }
    launches = [
        {"when": "Mon Nov 9, 8:14 PM", "rocket": "Falcon 9", "mission": "Starlink 12-30", "pad": "Space Launch Complex 4E, Vandenberg SFB, CA, USA"},
        {"when": "Wed Nov 11, 2:00 AM", "rocket": "Electron", "mission": "Sample Sat", "pad": "Launch Complex 1, Mahia Peninsula, New Zealand"},
    ]
    f1 = {
        "next": {"name": "Las Vegas Grand Prix", "locality": "Las Vegas", "sessions": [{"name": "FP1", "when": "Thu Nov 19, 1:30 PM"}, {"name": "Race", "when": "Sat Nov 21, 8:00 PM"}]},
        "last": {"name": "Sao Paulo Grand Prix", "podium": ["Driver One", "Driver Two", "Driver Three"]},
        "standings": ["Driver One: 410 pts", "Driver Two: 395 pts", "Driver Three: 360 pts"],
    }
    threats = {
        "summary": "Threat level: low. No active alerts, no quakes above M2.5 nearby, AQI 42, no fires in the Bay counties.",
        "alert_active": False,
        "lines": ["Quakes: none above M2.5 within 100 km in 24 h.", "NWS: no active alerts for San Mateo County.", "Air quality: AQI 42 (good).", "Fires: none active in Bay Area counties."],
    }
    return V.build_view(
        now=NOW,
        issue_no=1,
        city="Burlingame, CA",
        weather={"now_c": 14, "high": "19°C", "low": "11°C", "summary": "Morning fog clearing by noon, light breeze from the west, 10% chance of rain.", "sunrise": "6:41 AM", "sunset": "4:56 PM", "daylight": "10 h 15 min", "rain_pct": 10},
        countdown="Today: Veterans Day is in 2 days",
        threats=threats,
        issue=issue,
        fact={"text": "In 1983 the city of Oakland briefly held a national record for the largest number of dumb facts per capita.", "source_name": "Wikipedia"},
        day=day,
        launches=launches,
        f1=f1,
        image_src=None,
        sources_note="Sources are linked in the Telegram message.",
    )
