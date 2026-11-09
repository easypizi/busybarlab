from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from toy_lair_assistant.gazeta.sources import f1, feeds, launches, mail, occasions, threats, weather

ZONE = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 8, 18, 0, tzinfo=ZONE)


def quake(mag, lon, lat):
    return {"properties": {"mag": mag, "place": "x", "time": 1, "url": "u"}, "geometry": {"coordinates": [lon, lat, 5]}}


def test_quake_thresholds():
    data = {
        "features": [
            quake(2.6, -122.3, 37.6),  # near, small: keep
            quake(2.0, -122.3, 37.6),  # near, below min: drop
            quake(3.0, -121.0, 38.5),  # ~150 km, below far min: drop
            quake(4.2, -121.0, 38.5),  # ~150 km, M4+: keep
            quake(5.0, -118.0, 34.0),  # far away: drop
        ]
    }
    out = threats.parse_quakes(data)
    assert [q["mag"] for q in out] == [4.2, 2.6]


def test_alerts_only_actual():
    data = {"features": [
        {"properties": {"status": "Actual", "event": "Red Flag Warning", "severity": "Severe", "headline": "h"}},
        {"properties": {"status": "Test", "event": "Test"}},
    ]}
    alerts = threats.parse_alerts(data)
    assert len(alerts) == 1 and alerts[0]["event"] == "Red Flag Warning"


def test_fire_county_filter():
    data = [
        {"Name": "A", "County": "San Mateo", "AcresBurned": 10, "PercentContained": 5},
        {"Name": "B", "County": "Kern", "AcresBurned": 99, "PercentContained": 0},
        {"Name": "C", "Counties": ["Marin", "Sonoma"]},
    ]
    assert [f["name"] for f in threats.parse_fires(data)] == ["A", "C"]


def test_summary_and_alert_flag():
    quiet = {"quakes": [], "alerts": [], "fires": [], "aqi": 42}
    assert threats.summary_line(quiet) == "Quakes in 24h: none of note · AQI 42 · No active alerts"
    assert threats.alert_active(quiet) is False
    loud = {"quakes": [{"mag": 4.5, "km": 48, "place": "p"}], "alerts": [], "fires": [], "aqi": None}
    assert threats.alert_active(loud) is True
    assert "max M4.5 at 48 km" in threats.summary_line(loud)
    assert threats.bullet_lines(quiet)[-1] == "No active alerts, no strong quakes." or "AQI" in threats.bullet_lines(quiet)[-1]


def test_weather_parse():
    hours = [f"2026-11-08T{h:02d}:00" for h in range(24)]
    data = {
        "current": {"temperature_2m": 55.0},
        "hourly": {"time": hours, "temperature_2m": [50 + h * 0.5 for h in range(24)]},
        "daily": {
            "time": ["2026-11-08"],
            "temperature_2m_max": [68.0],
            "temperature_2m_min": [50.0],
            "precipitation_probability_max": [10],
            "sunrise": ["2026-11-08T06:42"],
            "sunset": ["2026-11-08T17:03"],
            "wind_speed_10m_max": [12.0],
        },
    }
    out = weather.parse(data, "2026-11-08")
    assert out["high"] == "68°F"
    assert "km/h" in out["summary"] and "°C" not in out["summary"]
    assert out["sunrise"] == "6:42 AM" and out["sunset"] == "5:03 PM"
    assert out["daylight"] == "10 h 21 min"
    assert "Morning 54°F" in out["summary"]


def test_launches_parse_converts_to_pt():
    data = {"results": [{
        "net": "2026-11-10T03:03:00Z",
        "rocket": {"configuration": {"name": "Falcon 9"}},
        "mission": {"name": "USSF-627"},
        "launch_service_provider": {"name": "SpaceX"},
        "pad": {"name": "SLC-4E", "location": {"name": "Vandenberg"}},
        "status": {"abbrev": "Go"},
    }]}
    out = launches.parse(data, ZONE)
    assert out[0]["when"] == "Mon Nov 9, 7:03 PM"
    assert out[0]["rocket"] == "Falcon 9"


def test_f1_parse():
    race = {
        "raceName": "Las Vegas Grand Prix", "round": "21", "date": "2026-11-22", "time": "04:00:00Z",
        "Circuit": {"circuitName": "Strip", "Location": {"locality": "Las Vegas"}},
        "Qualifying": {"date": "2026-11-21", "time": "04:00:00Z"},
    }
    out = f1.parse_next({"MRData": {"RaceTable": {"Races": [race]}}}, ZONE)
    assert out["sessions"][0] == {"name": "Qualifying", "when": "Fri 8:00 PM"}
    assert out["sessions"][-1]["name"] == "Race"
    last = f1.parse_last({"MRData": {"RaceTable": {"Races": [{"raceName": "R", "Results": [
        {"Driver": {"givenName": "A", "familyName": "B"}, "Constructor": {"name": "C"}}] * 3}]}}})
    assert len(last["podium"]) == 3


def task(content, due, string="every year", project="Friends & Family"):
    return SimpleNamespace(content=content, due_date=due, due_string=string, project=project)


def test_translit():
    assert occasions.translit("Ярослав Сивохин") == "Yaroslav Sivokhin"
    assert occasions.translit("Санёк") == "Sanyok"


def test_countdown_prefers_birthday_on_tie_and_nearest():
    today = date(2026, 11, 12)
    out = occasions.nearest(today, [task("Ярослав Сивохин", "2026-11-13"), task("Марк", "2027-09-24")])
    assert out["text"] == "Tomorrow: Yaroslav Sivokhin's birthday"
    assert occasions.nearest(date(2026, 11, 9), [])["label"] == "Veterans Day"
    out = occasions.nearest(date(2026, 11, 13), [task("Ярослав", "2026-11-13")])
    assert out["text"] == "Today: Yaroslav's birthday"


def test_countdown_ignores_other_projects_and_falls_back_to_holiday():
    out = occasions.nearest(date(2026, 11, 9), [task("Dentist", "2026-11-10", project="Work")])
    assert out["days"] is not None and "birthday" not in out["text"]
    assert occasions.nearest(date(2026, 10, 30), [])["label"] == "Halloween" or occasions.nearest(date(2026, 10, 30), [])["days"] <= 1


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Fresh</title><link>https://x/1</link><pubDate>Sun, 08 Nov 2026 20:00:00 GMT</pubDate><description>&lt;p&gt;hi&lt;/p&gt;</description></item>
<item><title>Old</title><link>https://x/2</link><pubDate>Mon, 02 Nov 2026 20:00:00 GMT</pubDate></item>
<item><title>No date</title><link>https://x/3</link></item>
</channel></rss>"""


def test_feed_window():
    rows = feeds.parse_feed(RSS, "Outlet", NOW)
    assert [r["title"] for r in rows] == ["Fresh"]
    assert rows[0]["snippet"] == "hi" and rows[0]["outlet"] == "Outlet"


class FakeImap:
    def __init__(self, host):
        self.raw = b"Subject: Sign this\r\nFrom: a@b.com\r\nDate: Sun, 08 Nov 2026 10:00:00 -0800\r\nMessage-ID: <1@x>\r\n\r\nPlease sign by Friday."

    def login(self, user, password):
        assert (user, password) == ("me@gmail.com", "pw")

    def select(self, name, readonly=False):
        assert readonly

    def search(self, *args):
        return "OK", [b"1 2"]

    def fetch(self, number, spec):
        return "OK", [(b"hdr", self.raw)]

    def logout(self):
        pass


def test_mail_fetch():
    out = mail.fetch("me@gmail.com", "pw", connect=FakeImap)
    assert len(out) == 2 and out[0]["subject"] == "Sign this"
    assert "sign by Friday" in out[0]["snippet"]
