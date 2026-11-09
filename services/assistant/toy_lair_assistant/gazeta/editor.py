"""Editor agent: Responses API tool loop plus hard guards applied in code."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from toy_lair_assistant.gazeta.articles import fetch_article
from toy_lair_assistant.gazeta.config import BAY_PLACES, SECTION_TITLES
from toy_lair_assistant.gazeta.state import norm

SKILL_PATH = Path(__file__).parent / "skills" / "editor.md"
WINDOW_HOURS = 36
MAX_FACT_CHARS = 220
MAX_STORIES = 5
GRAPHIC_TYPES = {"bar", "line", "map", "timeline"}


class EditorError(RuntimeError):
    pass


def clean_text(text: str) -> str:
    text = text.replace(" — ", ", ").replace("—", ", ").replace(" – ", ", ")
    return text.replace(";", ",")


def clean_tree(value: Any) -> Any:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return [clean_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: clean_tree(item) for key, item in value.items()}
    return value


def _parse_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _tokens(title: str) -> set[str]:
    return {word for word in norm(title).split() if len(word) > 3}


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.6


@dataclass
class Ledger:
    """What the agent has actually seen. Guards trust nothing outside it."""

    candidates: dict[str, dict] = field(default_factory=dict)  # url -> row from list_candidates
    searched: dict[str, str] = field(default_factory=dict)  # url -> title from web_search
    read: set[str] = field(default_factory=set)


def check_story(story: dict, ledger: Ledger, now: datetime) -> str | None:
    """Return a rejection reason, or None when the story passes."""
    url = str(story.get("url") or "")
    if not url:
        return "no url"
    in_candidates = url in ledger.candidates
    in_search = url in ledger.searched
    if not (in_candidates or in_search or url in ledger.read):
        return "url never appeared in tool results"
    if not (url in ledger.read or in_search):
        return "article was never opened"
    published = _parse_time(ledger.candidates.get(url, {}).get("published")) or _parse_time(story.get("published"))
    if published is None:
        return "no publication date"
    if now.astimezone(timezone.utc) - published.astimezone(timezone.utc) > timedelta(hours=WINDOW_HOURS):
        return "older than 36 hours"
    if not str(story.get("headline") or "").strip():
        return "no headline"
    return None


def check_graphic(graphic: dict | None) -> dict:
    if not isinstance(graphic, dict):
        return {"kind": "none"}
    kind = graphic.get("kind")
    if kind == "illustration":
        prompt = str(graphic.get("prompt") or "").strip()
        return {"kind": "illustration", "prompt": prompt, "caption": str(graphic.get("caption") or "")} if prompt else {"kind": "none"}
    if kind == "infographic":
        points = [p for p in graphic.get("points") or [] if isinstance(p, dict)]
        good = all(str(p.get("source") or "").strip() and str(p.get("label") or "").strip() and isinstance(p.get("value"), (int, float)) for p in points)
        if graphic.get("type") == "map":
            good = good and all(isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float)) for p in points)
        if graphic.get("type") in GRAPHIC_TYPES and 3 <= len(points) <= 12 and good:
            return {"kind": "infographic", "type": graphic["type"], "title": str(graphic.get("title") or ""), "points": points, "caption": str(graphic.get("caption") or "")}
        return {"kind": "none"}
    return {"kind": "none"}


def apply_guards(issue: dict, ledger: Ledger, now: datetime) -> tuple[dict, list[dict], list[str]]:
    """Return (clean issue, dropped notes, lead problems)."""
    issue = clean_tree(issue)
    dropped: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: list[str] = []

    def keep(story: dict) -> bool:
        reason = check_story(story, ledger, now)
        if reason is None and (story["url"] in seen_urls or any(_similar(story["headline"], t) for t in seen_titles)):
            reason = "duplicate"
        if reason:
            dropped.append({"headline": str(story.get("headline") or story.get("url") or "?"), "reason": reason})
            return False
        seen_urls.add(story["url"])
        seen_titles.append(story["headline"])
        return True

    lead = issue.get("lead")
    lead_problems: list[str] = []
    if isinstance(lead, dict) and keep(lead):
        lead["graphic"] = check_graphic(lead.get("graphic"))
    else:
        if isinstance(lead, dict):
            lead_problems.append(dropped[-1]["reason"])
        else:
            lead_problems.append("no lead")
        lead = None

    sections = []
    for block in issue.get("sections") or []:
        if block.get("id") not in SECTION_TITLES:
            continue
        stories = [s for s in block.get("stories") or [] if isinstance(s, dict) and keep(s)][:MAX_STORIES]
        if stories:
            sections.append({"id": block["id"], "title": SECTION_TITLES[block["id"]], "stories": stories})

    def local(story: dict) -> bool:
        blob = f"{story.get('where', '')} {story.get('headline', '')}".lower()
        if any(re.search(rf"\b{re.escape(place)}\b", blob) for place in BAY_PLACES):
            return True
        dropped.append({"headline": str(story.get("headline") or "?"), "reason": "outside the Bay Area"})
        return False

    incidents = [
        s
        for s in (issue.get("incidents") or {}).get("stories") or []
        if isinstance(s, dict) and local(s) and keep(s)
    ][:6]
    teasers = [t for t in issue.get("teasers") or [] if isinstance(t, dict) and t.get("headline")][:3]
    clean = {"lead": lead, "teasers": teasers, "sections": sections, "incidents": {"stories": incidents}}
    return clean, dropped + [d for d in issue.get("dropped") or [] if isinstance(d, dict)], lead_problems


STORY_PROPS = {
    "headline": {"type": "string"},
    "summary": {"type": "string", "description": "1-2 sentences: what happened and what it means for Ivan"},
    "url": {"type": "string"},
    "source": {"type": "string", "description": "outlet name"},
    "published": {"type": "string", "description": "ISO timestamp of the article"},
}
TOOLS: list[dict[str, Any]] = [
    {"type": "web_search"},
    {
        "type": "function",
        "name": "list_candidates",
        "description": "List fresh RSS candidates (last 36 hours) for a section id.",
        "parameters": {"type": "object", "properties": {"section": {"type": "string"}}, "required": ["section"]},
    },
    {
        "type": "function",
        "name": "read_article",
        "description": "Fetch an article page and return its text. Required before writing about it.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "type": "function",
        "name": "submit_fact",
        "description": "Submit the US fact of the day. The source page must have been opened with read_article.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "source_url": {"type": "string"}, "source_name": {"type": "string"}},
            "required": ["text", "source_url", "source_name"],
        },
    },
    {
        "type": "function",
        "name": "submit_issue",
        "description": "Submit the lead story and the incidents. Rubric sections are written by the desk, not by you. Call once at the end.",
        "parameters": {
            "type": "object",
            "properties": {
                "lead": {
                    "type": "object",
                    "properties": {
                        **STORY_PROPS,
                        "standfirst": {"type": "string"},
                        "body": {"type": "array", "items": {"type": "string"}, "description": "paragraphs, 120-180 words total"},
                        "why": {"type": "string", "description": "Why it matters to you"},
                        "graphic": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["infographic", "illustration"]},
                                "type": {"type": "string", "enum": sorted(GRAPHIC_TYPES)},
                                "title": {"type": "string"},
                                "caption": {"type": "string"},
                                "prompt": {"type": "string"},
                                "points": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"label": {"type": "string"}, "value": {"type": "number"}, "source": {"type": "string"}, "lat": {"type": "number"}, "lon": {"type": "number"}},
                                        "required": ["label", "value", "source"],
                                    },
                                },
                            },
                            "required": ["kind"],
                        },
                    },
                    "required": ["headline", "standfirst", "body", "why", "url", "source", "published", "graphic"],
                },
                "incidents": {
                    "type": "object",
                    "properties": {
                        "stories": {
                            "type": "array",
                            "items": {"type": "object", "properties": {**STORY_PROPS, "where": {"type": "string"}, "status": {"type": "string"}}, "required": ["headline", "summary", "url", "source", "published"]},
                        }
                    },
                    "required": ["stories"],
                },
                "dropped": {"type": "array", "items": {"type": "object", "properties": {"headline": {"type": "string"}, "reason": {"type": "string"}}, "required": ["headline", "reason"]}},
            },
            "required": ["lead", "incidents"],
        },
    },
]


@dataclass
class EditorResult:
    issue: dict
    fact: dict | None
    dropped: list[dict]
    tool_calls: int


class Editor:
    def __init__(
        self,
        client: Any,
        model: str,
        http: httpx.Client,
        now: datetime,
        budget: int = 40,
        skill: str | None = None,
        max_rounds: int = 60,
    ) -> None:
        self.client = client
        self.model = model
        self.http = http
        self.now = now
        self.budget = budget
        self.skill = skill if skill is not None else SKILL_PATH.read_text()
        self.max_rounds = max_rounds

    def run(self, context: dict, candidates: dict[str, list[dict]], used_facts: list[str]) -> EditorResult:
        self.candidates = candidates
        self.used = {norm(f) for f in used_facts}
        self.ledger = Ledger()
        self.calls = 0
        self.fact: dict | None = None
        self.result: dict | None = None
        self.submit_tries = 0
        self.dropped: list[dict] = []
        self.raw_issue: dict = {}
        self.usage = 0
        message = {
            **context,
            "tool_budget": self.budget,
            "sections": {**SECTION_TITLES, "incidents": "Bay Area Incidents"},
            "section_sizes": {sid: len(rows) for sid, rows in candidates.items()},
            "used_facts": used_facts[-60:],
        }
        response = self.client.respond(
            self.model, self.skill, [{"role": "user", "content": json.dumps(message, ensure_ascii=False)}], TOOLS
        )
        nudges = 0
        for _ in range(self.max_rounds):
            self._absorb(response)
            calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
            if not calls:
                if self.result is None and nudges < 2:
                    nudges += 1
                    nudge = [{"role": "user", "content": "Do not reply with text. Call submit_fact if it is still missing, then call submit_issue now with what you have verified."}]
                    response = self.client.respond(self.model, self.skill, nudge, TOOLS, previous_response_id=response["id"])
                    continue
                break
            outputs = []
            for call in calls:
                outputs.append({"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(self._dispatch(call), ensure_ascii=False)})
            if self.result is not None:
                break
            response = self.client.respond(self.model, self.skill, outputs, TOOLS, previous_response_id=response["id"])
        if self.result is None:
            raise EditorError("editor finished without submitting an issue")
        return EditorResult(self.result, self.fact, self.dropped, self.calls)

    def _absorb(self, response: dict) -> None:
        self.usage += int((response.get("usage") or {}).get("total_tokens") or 0)
        for item in response.get("output", []):
            if item.get("type") == "web_search_call":
                self.calls += 1
            if item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                for note in part.get("annotations") or []:
                    if note.get("type") == "url_citation" and note.get("url"):
                        self.ledger.searched[note["url"].split("?utm_")[0]] = str(note.get("title") or "")
                        self.ledger.searched[note["url"]] = str(note.get("title") or "")

    def _dispatch(self, call: dict) -> Any:
        name = call.get("name")
        try:
            args = json.loads(call.get("arguments") or "{}")
        except json.JSONDecodeError:
            return {"error": "arguments were not valid JSON"}
        if name == "submit_issue":
            return self._submit_issue(args)
        if name == "submit_fact":
            return self._submit_fact(args)
        if self.calls >= self.budget:
            return {"error": "tool budget exhausted. Call submit_fact and submit_issue now with what you have verified."}
        self.calls += 1
        if name == "list_candidates":
            return self._list(str(args.get("section") or ""))
        if name == "read_article":
            return self._read(str(args.get("url") or ""))
        return {"error": f"unknown tool {name}"}

    def _list(self, section: str) -> Any:
        rows = self.candidates.get(section)
        if rows is None:
            return {"error": f"unknown section {section}", "sections": list(self.candidates)}
        out = rows[:25]
        for row in out:
            self.ledger.candidates[row["url"]] = row
        return out

    def _read(self, url: str) -> Any:
        if not url.startswith(("http://", "https://")):
            return {"error": "url must be http(s)"}
        try:
            final, text = fetch_article(self.http, url)
        except Exception as exc:
            return {"error": f"fetch failed: {exc}"}
        self.ledger.read.add(url)
        self.ledger.read.add(final)
        return {"url": url, "text": text}

    def _submit_fact(self, args: dict) -> Any:
        text = clean_text(str(args.get("text") or "").strip())
        url = str(args.get("source_url") or "")
        if len(text) > MAX_FACT_CHARS:
            return {"error": f"fact is {len(text)} characters, limit is {MAX_FACT_CHARS}"}
        if url not in self.ledger.read:
            return {"error": "source page was not opened with read_article"}
        if url in self.ledger.candidates:
            return {"error": "that is a news article. A fact is timeless trivia from an encyclopedia, a government page or a reference site."}
        if re.search(r"\b20[0-9]{2}\b|%|\$|\b(announced|said|says|according to)\b", text, re.IGNORECASE):
            return {"error": "that reads like news or a statistic. A fact is timeless trivia with no year, percentage, dollar amount or attribution to a recent statement."}
        if norm(text) in self.used:
            return {"error": "this fact already ran, pick another"}
        self.fact = {"text": text, "source_url": url, "source_name": str(args.get("source_name") or "")}
        return {"ok": True}

    def _submit_issue(self, args: dict) -> Any:
        self.submit_tries += 1
        self.raw_issue = args
        issue = args if isinstance(args, dict) else {}
        clean, dropped, lead_problems = apply_guards(issue, self.ledger, self.now)
        problems = []
        if lead_problems:
            problems.append(f"lead story rejected: {lead_problems[0]}. Open the article with read_article, or choose another lead.")
        if self.fact is None:
            problems.append("no US fact yet. Find a source page, open it with read_article, then call submit_fact.")
        if not clean["incidents"]["stories"]:
            problems.append("incidents has no stories. Take 3 to 6 crime or public-safety articles from list_candidates('incidents'), open them with read_article, and list them under incidents.stories. Threat data is printed by code, never write it up as a story.")
        unopened = [d["headline"] for d in dropped if d["reason"] == "article was never opened"]
        if unopened:
            problems.append("these stories were dropped because you never opened them with read_article: " + "; ".join(unopened[:12]))
        if problems and self.submit_tries < 3:
            if self.submit_tries == 1:
                self.budget += 12
            return {"error": "issue not accepted yet", "problems": problems, "dropped": dropped, "tool_calls_left": max(0, self.budget - self.calls)}
        self.dropped = dropped
        self.result = clean
        return {"ok": True, "dropped": dropped}
