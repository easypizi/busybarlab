# Zayka as a data source

Zayka is the personal Obsidian vault (Zettelkasten + light PARA). Tito may **read** it to understand projects, areas, and standing notes. Tito does not write. Paco may create a fleeting note in `00 Inbox/` and append to today's daily note, then commit and push. Everything else stays read-only. `40 Areas/sensitive/` is never indexed.

## Locations

| Place | Value |
|-------|--------|
| Local vault | `~/Documents/Zayka` |
| Git remote | `git@github.com:easypizi/zayka.git` |
| Note count (2026-09-19) | ~175 markdown files |
| Rules in the vault | `.cursor/rules/obsidian-zayka.mdc` |

Heroku does not see the local disk. The assistant dyno clones the repo at boot and `git pull`s on a timer (see `toy_lair_assistant.zayka`). Paco's push needs a write-capable `ZAYKA_REPO_URL`. A read-only deploy key is enough for Tito's search. Do not put the token in git.

## Folder map

```
00 Inbox/           fleeting notes, process within 48h
10 Evergreen/       atomic permanent notes
20 Sources/         books, articles, courses
30 Projects/        active projects (HireScope, ideas/, travels, …)
40 Areas/           ongoing life/work areas
50 MOC/             maps of content
60 Daily/           daily notes
90 Templates/       templates
100 AI-Generated/   prompt-produced research
```

Hub: `Home.md`. Navigation is folders + MOCs, not a giant link dump.

## What the assistant may read

- `30 Projects/` (product context, ideas)
- `40 Areas/` **except** `40 Areas/sensitive/`
- `50 MOC/`
- `10 Evergreen/`
- `Home.md`, `30 Projects/30 Projects.md`, `40 Areas/40 Areas.md`

Tito does not index `00 Inbox/`, `20 Sources/`, `60 Daily/`, or `100 AI-Generated/`. Paco also reads `00 Inbox/` and `60 Daily/`.

## Never index or send to the model

- `40 Areas/sensitive/`
- `.obsidian/`, `.smart-env/`, `.git/`
- `Presentations/` (large HTML/binary)
- `.DS_Store`, binaries, attachment blobs

If a search hit would require opening a blocked path, skip it.

## Frontmatter

```yaml
---
id: YYYYMMDDHHMMSS
title: ""
date: YYYY-MM-DD
type: fleeting | evergreen | source | project | area | moc | daily
status: draft | review | evergreen
tags: []
related: []
source: ""
---
```

Workflow tags only: `#draft` `#review` `#evergreen` `#idea` `#to-process` `#waiting`. Topics use `[[wikilinks]]`, not topic tags.

## Language

Notes mix Russian and English. Technical terms stay English. Do not mix languages inside one sentence when writing new notes (vault rule). The assistant may answer the user in the language of the request.

## Agent tools

Tito:

- `zayka_search(query)` → titles, paths, short snippets
- `zayka_read(path)` → note body if the path is allowed

Tito does not create, update, delete, commit, or push.

Paco adds `zayka_list_inbox`, `zayka_inbox_create`, and `zayka_daily_append`. Writes are only a new `00 Inbox/YYYY-MM-DD-*.md` file or an append to `60 Daily/YYYY/MM/YYYY-MM-DD.md`. Paco does not edit or delete notes, and it does not write `60 Daily/Дневник/`.
