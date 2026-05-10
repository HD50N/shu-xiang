"""
Live STT loop: bridges MicCapture utterances to ElevenLabs Scribe and pushes
transcripts onto the orchestrator's asyncio.Queue.

Two channels:
  - Final (on mute click): Scribe → queue → consumed by the conversation loop
  - Partial (every PARTIAL_INTERVAL_S while unmuted): Scribe → on_partial_transcript
    callback. Lets the UI display the user's words as they speak.

This replaces voice/scripted.py's deterministic feeder when DEMO_MODE is
"live_walkthrough" (or any time the runner explicitly opts in via
state.use_live_voice).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from voice.elevenlabs_voice import STTConfig, transcribe_audio_bytes
from voice.mic_capture import MicCapture

logger = logging.getLogger("shuxiang.voice.live_stt")


@dataclass
class LiveSTT:
    """
    Owns a MicCapture and routes its utterances through Scribe → asyncio.Queue.

    Wire it once at orchestrator startup; the rest of the demo treats it as
    the same `voice_queue` interface that the scripted feeder used.
    """
    mic: MicCapture
    queue: asyncio.Queue
    on_state_change: Optional[callable] = None
    language_code: Optional[str] = "zho"
    _stt_config: STTConfig = field(default_factory=STTConfig)
    # Highest partial sequence number we've successfully transcribed and
    # displayed. Drops late-arriving stale Scribe responses.
    _last_seen_partial_seq: int = 0
    _seq_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @classmethod
    def attach(
        cls,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue,
        on_state_change: Optional[callable] = None,
        on_partial_transcript: Optional[Callable[[str], Awaitable[None]]] = None,
        language_code: Optional[str] = "zho",
    ) -> "LiveSTT":
        """Build, register the utterance handlers, and start the mic.

        on_partial_transcript(text): fired with each fresh-enough live partial
            transcript while the user is still speaking. Use it to update the
            visible transcript on the page in real time.
        """
        instance: LiveSTT  # forward reference for closure
        stt_config = STTConfig(language_code=language_code)

        async def _handle_utterance(wav_bytes: bytes) -> None:
            try:
                transcript = await transcribe_audio_bytes(wav_bytes, config=stt_config)
            except Exception:
                logger.exception("Scribe transcription failed")
                return
            if not transcript:
                logger.info("empty transcript — skipping")
                return
            logger.info("transcript: %r", transcript)
            if on_partial_transcript is not None:
                try:
                    await on_partial_transcript(transcript)
                except Exception:
                    logger.exception("on_partial_transcript handler raised for final transcript")
            await queue.put(transcript)

        async def _handle_partial(wav_bytes: bytes, seq: int) -> None:
            if on_partial_transcript is None:
                return
            try:
                transcript = await transcribe_audio_bytes(wav_bytes, config=stt_config)
            except Exception:
                logger.warning("partial Scribe transcription failed (seq=%d)", seq)
                return
            if not transcript:
                return
            # Drop late stale responses: only update if this seq is the
            # newest we've seen. Without this, a slow Scribe call for an
            # earlier buffer can overwrite a later, more-complete partial.
            async with instance._seq_lock:
                if seq <= instance._last_seen_partial_seq:
                    return
                instance._last_seen_partial_seq = seq
            try:
                await on_partial_transcript(transcript)
            except Exception:
                logger.exception("on_partial_transcript handler raised")

        mic = MicCapture(
            loop=loop,
            on_utterance=_handle_utterance,
            on_partial=_handle_partial if on_partial_transcript else None,
        )
        instance = cls(
            mic=mic,
            queue=queue,
            on_state_change=on_state_change,
            language_code=language_code,
            _stt_config=stt_config,
        )
        logger.info("Scribe STT language_code=%s", language_code or "auto")
        mic.start()
        return instance

    def set_language_code(self, language_code: Optional[str]) -> None:
        """Switch Scribe language for subsequent final and partial transcripts."""
        self.language_code = language_code
        # The handler closures share this mutable config object.
        self._stt_config.language_code = language_code
        logger.info("Scribe STT language_code=%s", language_code or "auto")

    def set_muted(self, muted: bool) -> None:
        self.mic.state.set_muted(muted)
        if self.on_state_change:
            try:
                self.on_state_change(muted)
            except Exception:
                logger.exception("on_state_change handler raised")

    def is_muted(self) -> bool:
        return self.mic.state.muted

    def toggle(self) -> bool:
        new_state = not self.mic.state.muted
        self.set_muted(new_state)
        return new_state

    def shutdown(self) -> None:
        self.mic.stop()
