"""One newspaper run: collect, edit, write, draw, lay out, render, deliver."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any

from . import delivery, fallback_facts, illustrator, writer
from .config import CITY, SECTION_TITLES
from .desk import Desk
from .editor import Editor, EditorError
from .puzzles import chess_daily, daily as puzzles_daily
from .layout import render as render_mod
from .layout import view as view_mod
from .openai_client import OpenAIClient
from .sources import f1 as f1_src
from .sources import feeds, http as http_mod
from .sources import launches as launches_src
from .sources import occasions, onthisday as onthisday_src, threats as threats_src, weather as weather_src
from .state import GazetaState

log = logging.getLogger(__name__)

DEFAULT_DAY = {"idea": None, "poem": ["The fog rolls in at seven,", "the printer hums along,", "the writers are on vacation,", "so here is half a song."]}
PRINT_CALLBACK = "gazeta:print"
EMPTY_ISSUE = {"lead": None, "teasers": [], "sections": [], "incidents": {"stories": []}}


class GazetaJob:
    def __init__(
        self,
        *,
        settings: Any,
        clock: Any,
        store: Any,
        todoist: Any,
        calendar: Any,
        notify: Any,
        client: OpenAIClient | None = None,
        send_email: Callable[..., None] = delivery.send_pdf,
        render_pdf: Callable[..., tuple[bytes, dict]] = render_mod.render,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.store = store
        self.todoist = todoist
        self.calendar = calendar
        self.notify = notify
        self.client = client or OpenAIClient(settings.openai_api_key)
        self.send_email = send_email
        self.render_pdf = render_pdf
        self._lock = threading.Lock()
        self._running = False
        self.last_pdf: bytes | None = None

    # ---- scheduling ----

    def start(self, on_demand: bool = False) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
        threading.Thread(target=self._guarded, args=(on_demand,), daemon=True, name="gazeta").start()
        return True

    def _guarded(self, on_demand: bool) -> None:
        try:
            self.run(on_demand)
        except Exception as exc:
            log.exception("gazeta failed")
            self._say(f"The paper did not make it to press: {str(exc)[:300]}")
        finally:
            with self._lock:
                self._running = False

    def _say(self, text: str) -> None:
        if self.notify is not None:
            try:
                self.notify.send_message(text)
            except Exception:
                log.exception("gazeta notice failed")

    # ---- the run ----

    def run(self, on_demand: bool = False) -> dict:
        now = self.clock.now()
        today = now.date()
        http = http_mod.client()
        zone = now.tzinfo
        tz = self.settings.timezone
        jobs = {
            "weather": lambda: weather_src.fetch(http, today.isoformat(), tz),
            "threats": lambda: threats_src.fetch(http, now),
            "launches": lambda: launches_src.fetch(http, now),
            "f1": lambda: f1_src.fetch(http, zone),
            "pool": lambda: feeds.fetch_all(http, now),
            "tasks": self._tasks,
            "events": self._events,
            "chess": lambda: chess_daily.fetch(http),
            "onthisday": lambda: onthisday_src.fetch(http, today),
        }
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {name: pool.submit(fn) for name, fn in jobs.items()}
        data: dict[str, Any] = {}
        for name, future in futures.items():
            try:
                data[name] = future.result()
            except Exception as exc:
                log.warning("gazeta source %s failed: %s", name, exc)
                data[name] = None
        tasks = data["tasks"] or []
        threats = data["threats"] or {"summary": "Threat data unavailable this morning.", "lines": [], "alert_active": False}
        countdown = occasions.nearest(today, tasks).get("text") or None
        state = GazetaState(self.store, self.clock.now)
        memory = state.load()
        issue, fact = self._edit(now, data, threats, memory)
        with ThreadPoolExecutor(max_workers=4) as pool:
            f_day = pool.submit(self._write, now, data, countdown, threats, issue)
            f_front = pool.submit(self._illustrate, issue)
            f_art = pool.submit(self._section_art, issue)
            f_puzzles = pool.submit(self._puzzles, now, issue, data, state, memory)
        day = f_day.result()
        image = f_front.result()
        art_src = f_art.result()
        puzzles, answers = f_puzzles.result()
        if art_src:
            issue["sections"][0]["art"] = art_src
        view = view_mod.build_view(
            now=now,
            issue_no=max(1, (today - date.fromisoformat(self.settings.gazeta_start_date)).days + 1),
            city=CITY,
            weather=data["weather"],
            countdown=countdown,
            threats=threats,
            issue=issue,
            fact=fact,
            day=day,
            launches=data["launches"] or [],
            f1=data["f1"],
            image_src=image,
            puzzles=puzzles,
        )
        pdf, info = self.render_pdf(view, self.settings.gazeta_max_pages)
        filename = f"Ivanity-Fair-{today.isoformat()}.pdf"
        self._deliver(now, pdf, filename, info, issue)
        self.last_pdf = pdf
        if not on_demand and self.store is not None:
            self.store.mark(f"gazeta:done:{today.isoformat()}")
        graphic = (issue.get("lead") or {}).get("graphic", {}).get("kind")
        state.record(fact["text"] if fact else None, graphic if graphic in ("infographic", "illustration", "none") else None, today.isoformat(), answers)
        return {"pages": info["pages"], "trims": info["trims"], "filename": filename}

    # ---- inputs ----

    def _tasks(self) -> list:
        return list(self.todoist.open_tasks()) if self.todoist is not None else []

    def _events(self) -> list[dict]:
        if self.calendar is None:
            return []
        now = self.clock.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        events = self.calendar.events_in_range(start, start + timedelta(days=1))
        return [{"title": e.title, "start": e.start} for e in events if not getattr(e, "todoist_id", None)]

    # ---- agents ----

    def _edit(self, now: datetime, data: dict, threats: dict, memory: dict) -> tuple[dict, dict | None]:
        used = list(memory.get("facts", []))
        context = {
            "today": now.isoformat(),
            "threats": threats,
            "recent_graphics": [g.get("kind") for g in memory.get("graphics", [])][-3:],
            "launches": data["launches"] or [],
            "f1": data["f1"] or {},
        }
        pool = data["pool"] or {}
        fact = None
        issue = dict(EMPTY_ISSUE)
        model = self.settings.gazeta_model_name()
        if pool:
            editor = Editor(self.client, model, http_mod.client(), now)
            for attempt in range(2):
                try:
                    result = editor.run(context, pool, used)
                    issue, fact = dict(result.issue), result.fact
                    log.info("gazeta editor: %s tool calls, dropped %s", result.tool_calls, [(d["reason"], d["headline"][:50]) for d in result.dropped])
                    break
                except EditorError as exc:
                    log.warning("editor attempt %s failed: %s", attempt + 1, exc)
            issue["sections"] = self._desk(model, now, pool, issue)
            issue["teasers"] = self._teasers(issue["sections"])
        if fact is None:
            fact = fallback_facts.pick(used)
        return issue, fact

    def _desk(self, model: str, now: datetime, pool: dict, issue: dict) -> list[dict]:
        taken = [s for s in [issue.get("lead")] if s] + list(issue.get("incidents", {}).get("stories", []))
        urls = {s["url"] for s in taken}
        titles = [s["headline"] for s in taken]
        try:
            return Desk(self.client, model, http_mod.client(), now).run(pool, urls, titles)
        except Exception as exc:
            log.warning("desk failed: %s", exc)
            return []

    @staticmethod
    def _teasers(sections: list[dict]) -> list[dict]:
        return [{"headline": sec["stories"][0]["headline"], "section": sec["id"]} for sec in sections[:3]]

    def _write(self, now: datetime, data: dict, countdown: str | None, threats: dict, issue: dict) -> dict:
        context = {
            "date": now.strftime("%A, %B %-d, %Y"),
            "weather": (data["weather"] or {}).get("summary"),
            "calendar_today": data["events"] or [],
            "countdown": countdown,
            "threat_summary": threats.get("summary"),
            "lead_headline": (issue.get("lead") or {}).get("headline"),
        }
        try:
            return writer.write(self.client, self.settings.gazeta_model_name(), context)
        except Exception as exc:
            log.warning("writer failed: %s", exc)
            return DEFAULT_DAY

    def _illustrate(self, issue: dict) -> str | None:
        """The front page always gets a picture: the editor's scene, or one built from the lead."""
        lead = issue.get("lead")
        if not lead:
            return None
        graphic = lead.get("graphic") or {}
        if graphic.get("kind") == "infographic":
            return None
        scene = (graphic.get("prompt") or "").strip()
        if not scene:
            scene = f"{lead['headline']}. {lead.get('standfirst', '')} Show the place or an object from the story, no people in distress."
            lead["graphic"] = {"kind": "illustration", "prompt": scene, "caption": graphic.get("caption", "")}
        return self._engrave(scene)

    def _section_art(self, issue: dict) -> str | None:
        sections = issue.get("sections") or []
        if not sections or not sections[0].get("stories"):
            return None
        story = sections[0]["stories"][0]
        return self._engrave(f"{story['headline']}. {story.get('summary', '')}")

    def _engrave(self, scene: str) -> str | None:
        for _ in range(2):
            src = illustrator.make(self.client, self.settings.gazeta_image_model, scene)
            if src:
                return src
        return None

    def _puzzles(self, now: datetime, issue: dict, data: dict, state: GazetaState, memory: dict) -> tuple[dict | None, dict | None]:
        try:
            today = now.date()
            yesterday = state.yesterday(today.isoformat(), memory)
            return puzzles_daily.assemble(
                self.client, self.settings.gazeta_model_name(), issue, today, data.get("chess"), data.get("onthisday") or [], yesterday
            )
        except Exception as exc:
            log.warning("puzzles failed: %s", exc)
            return None, None

    # ---- delivery ----

    def can_print(self) -> bool:
        s = self.settings
        return bool(s.gazeta_printer_email and s.gmail_user and s.gmail_app_password)

    def print_pdf(self, pdf: bytes, filename: str) -> None:
        if not self.can_print():
            raise RuntimeError("printer email or Gmail credentials are not set")
        s = self.settings
        self.send_email(s.gmail_user, s.gmail_app_password, s.gazeta_printer_email, filename, "", pdf, filename)

    def _links(self, issue: dict) -> list[str]:
        rows: list[tuple[str, dict]] = []
        if issue.get("lead"):
            rows.append(("Lead", issue["lead"]))
        for story in issue.get("incidents", {}).get("stories", []):
            rows.append(("Incidents", story))
        for section in issue.get("sections", []):
            for story in section.get("stories", []):
                rows.append((SECTION_TITLES.get(section["id"], section["id"]), story))
        return [f"{tag}: {s['headline']} ({s.get('source', '')}) {s['url']}" for tag, s in rows if s.get("url")]

    def _deliver(self, now: datetime, pdf: bytes, filename: str, info: dict, issue: dict) -> None:
        links = self._links(issue)
        caption = f"Ivanity Fair, {now.strftime('%B %-d')}. {info['pages']} pages."
        errors: list[str] = []
        buttons = [[{"text": "🖨 Print", "callback_data": PRINT_CALLBACK}]] if self.can_print() else None
        if self.notify is not None:
            try:
                self.notify.voice("tito").send_document(pdf, filename, caption, buttons=buttons)
                if links:
                    self.notify.voice("tito").send_message("Sources\n" + "\n".join(links)[:3800], preview=False)
            except Exception as exc:
                log.exception("telegram delivery failed")
                errors.append(f"Telegram: {exc}")
        if self.settings.gmail_user and self.settings.gmail_app_password:
            try:
                self.send_email(
                    self.settings.gmail_user,
                    self.settings.gmail_app_password,
                    self.settings.gazeta_email_to or self.settings.gmail_user,
                    f"Ivanity Fair, {now.strftime('%A, %B %-d')}",
                    caption + "\n\nSources\n" + "\n".join(links),
                    pdf,
                    filename,
                )
            except Exception as exc:
                log.exception("email delivery failed")
                errors.append(f"Email: {exc}")
        if errors:
            self._say("Paper printed, delivery problem: " + "; ".join(errors))
