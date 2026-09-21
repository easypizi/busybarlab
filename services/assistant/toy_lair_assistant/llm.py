from __future__ import annotations

import json
from typing import Any

import httpx

from toy_lair_assistant.agent import AgentResult, ToolCall

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "todoist_add",
            "description": "Create a Todoist task",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "due_string": {"type": "string"},
                    "due_datetime": {"type": "string"},
                    "priority": {"type": "integer"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "deadline": {"type": "string"},
                    "description": {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                    "project": {"type": "string"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todoist_upcoming",
            "description": "List upcoming Todoist tasks",
            "parameters": {
                "type": "object",
                "properties": {"days": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todoist_complete",
            "description": "Complete a Todoist task by id",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todoist_update",
            "description": "Update a Todoist task. Never delete tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "content": {"type": "string"},
                    "priority": {"type": "integer"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "deadline": {"type": "string"},
                    "description": {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                    "due_string": {"type": "string"},
                    "due_datetime": {"type": "string"},
                    "project": {"type": "string"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todoist_reschedule",
            "description": "Change a task due date using natural language",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "due_string": {"type": "string"},
                },
                "required": ["task_id", "due_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todoist_today",
            "description": "List tasks due today",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_events",
            "description": "List calendar events for a range of days",
            "parameters": {
                "type": "object",
                "properties": {"days": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_calendars",
            "description": "List Google calendar names the agent can read",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_create",
            "description": "Create a calendar event or meeting",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "description": {"type": "string"},
                },
                "required": ["title", "start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "free_slots",
            "description": "List free calendar windows over the planning horizon",
            "parameters": {
                "type": "object",
                "properties": {"days": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_apply",
            "description": "Apply a confirmed plan: create Todoist tasks only. Tito calendar mirrors them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "start": {"type": "string"},
                                "duration_minutes": {"type": "integer"},
                            },
                            "required": ["content", "start"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_move",
            "description": "Move a calendar event",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["event_id", "start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_delete",
            "description": "Delete a calendar event",
            "parameters": {
                "type": "object",
                "properties": {"event_id": {"type": "string"}},
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminder",
            "description": "Schedule a one-off Telegram reminder",
            "parameters": {
                "type": "object",
                "properties": {
                    "fire_at": {"type": "string", "description": "ISO datetime"},
                    "text": {"type": "string"},
                },
                "required": ["fire_at", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "zayka_search",
            "description": "Search the Zayka vault",
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
            "description": "Read an allowed Zayka note",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
]


class OpenAILLM:
    def __init__(self, api_key: str, model: str, http: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.http = http or httpx.Client(timeout=60)

    def complete(self, messages: list[dict[str, Any]], tools: list[str]) -> AgentResult:
        selected = [schema for schema in TOOL_SCHEMAS if schema["function"]["name"] in tools]
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if selected:
            body["tools"] = selected
        response = self.http.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        calls: list[ToolCall] = []
        for index, raw in enumerate(message.get("tool_calls") or []):
            fn = raw.get("function") or {}
            args = fn.get("arguments") or "{}"
            parsed = json.loads(args) if isinstance(args, str) else args
            calls.append(
                ToolCall(
                    name=fn.get("name"),
                    arguments=parsed or {},
                    call_id=str(raw.get("id") or f"call{index}"),
                )
            )
        return AgentResult(reply=str(message.get("content") or "").strip(), tool_calls=calls)


class EchoLLM:
    def complete(self, messages: list[dict[str, Any]], tools: list[str]) -> AgentResult:
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return AgentResult(reply=str(user), tool_calls=[])
