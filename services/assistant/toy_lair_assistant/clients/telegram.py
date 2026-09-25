from __future__ import annotations

import html as html_lib
import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from toy_lair_assistant.agent import invoke_agent

log = logging.getLogger(__name__)

_VOICE_LABELS = {"tito": "Tito", "paco": "Paco", "carlos": "Carlos"}
ADDRESS_RE = re.compile(
    r"^(tito|тито|paco|пако)[\s,:!]+(.+)$",
    re.IGNORECASE | re.DOTALL,
)

COMMANDS = [
    {"command": "today", "description": "Today's tasks and events"},
    {"command": "week", "description": "Next 7 days"},
    {"command": "plan", "description": "List of lines, Tito slots them"},
    {"command": "tito", "description": "Say it to Tito"},
    {"command": "paco", "description": "Say it to Paco"},
    {"command": "help", "description": "How Ostanovka works"},
]

HELP = (
    "**Остановка**\n"
    "Tito keeps the calendar. Paco keeps the notebook.\n\n"
    "**Tito**\n"
    "/today: day card\n"
    "/week: week by day\n"
    "/plan: list of lines\n"
    "Tito, ...\n"
    "/tito ...\n\n"
    "**Paco**\n"
    "Paco, запиши ...\n"
    "Paco, где ...\n"
    "/paco ...\n\n"
    "No name, and Ostanovka asks who it is for.\n"
    "Hold PTT on the r1 to talk."
)

TITO_HINT = "Say it to Tito.\n\n/tito what is on today\nTito, add milk"
PACO_HINT = "Say it to Paco.\n\n/paco запиши ...\nPaco, где ..."

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


def _addressed(text: str) -> tuple[str, str] | None:
    match = ADDRESS_RE.match(text.strip())
    if not match:
        return None
    name = match.group(1).casefold()
    who = "paco" if name in {"paco", "пако"} else "tito"
    rest = match.group(2).strip()
    if not rest:
        return None
    return who, rest


def _reply_who(message: dict) -> str:
    reply = message.get("reply_to_message") or {}
    raw = reply.get("text") or reply.get("caption") or ""
    first = raw.split("\n", 1)[0].strip()
    if first == "Tito":
        return "tito"
    if first == "Paco":
        return "paco"
    return ""


class Voice:
    def __init__(self, bot: TelegramBot, who: str) -> None:
        self.bot = bot
        self.who = who
        self.label = _VOICE_LABELS[who]

    @property
    def day_planner(self) -> Any:
        return self.bot.day_planner

    @day_planner.setter
    def day_planner(self, value: Any) -> None:
        self.bot.day_planner = value

    def send_text(self, text: str) -> None:
        self.send_message(text)

    def send_message(
        self,
        text: str,
        buttons: list[list[dict[str, str]]] | None = None,
        photo: Path | None = None,
    ) -> None:
        self.bot.send_message(f"**{self.label}**\n{text}", buttons=buttons, photo=photo)


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

    def voice(self, who: str) -> Voice:
        if who not in _VOICE_LABELS:
            raise ValueError(who)
        return Voice(self, who)

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

    def handle_update(self, update: dict, agent: Any, speech: Any, paco: Any = None) -> None:
        if update.get("callback_query"):
            self._callback(update["callback_query"], agent, paco)
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
            self._command(text, agent, paco)
            return
        addressed = _addressed(text)
        if addressed:
            who, rest = addressed
            self._to(who, rest, agent, paco)
            return
        reply_who = _reply_who(message)
        if reply_who:
            self._to(reply_who, text, agent, paco)
            return
        self._ask_who(text, agent)

    def ensure_profile(self, store: Any, now: datetime) -> None:
        key = f"tg_profile:v2:{now.date().isoformat()}"
        if store.seen(key):
            return
        self._method("setMyName", {"name": "Остановка"})
        self._method(
            "setMyDescription",
            {
                "description": (
                    "Ostanovka. The stop where Tito and Paco hang out. "
                    "Tito keeps the calendar, Paco keeps the notebook."
                )
            },
        )
        self._method(
            "setMyShortDescription",
            {"short_description": "Tito and Paco"},
        )
        self._method("setMyCommands", {"commands": COMMANDS})
        store.mark(key)

    def _command(self, text: str, agent: Any, paco: Any = None) -> None:
        parts = text.split(None, 1)
        cmd = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        name = cmd.split("@", 1)[0].lower()
        if name in {"/start", "/help"}:
            self.send_message(HELP, photo=self.photo_path)
            return
        if name == "/today":
            if agent is None:
                self.send_message("Tito is not here right now.")
                return
            self._send_today(agent)
            return
        if name == "/week":
            if agent is None:
                self.send_message("Tito is not here right now.")
                return
            self.voice("tito").send_message(self._week_text(agent))
            return
        if name == "/plan":
            self._send_plan(rest)
            return
        if name == "/tito":
            if not rest.strip():
                self.send_message(TITO_HINT)
                return
            self._agent_reply(agent, rest.strip())
            return
        if name == "/paco":
            if not rest.strip():
                self.send_message(PACO_HINT)
                return
            self._paco_reply(paco, rest.strip())
            return
        self._agent_reply(agent, text)

    def _to(self, who: str, text: str, agent: Any, paco: Any) -> None:
        if who == "paco":
            self._paco_reply(paco, text)
            return
        self._agent_reply(agent, text)

    def _ask_who(self, text: str, agent: Any) -> None:
        if self.store is None or not hasattr(self.store, "save_plan"):
            self._agent_reply(agent, text)
            return
        route_id = uuid.uuid4().hex[:8]
        self.store.save_plan(f"route:{route_id}", {"text": text}, self.now())
        self.send_message(
            "Who is this for?",
            buttons=[
                [
                    {"text": "Tito", "callback_data": f"to:tito:{route_id}"},
                    {"text": "Paco", "callback_data": f"to:paco:{route_id}"},
                ]
            ],
        )

    def _paco_reply(self, paco: Any, text: str) -> None:
        if paco is None:
            self.send_message("Paco is not here right now.")
            return
        started = time.perf_counter()
        result = paco.handle_text(text)
        ms = int((time.perf_counter() - started) * 1000)
        log.info("agent channel=telegram-paco ms=%s", ms)
        reply = str(getattr(result, "reply", "") or "")
        peek = getattr(result, "peek", None) or {}
        if peek.get("kind") == "hits":
            lines = [reply] if reply else []
            for item in peek.get("items") or []:
                lines.append(f"- {item.get('title')} ({item.get('path')})")
            reply = "\n".join(lines)
        turn_id = uuid.uuid4().hex[:8]
        self.voice("paco").send_message(reply, buttons=feedback_buttons(turn_id))

    def _send_plan(self, text: str) -> None:
        from toy_lair_assistant.day_plan import plan_buttons, parse_plan_lines, render

        raw = (text or "").strip()
        if not raw or self.day_planner is None:
            self.voice("tito").send_message(PLAN_HINT)
            return
        if not parse_plan_lines(raw):
            self.voice("tito").send_message(PLAN_HINT)
            return
        plan = self.day_planner.build_from_lines(raw, self.now())
        self.voice("tito").send_message(render(plan), buttons=plan_buttons(plan))

    def _agent_reply(self, agent: Any, text: str) -> None:
        if agent is None:
            self.send_message("Tito is not here right now.")
            return
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
            self.voice("tito").send_message(body or result.reply, buttons=buttons)
            return
        turn_id = uuid.uuid4().hex[:8]
        self.voice("tito").send_message(result.reply, buttons=feedback_buttons(turn_id))

    def _send_today(self, agent: Any) -> None:
        if self.day_planner is not None:
            from toy_lair_assistant.day_plan import plan_buttons, render

            plan = self.day_planner.build(self.now())
            self.voice("tito").send_message(render(plan), buttons=plan_buttons(plan))
            return
        self.voice("tito").send_message(self._today_text(agent))

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

    def _callback(self, query: dict, agent: Any, paco: Any = None) -> None:
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
        if data.startswith("to:"):
            self._route_choice(data, message, agent, paco)
            return
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
            self.voice("tito").send_message(render(plan), buttons=plan_buttons(plan))
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
            self.voice("tito").send_message(render(plan), buttons=plan_buttons(plan))
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

    def _route_choice(self, data: str, message: dict, agent: Any, paco: Any) -> None:
        parts = data.split(":")
        who = parts[1] if len(parts) > 1 else ""
        route_id = parts[2] if len(parts) > 2 else ""
        payload = None
        if self.store is not None and hasattr(self.store, "get_plan"):
            payload = self.store.get_plan(f"route:{route_id}")
        text = ""
        if isinstance(payload, dict):
            text = str(payload.get("text") or "").strip()
        if not text:
            self.send_message("That message is gone. Send it again.")
            return
        label = _VOICE_LABELS.get(who, who)
        self.sender(
            {
                "_method": "editMessageText",
                "chat_id": self.chat_id,
                "message_id": message.get("message_id"),
                "text": to_html(f"{text}\n→ {label}"),
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": []},
            }
        )
        self._to(who, text, agent, paco)

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
