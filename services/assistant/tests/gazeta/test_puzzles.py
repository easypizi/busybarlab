from datetime import date

from toy_lair_assistant.gazeta.puzzles import chess_daily, clues, crossword, sudoku
from toy_lair_assistant.gazeta.sources import onthisday

ISSUE = {
    "lead": {"headline": "Quake shakes Oakland tonight", "standfirst": "Residents felt it."},
    "incidents": {"stories": [{"headline": "Police arrest robbery suspects downtown", "summary": "Two men were held."}]},
    "sections": [
        {"id": "space", "stories": [{"headline": "SpaceX launches Starlink satellites", "summary": "From Vandenberg."}]},
        {"id": "ai", "stories": [{"headline": "Nvidia board reviews chips strategy", "summary": ""}, {"headline": "Google releases Gemini update", "summary": ""}, {"headline": "Ferrari unveils engine upgrade", "summary": ""}, {"headline": "Rosneft restricts gasoline sales", "summary": ""}]},
    ],
}


def test_sudoku_is_unique_and_seeded():
    a = sudoku.make(date(2026, 11, 10))
    b = sudoku.make(date(2026, 11, 10))
    assert a == b
    assert sum(1 for row in a["grid"] for n in row if n == 0) > 20
    for r in range(9):
        assert sorted(a["solution"][r]) == list(range(1, 10))
        assert all(a["grid"][r][c] in (0, a["solution"][r][c]) for c in range(9))


def test_crossword_words_cross_and_are_numbered():
    pairs = clues.blanks(ISSUE)
    cw = crossword.build(pairs, seed=3, seconds=0.5)
    assert cw and cw["words"] >= crossword.MIN_WORDS
    nums = {c["num"] for row in cw["cells"] for c in row if c and c["num"]}
    assert nums == {w["num"] for w in cw["across"] + cw["down"]}
    for w in cw["across"] + cw["down"]:
        assert len(w["answer"]) == w["length"]


def test_crossword_needs_enough_words():
    assert crossword.build([("ABC", "x")] * 3, seed=1) is None


def test_clue_validation_rejects_bad_pairs():
    text = "Quake shakes Oakland. Police arrest suspects."
    entries = [
        {"answer": "quake", "clue": "Tremor in Oakland"},
        {"answer": "QUAKE", "clue": "Duplicate"},
        {"answer": "OAKLAND", "clue": "City named Oakland"},
        {"answer": "POLICE", "clue": "Officers; they arrest"},
        {"answer": "ZEBRA", "clue": "Not in text"},
        {"answer": "AB", "clue": "short"},
        {"answer": "SUSPECTS", "clue": "They were arrested, police said"},
    ]
    out = clues.validate(entries, text)
    assert [a for a, _ in out] == ["QUAKE", "POLICE", "SUSPECTS"]
    assert ";" not in out[1][1]


def test_clues_fall_back_to_blanks_when_model_fails():
    class Boom:
        def chat_json(self, *a, **k):
            raise RuntimeError("down")

    pairs = clues.make(Boom(), "m", ISSUE)
    assert len(pairs) >= 6 and all("____" in c for _, c in pairs)


def test_chess_build_checks_legality():
    ok = {"puzzle": {"fen": "r1bqk2r/1p1n1pb1/4p1p1/1P1pP2p/pB1P1PQP/3B1N2/1P4P1/3K3R w kq - 0 1", "solution": ["g4e6", "f7e6", "d3g6"], "rating": 2100}}
    out = chess_daily.build(ok)
    assert out["solution"] == ["Qxe6+", "fxe6", "Bxg6#"] and out["mover"] == "White" and "<svg" in out["svg"]
    bad = {"puzzle": {**ok["puzzle"], "solution": ["a1a8"]}}
    try:
        chess_daily.build(bad)
    except ValueError:
        return
    raise AssertionError("illegal move accepted")


def test_onthisday_picks_spread_of_eras():
    rows = [{"year": y, "text": f"Event {y} happened."} for y in (1100, 1500, 1700, 1800, 1900, 1950, 2000)]
    out = onthisday.pick(rows)
    assert len(out) == 4 and out[0]["year"] == 1100 and out[-1]["year"] == 2000
