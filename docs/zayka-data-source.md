# Zayka as a data source

Zayka is the personal Obsidian vault (Zettelkasten + light PARA). Agents in this repo may **read** it to understand projects, areas, and standing notes. They must not write to it in v1. Capture goes to Todoist Inbox.

## Locations

| Place | Value |
|-------|--------|
| Local vault | `~/Documents/Zayka` |
| Git remote | `git@github.com:easypizi/zayka.git` |
| Note count (2026-09-19) | ~175 markdown files |
| Rules in the vault | `.cursor/rules/obsidian-zayka.mdc` |

Heroku does not see the local disk. The assistant dyno clones the repo with a **read-only deploy key** at boot and `git pull`s on a timer (see `toy_lair_assistant.zayka`).

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

Useful later, not in v1 index: `00 Inbox/`, `20 Sources/`, `60 Daily/`, `100 AI-Generated/`.

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

## Agent tools (v1)

- `zayka_search(query)` → titles, paths, short snippets
- `zayka_read(path)` → note body if the path is allowed

No create/update/delete. No commit/push to `easypizi/zayka`.
