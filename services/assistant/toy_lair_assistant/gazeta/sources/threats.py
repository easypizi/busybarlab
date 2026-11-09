"""Quakes (USGS), alerts (NWS), wildfires (CAL FIRE) and AQI (Open-Meteo)."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from toy_lair_assistant.gazeta.config import BAY_COUNTIES, LAT, LON
from toy_lair_assistant.gazeta.sources.http import get_json

USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
NWS = "https://api.weather.gov/alerts/active"
FIRE = "https://incidents.fire.ca.gov/umbraco/api/IncidentApi/List"
AQI = "https://air-quality-api.open-meteo.com/v1/air-quality"
ACRE_HA = 0.404686
NEAR_KM = 100
NEAR_MIN_MAG = 2.5
FAR_KM = 200
FAR_MIN_MAG = 4.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def parse_quakes(data: dict) -> list[dict]:
    out = []
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        lon, lat = feature["geometry"]["coordinates"][:2]
        mag = props.get("mag")
        if mag is None:
            continue
        km = haversine_km(LAT, LON, lat, lon)
        if not ((km <= NEAR_KM and mag >= NEAR_MIN_MAG) or (km <= FAR_KM and mag >= FAR_MIN_MAG)):
            continue
        out.append(
            {
                "mag": float(mag),
                "lat": lat,
                "lon": lon,
                "km": round(km),
                "place": str(props.get("place") or ""),
                "time_ms": props.get("time"),
                "url": str(props.get("url") or ""),
            }
        )
    out.sort(key=lambda q: -q["mag"])
    return out


def parse_alerts(data: dict) -> list[dict]:
    out = []
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        if props.get("status") != "Actual":
            continue
        out.append(
            {
                "event": str(props.get("event") or ""),
                "severity": str(props.get("severity") or ""),
                "headline": str(props.get("headline") or props.get("event") or ""),
                "ends": str(props.get("ends") or props.get("expires") or ""),
            }
        )
    return out


def parse_fires(data: Any) -> list[dict]:
    out = []
    for item in data if isinstance(data, list) else []:
        raw = item.get("County") or item.get("Counties") or ""
        if isinstance(raw, list):
            raw = ",".join(str(part) for part in raw)
        counties = {part.strip().lower().replace(" county", "") for part in str(raw).replace("/", ",").split(",")}
        if not counties & BAY_COUNTIES:
            continue
        out.append(
            {
                "name": str(item.get("Name") or ""),
                "county": str(item.get("County") or ""),
                "acres": item.get("AcresBurned") or 0,
                "contained": item.get("PercentContained") or 0,
                "url": str(item.get("Url") or ""),
            }
        )
    return out


def alert_active(threats: dict) -> bool:
    if any(a["severity"] in {"Severe", "Extreme"} or a["event"].lower().startswith("tsunami") for a in threats["alerts"]):
        return True
    if any(q["mag"] >= 4.0 for q in threats["quakes"]):
        return True
    return bool(threats["fires"])


def summary_line(threats: dict) -> str:
    quakes = threats["quakes"]
    if quakes:
        top = quakes[0]
        quake = f"Quakes in 24h: {len(quakes)}, max M{top['mag']:.1f} at {top['km']} km"
    else:
        quake = "Quakes in 24h: none of note"
    aqi = threats.get("aqi")
    parts = [quake]
    if aqi is not None:
        parts.append(f"AQI {aqi}")
    alerts = threats["alerts"]
    if alerts:
        parts.append(f"{len(alerts)} alert{'s' if len(alerts) != 1 else ''}: " + ", ".join(a["event"] for a in alerts[:2]))
    else:
        parts.append("No active alerts")
    if threats["fires"]:
        parts.append(f"{len(threats['fires'])} active fire{'s' if len(threats['fires']) != 1 else ''} nearby")
    return " · ".join(parts)


def bullet_lines(threats: dict) -> list[str]:
    lines = []
    for alert in threats["alerts"]:
        lines.append(f"NWS: {alert['headline']}")
    for quake in threats["quakes"][:5]:
        lines.append(f"M{quake['mag']:.1f} quake, {quake['place']} ({quake['km']} km away)")
    for fire in threats["fires"]:
        lines.append(f"Wildfire: {fire['name']} ({fire['county']}), {round(float(fire['acres']) * ACRE_HA)} ha, {fire['contained']}% contained")
    if threats.get("aqi") is not None:
        lines.append(f"Air quality: US AQI {threats['aqi']}")
    if not threats["alerts"] and not threats["quakes"] and not threats["fires"]:
        lines.append("No active alerts, no strong quakes.")
    return lines


def fetch(http: httpx.Client, now: datetime) -> dict:
    start = (now.astimezone(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    result: dict[str, Any] = {"quakes": [], "alerts": [], "fires": [], "aqi": None, "errors": []}
    steps = (
        ("quakes", lambda: parse_quakes(get_json(http, USGS, {"format": "geojson", "latitude": LAT, "longitude": LON, "maxradiuskm": FAR_KM, "minmagnitude": NEAR_MIN_MAG, "starttime": start}))),
        ("alerts", lambda: parse_alerts(get_json(http, NWS, {"point": f"{LAT},{LON}"}))),
        ("fires", lambda: parse_fires(get_json(http, FIRE, {"inactive": "false"}))),
        ("aqi", lambda: round(get_json(http, AQI, {"latitude": LAT, "longitude": LON, "current": "us_aqi"})["current"]["us_aqi"])),
    )
    for key, step in steps:
        try:
            result[key] = step()
        except Exception as exc:
            result["errors"].append(f"{key}: {exc}")
    result["summary"] = summary_line(result)
    result["alert_active"] = alert_active(result)
    result["lines"] = bullet_lines(result)
    return result
