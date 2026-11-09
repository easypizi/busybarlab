"""Recent inbox mail over IMAP with a Gmail app password."""

from __future__ import annotations

import imaplib
from collections.abc import Callable
from typing import Any

from toy_lair_assistant.collector.connectors.gmail_imap import mail_to_item

HOST = "imap.gmail.com"
QUERY = "newer_than:2d in:inbox -category:promotions -category:social -category:forums"
LIMIT = 25


def fetch(
    user: str,
    password: str,
    connect: Callable[[str], Any] = imaplib.IMAP4_SSL,
    limit: int = LIMIT,
) -> list[dict]:
    box = connect(HOST)
    try:
        box.login(user, password)
        box.select("INBOX", readonly=True)
        status, data = box.search(None, "X-GM-RAW", f'"{QUERY}"')
        if status != "OK":
            raise RuntimeError("IMAP search failed")
        ids = (data[0] or b"").split()[-limit:]
        out = []
        for number in reversed(ids):
            status, parts = box.fetch(number, "(RFC822)")
            if status != "OK" or not parts or not isinstance(parts[0], tuple):
                continue
            item = mail_to_item(parts[0][1], number.decode())
            out.append(
                {
                    "subject": item.title,
                    "from": item.author,
                    "date": item.captured_at,
                    "snippet": " ".join(item.text.split())[:400],
                }
            )
        return out
    finally:
        try:
            box.logout()
        except Exception:
            pass
