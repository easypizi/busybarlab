from typing import Any


def profile_lines(settings: Any | None = None) -> list[str]:
    start = int(getattr(settings, "work_hours_start", 9) or 9) if settings else 9
    end = int(getattr(settings, "work_hours_end", 17) or 17) if settings else 17
    return [
        (
            f"Weekdays {start:02d}:00-{end:02d}:00 you are at work: "
            "only quick desk-friendly things, no sport or errands."
        )
    ]


def profile_text(settings: Any | None = None) -> str:
    return "\n".join(profile_lines(settings))
