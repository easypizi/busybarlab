# Paco personal library design

Date: 2026-10-24. Status: approved plan, implementation in progress.

## Goal

Paco (Ostanovka Telegram bot) answers questions over a personal library built from Instagram saved posts, Telegram chats, Gmail, Chrome Reading List and the Zayka vault. A collector on the Mac fetches and enriches items, writes them into Zayka, and pushes index rows to Heroku. The R1 is out of scope.

## Decisions

- Hybrid: credentials and sessions stay on the Mac (Keychain). Heroku gets finished records only (title, url, summary, kind, topics, vault path, short snippet).
- Collector is a subpackage `toy_lair_assistant/collector/` with its own requirements file. Heroku never installs it.
- Mac opens no inbound ports. It pushes to `POST /api/library/items` and polls `GET /api/collector/jobs`, both with `COLLECTOR_TOKEN`.
- Videos: caption and author, Whisper transcript, LLM tagging. Media is deleted right after audio extraction.
- Gmail: IMAP with an app password. Starred mail, label `Paco`, mail to self. Bodies never leave the Mac, only subject, sender, summary, links.
- Search in v1 is Postgres full text (SQLite LIKE in tests and local).

## Vault writes

A separate writer (`collector/vault_layout.py`) with its own allowlist. `zayka_write.allowed_write` is unchanged.

- New items: `20 Sources/<source>/<slug>-<date>.md`, `type: source`, `status: draft`, `tags: [to-process]`.
- Collections: `50 MOC/MOC-<Kind>.md` once a kind has 3 or more items.
- Existing notes: only inside `<!-- paco:links -->` blocks.
- Never touched: `40 Areas/sensitive/`, `60 Daily/Дневник/`, `.obsidian/`, `.git/`, `Presentations/`.
- One commit per run by `Paco`, preceded by `git pull --ff-only`.

## Failure handling

Connectors are isolated. Auth problems alert Telegram once per day per source. Instagram stops on checkpoint with no retry. Backfill is batched.

## Tests

Pytest with fixtures, fake LLM, fake Whisper, temp git repo for the writer, API auth tests, Paco tool tests.
