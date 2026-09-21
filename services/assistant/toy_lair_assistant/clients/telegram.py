from __future__ import annotations

import html as html_lib
import json
import re
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from toy_lair_assistant.agent import invoke_agent

COMMANDS = [
    {"command": "today", "description": "Today's tasks and events"},
    {"command": "week", "description": "Next 7 days"},
    {"command": "plan", "description": "List of lines, Tito slots them"},
    {"command": "help", "description": "How Tito works"},
]

HELP = (
    "**Tito**\n"
    "Laid-back calendar butler.\n\n"
    "**Commands**\n"
    "/today: day card\n"
    "/week: week by day\n"
    "/plan: list of lines\n"
    "/help: this card\n\n"
    "**Plan**\n"
    "/plan\n"
    "уборка\n"
    "позвонить бате\n\n"
    "Hold PTT on the r1 to talk."
)

PLAN_HINT = (
    "**Plan**\n"
    "Each line is a task.\n\n"
    "/plan\n"
    "уборка\n"
    "позвонить бате"
)


def to_html(text: str) -> str:
    escaped = html_lib.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    lines = []
    for line in escaped.split("\n"):
        if line.startswith("- "):
            line = "• " + line[2:]
        lines.append(line)
    return "\n".join(lines)


def feedback_buttons(turn_id: str) -> list[list[dict[str, str]]]:
    return [
        [
            {"text": "👍", "callback_data": f"fb:up:{turn_id}"},
            {"text": "👎", "callback_data": f"fb:down:{turn_id}"},
        ]
    ]


def task_buttons(task_id: str) -> list[list[dict[str, str]]]:
    return [
        [
            {"text": "✅ Done", "callback_data": f"task:done:{task_id}"},
            {"text": "⏰ +1h", "callback_data": f"task:snooze:{task_id}:60"},
            {"text": "📅 Tomorrow", "callback_data": f"task:tomorrow:{task_id}"},
        ]
    ]


class TelegramBot:
    def __init__(
        self,
        token: str,
        chat_id: str,
        sender: Callable[[dict], None] | None = None,
        downloader: Callable[[str], bytes] | None = None,
        http: httpx.Client | None = None,
        store: Any = None,
        todoist: Any = None,
        photo_path: Path | None = None,
        now: Callable[[], datetime] | None = None,
        day_planner: Any = None,
        task_sync: Any = None,
    ) -> None:
        self.token = token
        self.chat_id = str(chat_id)
        self.http = http or httpx.Client(timeout=30)
        self._owns_http = http is None
        self.sender = sender or self._send
        self.downloader = downloader or self._download_voice
        self.store = store
        self.todoist = todoist
        self.photo_path = photo_path
        self.now = now or (lambda: datetime.now(ZoneInfo("America/Los_Angeles")))
        self.day_planner = day_planner
        self.task_sync = task_sync

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def allowed(self, chat_id: Any) -> bool:
        return str(chat_id) == self.chat_id

    def send_text(self, text: str) -> None:
        self.send_message(text)

    def send_message(
        self,
        text: str,
        buttons: list[list[dict[str, str]]] | None = None,
        photo: Path | None = None,
    ) -> None:
        markup = {"inline_keyboard": buttons} if buttons else None
        if photo and photo.exists():
            payload: dict[str, Any] = {
                "_method": "sendPhoto",
                "chat_id": self.chat_id,
                "caption": to_html(text),
                "parse_mode": "HTML",
                "_photo": str(photo),
            }
            if markup:
                payload["reply_markup"] = json.dumps(markup)
            self.sender(payload)
            return
        payload = {
            "chat_id": self.chat_id,
            "text": to_html(text),
            "parse_mode": "HTML",
        }
        if markup:
            payload["reply_markup"] = markup
        self.sender(payload)

    def handle_update(self, update: dict, agent: Any, speech: Any) -> None:
        if update.get("callback_query"):
            self._callback(update["callback_query"], agent)
            return
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        if not self.allowed(chat.get("id")):
            return
        text = (message.get("text") or "").strip()
        if not text and message.get("voice"):
            file_id = message["voice"]["file_id"]
            audio = self.downloader(file_id)
            text = speech.transcribe(audio, "audio/ogg")
        if not text:
            return
        if text.startswith("/"):
            self._command(text, agent)
            return
        self._agent_reply(agent, text)

    def ensure_profile(self, store: Any, now: datetime) -> None:
        key = f"tg_profile:{now.date().isoformat()}"
        if store.seen(key):
            return
        self._method("setMyName", {"name": "Tito"})
        self._method(
            "setMyDescription",
            {"description": "Tito, a laid-back Californian butler for Todoist and Calendar."},
        )
        self._method(
            "setMyShortDescription",
            {"short_description": "Calendar butler"},
        )
        self._method("setMyCommands", {"commands": COMMANDS})
        store.mark(key)

    def _command(self, text: str, agent: Any) -> None:
        parts = text.split(None, 1)
        cmd = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        name = cmd.split("@", 1)[0].lower()
        if name in {"/start", "/help"}:
            self.send_message(HELP, photo=self.photo_path)
            return
        if name == "/today":
            self._send_today(agent)
            return
        if name == "/week":
            self.send_message(self._week_text(agent))
            return
        if name == "/plan":
            self._send_plan(rest)
            return
        self._agent_reply(agent, text)

    def _send_plan(self, text: str) -> None:
        from toy_lair_assistant.day_plan import plan_buttons, parse_plan_lines, render

        raw = (text or "").strip()
        if not raw or self.day_planner is None:
            self.send_message(PLAN_HINT)
            return
        if not parse_plan_lines(raw):
            self.send_message(PLAN_HINT)
            return
        plan = self.day_planner.build_from_lines(raw, self.now())
        self.send_message(render(plan), buttons=plan_buttons(plan))

    def _agent_reply(self, agent: Any, text: str) -> None:
        from toy_lair_assistant.cards import (
            LIST_TOOLS,
            looks_like_list,
            render_schedule_card,
            schedule_kind,
            short_tito,
        )

        if looks_like_list(text) and self.day_planner is not None:
            self._send_plan(text)
            return
        result = invoke_agent(agent, text, channel="telegram")
        kind = schedule_kind(text)
        used = set(getattr(result, "used_tools", []) or [])
        if kind or used & LIST_TOOLS:
            card, buttons = render_schedule_card(self.day_planner, agent, kind or "today", self.now())
            note = short_tito(result.reply)
            body = "\n".join(part for part in (card, note) if part)
            self.send_message(body or result.reply, buttons=buttons)
            return
        turn_id = uuid.uuid4().hex[:8]
        self.send_message(result.reply, buttons=feedback_buttons(turn_id))

    def _send_today(self, agent: Any) -> None:
        if self.day_planner is not None:
            from toy_lair_assistant.day_plan import plan_buttons, render

            plan = self.day_planner.build(self.now())
            self.send_message(render(plan), buttons=plan_buttons(plan))
            return
        self.send_message(self._today_text(agent))

    def _today_text(self, agent: Any) -> str:
        payload = agent.today_payload(agent.now())
        tasks = [item for item in payload["items"] if item["kind"] == "task"]
        events = [item for item in payload["items"] if item["kind"] == "event"]
        tasks.sort(key=lambda item: int(item.get("priority") or 1), reverse=True)
        lines = ["**Today**"]
        if tasks:
            lines.append("**Tasks**")
            for item in tasks:
                mark = "🔴 " if int(item.get("priority") or 1) >= 4 else ""
                when = item.get("when") or ""
                lines.append(f"- {mark}{item['title']} {when}".rstrip())
        if events:
            lines.append("**Events**")
            for item in events:
                when = item.get("when") or ""
                lines.append(f"- {item['title']} {when}".rstrip())
        if len(lines) == 1:
            lines.append("Nothing on the books.")
        return "\n".join(lines)

    def _week_text(self, agent: Any) -> str:
        from datetime import timedelta

        from toy_lair_assistant.day_plan import render_week

        now = agent.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tasks = list(agent.todoist.upcoming(7))
        events = list(agent.calendar.events_in_range(start, start + timedelta(days=7)))
        return render_week(now, tasks, events)

    def _callback(self, query: dict, agent: Any) -> None:
        message = query.get("message") or {}
        chat = message.get("chat") or {}
        if not self.allowed(chat.get("id")):
            return
        self.sender(
            {
                "_method": "answerCallbackQuery",
                "callback_query_id": query.get("id"),
                "text": "Noted",
            }
        )
        data = str(query.get("data") or "")
        if data.startswith("fb:"):
            parts = data.split(":")
            vote = parts[1] if len(parts) > 1 else ""
            turn_id = parts[2] if len(parts) > 2 else ""
            if self.store and hasattr(self.store, "add_feedback"):
                self.store.add_feedback("telegram", turn_id, vote, self.now())
            return
        if data.startswith("plan:") and self.day_planner is not None:
            self._plan_action(data, message)
            return
        if data.startswith("task:") and self.todoist is not None:
            self._task_action(data, message)

    def _plan_action(self, data: str, message: dict) -> None:
        from toy_lair_assistant.day_plan import plan_buttons, render

        if data == "plan:redo":
            plan = self._rebuild_plan()
            self.send_message(render(plan), buttons=plan_buttons(plan))
            return
        if data == "plan:tomorrow":
            if self.day_planner._draft_lines:
                plan = self.day_planner.build_from_lines(
                    self.day_planner._draft_lines,
                    self.now(),
                    day_offset=self.day_planner._draft_offset + 1,
                )
            else:
                from datetime import timedelta

                plan = self.day_planner.build(self.now() + timedelta(days=1))
            self.send_message(render(plan), buttons=plan_buttons(plan))
            return
        if not data.startswith("plan:apply:"):
            return
        plan_id = data.split(":", 2)[2]
        plan = self.day_planner.apply(plan_id, self.now())
        count = len(plan.suggested) if plan else 0
        created = sum(
            1
            for item in (plan.suggested if plan else [])
            if item.is_new or str(item.task_id).startswith("new:")
        )
        note = f"Applied {count} slots, {created} new task." if created else f"Applied {count} slots."
        original = message.get("text") or message.get("caption") or ""
        self.sender(
            {
                "_method": "editMessageText",
                "chat_id": self.chat_id,
                "message_id": message.get("message_id"),
                "text": to_html(f"{original}\n{note}"),
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": []},
            }
        )

    def _rebuild_plan(self):
        if self.day_planner._draft_lines:
            return self.day_planner.build_from_lines(
                self.day_planner._draft_lines,
                self.now(),
                day_offset=self.day_planner._draft_offset,
            )
        return self.day_planner.build(self.now())

    def _task_action(self, data: str, message: dict) -> None:
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        task_id = parts[2] if len(parts) > 2 else ""
        note = ""
        if action == "done":
            self.todoist.complete(task_id)
            note = "Closed."
        elif action == "snooze":
            self.todoist.reschedule(task_id, "in 1 hour")
            note = "Snoozed +1h."
        elif action == "tomorrow":
            self.todoist.reschedule(task_id, "tomorrow")
            note = "Moved to tomorrow."
        else:
            return
        original = message.get("text") or message.get("caption") or ""
        self.sender(
            {
                "_method": "editMessageText",
                "chat_id": self.chat_id,
                "message_id": message.get("message_id"),
                "text": to_html(f"{original}\n{note}"),
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": []},
            }
        )

    def _method(self, method: str, payload: dict[str, Any]) -> None:
        self.sender({"_method": method, **payload})

    def _send(self, payload: dict) -> None:
        method = str(payload.pop("_method", "sendMessage"))
        if method == "sendPhoto":
            path = Path(str(payload.pop("_photo")))
            files = {"photo": (path.name, path.read_bytes(), "image/png")}
            data = {key: value for key, value in payload.items() if key != "chat_id"}
            data["chat_id"] = payload.get("chat_id", self.chat_id)
            url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
            self.http.post(url, data=data, files=files).raise_for_status()
            return
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        self.http.post(url, json=payload).raise_for_status()

    def _download_voice(self, file_id: str) -> bytes:
        meta = self.http.get(
            f"https://api.telegram.org/bot{self.token}/getFile",
            params={"file_id": file_id},
        )
        meta.raise_for_status()
        path = meta.json()["result"]["file_path"]
        data = self.http.get(f"https://api.telegram.org/file/bot{self.token}/{path}")
        data.raise_for_status()
        return data.content
