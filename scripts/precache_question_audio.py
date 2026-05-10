"""
Pre-cache all Chinese audio the demo plays through.

Three groups:
- Phase 1 conversation questions (4 turns)
- Phase 2 obligation map voice-over
- Phase 3 in-flow clarifications (4 fields)
- Closing chained next-step

All cached via ElevenLabs Multilingual v2 with whatever voice is set in
ELEVENLABS_VOICE_ID. Audio plays during the demo at sub-100ms latency.

Usage:
    ELEVENLABS_API_KEY=... python scripts/precache_question_audio.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from corpus import judgment_fields
from voice.elevenlabs_voice import TTSConfig, synthesize_to_file


CACHE_DIR = Path(__file__).resolve().parent.parent / "assets" / "audio_cache"


# ── Phase 1 conversation script (matches DEMO_TURNS in preflight_conversation.py)
PHASE1_AUDIO = {
    "phase1_q1_business": "你好！告诉我你的生意 — 你做什么，公司叫什么名字？",
    "phase1_q2_location": "你的店开在哪里？地址或者大概的位置都可以。",
    "phase1_q3_owner_hire": "你是唯一的所有者吗？打算雇人吗？",
    "phase1_q4_food_alcohol": "餐厁卖什么？只卖食物，还是也卖酒？",
}

# ── Conversational acknowledgments — played after the user answers each turn.
# Without these the AI feels mechanical (silent transition between turns).
# We rotate through a few so it doesn't sound like the same recording.
ACK_AUDIO = {
    "ack_1": "好的。",
    "ack_2": "明白了。",
    "ack_3": "知道了。",
    "ack_thinking": "好，让我想一下。",
}

# ── Phase 2 obligation map reveal voice-over
PHASE2_AUDIO = {
    "phase2_reveal": (
        "好的，我知道了。根据你的生意，我为你定制了一份合规清单。"
        "这些是你必须办的手续，按顺序处理。"
    ),
}

# ── Phase 3 chained next-step (after LLC submit)
CHAINED_AUDIO = {
    "chained_next_ein": (
        "LLC 已提交。下一步是 EIN — 联邦税号。"
        "这是你开商业银行账户的关键。要现在做吗？"
    ),
}


async def main():
    if not os.environ.get("ELEVENLABS_API_KEY"):
        print("ELEVENLABS_API_KEY not set — set it in .env first.")
        sys.exit(2)

    voice_id = os.environ.get("ELEVENLABS_VOICE_ID")
    config = TTSConfig(voice_id=voice_id) if voice_id else TTSConfig()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Caching to {CACHE_DIR}")
    print(f"Voice: {voice_id or '(default)'}")
    print()

    total = 0

    # Phase 3 in-flow clarifications (one per judgment field with question_zh)
    print("─── Phase 3: in-flow clarifications ───")
    for f in judgment_fields():
        if not f.question_zh:
            continue
        out = CACHE_DIR / f"{f.schema_key}.mp3"
        print(f"  → {f.schema_key}: {f.question_zh}")
        await synthesize_to_file(f.question_zh, out, config)
        total += 1

    # Phase 1 conversation
    print("\n─── Phase 1: conversation turns ───")
    for key, text in PHASE1_AUDIO.items():
        out = CACHE_DIR / f"{key}.mp3"
        print(f"  → {key}: {text}")
        await synthesize_to_file(text, out, config)
        total += 1

    # Acknowledgments (between Phase 1 turns)
    print("\n─── Conversational acknowledgments ───")
    for key, text in ACK_AUDIO.items():
        out = CACHE_DIR / f"{key}.mp3"
        print(f"  → {key}: {text}")
        await synthesize_to_file(text, out, config)
        total += 1

    # Phase 2 reveal
    print("\n─── Phase 2: obligation map reveal ───")
    for key, text in PHASE2_AUDIO.items():
        out = CACHE_DIR / f"{key}.mp3"
        print(f"  → {key}: {text}")
        await synthesize_to_file(text, out, config)
        total += 1

    # Chained next-step
    print("\n─── Chained close: next-step gesture ───")
    for key, text in CHAINED_AUDIO.items():
        out = CACHE_DIR / f"{key}.mp3"
        print(f"  → {key}: {text}")
        await synthesize_to_file(text, out, config)
        total += 1

    print(f"\nDone. Cached {total} audio files to {CACHE_DIR}")
    print(f"Verify the audio plays cleanly:")
    print(f"  open {CACHE_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
