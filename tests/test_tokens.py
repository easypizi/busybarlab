"""Tests for dual-account token store."""

from pathlib import Path

from busybar.cursor_pet.tokens import StoredToken, TokenStore, load_token_store, save_token_store


def test_token_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "cursor_tokens.json"
    store = TokenStore(
        personal=StoredToken(
            account="personal",
            access_token="tok-personal",
            email="me@example.com",
            exported_at=1.0,
            source_host="macbook",
        )
    )
    save_token_store(store, path)
    loaded = load_token_store(path)
    assert loaded.personal is not None
    assert loaded.personal.access_token == "tok-personal"
    assert loaded.accounts_with_tokens() == ["personal"]
    loaded.set(
        StoredToken(
            account="work",
            access_token="tok-work",
            email="work@example.com",
            exported_at=2.0,
        )
    )
    save_token_store(loaded, path)
    again = load_token_store(path)
    assert again.accounts_with_tokens() == ["work", "personal"]
