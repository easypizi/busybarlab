import json
import subprocess
from pathlib import Path

from toy_lair_assistant.agent import AgentResult
from toy_lair_assistant.carlos import CarlosAgent
from toy_lair_assistant.factory import build_app
from toy_lair_assistant.settings import Settings
from toy_lair_assistant.store import MemoryStore

ROOT = Path(__file__).resolve().parents[3]


class ScriptedLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.seen: list[list[dict]] = []

    def complete(self, messages, tools, schemas=None):
        self.seen.append(messages)
        return AgentResult(reply=self.reply)


def _card() -> dict:
    return {
        "date": "2026-09-22",
        "sessionId": "module-strike",
        "title": "Модуль · вторник",
        "exercises": ["Блок 1. Strike"],
    }


def test_done_with_a_calm_back_keeps_items_empty() -> None:
    store = MemoryStore()
    reply = json.dumps(
        {
            "date": "1999-01-01",
            "sessionId": "other",
            "status": "done",
            "back": "ok",
            "items": [],
            "raw": "rewritten",
        }
    )
    llm = ScriptedLLM(reply)
    result = CarlosAgent(llm, store).log("Сделал, спина в порядке", _card())
    assert result.ok is True
    assert result.entry["status"] == "done"
    assert result.entry["back"] == "ok"
    assert result.entry["items"] == []
    assert result.entry["raw"] == "Сделал, спина в порядке"
    assert result.entry["date"] == "2026-09-22"
    assert result.entry["sessionId"] == "module-strike"
    assert result.line == "сделано · спина в порядке"
    assert store.last_workout_log("2026-09-22") == result.entry
    prompt = llm.seen[0][-1]["content"]
    assert "Do not invent reps" in prompt


def test_off_card_exercise_is_dropped() -> None:
    store = MemoryStore()
    reply = json.dumps(
        {
            "status": "partial",
            "back": None,
            "items": [
                {"name": "Становая", "actual": "100"},
                {"name": "Блок 1. Strike", "actual": "60 мин"},
                {"name": "Блок 1. Strike", "actual": ""},
            ],
        }
    )
    result = CarlosAgent(ScriptedLLM(reply), store).log("мешок 60 минут", _card())
    assert result.ok is True
    assert result.entry["items"] == [{"name": "Блок 1. Strike", "actual": "60 мин"}]
    assert result.entry["back"] is None


def test_broken_json_writes_nothing() -> None:
    store = MemoryStore()
    result = CarlosAgent(ScriptedLLM("not json"), store).log("сделал", _card())
    assert result.ok is False
    assert result.entry is None
    assert store.last_workout_log("2026-09-22") is None


def test_fenced_json_parses() -> None:
    reply = "```json\n" + json.dumps({"status": "skipped", "back": "stop", "items": []}) + "\n```"
    result = CarlosAgent(ScriptedLLM(reply), MemoryStore()).log("пропуск, спина стоп", _card())
    assert result.ok is True
    assert result.entry["status"] == "skipped"
    assert result.entry["back"] == "stop"


def test_correct_replaces_the_last_row_for_that_date() -> None:
    store = MemoryStore()
    agent = CarlosAgent(
        ScriptedLLM(json.dumps({"status": "done", "back": "ok", "items": []})),
        store,
    )
    agent.log("сделал", _card())
    agent.llm = ScriptedLLM(json.dumps({"status": "partial", "back": "sore", "items": []}))
    agent.log("исправь, спина ноет", _card())
    assert len(store.workout_logs) == 1
    last = store.last_workout_log("2026-09-22")
    assert last["status"] == "partial"
    assert last["back"] == "sore"
    assert last["raw"] == "исправь, спина ноет"


def test_days_file_matches_the_cycle() -> None:
    data = json.loads((ROOT / "rabbit" / "carlos" / "days.json").read_text(encoding="utf-8"))
    days = data["days"]
    assert data["dayCount"] == 168
    assert len(days) == 168
    assert days[0]["date"] == "2026-09-21"
    assert days[-1]["date"] == "2027-03-07"
    assert all(day["title"] for day in days)
    fridays = [day for day in days if day["sessionId"] == "friday-flex"]
    assert fridays
    assert all(day["choice"]["required"] for day in fridays)
    assert {day["weekday"] for day in days if day["raceSlot"]} == {"wed", "sat"}
    help_sections = json.loads((ROOT / "rabbit" / "carlos" / "help.json").read_text(encoding="utf-8"))
    assert [section["title"] for section in help_sections] == [
        "Спина",
        "Карта",
        "Boss",
        "Тесты",
        "Восстановление",
    ]


def test_card_rules_in_javascript(tmp_path: Path) -> None:
    rules = (ROOT / "rabbit" / "carlos" / "rules.js").read_text(encoding="utf-8")
    check = r"""
var R = CARLOS_RULES;
if (R.mondayOf("2026-09-23") !== "2026-09-21") throw new Error("wed monday");
if (R.mondayOf("2026-09-27") !== "2026-09-21") throw new Error("sun monday");
if (R.screenFor("2026-09-21") !== "early") throw new Error("early");
if (R.screenFor("2026-09-22") !== "card") throw new Error("open");
if (R.screenFor("2027-03-07") !== "card") throw new Error("end");
if (R.screenFor("2027-03-08") !== "late") throw new Error("late");
if (R.shiftCursor("2026-09-21", -1) !== "2026-09-21") throw new Error("back stop");
if (R.shiftCursor("2027-03-07", 1) !== "2027-03-07") throw new Error("fwd stop");
if (R.shiftCursor("2026-09-22", -1) !== "2026-09-21") throw new Error("back one");
var tue = {date:"2026-09-22", weekday:"tue", deload:false, sessionId:"module-strike", choice:null, exercises:[{name:"Блок"}]};
var sun = {date:"2026-09-27", weekday:"sun", deload:false, sessionId:"rest", choice:null, exercises:[{name:"Подвижность"}]};
var wed = {date:"2026-09-23", weekday:"wed", deload:false, sessionId:"run-intervals", choice:null, exercises:[{name:"Интервалы"}]};
var sat = {date:"2026-09-26", weekday:"sat", deload:false, sessionId:"long-day", choice:null, exercises:[{name:"Ruck"}]};
var deload = {date:"2026-10-13", weekday:"tue", deload:true, sessionId:"module-strike", choice:null, exercises:[{name:"Блок"}]};
var flex = {date:"2026-10-02", weekday:"fri", deload:false, sessionId:"friday-flex", choice:{required:true, options:[{id:"bow", name:"Лук"},{id:"ruck", name:"Соло"}]}, exercises:[]};
var satRace = {"raceWeek:2026-09-21":"sat"};
if (R.volumeNote(tue, "sat") !== R.VOLUME_TEXT) throw new Error("volume");
if (R.volumeNote(sun, "sat") !== "") throw new Error("sunday");
if (R.volumeNote(sat, "sat") !== "") throw new Error("start");
if (R.hidesExercises(sat, "sat") !== true) throw new Error("hide start");
if (R.hidesExercises(wed, "sat") !== false) throw new Error("intervals stay");
if (R.hidesExercises(wed, "wed") !== true) throw new Error("hide intervals");
if (R.volumeNote(deload, "sat") !== "") throw new Error("deload");
if (R.needsChoice(flex, {}) !== true) throw new Error("choice");
var chosen = {"friday:2026-10-02":"bow"};
if (R.needsChoice(flex, chosen) !== false) throw new Error("chosen");
if (R.exerciseNames(flex, chosen).join() !== "Лук") throw new Error("names");
var view = R.present(sat, satRace);
if (view.raceText !== R.RACE_TEXT) throw new Error("race text");
if (view.names.length !== 0) throw new Error("race names");
if (R.logLine({status:"done", back:"ok"}) !== "сделано · спина в порядке") throw new Error("line");
if (R.logLine({status:"done", back:null}) !== "сделано") throw new Error("line bare");
"""
    path = tmp_path / "rules-check.js"
    path.write_text(rules + "\n" + check, encoding="utf-8")
    subprocess.run(["osascript", "-l", "JavaScript", str(path)], check=True)


def test_factory_builds_carlos_without_todoist(monkeypatch) -> None:
    created: dict = {}

    class FakeCarlos:
        def __init__(self, llm, store=None) -> None:
            created["llm"] = llm
            created["store"] = store

    monkeypatch.setattr("toy_lair_assistant.factory.CarlosAgent", FakeCarlos)
    build_app(
        Settings(
            assistant_api_token="secret",
            openai_api_key="sk-test",
            tick_interval_seconds=0,
            zayka_dir="",
            zayka_sync_enabled=False,
            database_url="",
            todoist_api_token="",
            google_refresh_token="",
            telegram_bot_token="",
        )
    )
    assert created["llm"] is not None
    assert created["store"] is not None
