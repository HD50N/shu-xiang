"""Shared text-to-speech helpers for user-facing demo narration."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from playwright.async_api import Page

from agent.i18n import Language

logger = logging.getLogger("shuxiang.speech")

_AUDIO_CACHE_DIR = Path(__file__).resolve().parent.parent / "assets" / "audio_cache"


async def _add_agent_transcript(page: Page, text: str) -> None:
    """Add AI-spoken text to the visible conversation transcript."""
    if not text:
        return
    try:
        await page.evaluate(
            """(t) => {
                window.shuxiang &&
                    window.shuxiang.updateLiveTranscript &&
                    window.shuxiang.updateLiveTranscript({ speaker: "agent", text: t });
            }""",
            text,
        )
    except Exception:
        logger.debug("failed to update agent transcript", exc_info=True)


async def stop_speech(page: Page) -> None:
    """Stop any browser-side AI speech that is currently playing."""
    await page.evaluate(
        """() => {
            if (window.shuxiang && typeof window.shuxiang.stopSpeech === 'function') {
                window.shuxiang.stopSpeech();
                return;
            }
            const audio = window.__shuxiangActiveAudio;
            if (!audio) return;
            try {
                audio.pause();
                audio.currentTime = 0;
            } catch (e) { /* ignore */ }
            if (typeof audio.__shuxiangResolve === 'function') {
                audio.__shuxiangResolve();
            }
            window.__shuxiangActiveAudio = null;
        }"""
    )


async def _play_audio_url(page: Page, url: str) -> None:
    """Play a URL in the browser, tracking it so user speech can interrupt it."""
    await page.evaluate(
        """(url) => new Promise((resolve) => {
            const stopExisting = () => {
                const active = window.__shuxiangActiveAudio;
                if (!active) return;
                try {
                    active.pause();
                    active.currentTime = 0;
                } catch (e) { /* ignore */ }
                if (typeof active.__shuxiangResolve === 'function') {
                    active.__shuxiangResolve();
                }
            };
            stopExisting();

            const audio = new Audio(url);
            let settled = false;
            const finish = () => {
                if (settled) return;
                settled = true;
                if (window.__shuxiangActiveAudio === audio) {
                    window.__shuxiangActiveAudio = null;
                }
                resolve();
            };
            audio.__shuxiangResolve = finish;
            audio.onended = finish;
            audio.onerror = finish;
            window.__shuxiangActiveAudio = audio;
            audio.play().catch(finish);
        })""",
        url,
    )


async def play_audio_bytes(page: Page, mp3_bytes: bytes) -> None:
    """Play mp3 bytes in the browser via a base64 data URL."""
    b64 = base64.b64encode(mp3_bytes).decode("ascii")
    await _play_audio_url(page, "data:audio/mpeg;base64," + b64)


async def play_cached_audio(page: Page, audio_key: str) -> bool:
    """Play assets/audio_cache/<audio_key>.mp3. Returns False on cache miss."""
    audio_path = _AUDIO_CACHE_DIR / f"{audio_key}.mp3"
    if not audio_path.exists():
        logger.warning("audio cache miss: %s", audio_path)
        return False
    await _play_audio_url(page, audio_path.as_uri())
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
    await _add_agent_transcript(page, text)
    if language == "zh" and audio_key and await play_cached_audio(page, audio_key):
        return

    try:
        from voice.elevenlabs_voice import synthesize_to_bytes

        mp3 = await synthesize_to_bytes(text)
        await play_audio_bytes(page, mp3)
    except Exception:
        logger.exception("TTS failed for %r — continuing text-only", text)
