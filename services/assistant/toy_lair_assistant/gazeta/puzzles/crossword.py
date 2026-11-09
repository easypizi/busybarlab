"""Crossword builder.

The word placement core (`_Placer`) is adapted from genxword by Bryan Helmig and
David Whitlock (https://github.com/riverrun/genxword), GNU GPL v3 or later.
Changes: no cairo/Pango, seeded random generator, a bounding box crop,
and numbering done in plain Python.
Copyright (C) 2010-2011 Bryan Helmig, 2011-2020 David Whitlock.
This file is free software under the GNU General Public License version 3 or later:
https://www.gnu.org/licenses/gpl-3.0.html
"""

from __future__ import annotations

import random
import time
from collections import defaultdict
from operator import itemgetter

SIZE = 13
MIN_WORDS = 6
EMPTY = " "


class _Placer:
    def __init__(self, rows: int, cols: int, words: list[list], rng: random.Random) -> None:
        self.rows, self.cols, self.rng = rows, cols, rng
        self.available_words = words
        self.let_coords: dict[str, list] = defaultdict(list)
        self.grid: list[list[str]] = []
        self.current: list[list] = []
        self.best: list[list] = []
        self.best_grid: list[list[str]] = []

    def _prep(self) -> None:
        self.current = []
        self.let_coords.clear()
        self.grid = [[EMPTY] * self.cols for _ in range(self.rows)]
        self._first_word([self.available_words[0][0], self.available_words[0][1]])

    def compute(self, time_permitted: float = 1.5) -> None:
        start = time.time()
        total = len(self.available_words)
        while time.time() - start < time_permitted:
            self._prep()
            for _ in range(2):
                for word in self.available_words:
                    if not any(w[0] == word[0] for w in self.current):
                        self._add_word([word[0], word[1]])
            if len(self.current) > len(self.best):
                self.best = [list(w) for w in self.current]
                self.best_grid = [list(r) for r in self.grid]
            if len(self.best) == total:
                break
            self.rng.shuffle(self.available_words)

    def _occupied(self, row: int, col: int) -> bool:
        return self.grid[row][col] != EMPTY

    def _coords(self, word: list):
        length = len(word[0])
        options = []
        pairs = [(l, v) for l, letter in enumerate(word[0]) for k, v in self.let_coords.items() if k == letter]
        for letc, items in pairs:
            for rowc, colc, vertc in items:
                if vertc:
                    if colc - letc >= 0 and (colc - letc) + length <= self.cols:
                        score = self._score_h(word, rowc, colc - letc, length)
                        if score:
                            options.append([rowc, colc - letc, 0, score])
                else:
                    if rowc - letc >= 0 and (rowc - letc) + length <= self.rows:
                        score = self._score_v(word, rowc - letc, colc, length)
                        if score:
                            options.append([rowc - letc, colc, 1, score])
        return max(options, key=itemgetter(3)) if options else None

    def _first_word(self, word: list) -> None:
        vertical = self.rng.randrange(0, 2)
        if vertical:
            row = self.rng.randrange(0, self.rows - len(word[0]) + 1)
            col = self.rng.randrange(0, self.cols)
        else:
            row = self.rng.randrange(0, self.rows)
            col = self.rng.randrange(0, self.cols - len(word[0]) + 1)
        self._set(word, row, col, vertical)

    def _add_word(self, word: list) -> None:
        found = self._coords(word)
        if found:
            self._set(word, found[0], found[1], found[2])

    def _score_h(self, word, row, col, length, score=1):
        if col and self._occupied(row, col - 1) or col + length != self.cols and self._occupied(row, col + length):
            return 0
        for letter in word[0]:
            cell = self.grid[row][col]
            if cell == EMPTY:
                if row + 1 != self.rows and self._occupied(row + 1, col) or row and self._occupied(row - 1, col):
                    return 0
            elif cell == letter:
                score += 1
            else:
                return 0
            col += 1
        return score

    def _score_v(self, word, row, col, length, score=1):
        if row and self._occupied(row - 1, col) or row + length != self.rows and self._occupied(row + length, col):
            return 0
        for letter in word[0]:
            cell = self.grid[row][col]
            if cell == EMPTY:
                if col + 1 != self.cols and self._occupied(row, col + 1) or col and self._occupied(row, col - 1):
                    return 0
            elif cell == letter:
                score += 1
            else:
                return 0
            row += 1
        return score

    def _set(self, word: list, row: int, col: int, vertical: int) -> None:
        placed = [word[0], word[1], row, col, vertical]
        self.current.append(placed)
        horizontal = not vertical
        for letter in word[0]:
            self.grid[row][col] = letter
            if (row, col, horizontal) not in self.let_coords[letter]:
                self.let_coords[letter].append((row, col, vertical))
            else:
                self.let_coords[letter].remove((row, col, horizontal))
            if vertical:
                row += 1
            else:
                col += 1


def build(pairs: list[tuple[str, str]], seed: int, size: int = SIZE, seconds: float = 1.5) -> dict | None:
    """pairs: (ANSWER, clue). Returns the crossword view or None when fewer than MIN_WORDS words fit."""
    if len(pairs) < MIN_WORDS:
        return None
    rng = random.Random(seed)
    words = [[a, c] for a, c in pairs]
    words.sort(key=lambda w: -len(w[0]))
    placer = _Placer(size, size, words, rng)
    placer.compute(seconds)
    if len(placer.best) < MIN_WORDS:
        return None
    placed = placer.best
    r0 = min(w[2] for w in placed)
    c0 = min(w[3] for w in placed)
    r1 = max(w[2] + (len(w[0]) if w[4] else 1) for w in placed)
    c1 = max(w[3] + (1 if w[4] else len(w[0])) for w in placed)
    rows, cols = r1 - r0, c1 - c0
    grid = [[placer.best_grid[r][c] for c in range(c0, c1)] for r in range(r0, r1)]
    starts: dict[tuple[int, int], dict] = {}
    for answer, clue, row, col, vertical in placed:
        key = (row - r0, col - c0)
        starts.setdefault(key, {})["down" if vertical else "across"] = (answer, clue)
    numbers: dict[tuple[int, int], int] = {}
    across: list[dict] = []
    down: list[dict] = []
    for n, key in enumerate(sorted(starts), start=1):
        numbers[key] = n
        if "across" in starts[key]:
            a, c = starts[key]["across"]
            across.append({"num": n, "clue": c, "length": len(a), "answer": a})
        if "down" in starts[key]:
            a, c = starts[key]["down"]
            down.append({"num": n, "clue": c, "length": len(a), "answer": a})
    cells = [
        [{"letter": grid[r][c], "num": numbers.get((r, c))} if grid[r][c] != EMPTY else None for c in range(cols)]
        for r in range(rows)
    ]
    return {"rows": rows, "cols": cols, "cells": cells, "across": across, "down": down, "words": len(placed)}
