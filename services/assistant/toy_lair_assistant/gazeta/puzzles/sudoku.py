"""Sudoku with a unique solution, seeded by the date so a rerun gives the same grid."""

from __future__ import annotations

from datetime import date

from sudoku import Sudoku

DIFFICULTY = 0.55
ATTEMPTS = 10


def make(day: date) -> dict | None:
    base = day.toordinal()
    for attempt in range(ATTEMPTS):
        puzzle = Sudoku(3, seed=base * 100 + attempt).difficulty(DIFFICULTY)
        if puzzle.has_multiple_solutions():
            continue
        solved = puzzle.solve()
        if not solved.validate():
            continue
        grid = [[c or 0 for c in row] for row in puzzle.board]
        solution = [list(row) for row in solved.board]
        return {"grid": grid, "solution": solution}
    return None
