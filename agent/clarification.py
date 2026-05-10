"""
The in-flow pause clarification — THE centerpiece moment.

Sequence:
  1. agent reaches the chosen judgment field
  2. orchestrator calls show_overlay() — ring + card fade in
  3. pre-cached ElevenLabs audio plays the Chinese question (sub-100ms)
  4. orchestrator opens voice listen on asyncio.Queue
  5. user voice-answers in Chinese (or fallback audio plays during recording)
  6. transcript → regex first → Haiku fallback → enum value
  7. schema dict is updated (single writer)
  8. mark_listening('recorded') turns ring green
  9. hide overlay, fill the field, agent continues
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.async_api import Page

from corpus import FIELDS_BY_KEY, FieldSpec
from voice.intent_extraction import resolve_enum_answer

from agent.i18n import Language, field_explanation, field_question, t
from agent.overlay_bridge import (
    hide_overlay,
    mark_listening,
    show_overlay,
)
from agent.speech import speak_text
from agent.voice_questions import answer_if_clarifying_question


_AUDIO_CACHE_DIR = Path(__file__).resolve().parent.parent / "assets" / "audio_cache"


async def _play_question_audio(page: Page, schema_key: str) -> None:
    """
    Play the pre-cached Chinese question via the page's audio context.
    Falls through silently if the cache file isn't there yet (recording
    sessions may run before precache is done).
    """
    audio_path = _AUDIO_CACHE_DIR / f"{schema_key}.mp3"
    if not audio_path.exists():
        return
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


@dataclass
class ClarificationResult:
    field_key: str
    value: Optional[str]
    source: str  # 'regex' | 'llm' | 'miss'
    voice_to_value_ms: float


async def run_clarification(
    page: Page,
    field: FieldSpec,
    target_env: str,
    voice_queue: asyncio.Queue,
    listen_timeout_s: float = 10.0,
    *,
    pre_voice_hold_s: float = 0.0,
    post_audio_pause_s: float = 0.0,
    listening_visible_s: float = 0.0,
    recorded_hold_s: float = 0.3,
    language: Language = "zh",
) -> ClarificationResult:
    """
    Show overlay → wait for transcript on voice_queue → resolve enum →
    update overlay state → hide. Caller is responsible for filling the form.

    Returns ClarificationResult with the resolved value, or value=None if
    the user couldn't be understood within the timeout.
    """
    question = field_question(field, language)
    explanation = field_explanation(field, language)
    if not question or not explanation:
        raise ValueError(f"Judgment field {field.name!r} missing overlay copy")

    sel = field.selector_mock if target_env == "mock" else field.selector_live
    if not sel:
        raise RuntimeError(f"No selector for {field.name!r} in {target_env}")

    # Show the overlay.
    ok = await show_overlay(
        page,
        selector=sel,
        question=question,
        explanation=explanation,
        listening_label=t("listening", language),
    )
    if not ok:
        raise RuntimeError(f"Could not anchor overlay on selector {sel!r}")

    # Demo pacing: hold the overlay visible BEFORE any audio fires so the
    # judge has time to register the highlight ring and start reading.
    if pre_voice_hold_s > 0:
        await asyncio.sleep(pre_voice_hold_s)

    # Play the pre-cached Chinese question audio (sub-100ms playback start).
    # Awaits the playback so the listening window opens AFTER the user has
    # heard the question — prevents the user from talking over the prompt.
    await speak_text(page, question, language=language, audio_key=field.schema_key)

    # Pause AFTER the question audio finishes so the judge has time to
    # actually read the bilingual explanation card (recording-mode reads,
    # live-mode hears).
    if post_audio_pause_s > 0:
        await asyncio.sleep(post_audio_pause_s)

    # Hold the listening dots visible for a beat — sells "the agent is
    # actively listening" instead of "fields auto-answer themselves."
    if listening_visible_s > 0:
        await asyncio.sleep(listening_visible_s)

    voice_start = time.perf_counter()

    value: Optional[str] = None
    source = "miss"
    for attempt in range(3):
        # Wait for the voice answer transcript to land in the queue.
        try:
            transcript: str = await asyncio.wait_for(
                voice_queue.get(), timeout=listen_timeout_s
            )
        except asyncio.TimeoutError:
            await mark_listening(page, "retry")
            await asyncio.sleep(0.6)
            await hide_overlay(page)
            return ClarificationResult(
                field_key=field.schema_key,
                value=None,
                source="miss",
                voice_to_value_ms=(time.perf_counter() - voice_start) * 1000,
            )

        await mark_listening(page, "thinking")
        clarification = await answer_if_clarifying_question(
            transcript,
            language=language,
            current_prompt=question,
            field_name=field.schema_key,
            explanation=explanation,
            allowed_values=list(field.enum_values or ()),
        )
        if clarification.is_question:
            if clarification.answer:
                await speak_text(page, clarification.answer, language=language)
            await mark_listening(page, "listening")
            continue

        # Regex first; Haiku fallback.
        value, source = await resolve_enum_answer(field.schema_key, transcript)
        if value:
            break
        if attempt < 2:
            await mark_listening(page, "retry")
            await asyncio.sleep(0.5)
            await speak_text(page, question, language=language, audio_key=field.schema_key)
    elapsed_ms = (time.perf_counter() - voice_start) * 1000

    # Visual feedback before fill.
    if value:
        await mark_listening(page, "recorded")
        await asyncio.sleep(max(recorded_hold_s, 0.3))  # let the ring color shift register
    else:
        await mark_listening(page, "retry")
        await asyncio.sleep(0.5)

    await hide_overlay(page)

    return ClarificationResult(
        field_key=field.schema_key,
        value=value,
        source=source,
        voice_to_value_ms=elapsed_ms,
    )
