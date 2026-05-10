"""
ElevenLabs voice loop — handles BOTH sides of voice for the demo.

- TTS (text-to-speech): Multilingual v2 generates the scripted Chinese question
  audio. Pre-cached at design time so playback is sub-100ms during recording.
- STT (speech-to-text): Scribe (REST) for batched transcription, or the
  streaming WebSocket for live walkthrough mode. Pushes transcripts onto the
  same asyncio.Queue the orchestrator uses.

Single vendor for voice. One API key (ELEVENLABS_API_KEY). Swap-in replacement
for what was previously OpenAI Realtime.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Optional

import httpx

logger = logging.getLogger("shuxiang.voice.elevenlabs")


# Default voice IDs. Swap to a Mandarin-native voice tonight when the team
# picks one in the ElevenLabs voice library. Multilingual v2 covers Mandarin
# from any voice, but a native-Mandarin actor sounds more authentic.
DEFAULT_VOICE_ID_ZH = "pNInz6obpgDQGcFmaJgB"  # Adam — placeholder
DEFAULT_MODEL_TTS = "eleven_multilingual_v2"
DEFAULT_MODEL_STT = "scribe_v1"

_STT_LANGUAGE_CODES = {
    "zh": "zho",
    "zh-cn": "zho",
    "zh_cn": "zho",
    "chinese": "zho",
    "mandarin": "zho",
    "中文": "zho",
    "en": "eng",
    "en-us": "eng",
    "en_us": "eng",
    "english": "eng",
    "es": "spa",
    "spanish": "spa",
    "español": "spa",
    "fr": "fra",
    "french": "fra",
    "de": "deu",
    "german": "deu",
    "ja": "jpn",
    "japanese": "jpn",
    "ko": "kor",
    "korean": "kor",
    "ar": "ara",
    "arabic": "ara",
    "hi": "hin",
    "hindi": "hin",
    "ru": "rus",
    "russian": "rus",
    "pt": "por",
    "portuguese": "por",
    "it": "ita",
    "italian": "ita",
    "vi": "vie",
    "vietnamese": "vie",
    "th": "tha",
    "thai": "tha",
    "tr": "tur",
    "turkish": "tur",
    "nl": "nld",
    "dutch": "nld",
    "pl": "pol",
    "polish": "pol",
}


# ──────────────────────────────────────────────────────────────────────────
# TTS — pre-cache the scripted Chinese question audio
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class TTSConfig:
    voice_id: str = DEFAULT_VOICE_ID_ZH
    model: str = DEFAULT_MODEL_TTS
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0


def _build_tts_payload(text_zh: str, cfg: TTSConfig) -> tuple[str, dict, dict]:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{cfg.voice_id}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "text": text_zh,
        "model_id": cfg.model,
        "voice_settings": {
            "stability": cfg.stability,
            "similarity_boost": cfg.similarity_boost,
            "style": cfg.style,
            "use_speaker_boost": True,
        },
    }
    return url, headers, payload


async def synthesize_to_file(
    text_zh: str,
    output_path: Path,
    config: Optional[TTSConfig] = None,
) -> Path:
    """
    Render `text_zh` to an mp3 file. Used at design time to pre-cache the
    scripted Chinese question for the in-flow pause beat.
    """
    cfg = config or TTSConfig()
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    url, headers, payload = _build_tts_payload(text_zh, cfg)
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        output_path.write_bytes(resp.content)

    logger.info("TTS cached: %s (%d bytes)", output_path.name, len(resp.content))
    return output_path


async def synthesize_to_bytes(
    text_zh: str,
    config: Optional[TTSConfig] = None,
    *,
    timeout_s: float = 30.0,
) -> bytes:
    """
    Render `text_zh` to mp3 bytes in-memory. Used for dynamic TTS during the
    conversational intake — Sonnet generates a fresh question per turn, we
    synthesize and play without writing to disk.
    """
    cfg = config or TTSConfig()
    url, headers, payload = _build_tts_payload(text_zh, cfg)
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.content


# ──────────────────────────────────────────────────────────────────────────
# STT — Scribe REST for batched transcription
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class STTConfig:
    model: str = DEFAULT_MODEL_STT
    language_code: Optional[str] = "zho"  # ISO 639-3; None lets Scribe auto-detect.
    diarize: bool = False
    timestamps_granularity: str = "word"


def stt_language_code(language: str | None) -> Optional[str]:
    """Map a selected UI language to ElevenLabs Scribe's ISO 639-3 code."""
    override = os.environ.get("ELEVENLABS_STT_LANGUAGE_CODE")
    if override:
        return override.strip() or None
    value = (language or "").strip().lower()
    if not value:
        return "zho"
    return _STT_LANGUAGE_CODES.get(value)


async def transcribe_audio_bytes(
    audio_bytes: bytes,
    config: Optional[STTConfig] = None,
    *,
    mime_type: str = "audio/wav",
) -> str:
    """
    Transcribe a chunk of audio (e.g., a recorded user answer). Returns the
    transcript text. Used in live walkthrough mode after the user clicks mute.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    cfg = config or STTConfig()
    url = "https://api.elevenlabs.io/v1/speech-to-text"
    headers = {"xi-api-key": api_key}
    files = {"file": ("audio.wav", audio_bytes, mime_type)}
    data = {
        "model_id": cfg.model,
        "diarize": str(cfg.diarize).lower(),
        "timestamps_granularity": cfg.timestamps_granularity,
    }
    if cfg.language_code:
        data["language_code"] = cfg.language_code

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, files=files, data=data)
        resp.raise_for_status()
        body = resp.json()

    # Scribe returns {"text": "...", "words": [...], ...}
    return body.get("text", "").strip()


# ──────────────────────────────────────────────────────────────────────────
# STT streaming — for live walkthrough mode
# ──────────────────────────────────────────────────────────────────────────

async def stream_transcripts(
    queue: asyncio.Queue,
    audio_chunks: AsyncIterator[bytes],
    *,
    stop_event: Optional[asyncio.Event] = None,
    chunk_seconds: float = 1.5,
    language_code: Optional[str] = "zho",
) -> None:
    """
    Live walkthrough STT. Buffers `audio_chunks` from the mic (PCM 16k mono),
    sends each segmented utterance to Scribe, pushes the transcript onto
    `queue`.

    The actual VAD logic lives in the platform-specific mic-capture module
    that produces `audio_chunks`. This function is the segment → Scribe →
    queue pipeline. Tonight's task: wire a mic capture loop on macOS.
    """
    buffer = bytearray()
    last_flush = asyncio.get_event_loop().time()

    async for chunk in audio_chunks:
        if stop_event and stop_event.is_set():
            break
        buffer.extend(chunk)
        now = asyncio.get_event_loop().time()
        # Naive segmentation: flush every chunk_seconds. Replace with a real
        # VAD (e.g., webrtcvad) before live walkthrough demo.
        if now - last_flush >= chunk_seconds and len(buffer) > 0:
            audio_bytes = bytes(buffer)
            buffer.clear()
            last_flush = now
            try:
                transcript = await transcribe_audio_bytes(
                    audio_bytes,
                    config=STTConfig(language_code=language_code),
                    mime_type="audio/wav",
                )
                if transcript:
                    logger.info("transcript: %r", transcript)
                    await queue.put(transcript)
            except Exception as exc:  # noqa: BLE001
                logger.warning("STT chunk failed: %s", exc)
