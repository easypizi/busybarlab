# IVANencial Times design

Personal daily newspaper, English, black and white, A4 PDF. Module `toy_lair_assistant/gazeta/` inside the Tito service.

## Goal

At 07:00 PT and on `/gazeta`, build a multi-page PDF and send it to Gmail and to the Ostanovka Telegram chat. The 08:00 text briefing stays.

## Reader

Ivan, Burlingame CA 94010 (37.5841, -122.3661), `America/Los_Angeles`. Topics: applied AI, AI dev tools, space, F1, gadgets, Bay Area, Russia, tech jobs, D&D, drum and bass. Bay Area threats and crime. One dumb but true US fact per issue. Countdown to the nearest holiday (RU or US) or friend birthday from Todoist project `Friends & Family`.

## Pages

1. Front page: masthead, weather, countdown, lead story with graphic (editor picks infographic, illustration or none), "In this issue", threat line.
2. Your Day: tear-off calendar sheet from the morning-paper skill (tasks, idea, US fact, roast comic, poem).
3. Sections: Bay Area Incidents first (always), then other sections, launches table, F1 block. Hard cap `GAZETA_MAX_PAGES`.

## Components

- `sources/`: weather, threats, launches, f1, occasions, mail, feeds. Each optional, a failure drops the block and adds a note to the Telegram message.
- `editor.py`: tool loop on the OpenAI Responses API with `list_candidates`, `read_article`, `web_search`, `submit_fact`, `submit_issue`. Code guards: URL must appear in tool results, 36 hour window, dedupe, fact not repeated, infographic points need sources.
- `writer.py`: Your Day texts via JSON schema, comic limits enforced with retries.
- `illustrator.py`, `charts.py`: engraving via OpenAI image API, SVG charts in code.
- `layout/` Jinja templates, `render.py` Playwright PDF with page cap.
- `delivery.py`: Gmail SMTP and Telegram `sendDocument`.
- `job.py`: single-flight build in a background thread, issue number from `GAZETA_START_DATE`.

## Decisions

- Mail uses a Gmail app password (IMAP read, SMTP send).
- Models run through the existing OpenAI key.
- Skill text for the editor lives in `gazeta/skills/editor.md` and is verified against fixtures with a no-skill control.
- Nothing is committed or deployed without an explicit command.
