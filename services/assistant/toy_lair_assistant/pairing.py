from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta


class PairingFull(Exception):
    pass


@dataclass
class PairSession:
    code: str
    secret: str
    expires_at: datetime
    approved: bool = False


class Pairing:
    def __init__(
        self,
        token: str,
        ttl_seconds: int = 600,
        max_sessions: int = 20,
    ) -> None:
        self.token = token
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._by_code: dict[str, PairSession] = {}
        self._by_secret: dict[str, PairSession] = {}

    def start(self, now: datetime) -> dict[str, str | int]:
        self._purge(now)
        if len(self._by_code) >= self.max_sessions:
            raise PairingFull()
        code = self._unique_code()
        secret = secrets.token_urlsafe(16)
        session = PairSession(
            code=code,
            secret=secret,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        self._by_code[code] = session
        self._by_secret[secret] = session
        return {
            "code": code,
            "secret": secret,
            "expires_in": self.ttl_seconds,
        }

    def approve(self, code: str, now: datetime) -> bool:
        self._purge(now)
        session = self._by_code.get(code.strip())
        if session is None:
            return False
        session.approved = True
        return True

    def claim(self, secret: str, now: datetime) -> dict[str, str] | None:
        self._purge(now)
        session = self._by_secret.get(secret)
        if session is None:
            return None
        if not session.approved:
            return {"status": "pending"}
        self._drop(session)
        return {"status": "approved", "token": self.token}

    def _unique_code(self) -> str:
        while True:
            code = f"{secrets.randbelow(10000):04d}"
            if code not in self._by_code:
                return code

    def _purge(self, now: datetime) -> None:
        expired = [
            session
            for session in list(self._by_code.values())
            if session.expires_at <= now
        ]
        for session in expired:
            self._drop(session)

    def _drop(self, session: PairSession) -> None:
        self._by_code.pop(session.code, None)
        self._by_secret.pop(session.secret, None)
