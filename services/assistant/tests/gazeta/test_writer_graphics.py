import xml.etree.ElementTree as ET

import pytest

from toy_lair_assistant.gazeta import charts, illustrator, writer
from toy_lair_assistant.gazeta.editor import check_graphic


def draft(**over):
    out = {
        "tasks": [{"title": "Reply to Anna", "note": "Mail, due Fri", "origin": "mail"}],
        "idea": {"hook": "h", "text": "t"},
        "poem": ["a", "b", "c", "d"],
        "comic": {
            "p1": {"you": ["Build my paper"], "printer": ["Done. Get up."]},
            "p2": {"caption": "Snoozed five times.", "speech": ["Five more min"]},
            "p3": {"caption": "Bought a plan.", "speech": ["I am a planner"], "prop": "365 days"},
            "p4": {"caption": "Went once.", "speech": ["Weather did it"]},
        },
    }
    out.update(over)
    return out


class FakeClient:
    def __init__(self, drafts):
        self.drafts = list(drafts)
        self.users = []

    def chat_json(self, model, system, user, schema, name):
        self.users.append(user)
        return self.drafts.pop(0)


def test_valid_draft_has_no_violations():
    assert writer.violations(draft()) == []


def test_violations_reported():
    bad = draft()
    bad["comic"]["p1"]["you"] = ["this line is far too long"]
    bad["comic"]["p3"]["prop"] = "way too long prop"
    bad["poem"] = ["a", "b"]
    found = writer.violations(bad)
    assert any("p1.you" in v for v in found) and any("p3.prop" in v for v in found) and any("poem" in v for v in found)


def test_retry_feeds_violations_back_and_stops_when_clean():
    bad = draft()
    bad["comic"]["p2"]["speech"] = ["x" * 30]
    client = FakeClient([bad, draft()])
    out = writer.write(client, "m", {"name": "Ivan"})
    assert writer.violations(out) == []
    assert len(client.users) == 2 and "broke these limits" in client.users[1]


def test_broken_comic_is_replaced_after_retries():
    bad = draft()
    bad["comic"]["p4"]["speech"] = ["this is much longer than sixteen", "second", "third"]
    client = FakeClient([bad, bad, bad])
    out = writer.write(client, "m", {})
    assert writer.violations(out) == []
    assert len(client.users) == 3
    assert out["comic"] == writer.DEFAULT_COMIC


POINTS = [{"label": "Mon", "value": 3, "source": "s"}, {"label": "Tue", "value": 9, "source": "s"}, {"label": "Wed launch of something long", "value": 5, "source": "s"}]
QUAKES = [{"label": "M4.6 Pinnacles", "value": 4.6, "lat": 36.6, "lon": -121.2, "source": "USGS"}, {"label": "M2.9 Berkeley", "value": 2.9, "lat": 37.87, "lon": -122.3, "source": "USGS"}, {"label": "M3.1 San Jose", "value": 3.1, "lat": 37.3, "lon": -121.9, "source": "USGS"}]


@pytest.mark.parametrize("kind,points", [("bar", POINTS), ("line", POINTS), ("timeline", POINTS), ("map", QUAKES)])
def test_charts_are_valid_svg(kind, points):
    svg = charts.render({"type": kind, "title": "Title & more", "points": points})
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "Title &amp; more" in svg


def test_map_requires_coordinates_in_guard():
    pts = [{"label": c, "value": 1, "source": "s"} for c in "abc"]
    assert check_graphic({"kind": "infographic", "type": "map", "points": pts})["kind"] == "none"
    assert check_graphic({"kind": "infographic", "type": "map", "points": QUAKES})["kind"] == "infographic"


class ImageClient:
    def image(self, model, prompt, size):
        assert "engraving" in prompt and "Scene: an owl" in prompt
        return b"\x89PNG"


def test_illustrator_returns_data_uri_or_none():
    assert illustrator.make(ImageClient(), "m", "an owl").startswith("data:image/png;base64,")

    class Boom:
        def image(self, *args):
            raise RuntimeError("no")

    assert illustrator.make(Boom(), "m", "x") is None
