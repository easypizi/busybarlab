from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from toy_lair_assistant.agent import AgentResult, ToolCall
from toy_lair_assistant.paco_vault import PacoVault
from toy_lair_assistant.zayka_write import ZaykaWrite

CHANNEL = "r1-paco"
DRAFT_BODY_LIMIT = 1500
INBOX_CUES = (
    "запиши",
    "сохрани",
    "сохраня",
    "добав",
    "в inbox",
    "в обсиди",
    "write it down",
    "save it",
)
DAILY_CUES = ("в дневник", "в daily", "today's note")

PACO_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "zayka_search",
            "description": "Search allowed Zayka notes. Snippets are enough for a short answer.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "zayka_read",
            "description": "Read one allowed note. The body may be truncated.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "zayka_list_inbox",
            "description": "List the newest Inbox notes and the full count.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_update",
            "description": "Revise the unsaved note draft. Does not write to the vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "filename_hint": {"type": "string"},
                    "related": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "zayka_inbox_create",
            "description": "Save the draft, or the given text, as a fleeting note. Only after a save phrase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "filename_hint": {"type": "string"},
                    "related": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "zayka_daily_append",
            "description": "Append the draft, or the given text, to today's daily note. Only after a daily phrase.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
]


@dataclass
class PacoResult:
    reply: str
    peek: dict[str, Any] = field(default_factory=dict)
    action: str = ""


class PacoAgent:
    def __init__(
        self,
        llm: Any,
        vault: PacoVault,
        writer: ZaykaWrite,
        now: Any,
        store: Any = None,
    ) -> None:
        self.llm = llm
        self.vault = vault
        self.writer = writer
        self.now = now
        self.store = store
        self.tools = {
            "zayka_search": self._search,
            "zayka_read": self._read,
            "zayka_list_inbox": self._list_inbox,
            "draft_update": self._draft_update,
            "zayka_inbox_create": self._inbox_create,
            "zayka_daily_append": self._daily_append,
        }
        self._searched = False
        self._hits: list[dict[str, str]] = []
        self._user_text = ""

    def handle_text(self, text: str) -> PacoResult:
        now = self.now()
        self._user_text = text
        self._searched = False
        self._hits = []
        self._saved = False
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt(now)}]
        if self.store is not None and hasattr(self.store, "recent_turns"):
            for turn in self.store.recent_turns(CHANNEL, now, limit=6, ttl_minutes=15):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": text})
        last = AgentResult(reply="ok")
        for _round in range(4):
            last = self.llm.complete(messages, list(self.tools), PACO_TOOL_SCHEMAS)
            if not last.tool_calls:
                break
            messages.append(_assistant_tool_message(last))
            for index, call in enumerate(last.tool_calls):
                if not call.call_id:
                    call.call_id = f"call{index}"
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.call_id,
                        "content": self._run(call),
                    }
                )
        reply = last.reply or "ok"
        self._remember(text, reply, now)
        peek = self._hit_peek() if self._searched else self.inbox_payload()
        return PacoResult(reply=reply, peek=peek, action="saved" if self._saved else "")

    def inbox_payload(self) -> dict[str, Any]:
        items, count = self.vault.list_inbox(self.now())
        return {"kind": "inbox", "items": items, "count": count}

    def system_prompt(self, now: datetime) -> str:
        if now.tzinfo is None:
            local = now.replace(tzinfo=self.vault.zone)
        else:
            local = now.astimezone(self.vault.zone)
        zone = getattr(local.tzinfo, "key", None) or str(local.tzinfo or "UTC")
        items, count = self.vault.list_inbox(local)
        lines = [
            "You are Paco.",
            f"Now: {local.strftime('%Y-%m-%d %H:%M')} {zone}.",
            "Fleeting notes go to 00 Inbox and should be processed within 48 hours.",
            "One note is one idea.",
            "Write the dictated thought in the user's words. Do not turn it into an essay.",
            "Link with [[wikilinks]] only to notes that exist.",
            "Workflow tags only: #draft #review #evergreen #idea #to-process #waiting. No topic tags.",
            "Do not mix languages inside one sentence. Technical terms stay in English.",
            "New filenames are kebab-case ASCII. No spaces. No Cyrillic.",
            "Inbox should stay at or under 20 notes. If it is over, say so.",
            "Answer in the language of the user's request.",
            "Inbox:",
        ]
        if not items:
            lines.append("(none)")
        for item in items:
            lines.append(f"{item['title']} · {item['age_hours']}h")
        if count > 20:
            lines.append(f"Inbox count: {count} (over 20)")
        daily = self.vault.daily_rel(local)
        daily_label = daily if (self.vault.root / daily).exists() else "none"
        lines.append(f"Daily today: {daily_label}")
        mocs = self.vault.moc_names()
        lines.append("MOCs: " + (", ".join(mocs) if mocs else "(none)"))
        lines.extend(self._draft_lines(local))
        lines.append(
            "While the user is shaping a note, call draft_update. "
            "Do not call zayka_inbox_create or zayka_daily_append."
        )
        lines.append(
            "Call zayka_inbox_create only when this message has a save phrase: "
            "запиши, сохрани, сохраняй, добавь, в inbox, в обсидиан, write it down."
        )
        lines.append(
            "Call zayka_daily_append only when this message has a daily phrase: "
            "в дневник, в daily, today's note."
        )
        lines.append(
            "If the user asks for an evergreen or project note, or to edit or delete, "
            "refuse in one sentence. Do not call a write tool."
        )
        lines.append(
            "Spoken replies are one or two sentences. Do not read the catalog. "
            "If there are many hits, say to look at the peek."
        )
        return "\n".join(lines)

    def _run(self, call: ToolCall) -> str:
        handler = self.tools.get(call.name)
        if handler is None:
            return f"unknown tool {call.name}"
        try:
            return str(handler(**(call.arguments or {})))
        except TypeError:
            return "bad arguments"

    def _search(self, query: str) -> str:
        hits = self.vault.search(query)
        self._searched = True
        self._hits = [
            {"path": hit.path, "title": hit.title, "snippet": hit.snippet} for hit in hits
        ]
        if not hits:
            return "No notes."
        return "\n".join(f"- {hit.path}: {hit.snippet}" for hit in hits)

    def _read(self, path: str) -> str:
        return self.vault.read_for_model(path)

    def _list_inbox(self) -> str:
        items, count = self.vault.list_inbox(self.now())
        lines = [f"inbox_count={count}"]
        lines.extend(f"{item['title']} · {item['age_hours']}h" for item in items)
        return "\n".join(lines)

    def _draft_lines(self, now: datetime) -> list[str]:
        draft = self._load_draft(now)
        title = str(draft.get("title") or "")
        body = str(draft.get("body") or "")
        hint = str(draft.get("filename_hint") or "")
        if not title and not body and not hint:
            return ["Draft:", "none"]
        if len(body) > DRAFT_BODY_LIMIT:
            body = body[:DRAFT_BODY_LIMIT]
        return ["Draft:", f"title: {title}", f"hint: {hint}", f"body: {body}"]

    def _draft_update(
        self,
        title: str = "",
        body: str = "",
        filename_hint: str = "",
        related: Any = None,
    ) -> str:
        if self.store is None or not hasattr(self.store, "save_draft"):
            return "Draft is not configured."
        current = self._load_draft()
        merged = {
            "title": title.strip() or str(current.get("title") or ""),
            "body": body.strip() or str(current.get("body") or ""),
            "filename_hint": filename_hint.strip() or str(current.get("filename_hint") or ""),
            "related": _related_list(related) or list(current.get("related") or []),
        }
        self.store.save_draft(CHANNEL, merged, self.now())
        return "Draft updated."

    def _inbox_create(
        self,
        title: str,
        body: str,
        filename_hint: str = "",
        related: Any = None,
    ) -> str:
        if not self._has_cue(INBOX_CUES):
            return "Not saved. Draft only."
        if isinstance(related, str):
            related = [related]
        title, body, filename_hint, related = self._from_draft(
            title, body, filename_hint, list(related or [])
        )
        if not str(body).strip():
            return "Refused."
        result = self.writer.inbox_create(
            self.now(),
            title,
            body,
            filename_hint,
            related,
        )
        if result.message == "wrote":
            self._saved = True
            self._clear_draft()
            return f"Wrote to Inbox: {title}"
        if result.message == "pull_failed":
            return "Pull failed. The vault is ahead."
        if result.message == "push_failed":
            return "Push failed."
        if result.message == "token_expired":
            return "GitHub token expired. Update ZAYKA_REPO_URL."
        return "Refused."

    def _daily_append(self, text: str) -> str:
        if not self._has_cue(DAILY_CUES):
            return "Not saved. Draft only."
        _title, body, _hint, _related = self._from_draft("", text, "", [])
        if not str(body).strip():
            return "Refused."
        result = self.writer.daily_append(self.now(), body)
        if result.message == "wrote":
            self._saved = True
            self._clear_draft()
            return "Added to daily."
        if result.message == "pull_failed":
            return "Pull failed. The vault is ahead."
        if result.message == "push_failed":
            return "Push failed."
        if result.message == "token_expired":
            return "GitHub token expired. Update ZAYKA_REPO_URL."
        return "Refused."

    def _from_draft(
        self,
        title: str,
        body: str,
        filename_hint: str,
        related: list[str],
    ) -> tuple[str, str, str, list[str]]:
        draft = self._load_draft()
        if draft.get("body"):
            body = str(draft["body"])
        if draft.get("title"):
            title = str(draft["title"])
        if draft.get("filename_hint"):
            filename_hint = str(draft["filename_hint"])
        if draft.get("related"):
            related = [str(item) for item in draft["related"]]
        return title, body, filename_hint, related

    def _has_cue(self, cues: tuple[str, ...]) -> bool:
        text = self._user_text.casefold()
        return any(cue.casefold() in text for cue in cues)

    def _load_draft(self, now: datetime | None = None) -> dict[str, Any]:
        if self.store is None or not hasattr(self.store, "get_draft"):
            return {}
        found = self.store.get_draft(CHANNEL, now or self.now())
        return found if isinstance(found, dict) else {}

    def _clear_draft(self) -> None:
        if self.store is not None and hasattr(self.store, "clear_draft"):
            self.store.clear_draft(CHANNEL)

    def _hit_peek(self) -> dict[str, Any]:
        return {"kind": "hits", "items": self._hits, "count": len(self._hits)}

    def _remember(self, user: str, reply: str, now: datetime) -> None:
        if self.store is None or not hasattr(self.store, "add_turn"):
            return
        self.store.add_turn(CHANNEL, "user", user, now)
        self.store.add_turn(CHANNEL, "assistant", reply, now)


def _related_list(related: Any) -> list[str]:
    if related is None:
        return []
    if isinstance(related, str):
        related = [related]
    return [str(item).strip() for item in related if str(item).strip()]


def _assistant_tool_message(result: AgentResult) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": result.reply or None,
        "tool_calls": [
            {
                "id": call.call_id or call.name,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                },
            }
            for call in result.tool_calls
        ],
    }
