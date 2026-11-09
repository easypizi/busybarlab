"""Launch Library 2: launches in the next 7 days."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from toy_lair_assistant.gazeta.sources.http import get_json

URL = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"


def parse(data: dict, zone: ZoneInfo) -> list[dict]:
    out = []
    for item in data.get("results") or []:
        net = item.get("net")
        if not net:
            continue
        when = datetime.fromisoformat(net.replace("Z", "+00:00")).astimezone(zone)
        out.append(
            {
                "when": when.strftime("%a %b %-d, %-I:%M %p"),
                "iso": when.isoformat(),
                "rocket": str((item.get("rocket") or {}).get("configuration", {}).get("name") or ""),
                "mission": str((item.get("mission") or {}).get("name") or item.get("name") or ""),
                "provider": str((item.get("launch_service_provider") or {}).get("name") or ""),
                "pad": str((item.get("pad") or {}).get("name") or ""),
                "location": str(((item.get("pad") or {}).get("location") or {}).get("name") or ""),
                "status": str((item.get("status") or {}).get("abbrev") or ""),
            }
        )
    out.sort(key=lambda row: row["iso"])
    return out


def fetch(http: httpx.Client, now: datetime) -> list[dict]:
    end = (now.astimezone(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = get_json(http, URL, {"limit": 25, "mode": "normal", "net__lte": end, "ordering": "net"})
    return parse(data, now.tzinfo if isinstance(now.tzinfo, ZoneInfo) else ZoneInfo("America/Los_Angeles"))
