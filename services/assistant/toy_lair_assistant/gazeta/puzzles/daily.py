"""Puts the last page together: every part is optional and a failing part is simply left out."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from . import clues, crossword, sudoku

log = logging.getLogger(__name__)


def _crossword(client: Any, model: str, issue: dict, day: date) -> dict | None:
    try:
        pairs = clues.make(client, model, issue)
        return crossword.build(pairs, seed=day.toordinal())
    except Exception as exc:
        log.warning("crossword skipped: %s", exc)
        return None


def _sudoku(day: date) -> dict | None:
    try:
        return sudoku.make(day)
    except Exception as exc:
        log.warning("sudoku skipped: %s", exc)
        return None


def assemble(client: Any, model: str, issue: dict, day: date, chess: dict | None, onthisday: list[dict], yesterday: dict | None) -> tuple[dict | None, dict | None]:
    """Returns (view, answers to store). View is None when there is nothing to print."""
    cw = _crossword(client, model, issue, day)
    sk = _sudoku(day)
    view = {"crossword": cw, "sudoku": sk, "chess": chess, "onthisday": list(onthisday), "yesterday": yesterday}
    if not (cw or sk or chess or onthisday):
        return None, None
    answers: dict[str, Any] = {}
    if cw:
        answers["crossword"] = {
            "across": [[w["num"], w["answer"]] for w in cw["across"]],
            "down": [[w["num"], w["answer"]] for w in cw["down"]],
        }
    if sk:
        answers["sudoku"] = sk["solution"]
    if chess:
        answers["chess"] = chess["solution"]
    return view, answers
