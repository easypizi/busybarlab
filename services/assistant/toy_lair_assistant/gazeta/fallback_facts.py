"""Curated true trivia about the US, used when the editor cannot verify a fact."""

from __future__ import annotations

from toy_lair_assistant.gazeta.state import norm

FACTS = [
    "Alaska is the northernmost, westernmost and easternmost US state at once, because the Aleutian Islands cross the 180th meridian.",
    "Q is the only letter that does not appear in the name of any US state.",
    "Maine is the only US state whose name has just one syllable.",
    "Nebraska is the only US state with a one-chamber legislature.",
    "Oregon is the only state with a two-sided flag. The back shows a beaver.",
    "Ohio has the only non-rectangular state flag, a swallowtail pennant.",
    "Louisiana has parishes instead of counties.",
    "Colorado, Utah, Arizona and New Mexico meet at one point, so you can stand in four states at once.",
    "Kentucky, Massachusetts, Pennsylvania and Virginia are officially commonwealths, not just states.",
    "Iolani Palace in Honolulu is the only official royal residence on US soil.",
    "Hawaii is the only US state made up entirely of islands.",
    "Alaska has more coastline than all the other US states combined.",
    "Missouri and Tennessee each border eight states, more than any other state.",
]


def pick(used: list[str]) -> dict | None:
    taken = {norm(item) for item in used}
    for text in FACTS:
        if norm(text) not in taken:
            return {"text": text, "source_url": "", "source_name": "Wikipedia"}
    return None
