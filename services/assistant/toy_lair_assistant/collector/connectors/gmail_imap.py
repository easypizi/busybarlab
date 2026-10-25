from __future__ import annotations

import email
import email.utils
import imaplib
import re
from collections.abc import Callable, Iterator
from email import policy
from email.message import Message
from urllib.parse import quote

from toy_lair_assistant.collector.enrich import html_to_text
from toy_lair_assistant.collector.models import ConnectorAuthError, FetchContext, RawItem

HOST = "imap.gmail.com"
ALL_MAIL = '"[Gmail]/All Mail"'
BODY_LIMIT = 6000
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def _body_text(msg: Message) -> str:
    plain = msg.get_body(preferencelist=("plain",))
    if plain is not None:
        return plain.get_content()
    html = msg.get_body(preferencelist=("html",))
    return html_to_text(html.get_content()) if html is not None else ""


class GmailImap:
    name = "gmail"

    def __init__(
        self,
        user: str,
        password: str,
        query: str,
        connect: Callable[[], imaplib.IMAP4_SSL] | None = None,
    ) -> None:
        self.user = user
        self.password = password
        self.query = query
        self._connect = connect or (lambda: imaplib.IMAP4_SSL(HOST))

    def fetch(self, ctx: FetchContext) -> Iterator[RawItem]:
        conn = self._connect()
        try:
            try:
                conn.login(self.user, self.password)
            except imaplib.IMAP4.error as exc:
                raise ConnectorAuthError(f"Gmail login failed: {exc}") from exc
            conn.select(ALL_MAIL, readonly=True)
            status, data = conn.uid("SEARCH", "X-GM-RAW", f'"{self.query}"')
            if status != "OK" or not data or not data[0]:
                return
            uids = data[0].split()
            uids.reverse()
            for uid in uids:
                message_id = self._message_id(conn, uid)
                if not message_id or ctx.seen(message_id):
                    continue
                item = self._load(conn, uid, message_id)
                if item is not None:
                    yield item
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _message_id(self, conn: imaplib.IMAP4_SSL, uid: bytes) -> str:
        status, parts = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
        if status != "OK" or not parts or not isinstance(parts[0], tuple):
            return ""
        header = email.message_from_bytes(parts[0][1], policy=policy.default)
        return str(header.get("Message-ID") or "").strip()

    def _load(self, conn: imaplib.IMAP4_SSL, uid: bytes, message_id: str) -> RawItem | None:
        status, parts = conn.uid("FETCH", uid, "(BODY.PEEK[])")
        if status != "OK" or not parts or not isinstance(parts[0], tuple):
            return None
        msg = email.message_from_bytes(parts[0][1], policy=policy.default)
        body = _body_text(msg)[:BODY_LIMIT]
        links = list(dict.fromkeys(URL_RE.findall(body)))[:5]
        stamp = ""
        try:
            stamp = email.utils.parsedate_to_datetime(str(msg.get("Date"))).isoformat()
        except (TypeError, ValueError):
            pass
        text = body if not links else body + "\n" + "\n".join(links)
        return RawItem(
            source=self.name,
            external_id=message_id,
            url="https://mail.google.com/mail/u/0/#search/rfc822msgid:" + quote(message_id.strip("<>")),
            title=str(msg.get("Subject") or "(no subject)"),
            author=str(msg.get("From") or ""),
            text=text,
            captured_at=stamp,
            private=True,
            extra={"links": links},
        )
