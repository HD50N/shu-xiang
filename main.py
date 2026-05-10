"""
Shu Xiang demo — entry point.

Modes (via DEMO_MODE env var):
- recording (default): seeded data, scripted voice, local mock form
- live_walkthrough: live ElevenLabs voice loop (Scribe in / Multilingual v2 out), live IL SOS site

Usage:
    python main.py
    TARGET_ENV=live python main.py    # use real IL SOS instead of mock
    DEMO_MODE=live_walkthrough python main.py
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()  # read .env if present

from agent.demo_runner import main as runner_main


if __name__ == "__main__":
    try:
        asyncio.run(runner_main())
    except KeyboardInterrupt:
        sys.exit(130)
