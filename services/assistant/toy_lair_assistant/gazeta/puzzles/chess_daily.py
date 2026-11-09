"""Lichess daily puzzle: board SVG in black and white plus the solution in SAN."""

from __future__ import annotations

import logging
from typing import Any

import chess
import chess.svg

log = logging.getLogger(__name__)
URL = "https://lichess.org/api/puzzle/daily"
COLORS = {
    "square light": "#ffffff",
    "square dark": "#bdbdbd",
    "margin": "#ffffff",
    "coord": "#000000",
}


def build(data: dict) -> dict:
    """Pure part: validates the position and moves, returns the view fields."""
    puzzle = data["puzzle"]
    board = chess.Board(puzzle["fen"])
    moves = list(puzzle["solution"])
    if not moves:
        raise ValueError("empty solution")
    mover = "White" if board.turn == chess.WHITE else "Black"
    probe = board.copy()
    san: list[str] = []
    for uci in moves:
        move = chess.Move.from_uci(uci)
        if move not in probe.legal_moves:
            raise ValueError(f"illegal move {uci}")
        san.append(probe.san(move))
        probe.push(move)
    svg = chess.svg.board(board, colors=COLORS, size=300, orientation=board.turn, coordinates=True)
    return {
        "svg": svg,
        "mover": mover,
        "moves": len(moves),
        "rating": puzzle.get("rating"),
        "solution": san,
    }


def fetch(http: Any) -> dict | None:
    try:
        response = http.get(URL)
        response.raise_for_status()
        return build(response.json())
    except Exception as exc:
        log.warning("chess puzzle skipped: %s", exc)
        return None
