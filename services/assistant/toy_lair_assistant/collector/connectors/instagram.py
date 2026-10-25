from __future__ import annotations

import json
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from toy_lair_assistant.collector.models import ConnectorAuthError, FetchContext, RawItem

MAX_AUDIO_BYTES = 24 * 1024 * 1024


def extract_audio(video_url: str, runner: Callable[..., Any] = subprocess.run) -> bytes:
    """Pull the audio track only. The video is never written to disk."""
    with tempfile.TemporaryDirectory(prefix="paco-ig-") as tmp:
        out = Path(tmp) / "audio.m4a"
        result = runner(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", video_url, "-vn", "-ac", "1", "-b:a", "48k", str(out)],
            capture_output=True,
            timeout=180,
        )
        if result.returncode != 0 or not out.exists():
            raise RuntimeError("ffmpeg failed")
        data = out.read_bytes()
    if len(data) > MAX_AUDIO_BYTES:
        raise RuntimeError("audio too large")
    return data


class InstagramSaved:
    name = "instagram"

    def __init__(
        self,
        username: str,
        session_json: str,
        loader_factory: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        pause_seconds: float = 3.0,
    ) -> None:
        self.username = username
        self.session_json = session_json
        self._factory = loader_factory
        self.sleep = sleep
        self.pause = pause_seconds

    def _loader(self) -> Any:
        if self._factory is not None:
            return self._factory()
        import instaloader

        return instaloader.Instaloader(
            quiet=True, download_pictures=False, download_videos=False,
            download_video_thumbnails=False, download_comments=False,
            save_metadata=False, compress_json=False,
        )

    def fetch(self, ctx: FetchContext) -> Iterator[RawItem]:
        if not self.session_json:
            raise ConnectorAuthError("Instagram session missing, run auth instagram")
        loader = self._loader()
        try:
            loader.load_session(self.username, json.loads(self.session_json))
            profile = _profile(loader, self.username)
            fresh = 0
            for post in profile.get_saved_posts():
                if ctx.seen(post.shortcode):
                    continue
                yield self._item(post)
                fresh += 1
                if fresh >= ctx.limit:
                    return
                self.sleep(self.pause)
        except ConnectorAuthError:
            raise
        except Exception as exc:
            name = type(exc).__name__
            if name in {
                "LoginRequiredException", "BadCredentialsException", "TwoFactorAuthRequiredException",
                "TooManyRequestsException", "QueryReturnedForbiddenException",
                "QueryReturnedBadRequestException", "ConnectionException", "InvalidArgumentException",
            }:
                raise ConnectorAuthError(f"Instagram stopped ({name}). Check the session or checkpoint.") from exc
            raise

    def _item(self, post: Any) -> RawItem:
        caption = getattr(post, "caption", "") or ""
        first = caption.strip().splitlines()[0] if caption.strip() else ""
        video_url = getattr(post, "video_url", None) if getattr(post, "is_video", False) else None
        stamp = getattr(post, "date_utc", None)
        return RawItem(
            source=self.name,
            external_id=post.shortcode,
            url=f"https://www.instagram.com/p/{post.shortcode}/",
            title=first[:100] or f"Instagram {post.shortcode}",
            author=str(getattr(post, "owner_username", "") or ""),
            text=caption,
            captured_at=stamp.isoformat() + "+00:00" if stamp else "",
            audio=(lambda url=video_url: extract_audio(url)) if video_url else None,
        )


def _profile(loader: Any, username: str) -> Any:
    import instaloader

    return instaloader.Profile.from_username(loader.context, username)
