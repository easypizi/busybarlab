from types import SimpleNamespace

from toy_lair_assistant.profile import profile_lines, profile_text


def test_profile_has_work_hours() -> None:
    settings = SimpleNamespace(work_hours_start=9, work_hours_end=17)
    text = profile_text(settings)
    assert "Weekdays 09:00-17:00" in text
    assert "no sport" in text
    assert profile_lines(settings)[0] in text
