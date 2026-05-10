"""
Demo pacing presets — controls how long each beat holds.

The 7-second smoke run is correct for dev iteration ("does the wiring work?").
For recording, every beat needs to land — the user speaks, fields cascade,
the agent visibly pauses, the user reads the explanation, voice answers,
ring greens, demo continues, PDF appears, closing message holds.

Locked from /plan-design-review's 180s storyboard, compressed to ~75-90s.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DemoPacing:
    """All wall-clock timings in seconds, all stagger in ms."""

    # Opening scene (NEW)
    opening_prompt_hold_s: float        # how long the "用中文告诉我你的生意" toast shows alone
    typewriter_char_ms: int             # per-char delay for simulated speech in sidebar
    sentence_to_extraction_pause_s: float  # pause between sentence finished and extraction starting

    # Cold-open beat
    cold_open_stagger_ms: int           # delay between each of six fields filling
    cold_open_after_done_pause_s: float # pause after all six filled (let judge see the result)

    # In-flow pause beat
    in_flow_pre_voice_hold_s: float     # how long overlay shows BEFORE scripted voice fires
    in_flow_post_audio_pause_s: float   # pause after question audio finishes, before listening
    in_flow_listening_visible_s: float  # how long listening dots stay visible before answer arrives
    in_flow_recorded_hold_s: float      # how long ring stays green after answer + before fade
    in_flow_after_fill_pause_s: float   # pause after fill, before continuing

    # Continue stage
    judgment_fill_stagger_s: float      # pause between remaining judgment fields
    pre_submit_pause_s: float           # pause before clicking submit
    post_submit_pause_s: float          # pause after submit (let confirmation render)

    # PDF beat
    pdf_generating_toast_s: float       # how long "正在生成..." toast shows
    pdf_done_toast_s: float             # how long "完成!" toast shows

    # Closing scene (NEW)
    closing_message_hold_s: float       # how long final closing toast holds


PRESET_FAST = DemoPacing(
    opening_prompt_hold_s=0.0,
    typewriter_char_ms=0,
    sentence_to_extraction_pause_s=0.0,
    cold_open_stagger_ms=200,
    cold_open_after_done_pause_s=0.4,
    in_flow_pre_voice_hold_s=0.6,
    in_flow_post_audio_pause_s=0.0,
    in_flow_listening_visible_s=0.0,
    in_flow_recorded_hold_s=0.3,
    in_flow_after_fill_pause_s=0.0,
    judgment_fill_stagger_s=0.15,
    pre_submit_pause_s=0.5,
    post_submit_pause_s=1.0,
    pdf_generating_toast_s=0.0,  # the toast itself has internal duration
    pdf_done_toast_s=0.4,
    closing_message_hold_s=0.0,
)


PRESET_DEMO = DemoPacing(
    # Opening: 5–8s
    opening_prompt_hold_s=2.5,
    typewriter_char_ms=80,            # ~3s for the demo sentence
    sentence_to_extraction_pause_s=1.2,
    # Cold-open: 4–5s
    cold_open_stagger_ms=600,         # ~3.6s for six fields, readable cascade
    cold_open_after_done_pause_s=2.0,
    # In-flow pause: 12–18s (the centerpiece beat)
    in_flow_pre_voice_hold_s=2.0,     # let judge see ring + start reading
    in_flow_post_audio_pause_s=2.5,   # let judge READ the Chinese explanation
    in_flow_listening_visible_s=1.5,  # listening dots breathe
    in_flow_recorded_hold_s=1.0,      # green ring lands
    in_flow_after_fill_pause_s=1.5,
    # Continue: 4–6s
    judgment_fill_stagger_s=0.8,
    pre_submit_pause_s=1.5,
    post_submit_pause_s=2.0,
    # PDF: 5–7s
    pdf_generating_toast_s=2.5,
    pdf_done_toast_s=3.5,
    # Closing: 3–4s
    closing_message_hold_s=3.5,
)


def get_pacing() -> DemoPacing:
    """
    Choose preset from env. Default to 'demo' so a fresh run looks like a
    demo, not a smoke test. Set PACING=fast for dev iteration.
    """
    preset = os.environ.get("PACING", "demo").lower()
    if preset == "fast":
        return PRESET_FAST
    return PRESET_DEMO
