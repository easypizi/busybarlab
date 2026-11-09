"""Manual run: python -m toy_lair_assistant.gazeta [--out PATH]. Builds the real issue, writes the PDF, delivers nothing."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="ivanencial-times.pdf")
    args = parser.parse_args()
    from toy_lair_assistant.factory import build_app

    job = build_app().state.gazeta
    if job is None:
        raise SystemExit("Gazeta is not configured: need OPENAI_API_KEY and TODOIST_API_TOKEN")
    job.notify = None
    job.settings.gmail_app_password = ""
    result = job.run(on_demand=True)
    Path(args.out).write_bytes(job.last_pdf or b"")
    print(result, args.out)


if __name__ == "__main__":
    main()
