from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from typing import Any

from toy_lair_assistant.collector.models import ConnectorAuthError, FetchContext, RawItem

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def extract_urls(text: str, entity_urls: list[str]) -> list[str]:
    return list(dict.fromkeys([*entity_urls, *URL_RE.findall(text or "")]))


class TelegramUser:
    name = "telegram"

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session: str,
        allowlist: list[str],
        client_factory: Any = None,
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.session = session
        self.allowlist = allowlist
        self._factory = client_factory

    def fetch(self, ctx: FetchContext) -> Iterator[RawItem]:
        if not self.allowlist:
            return iter(())
        return iter(asyncio.run(self._collect(ctx)))

    def _client(self) -> Any:
        if self._factory is not None:
            return self._factory()
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        return TelegramClient(StringSession(self.session), self.api_id, self.api_hash)

    async def _collect(self, ctx: FetchContext) -> list[RawItem]:
        client = self._client()
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise ConnectorAuthError("Telegram session is not authorized, run auth telegram")
            out: list[RawItem] = []
            for chat in self.allowlist:
                entity = await client.get_entity(int(chat) if chat.lstrip("-").isdigit() else chat)
                chat_id = getattr(entity, "id", chat)
                last = int(ctx.cursor(f"telegram:{chat_id}") or 0)
                newest = last
                async for msg in client.iter_messages(entity, min_id=last, limit=ctx.limit * 4):
                    newest = max(newest, msg.id)
                    text = getattr(msg, "message", "") or ""
                    entity_urls = [
                        e.url for e in (getattr(msg, "entities", None) or []) if getattr(e, "url", None)
                    ]
                    urls = extract_urls(text, entity_urls)
                    forwarded = getattr(msg, "fwd_from", None) is not None
                    if not urls and not forwarded:
                        continue
                    ext = f"{chat_id}:{msg.id}"
                    if ctx.seen(ext):
                        continue
                    first = text.strip().splitlines()[0] if text.strip() else ""
                    out.append(
                        RawItem(
                            source=self.name,
                            external_id=ext,
                            url=urls[0] if urls else f"https://t.me/c/{chat_id}/{msg.id}",
                            title=first[:100],
                            author=str(getattr(entity, "title", "") or getattr(entity, "username", "") or chat),
                            text=text,
                            captured_at=msg.date.isoformat() if getattr(msg, "date", None) else "",
                            fetch_page=bool(urls),
                            extra={"urls": urls},
                        )
                    )
                if newest > last:
                    ctx.stage_cursor(f"telegram:{chat_id}", str(newest))
            return out
        finally:
            await client.disconnect()
