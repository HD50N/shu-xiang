"""Shared text-to-speech helpers for user-facing demo narration."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from playwright.async_api import Page

from agent.i18n import Language

logger = logging.getLogger("shuxiang.speech")

_AUDIO_CACHE_DIR = Path(__file__).resolve().parent.parent / "assets" / "audio_cache"


async def play_audio_bytes(page: Page, mp3_bytes: bytes) -> None:
    """Play mp3 bytes in the browser via a base64 data URL."""
    b64 = base64.b64encode(mp3_bytes).decode("ascii")
    await page.evaluate(
        """(b64) => new Promise((resolve) => {
            const url = 'data:audio/mpeg;base64,' + b64;
            const a = new Audio(url);
            a.onended = resolve;
            a.onerror = resolve;
            a.play().catch(resolve);
        })""",
        b64,
    )


async def play_cached_audio(page: Page, audio_key: str) -> bool:
    """Play assets/audio_cache/<audio_key>.mp3. Returns False on cache miss."""
    audio_path = _AUDIO_CACHE_DIR / f"{audio_key}.mp3"
    if not audio_path.exists():
        logger.warning("audio cache miss: %s", audio_path)
        return False
    audio_url = audio_path.as_uri()
    await page.evaluate(
        """(url) => new Promise((resolve) => {
            const a = new Audio(url);
            a.onended = resolve;
            a.onerror = resolve;
            a.play().catch(resolve);
        })""",
        audio_url,
    )
    return True


async def speak_text(
    page: Page,
    text: str,
    *,
    language: Language,
    audio_key: str | None = None,
) -> None:
    """Speak text in the selected language, using cached Chinese audio when available."""
    if not text:
        return
    if language == "zh" and audio_key and await play_cached_audio(page, audio_key):
        return

    try:
        from voice.elevenlabs_voice import synthesize_to_bytes

        mp3 = await synthesize_to_bytes(text)
        await play_audio_bytes(page, mp3)
    except Exception:
        logger.exception("TTS failed for %r — continuing text-only", text)
