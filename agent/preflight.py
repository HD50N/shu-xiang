"""
Pre-flight conversational intake.

In recording mode, the demo seeds from corpus.DEMO_SEED so the recording is
deterministic. In live walkthrough mode, this module runs the actual Chinese
conversation: capture the cold-open sentence via ElevenLabs Scribe → call
voice.intent_extraction.extract_cold_open() → merge results into the schema.

Built but not wired by default; demo_runner._stage_pre_flight uses the seeded
path. Switch via env var DEMO_MODE=live_walkthrough.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from voice.intent_extraction import extract_cold_open

from agent.state import LLCSchema

logger = logging.getLogger("shuxiang.preflight")


async def run_live_preflight(
    schema: LLCSchema,
    chinese_sentence: Optional[str] = None,
) -> dict:
    """
    Live walkthrough pre-flight: extract a Chinese sentence into structured
    fields and merge them into `schema`. Returns the extracted dict (raw).
    """
    if not chinese_sentence:
        # Real implementation calls voice.elevenlabs_voice.transcribe_audio_bytes
        # on the user's recorded intake; for now just refuse rather than silently
        # using the demo seed.
        raise RuntimeError(
            "Live pre-flight needs a Chinese sentence. "
            "Pipe one from voice/elevenlabs_voice.transcribe_audio_bytes."
        )

    result = await extract_cold_open(chinese_sentence)
    logger.info(
        "cold-open extraction: %dms, fields=%s",
        int(result.elapsed_ms), list(result.extracted.keys()),
    )

    # Map extracted dict to schema fields. Sole-owner shortcut: organizer is
    # also the registered agent.
    extracted = dict(result.extracted)
    if extracted.get("entity_name") and not extracted["entity_name"].endswith(("LLC", "L.L.C.")):
        extracted["entity_name"] = f"{extracted['entity_name']} LLC"

    if extracted.get("is_sole_owner"):
        # Default: organizer is also the registered agent. Address falls
        # back to principal address.
        if extracted.get("organizer_name"):
            extracted.setdefault("registered_agent_name", extracted["organizer_name"])
        # Address composition handled separately if/when we add geocoding.

    schema.update_from(extracted)
    return result.extracted
