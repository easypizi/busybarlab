from fastapi import Header, HTTPException

from toy_lair_assistant.settings import Settings


def require_token(settings: Settings, x_assistant_token: str | None) -> None:
    if not settings.assistant_api_token:
        raise HTTPException(status_code=500, detail="assistant token is not configured")
    if x_assistant_token != settings.assistant_api_token:
        raise HTTPException(status_code=401, detail="invalid assistant token")


def token_header(x_assistant_token: str | None = Header(default=None)) -> str | None:
    return x_assistant_token
