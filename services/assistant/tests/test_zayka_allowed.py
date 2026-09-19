from toy_lair_assistant.zayka import ZaykaIndex


def test_allowed_paths() -> None:
    index = ZaykaIndex.__new__(ZaykaIndex)
    assert index.allowed("30 Projects/hirescope.md")
    assert index.allowed("40 Areas/personal/life-plan.md")
    assert index.allowed("Home.md")
    assert not index.allowed("40 Areas/sensitive/secrets.md")
    assert not index.allowed(".obsidian/app.json")
    assert not index.allowed("Presentations/deck.html")
