"""Skill evaluation harness: baseline prompt vs full editor skill on fixed scenarios.

Usage: python -m toy_lair_assistant.gazeta.eval record
       python -m toy_lair_assistant.gazeta.eval run --reps 5 --model gpt-4.1-mini --budget 25
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from toy_lair_assistant.gazeta.editor import Editor, SKILL_PATH
from toy_lair_assistant.gazeta.openai_client import OpenAIClient
from toy_lair_assistant.gazeta.sources import feeds, http as http_mod
from toy_lair_assistant.settings import Settings

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "gazeta" / "fixtures"
BASELINE = (
    "You are the editor of a short daily newspaper for one reader, Ivan, a software engineer in Burlingame, CA. "
    "Pick the best stories from the candidates, open the articles, write the issue and call submit_issue. "
    "Also find one funny, true fact about the USA and call submit_fact."
)
BANNED = ["delve", "game-changer", "revolutionary", "groundbreaking", "landscape", "unlock", "seamless", "robust", "it's worth noting", "fast-paced"]
QUIET = {"summary": "Quakes in 24h: none of note · AQI 38 · No active alerts", "lines": ["No active alerts, no strong quakes.", "Air quality: US AQI 38"], "alert_active": False}
LOUD = {
    "summary": "Quakes in 24h: 4, max M4.6 at 61 km · AQI 61 · 1 alert: Red Flag Warning · 1 active fire nearby",
    "lines": [
        "NWS: Red Flag Warning in effect until 6 PM PST Tuesday for the Santa Cruz Mountains",
        "M4.6 quake, 7 km NE of Pinnacles, CA (61 km away)",
        "M2.9 quake, 3 km W of Berkeley, CA (23 km away)",
        "Wildfire: Skyline Fire (San Mateo), 49 ha, 10% contained",
        "Air quality: US AQI 61",
    ],
    "alert_active": True,
}
SCENARIOS = {
    "quiet": {"threats": QUIET, "recent_graphics": ["infographic", "none"]},
    "loud": {"threats": LOUD, "recent_graphics": ["illustration", "infographic"]},
    "repeat_form": {"threats": QUIET, "recent_graphics": ["illustration", "illustration"]},
}


def record() -> None:
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    pool = feeds.fetch_all(http_mod.client(), now)
    path = FIXTURES / f"pool-{now.date().isoformat()}.json"
    path.write_text(json.dumps({"now": now.isoformat(), "pool": pool}, ensure_ascii=False, indent=1))
    print(path, {k: len(v) for k, v in pool.items()})


def score(editor: Editor, result, error: str | None) -> dict:
    raw = json.dumps(editor.raw_issue, ensure_ascii=False)
    texts = " ".join(re.findall(r'"(?:headline|summary|standfirst|why|body)": ?"([^"]*)"', raw) + re.findall(r'"([^"]{20,})"', raw))
    out = {
        "error": error,
        "tokens": editor.usage,
        "calls": editor.calls,
        "dash_semicolon": raw.count("—") + raw.count(";") + raw.count(" – "),
        "banned": sum(texts.lower().count(word) for word in BANNED),
        "dropped": dict(Counter(d["reason"] for d in editor.dropped)),
        "fact": bool(editor.fact),
        "graphic": None,
        "lead": None,
        "sections": 0,
        "incidents": 0,
        "stories": 0,
    }
    if result is not None:
        issue = result.issue
        out["graphic"] = (issue["lead"] or {}).get("graphic", {}).get("kind") if issue["lead"] else None
        out["lead"] = (issue["lead"] or {}).get("headline")
        out["sections"] = len(issue["sections"])
        out["incidents"] = len(issue["incidents"]["stories"])
        out["stories"] = sum(len(s["stories"]) for s in issue["sections"])
    return out


def one(variant: str, scenario: str, rep: int, pool_file: Path, model: str, budget: int, key: str) -> dict:
    data = json.loads(pool_file.read_text())
    now = datetime.fromisoformat(data["now"])
    http = http_mod.client()
    editor = Editor(OpenAIClient(key), model, http, now, budget=budget, skill=BASELINE if variant == "baseline" else SKILL_PATH.read_text())
    spec = SCENARIOS[scenario]
    context = {"today": now.isoformat(), "threats": spec["threats"], "recent_graphics": spec["recent_graphics"], "launches": [], "f1": {}}
    result, error = None, None
    try:
        result = editor.run(context, data["pool"], [])
    except Exception as exc:
        error = str(exc)[:200]
    row = score(editor, result, error)
    row.update(variant=variant, scenario=scenario, rep=rep)
    dump = FIXTURES.parent / "eval_runs"
    dump.mkdir(exist_ok=True)
    (dump / f"{variant}-{scenario}-{rep}.json").write_text(json.dumps({"row": row, "raw": editor.raw_issue, "fact": editor.fact}, ensure_ascii=False, indent=1))
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["record", "run"])
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--budget", type=int, default=25)
    parser.add_argument("--variants", default="baseline,skill")
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    args = parser.parse_args()
    if args.cmd == "record":
        record()
        return 0
    key = Settings().openai_api_key
    pool_file = sorted(FIXTURES.glob("pool-*.json"))[-1]
    jobs = [(v, s, r) for v in args.variants.split(",") for s in args.scenarios.split(",") for r in range(args.reps)]
    with ThreadPoolExecutor(3) as pool:
        rows = list(pool.map(lambda j: one(*j, pool_file, args.model, args.budget, key), jobs))
    print(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
