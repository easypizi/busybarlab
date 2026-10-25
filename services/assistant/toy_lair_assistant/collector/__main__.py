from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from toy_lair_assistant.collector.config import CollectorConfig, load_config
from toy_lair_assistant.collector.connectors.bot_inbox import BotInbox
from toy_lair_assistant.collector.enrich import Classifier, Enricher
from toy_lair_assistant.collector.ingest_client import IngestClient
from toy_lair_assistant.collector.keychain import get_secret, set_secret
from toy_lair_assistant.collector.pipeline import Pipeline
from toy_lair_assistant.collector.runner import Runner
from toy_lair_assistant.collector.state import CollectorState
from toy_lair_assistant.collector.vault_layout import VaultWriter, git_runner


def build_connectors(cfg: CollectorConfig, bot: BotInbox) -> dict:
    log = logging.getLogger("collector")
    out: dict = {"bot": bot}
    if cfg.vault_path.exists():
        from toy_lair_assistant.collector.connectors.zayka_notes import ZaykaNotes

        out["zayka"] = ZaykaNotes(cfg.vault_path)
    from toy_lair_assistant.collector.connectors.chrome_reading_list import ChromeReadingList

    out["chrome"] = ChromeReadingList(cfg.chrome_profile)
    password = get_secret("gmail_app_password")
    if cfg.gmail_user and password:
        from toy_lair_assistant.collector.connectors.gmail_imap import GmailImap

        out["gmail"] = GmailImap(cfg.gmail_user, password, cfg.gmail_query)
    else:
        log.info("gmail skipped: no user or app password")
    api_id = get_secret("telegram_api_id")
    api_hash = get_secret("telegram_api_hash")
    session = get_secret("telegram_session")
    if api_id and api_hash and session and cfg.telegram_allowlist:
        from toy_lair_assistant.collector.connectors.telegram_user import TelegramUser

        out["telegram"] = TelegramUser(int(api_id), api_hash, session, cfg.telegram_allowlist)
    else:
        log.info("telegram skipped: missing credentials or allowlist")
    ig = get_secret("instagram_session")
    if cfg.instagram_user and ig:
        from toy_lair_assistant.collector.connectors.instagram import InstagramSaved

        out["instagram"] = InstagramSaved(cfg.instagram_user, ig)
    else:
        log.info("instagram skipped: missing user or session")
    return out


def build_runner(cfg: CollectorConfig) -> Runner:
    from toy_lair_assistant.llm import OpenAILLM
    from toy_lair_assistant.speech import OpenAISpeech

    key = get_secret("openai_api_key")
    if not key:
        raise SystemExit("OpenAI key missing. Run: python -m toy_lair_assistant.collector auth openai_api_key")
    token = get_secret("collector_token")
    if not token:
        raise SystemExit("Collector token missing. Run: python -m toy_lair_assistant.collector auth collector_token")
    zone = ZoneInfo(cfg.timezone)
    state = CollectorState(cfg.state_path)
    speech = OpenAISpeech(key, stt_model=cfg.openai_stt_model)
    llm = OpenAILLM(key, cfg.openai_model)
    ingest = IngestClient(cfg.heroku_url, token)
    vault = VaultWriter(cfg.vault_path, zone, state, git_runner)
    pipeline = Pipeline(state, Enricher(speech.transcribe), Classifier(llm), vault, ingest, cfg.per_run_limit)
    bot = BotInbox()
    connectors = build_connectors(cfg, bot)
    return Runner(cfg, pipeline, connectors, bot, ingest, state, lambda: datetime.now(zone))


def auth(name: str) -> None:
    if name == "instagram":
        import instaloader

        user = input("Instagram username: ").strip()
        loader = instaloader.Instaloader()
        loader.login(user, getpass.getpass("Instagram password: "))
        set_secret("instagram_session", json.dumps(loader.save_session()))
        print("Saved instagram_session. Put instagram_user in collector.json.")
        return
    if name == "telegram":
        from telethon.sessions import StringSession
        from telethon.sync import TelegramClient

        api_id = input("Telegram api_id (my.telegram.org): ").strip()
        api_hash = getpass.getpass("Telegram api_hash: ").strip()
        with TelegramClient(StringSession(), int(api_id), api_hash) as client:
            session = client.session.save()
        set_secret("telegram_api_id", api_id)
        set_secret("telegram_api_hash", api_hash)
        set_secret("telegram_session", session)
        print("Saved Telegram credentials. Put telegram_allowlist in collector.json.")
        return
    set_secret(name, getpass.getpass(f"{name}: ").strip())
    print(f"Saved {name}.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collector")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="one full run now")
    run.add_argument("--source", action="append")
    sub.add_parser("backfill", help="repeat runs until nothing new")
    sub.add_parser("poll", help="serve queued jobs, then run if the schedule is due")
    au = sub.add_parser("auth", help="store a secret in the Keychain")
    au.add_argument("name", help="instagram, telegram, gmail_app_password, openai_api_key, collector_token")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.cmd == "auth":
        auth(args.name)
        return 0
    runner = build_runner(load_config())
    if args.cmd == "run":
        print(runner.run(args.source).counts)
    elif args.cmd == "backfill":
        for _round in range(100):
            report = runner.run()
            print(report.counts, report.errors)
            if report.total == 0 or report.errors:
                break
    else:
        print("handled", runner.poll())
    return 0


if __name__ == "__main__":
    sys.exit(main())
