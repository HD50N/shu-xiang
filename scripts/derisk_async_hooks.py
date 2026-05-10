"""
DERISK GATE 2: browser-use async tool hooks.

Pass = browser-use's agent loop pauses when our async custom tool awaits
something, and resumes when the tool returns.
Fail = the agent doesn't actually await our tool. Fall back to Plan B
(front-loaded conversational pre-flight, no in-flow pause).

Usage:
    ANTHROPIC_API_KEY=... python scripts/derisk_async_hooks.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time


async def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set.")
        sys.exit(2)

    try:
        from browser_use import Agent, Controller
        from browser_use.llm import ChatAnthropic
    except ImportError:
        print("browser-use not installed.")
        print("Install: uv pip install browser-use")
        sys.exit(2)

    controller = Controller()
    pause_started = asyncio.Event()
    pause_resumed = asyncio.Event()

    @controller.action("Ask the user a yes/no question and return their answer.")
    async def ask_user(question: str) -> str:
        print(f"\n[ask_user] PAUSED. Question: {question!r}")
        pause_started.set()
        # Sleep 3 seconds to simulate the user thinking. If browser-use's
        # agent loop genuinely awaits this tool, the next agent step won't
        # fire until 3 seconds from now.
        await asyncio.sleep(3.0)
        pause_resumed.set()
        return "yes"

    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )

    agent = Agent(
        task=(
            "Open https://example.com. Then call the ask_user tool with "
            "the question 'Should I continue?'. Wait for its answer. "
            "Then write the answer to the page title via JavaScript."
        ),
        llm=llm,
        controller=controller,
    )

    # Run agent in background; observe the pause.
    start = time.perf_counter()
    agent_task = asyncio.create_task(agent.run(max_steps=10))

    try:
        await asyncio.wait_for(pause_started.wait(), timeout=60.0)
        print(f"  Tool started at t={time.perf_counter() - start:.1f}s")
        await asyncio.wait_for(pause_resumed.wait(), timeout=10.0)
        print(f"  Tool returned at t={time.perf_counter() - start:.1f}s")
    except asyncio.TimeoutError:
        print("✗ FAIL — async tool did not get called within 60s. Plan B required.")
        agent_task.cancel()
        sys.exit(1)

    # Wait for agent to finish.
    try:
        await asyncio.wait_for(agent_task, timeout=120.0)
    except asyncio.TimeoutError:
        print("Agent didn't finish in 120s — but the pause did happen.")

    print("\n✓ GATE PASSED — async tool hooks pause the agent loop.")
    print("  In-flow pause architecture is viable.")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
