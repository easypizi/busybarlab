"""Dual-account Cursor token store: export from local SQLite, reuse on pet host."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from busybar.cursor_pet.collector import DEFAULT_DB, AccountRole, read_access_token

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOKENS_PATH = ROOT / "data" / "cursor_tokens.json"


@dataclass
class StoredToken:
    account: AccountRole
    access_token: str
    email: str | None = None
    exported_at: float = 0.0
    source_host: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoredToken:
        return cls(
            account=data["account"],  # type: ignore[arg-type]
            access_token=str(data["access_token"]),
            email=data.get("email"),
            exported_at=float(data.get("exported_at") or 0),
            source_host=data.get("source_host"),
        )


@dataclass
class TokenStore:
    work: StoredToken | None = None
    personal: StoredToken | None = None

    def get(self, account: AccountRole) -> StoredToken | None:
        return self.work if account == "work" else self.personal

    def set(self, token: StoredToken) -> None:
        if token.account == "work":
            self.work = token
        else:
            self.personal = token

    def accounts_with_tokens(self) -> list[AccountRole]:
        out: list[AccountRole] = []
        if self.work and self.work.access_token:
            out.append("work")
        if self.personal and self.personal.access_token:
            out.append("personal")
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "work": self.work.to_dict() if self.work else None,
            "personal": self.personal.to_dict() if self.personal else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenStore:
        store = cls()
        if data.get("work"):
            store.work = StoredToken.from_dict(data["work"])
        if data.get("personal"):
            store.personal = StoredToken.from_dict(data["personal"])
        return store


def read_cached_email(db_path: Path | None = None) -> str | None:
    path = db_path or DEFAULT_DB
    if not path.exists():
        return None
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT value FROM ItemTable WHERE key=?",
            ("cursorAuth/cachedEmail",),
        ).fetchone()
    finally:
        con.close()
    if not row or not row[0]:
        return None
    return str(row[0])


def load_token_store(path: Path | None = None) -> TokenStore:
    path = path or DEFAULT_TOKENS_PATH
    if not path.exists():
        return TokenStore()
    data = json.loads(path.read_text(encoding="utf-8"))
    return TokenStore.from_dict(data)


def save_token_store(store: TokenStore, path: Path | None = None) -> None:
    path = path or DEFAULT_TOKENS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(store.to_dict(), indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def export_local_account(
    account: AccountRole,
    *,
    path: Path | None = None,
    db_path: Path | None = None,
    source_host: str | None = None,
) -> StoredToken:
    """Read this machine's Cursor session and merge into the token store."""
    import socket

    token = read_access_token(db_path)
    email = read_cached_email(db_path)
    stored = StoredToken(
        account=account,
        access_token=token,
        email=email,
        exported_at=time.time(),
        source_host=source_host or socket.gethostname(),
    )
    store = load_token_store(path)
    store.set(stored)
    save_token_store(store, path)
    return stored


def resolve_collectors(
    *,
    tokens_path: Path | None = None,
    local_account: AccountRole | None = None,
    prefer_store: bool = True,
) -> dict[AccountRole, str]:
    """
    Build account -> bearer token map.

    Preference:
    1. Tokens from data/cursor_tokens.json when present
    2. Else local SQLite for --local-account only
    """
    result: dict[AccountRole, str] = {}
    if prefer_store:
        store = load_token_store(tokens_path)
        for account in store.accounts_with_tokens():
            tok = store.get(account)
            if tok:
                result[account] = tok.access_token
    if not result and local_account:
        result[local_account] = read_access_token()
    elif local_account and local_account not in result:
        # Fill missing local role from live session if store incomplete.
        try:
            result[local_account] = read_access_token()
        except Exception:
            pass
    return result
