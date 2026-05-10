"""
Scripted voice feeder — feeds pre-determined Chinese transcripts into the
asyncio voice_queue at scheduled times.

This is the recording-mode default: every "voice answer" the demo expects
arrives on a deterministic clock so the 180s storyboard hits its marks
regardless of live STT reliability.

For live walkthrough mode, swap this for voice/elevenlabs_voice.py
(stream_transcripts), which writes transcripts to the same queue.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable

logger = logging.getLogger("shuxiang.voice.scripted")


@dataclass
class ScriptedAnswer:
    """One scripted voice answer to feed into the orchestrator."""
    delay_s: float  # seconds AFTER the previous answer (or start) before pushing
    transcript_zh: str
    label: str = ""  # optional descriptor for logs


# The demo path's expected voice answers, in chronological order.
# This is the WORD-FOR-WORD freeze locked tonight (per eng-review D13 task 13).
DEMO_SCRIPT: list[ScriptedAnswer] = [
    ScriptedAnswer(
        delay_s=0.0,
        transcript_zh="我自己运营",  # member-managed
        label="management_structure",
    ),
]


async def feed_voice_queue(
    queue: asyncio.Queue,
    script: Iterable[ScriptedAnswer] = DEMO_SCRIPT,
    *,
    started_event: asyncio.Event | None = None,
) -> None:
    """
    Push scripted transcripts onto the queue at the scripted intervals.
    Awaits `started_event` first if provided (so the script aligns with the
    in-flow pause moment, not the demo start).
    """
    if started_event is not None:
        await started_event.wait()

    for entry in script:
        await asyncio.sleep(entry.delay_s)
        logger.info("scripted voice → queue: %r (%s)", entry.transcript_zh, entry.label)
        await queue.put(entry.transcript_zh)
