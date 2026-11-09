"""Recent inbox mail over IMAP with a Gmail app password."""

from __future__ import annotations

import email
import email.utils
import imaplib
import re
from email import policy
from collections.abc import Callable
from typing import Any


HOST = "imap.gmail.com"
QUERY = "newer_than:2d in:inbox -category:promotions -category:social -category:forums"
LIMIT = 25


def _text(msg: Any) -> str:
    plain = msg.get_body(preferencelist=("plain",))
    if plain is not None:
        return plain.get_content()
    html = msg.get_body(preferencelist=("html",))
    return re.sub(r"<[^>]+>", " ", html.get_content()) if html is not None else ""


def parse_mail(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw, policy=policy.default)
    stamp = ""
    try:
        stamp = email.utils.parsedate_to_datetime(str(msg.get("Date"))).isoformat()
    except (TypeError, ValueError):
        pass
    return {
        "subject": str(msg.get("Subject") or "(no subject)"),
        "from": str(msg.get("From") or ""),
        "date": stamp,
        "snippet": " ".join(_text(msg).split())[:400],
    }


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
            out.append(parse_mail(parts[0][1]))
        return out
    finally:
        try:
            box.logout()
        except Exception:
            pass
