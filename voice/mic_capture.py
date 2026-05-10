"""
Live microphone capture with manual press-to-record / press-to-stop turn-taking.

Architecture:
  sounddevice InputStream at 16kHz mono PCM16
    -> ring buffer
    -> while UNMUTED: every frame appended to the current utterance buffer
    -> on MUTE click: finalize the buffer, wrap as WAV bytes, dispatch
       on_utterance(wav_bytes); orchestrator's transcript loop picks it up
    -> next UNMUTE click: fresh buffer starts

This replaced the previous VAD-segmented model. The 700ms-silence-after-speech
heuristic was unreliable in practice — it cut users off mid-sentence when they
paused to think, and false-triggered on background noise. Manual segmentation
puts the user in charge of "I'm done": click to start, click to stop.

Mute state is consulted on every captured frame:
  - muted=True: frames discarded; if we just transitioned from unmuted, the
    accumulated buffer is finalized and dispatched.
  - muted=False: frames appended to the buffer; if we just transitioned from
    muted, the buffer starts fresh.

The callback is async; wrap it in run_coroutine_threadsafe so the audio
thread can dispatch to the orchestrator's event loop.
"""

from __future__ import annotations

import asyncio
import io
import logging
import threading
import time
import wave
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger("shuxiang.voice.mic")


# All audio runs at 16 kHz mono PCM16 — matches ElevenLabs Scribe's expected input.
SAMPLE_RATE = 16_000
CHANNELS = 1
FRAME_MS = 30
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)  # 480 samples per frame
MAX_UTTERANCE_S = 60.0  # safety cap if user forgets to click mute
# How often to dispatch a partial-buffer snapshot for live transcription.
# Each partial = one Scribe REST call. 1.5s gives a balance between perceived
# liveness and API cost — the partial typically appears ~1-2s after the user
# speaks (Scribe round-trip is ~700ms-1500ms depending on audio length).
PARTIAL_INTERVAL_S = 1.5
# Don't fire a partial before the user has accumulated this much audio —
# transcribing 200ms of speech rarely produces useful text.
PARTIAL_MIN_AUDIO_S = 0.6


def pcm16_to_wav_bytes(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw PCM16 mono in a minimal WAV container for Scribe upload."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)  # PCM16 → 2 bytes/sample
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


@dataclass
class MicState:
    """Shared state between the audio thread and the orchestrator."""
    muted: bool = True
    listening_indicator_dirty: bool = True
    last_utterance_started_at: Optional[float] = None
    last_utterance_ended_at: Optional[float] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set_muted(self, muted: bool) -> None:
        with self._lock:
            if self.muted != muted:
                self.muted = muted
                self.listening_indicator_dirty = True
                logger.info("mic %s", "MUTED" if muted else "UNMUTED")


class MicCapture:
    """
    Owns the sounddevice InputStream and runs the capture loop in a background
    thread. Segmentation is mute-driven, not VAD-driven.

    Public API:
      mic = MicCapture(loop=asyncio.get_event_loop(),
                       on_utterance=lambda wav: handle(wav))
      mic.start()
      ... mic.state.set_muted(False) when user clicks to start recording ...
      ... mic.state.set_muted(True)  when user clicks to stop  → finalizes ...
      mic.stop()
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_utterance: Callable[[bytes], Awaitable[None]],
        on_partial: Optional[Callable[[bytes, int], Awaitable[None]]] = None,
    ):
        """
        on_utterance(wav_bytes): called when the user clicks mute. The final
            audio buffer is wrapped as WAV and dispatched.
        on_partial(wav_bytes, seq): optional, called every PARTIAL_INTERVAL_S
            while unmuted with the buffer-so-far. `seq` increments per dispatch
            so the consumer can drop late-arriving stale results.
        """
        self._loop = loop
        self._on_utterance = on_utterance
        self._on_partial = on_partial
        self.state = MicState(muted=True)
        self._stream: Optional[sd.InputStream] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="mic-capture", daemon=True)
        self._thread.start()
        logger.info("mic capture started (16kHz mono, manual segmentation)")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None
        logger.info("mic capture stopped")

    # ── audio thread ──────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
            ) as stream:
                self._stream = stream
                self._capture_loop(stream)
        except Exception:
            logger.exception("mic capture thread crashed")

    def _capture_loop(self, stream: sd.RawInputStream) -> None:
        utterance_frames: list[bytes] = []
        last_muted = self.state.muted  # starts True
        # Live-transcription partial dispatch state. next_partial_at is a
        # monotonic timestamp; when reached, we snapshot the buffer-so-far
        # and call on_partial. partial_seq disambiguates late-arriving
        # transcriptions (the consumer keeps the highest seq it's seen).
        next_partial_at: Optional[float] = None
        partial_seq = 0
        # Diagnostics — log audio level once per second so we can verify
        # frames are arriving and the mic input level is reasonable.
        diag_frame_count = 0
        diag_max_rms = 0
        diag_unmuted_frames = 0

        logger.info(
            "mic stream open: samplerate=%s channels=%s blocksize=%s",
            stream.samplerate, stream.channels, stream.blocksize,
        )

        while not self._stop_event.is_set():
            try:
                data, _overflow = stream.read(FRAME_SAMPLES)
            except Exception:
                logger.exception("stream.read failed")
                continue

            frame_bytes = bytes(data)
            currently_muted = self.state.muted

            # Diagnostics — periodic level report.
            try:
                samples = np.frombuffer(frame_bytes, dtype=np.int16)
                rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
            except Exception:
                rms = 0.0
            diag_frame_count += 1
            if rms > diag_max_rms:
                diag_max_rms = rms
            if not currently_muted:
                diag_unmuted_frames += 1
            if diag_frame_count >= 33:
                logger.info(
                    "mic 1s report: muted=%s unmuted_frames=%d max_rms=%.0f (RMS<200=silence, >2000=loud)",
                    currently_muted, diag_unmuted_frames, diag_max_rms,
                )
                diag_frame_count = 0
                diag_max_rms = 0
                diag_unmuted_frames = 0

            # Detect mute / unmute transitions BEFORE handling the frame.
            if last_muted is False and currently_muted is True:
                # Just clicked MUTE → user finished talking. Finalize.
                if utterance_frames:
                    pcm = b"".join(utterance_frames)
                    wav = pcm16_to_wav_bytes(pcm)
                    duration_ms = len(utterance_frames) * FRAME_MS
                    logger.info(
                        "utterance finalized on mute: %d ms, %d bytes WAV",
                        duration_ms, len(wav),
                    )
                    self._dispatch_utterance(wav)
                else:
                    logger.info("mute clicked with no audio recorded — skipping")
                utterance_frames = []
                next_partial_at = None
            elif last_muted is True and currently_muted is False:
                # Just clicked UNMUTE → start a fresh buffer + arm the
                # partial dispatcher.
                utterance_frames = []
                next_partial_at = time.monotonic() + PARTIAL_INTERVAL_S
                logger.info("recording started — click mic again to stop")

            last_muted = currently_muted

            if currently_muted:
                continue

            # Unmuted: accumulate the frame. Hard-cap to prevent a forgotten-mic
            # state from filling memory; auto-finalize and re-mute on cap.
            utterance_frames.append(frame_bytes)
            duration_ms = len(utterance_frames) * FRAME_MS
            if duration_ms >= MAX_UTTERANCE_S * 1000:
                pcm = b"".join(utterance_frames)
                wav = pcm16_to_wav_bytes(pcm)
                logger.warning(
                    "utterance hit MAX_UTTERANCE_S cap (%ds) — auto-finalizing + muting",
                    int(MAX_UTTERANCE_S),
                )
                self._dispatch_utterance(wav)
                utterance_frames = []
                next_partial_at = None
                self.state.set_muted(True)
                last_muted = True
                continue

            # Periodic partial dispatch for live transcription. Skip if no
            # consumer is wired, or if the buffer is too short to be useful.
            if (
                self._on_partial is not None
                and next_partial_at is not None
                and time.monotonic() >= next_partial_at
                and duration_ms >= PARTIAL_MIN_AUDIO_S * 1000
            ):
                partial_seq += 1
                pcm_so_far = b"".join(utterance_frames)
                wav_so_far = pcm16_to_wav_bytes(pcm_so_far)
                self._dispatch_partial(wav_so_far, partial_seq)
                next_partial_at = time.monotonic() + PARTIAL_INTERVAL_S

    def _dispatch_utterance(self, wav_bytes: bytes) -> None:
        """Send a finalized utterance to the orchestrator's event loop."""
        try:
            asyncio.run_coroutine_threadsafe(
                self._on_utterance(wav_bytes), self._loop
            )
        except Exception:
            logger.exception("dispatch failed")

    def _dispatch_partial(self, wav_bytes: bytes, seq: int) -> None:
        """Fire-and-forget a partial-buffer snapshot for live transcription."""
        if self._on_partial is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._on_partial(wav_bytes, seq), self._loop
            )
        except Exception:
            logger.exception("partial dispatch failed")
