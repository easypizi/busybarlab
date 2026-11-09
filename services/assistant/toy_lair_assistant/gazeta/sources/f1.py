"""Jolpica (Ergast successor): next race, last podium, standings leaders."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from toy_lair_assistant.gazeta.sources.http import get_json

BASE = "https://api.jolpi.ca/ergast/f1/current"
SESSIONS = (
    ("FirstPractice", "FP1"),
    ("SecondPractice", "FP2"),
    ("ThirdPractice", "FP3"),
    ("SprintQualifying", "Sprint Quali"),
    ("Sprint", "Sprint"),
    ("Qualifying", "Qualifying"),
)


def _stamp(date: str, time: str | None, zone: ZoneInfo) -> str:
    if not time:
        return date
    when = datetime.fromisoformat(f"{date}T{time.replace('Z', '+00:00')}").astimezone(zone)
    return when.strftime("%a %-I:%M %p")


def parse_next(data: dict, zone: ZoneInfo) -> dict | None:
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return None
    race = races[0]
    sessions = []
    for key, label in SESSIONS:
        if key in race:
            sessions.append({"name": label, "when": _stamp(race[key]["date"], race[key].get("time"), zone)})
    sessions.append({"name": "Race", "when": _stamp(race["date"], race.get("time"), zone)})
    return {
        "name": str(race["raceName"]),
        "round": int(race["round"]),
        "circuit": str(race["Circuit"]["circuitName"]),
        "locality": str(race["Circuit"]["Location"]["locality"]),
        "date": str(race["date"]),
        "sessions": sessions,
    }


def parse_last(data: dict) -> dict | None:
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return None
    race = races[0]
    podium = [
        f"{r['Driver']['givenName']} {r['Driver']['familyName']} ({r['Constructor']['name']})"
        for r in race["Results"][:3]
    ]
    return {"name": str(race["raceName"]), "podium": podium}


def parse_standings(data: dict) -> list[str]:
    lists = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists:
        return []
    return [
        f"{row['Driver']['givenName']} {row['Driver']['familyName']}: {row['points']} pts"
        for row in lists[0]["DriverStandings"][:3]
    ]


def fetch(http: httpx.Client, zone: ZoneInfo) -> dict:
    out: dict = {"next": None, "last": None, "standings": []}
    for key, path, parser in (
        ("next", "/next.json", lambda d: parse_next(d, zone)),
        ("last", "/last/results.json", parse_last),
        ("standings", "/driverStandings.json", parse_standings),
    ):
        try:
            out[key] = parser(get_json(http, BASE + path))
        except Exception:
            continue
    return out
