import json
from datetime import datetime, timezone

import httpx
import pytest

from toy_lair_assistant.gazeta.editor import Editor, EditorError, Ledger, apply_guards, check_graphic, clean_text
from toy_lair_assistant.gazeta.state import GazetaState
from toy_lair_assistant.store import MemoryStore

NOW = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
FRESH = "2026-11-09T10:00:00+00:00"
OLD = "2026-11-05T10:00:00+00:00"


def row(n, published=FRESH, title=None):
    return {"title": title or f"Title number {n} alpha", "url": f"https://x/{n}", "outlet": "O", "published": published, "snippet": ""}


def story(n, **extra):
    return {"headline": f"Headline {n} unique{n}word", "summary": "s", "url": f"https://x/{n}", "source": "O", "published": FRESH, **extra}


def ledger(read=(), listed=(), searched=()):
    led = Ledger()
    for r in listed:
        led.candidates[r["url"]] = r
    led.read.update(read)
    for u in searched:
        led.searched[u] = "t"
    return led


def lead(n=1, graphic=None):
    return {**story(n), "standfirst": "s", "body": ["b"], "why": "w", "graphic": graphic or {"kind": "none"}}


def test_clean_text_removes_dashes_and_semicolons():
    assert clean_text("a — b; c") == "a, b, c"


def test_guard_rejects_unread_unknown_old_and_duplicates():
    led = ledger(read={"https://x/1", "https://x/3", "https://x/4", "https://x/5"}, listed=[row(1), row(2), row(3, OLD), row(4), row(5)])
    issue = {
        "lead": lead(1),
        "sections": [
            {"id": "space", "stories": [story(2), story(3), story(9), story(4), story(5, headline="Headline 4 unique4word again")]},
            {"id": "nope", "stories": [story(4)]},
        ],
        "incidents": {"stories": []},
    }
    clean, dropped, problems = apply_guards(issue, led, NOW)
    kept = [s["url"] for sec in clean["sections"] for s in sec["stories"]]
    assert kept == ["https://x/4"]
    reasons = {d["headline"]: d["reason"] for d in dropped}
    assert reasons["Headline 2 unique2word"] == "article was never opened"
    assert reasons["Headline 3 unique3word"] == "older than 36 hours"
    assert reasons["Headline 9 unique9word"] == "url never appeared in tool results"
    assert "duplicate" in reasons.values()
    assert problems == []


def test_search_sourced_story_needs_its_own_date():
    led = ledger(searched={"https://web/1"})
    ok = {**story(1), "url": "https://web/1"}
    bad = {**story(2), "url": "https://web/1", "published": OLD}
    assert apply_guards({"lead": lead(1), "sections": [{"id": "space", "stories": [ok]}], "incidents": {"stories": []}}, led, NOW)[0]["sections"][0]["stories"]
    clean, dropped, _ = apply_guards({"lead": lead(1), "sections": [{"id": "space", "stories": [bad]}], "incidents": {"stories": []}}, led, NOW)
    assert clean["sections"] == [] and dropped[-1]["reason"] == "older than 36 hours"


def test_graphic_rules():
    pts = [{"label": c, "value": i, "source": "USGS"} for i, c in enumerate("abc")]
    assert check_graphic({"kind": "infographic", "type": "bar", "points": pts})["kind"] == "infographic"
    assert check_graphic({"kind": "infographic", "type": "bar", "points": pts[:2]})["kind"] == "none"
    assert check_graphic({"kind": "infographic", "type": "bar", "points": pts[:2] + [{"label": "z", "value": 1, "source": ""}]})["kind"] == "none"
    assert check_graphic({"kind": "infographic", "type": "pie", "points": pts})["kind"] == "none"
    assert check_graphic({"kind": "illustration", "prompt": "a owl"})["kind"] == "illustration"
    assert check_graphic({"kind": "illustration"})["kind"] == "none"
    assert check_graphic(None)["kind"] == "none"


def test_empty_sections_dropped_and_incidents_always_present():
    led = ledger(read={"https://x/1"}, listed=[row(1)])
    clean, _, _ = apply_guards({"lead": lead(1), "sections": [{"id": "space", "stories": []}], "incidents": {"stories": []}}, led, NOW)
    assert clean["sections"] == [] and clean["incidents"] == {"stories": []}


class Scripted:
    """Fake Responses client replaying prepared outputs."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []

    def respond(self, model, instructions, input, tools, previous_response_id=None):
        self.requests.append(input)
        return self.steps.pop(0)


def fn(name, call_id, **args):
    return {"type": "function_call", "name": name, "call_id": call_id, "arguments": json.dumps(args)}


def resp(i, *items):
    return {"id": f"r{i}", "output": list(items)}


def page_http():
    def handler(request):
        return httpx.Response(200, text="<html><body><p>Real article text</p></body></html>", headers={"content-type": "text/html"})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_editor_loop_end_to_end():
    issue = {"lead": lead(1), "teasers": [], "sections": [{"id": "space", "stories": [story(1, headline="Other thing entirely different")]}], "incidents": {"stories": [story(2, headline="Burglary downtown zzz", where="Burlingame")]}}
    # Same URL as lead is a duplicate on purpose: only the lead survives in sections.
    client = Scripted([
        resp(1, fn("list_candidates", "c1", section="space"), fn("list_candidates", "c1b", section="incidents")),
        resp(2, fn("read_article", "c2", url="https://x/1"), fn("read_article", "c2b", url="https://x/2"), fn("read_article", "c2c", url="https://ref/1")),
        resp(3, fn("submit_fact", "c3", text="Alaska crosses the 180th meridian.", source_url="https://ref/1", source_name="Wiki")),
        resp(4, fn("submit_issue", "c4", **issue)),
    ])
    editor = Editor(client, "m", page_http(), NOW, skill="skill")
    result = editor.run({"today": "2026-11-09"}, {"space": [row(1)], "incidents": [row(2)]}, [])
    assert result.issue["lead"]["url"] == "https://x/1"
    assert result.issue["sections"] == []
    assert result.fact["text"].startswith("Alaska")
    assert result.tool_calls == 5
    assert len(result.issue["incidents"]["stories"]) == 1
    outputs = client.requests[1]
    assert outputs[0]["type"] == "function_call_output" and "Title number 1" in outputs[0]["output"]


def test_fact_must_be_read_fresh_short_and_unseen():
    editor = Editor(Scripted([]), "m", page_http(), NOW, skill="s")
    editor.ledger = Ledger()
    editor.used = {"already ran"}
    editor.fact = None
    assert "not opened" in editor._submit_fact({"text": "x", "source_url": "https://x/1", "source_name": "n"})["error"]
    editor.ledger.read.add("https://x/1")
    assert "limit is 220" in editor._submit_fact({"text": "x" * 300, "source_url": "https://x/1", "source_name": "n"})["error"]
    assert "already ran" in editor._submit_fact({"text": "Already ran", "source_url": "https://x/1", "source_name": "n"})["error"]
    assert editor._submit_fact({"text": "New one", "source_url": "https://x/1", "source_name": "n"}) == {"ok": True}


def test_lead_rejected_then_accepted_on_third_try():
    editor = Editor(Scripted([]), "m", page_http(), NOW, skill="s")
    editor.ledger = Ledger()
    editor.submit_tries = 0
    editor.result = None
    editor.raw_issue = {}
    bad = {"lead": lead(1), "sections": [], "incidents": {"stories": []}}
    editor.fact = None
    editor.calls = 0
    first = editor._submit_issue(bad)
    assert first["error"] == "issue not accepted yet" and any("lead story rejected" in p for p in first["problems"])
    assert any("no US fact" in p for p in first["problems"]) and any("incidents has no stories" in p for p in first["problems"])
    assert editor.budget == 52
    assert "error" in editor._submit_issue(bad)
    assert editor._submit_issue(bad)["ok"] is True and editor.result["lead"] is None


def test_budget_blocks_tools_but_not_submit():
    editor = Editor(Scripted([]), "m", page_http(), NOW, budget=1, skill="s")
    editor.candidates = {"space": [row(1)]}
    editor.ledger = Ledger()
    editor.calls = 0
    assert isinstance(editor._dispatch(fn("list_candidates", "a", section="space")), list)
    assert "budget exhausted" in editor._dispatch(fn("read_article", "b", url="https://x/1"))["error"]


def test_no_submission_raises():
    editor = Editor(Scripted([resp(1), resp(2), resp(3)]), "m", page_http(), NOW, skill="s")
    with pytest.raises(EditorError):
        editor.run({}, {}, [])


def test_state_roundtrip_trims_and_persists():
    store = MemoryStore()
    state = GazetaState(store, lambda: NOW)
    state.record("fact one", "infographic", "2026-11-08")
    state.record("fact two", "illustration", "2026-11-09")
    data = state.load()
    assert data["facts"] == ["fact one", "fact two"]
    assert [g["kind"] for g in data["graphics"]] == ["infographic", "illustration"]


def test_nudge_when_model_answers_in_text():
    issue = {"lead": lead(1), "teasers": [], "sections": [], "incidents": {"stories": [story(2, headline="Burglary downtown zzz", where="Burlingame")]}}
    client = Scripted([
        resp(1, fn("list_candidates", "a", section="space"), fn("list_candidates", "b", section="incidents")),
        resp(2, fn("read_article", "c", url="https://x/1"), fn("read_article", "d", url="https://x/2"), fn("read_article", "d2", url="https://ref/1")),
        resp(3, fn("submit_fact", "e", text="Alaska crosses the 180th meridian.", source_url="https://ref/1", source_name="W")),
        resp(4, {"type": "message", "content": []}),
        resp(5, fn("submit_issue", "f", **issue)),
    ])
    editor = Editor(client, "m", page_http(), NOW, skill="s")
    result = editor.run({}, {"space": [row(1)], "incidents": [row(2)]}, [])
    assert result.issue["lead"]["url"] == "https://x/1"
    assert client.requests[4][0]["role"] == "user"


def test_incident_locality_guard():
    led = ledger(read={"https://x/1", "https://x/2", "https://x/3"}, listed=[row(1), row(2), row(3)])
    issue = {
        "lead": lead(1),
        "sections": [],
        "incidents": {"stories": [
            story(2, where="Charleston, SC", headline="Dad arrested in Pokemon line story zz"),
            story(3, where="Burlingame", headline="Burglary on Broadway qq"),
        ]},
    }
    clean, dropped, _ = apply_guards(issue, led, NOW)
    assert [s["url"] for s in clean["incidents"]["stories"]] == ["https://x/3"]
    assert any(d["reason"] == "outside the Bay Area" for d in dropped)


def test_fact_rejects_news_and_statistics():
    editor = Editor(Scripted([]), "m", page_http(), NOW, skill="s")
    editor.ledger = Ledger()
    editor.used = set()
    editor.fact = None
    editor.ledger.read.update({"https://news/1", "https://ref/1"})
    editor.ledger.candidates["https://news/1"] = row(1)
    assert "news article" in editor._submit_fact({"text": "Alaska is big.", "source_url": "https://news/1", "source_name": "n"})["error"]
    assert "reads like news" in editor._submit_fact({"text": "Spending hit $10 billion in 2026.", "source_url": "https://ref/1", "source_name": "n"})["error"]
    assert editor._submit_fact({"text": "Alaska crosses the 180th meridian.", "source_url": "https://ref/1", "source_name": "n"}) == {"ok": True}
