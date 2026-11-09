"""Open-Meteo forecast for the reader's point, in Fahrenheit for the headline figure, Celsius and km/h in the text."""

from __future__ import annotations

from datetime import datetime

import httpx

from toy_lair_assistant.gazeta.config import LAT, LON
from toy_lair_assistant.gazeta.sources.http import get_json

URL = "https://api.open-meteo.com/v1/forecast"


def _fmt(f: float) -> str:
    return f"{round((f - 32) * 5 / 9)}°C"


def parse(data: dict, today: str) -> dict:
    daily = data["daily"]
    index = daily["time"].index(today)
    hourly = data["hourly"]
    temps = {}
    for label, hour in (("morning", 8), ("afternoon", 14), ("evening", 20)):
        stamp = f"{today}T{hour:02d}:00"
        temps[label] = hourly["temperature_2m"][hourly["time"].index(stamp)]
    sunrise = datetime.fromisoformat(daily["sunrise"][index])
    sunset = datetime.fromisoformat(daily["sunset"][index])
    daylight = sunset - sunrise
    hours, rem = divmod(int(daylight.total_seconds()), 3600)
    now_f = data.get("current", {}).get("temperature_2m", temps["morning"])
    rain = daily["precipitation_probability_max"][index]
    wind = daily["wind_speed_10m_max"][index]
    parts = [
        f"Morning {_fmt(temps['morning'])}, afternoon {_fmt(temps['afternoon'])}, evening {_fmt(temps['evening'])}.",
        f"Rain chance {int(rain or 0)}%, wind up to {round(wind)} km/h.",
    ]
    return {
        "now_f": round(now_f),
        "high": _fmt(daily["temperature_2m_max"][index]),
        "low": _fmt(daily["temperature_2m_min"][index]),
        "summary": " ".join(parts),
        "sunrise": sunrise.strftime("%-I:%M %p"),
        "sunset": sunset.strftime("%-I:%M %p"),
        "daylight": f"{hours} h {rem // 60} min",
        "rain_pct": int(rain or 0),
    }


def fetch(http: httpx.Client, today: str, timezone: str) -> dict:
    data = get_json(
        http,
        URL,
        {
            "latitude": LAT,
            "longitude": LON,
            "timezone": timezone,
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "kmh",
            "current": "temperature_2m",
            "hourly": "temperature_2m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
            "sunrise,sunset,wind_speed_10m_max",
            "forecast_days": 2,
        },
    )
    return parse(data, today)
