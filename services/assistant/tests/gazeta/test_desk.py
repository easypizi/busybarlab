import json
from datetime import datetime, timedelta, timezone

import httpx

from toy_lair_assistant.gazeta import desk as desk_mod
from toy_lair_assistant.gazeta.desk import Desk

NOW = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)


def row(n, outlet="Wire", hours=2, title=None):
    stamp = (NOW - timedelta(hours=hours)).isoformat()
    return {"title": title or f"Alpha{n} beta{n} gamma{n} delta{n} epsilon{n}", "url": f"https://x/{n}", "outlet": outlet, "published": stamp, "snippet": ""}


class Client:
    def __init__(self, picks, headlines=None):
        self.picks = picks
        self.headlines = headlines or {}
        self.calls = []

    def chat_json(self, model, system, user, schema, name):
        payload = json.loads(user)
        self.calls.append((name, payload))
        if name == "desk_pick":
            return {"picks": [{"index": i, "score": s, "reason": "r"} for i, s in self.picks(payload)]}
        return {"stories": [{"index": a["i"], "headline": self.headlines.get(a["i"], "Report; " + a["title"]), "summary": "Summary \u2014 text."} for a in payload["articles"]]}


def http_ok(failing=()):
    def handler(request):
        if any(f in str(request.url) for f in failing):
            return httpx.Response(500)
        return httpx.Response(200, text="<html><body><p>Article body text here.</p></body></html>", headers={"content-type": "text/html"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def make(picks, failing=(), **kw):
    client = Client(picks, **kw)
    return Desk(client, "m", http_ok(failing), NOW, workers=1), client


def test_section_picks_opens_and_writes_in_order_with_cleaned_text():
    d, client = make(lambda p: [(2, 3), (0, 2), (1, 1)])
    stories = d.section("space", [row(0), row(1), row(2)], set(), [])
    assert [s["url"] for s in stories] == ["https://x/2", "https://x/0", "https://x/1"][:4]
    assert all(";" not in s["headline"] and "\u2014" not in s["summary"] for s in stories)
    assert stories[0]["source"] == "Wire"


def test_invalid_and_duplicate_indices_are_ignored():
    d, _ = make(lambda p: [(99, 3), (-1, 3), (1, 2), (1, 2)])
    stories = d.section("space", [row(0), row(1)], set(), [])
    assert [s["url"] for s in stories] == ["https://x/1"]


def test_limit_per_section_and_spares_fill_failed_downloads():
    rows = [row(n) for n in range(8)]
    d, _ = make(lambda p: [(n, 3) for n in range(8)], failing=("/0",))
    stories = d.section("f1", rows, set(), [])
    assert len(stories) == 3
    assert "https://x/0" not in [s["url"] for s in stories]


def test_old_excluded_and_similar_candidates_never_reach_the_model():
    rows = [row(0, hours=40), row(1), row(2, title="Lead story headline words repeated here")]
    d, client = make(lambda p: [(i["i"], 2) for i in p["candidates"]])
    stories = d.section("space", rows, {"https://x/1"}, ["Lead story headline words repeated"])
    assert stories == []
    assert client.calls == []


def test_all_downloads_failing_gives_no_stories():
    d, _ = make(lambda p: [(0, 3)], failing=("x/",))
    assert d.section("space", [row(0)], set(), []) == []


def test_run_dedupes_across_sections_and_skips_empty_and_failed_sections():
    shared = row(1, title="OpenAI ships agent builder for developers today")
    pool = {"ai_applied": [shared, row(2)], "ai_dev": [shared, row(3)], "space": [], "f1": [row(4)]}
    d, _ = make(lambda p: [(i["i"], 2) for i in p["candidates"]])
    sections = d.run(pool, set(), [])
    by_id = {s["id"]: [x["url"] for x in s["stories"]] for s in sections}
    assert by_id["ai_applied"] == ["https://x/1", "https://x/2"]
    assert by_id["ai_dev"] == ["https://x/3"]
    assert "space" not in by_id and "f1" in by_id


def test_a_failing_section_does_not_break_others():
    pool = {"ai_applied": [row(1)], "f1": [row(2)]}
    d, client = make(lambda p: (_ for _ in ()).throw(RuntimeError("boom")) if p["section"] == "Applied AI" else [(0, 2)])
    sections = d.run(pool, set(), [])
    assert [s["id"] for s in sections] == ["f1"]
