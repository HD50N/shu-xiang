"""
browser-use integration for live-walkthrough mode.

Architecture (locked in eng review):
- Demo path uses deterministic Playwright fills + scripted in-flow pause.
- Live walkthrough mode uses browser-use as the agent loop, with a custom
  `ask_user_for_clarification` tool that bridges into the same clarification
  module used in recording mode. This is where browser-use earns its place
  in the pitch ("works on any English form").

This module is ONLY imported when DEMO_MODE=live_walkthrough so a stale
browser-use API doesn't block the recording-mode happy path.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

from playwright.async_api import Page

from corpus import FIELDS_BY_KEY, FieldSpec
from voice.intent_extraction import resolve_enum_answer

from agent.overlay_bridge import (
    hide_overlay,
    install_overlay,
    mark_listening,
    show_overlay,
)
from agent.state import LLCSchema

logger = logging.getLogger("shuxiang.browser_loop")


@dataclass
class BrowserUseConfig:
    """Subset of browser-use config we care about."""
    model: str = "claude-sonnet-4-6"
    max_steps: int = 30
    headless: bool = False


def build_clarification_tool(
    page: Page,
    schema: LLCSchema,
    voice_queue: asyncio.Queue,
):
    """
    Build the custom browser-use tool that browser-use's agent calls when it
    reaches a judgment field. The tool:
      1. Looks up the field in the corpus.
      2. Shows the bilingual overlay anchored to the field selector.
      3. Awaits a transcript on voice_queue.
      4. Resolves to enum value via regex/Haiku.
      5. Updates the orchestrator schema (single writer).
      6. Returns the resolved value back to browser-use.

    The function signature here matches browser-use's custom-tool pattern.
    The actual registration with the browser-use Controller happens in
    run_live_walkthrough below.
    """

    async def ask_user_for_clarification(
        field_key: str,
        field_selector: str,
    ) -> str:
        """
        Pause the agent loop, ask the user a Chinese question about
        `field_key`, return the chosen enum value.
        """
        field = FIELDS_BY_KEY.get(field_key)
        if not field:
            return "unknown"

        if not field.question_zh or not field.explanation_zh:
            return "unknown"

        await show_overlay(
            page,
            selector=field_selector,
            question=field.question_zh,
            explanation=field.explanation_zh,
        )

        try:
            transcript = await asyncio.wait_for(voice_queue.get(), timeout=300.0)
        except asyncio.TimeoutError:
            await mark_listening(page, "retry")
            await asyncio.sleep(0.6)
            await hide_overlay(page)
            return "unknown"

        value, source = await resolve_enum_answer(field_key, transcript)

        if value:
            schema.update_from({field_key: value})
            await mark_listening(page, "recorded")
            await asyncio.sleep(0.3)

        await hide_overlay(page)

        logger.info(
            "ask_user_for_clarification: %s = %r (source=%s)",
            field_key, value, source,
        )
        return value or "unknown"

    return ask_user_for_clarification


async def run_live_walkthrough(
    page: Page,
    schema: LLCSchema,
    voice_queue: asyncio.Queue,
    task: str,
    config: Optional[BrowserUseConfig] = None,
) -> None:
    """
    Run the live walkthrough mode. Imports browser-use lazily so recording
    mode never depends on it.

    `task` is the natural-language task description handed to browser-use.
    Example: "Fill out this Illinois LLC filing form using the data already
    entered and the user's voice answers via ask_user_for_clarification."
    """
    config = config or BrowserUseConfig()

    try:
        from browser_use import Agent, Controller
        from browser_use.llm import ChatAnthropic
    except ImportError as e:
        raise RuntimeError(
            "browser-use not installed. Live walkthrough requires it.\n"
            "Install: uv pip install browser-use"
        ) from e

    # Register the clarification tool.
    controller = Controller()
    clarify = build_clarification_tool(page, schema, voice_queue)

    # browser-use's @controller.action decorator pattern (verify against
    # current API tonight — this signature is the canonical one but the
    # exact decorator name has evolved across versions).
    @controller.action(
        "Pause the agent and ask the user a bilingual clarification question "
        "for a judgment field. Returns the enum value the user chose."
    )
    async def ask_user_for_clarification(
        field_key: str, field_selector: str
    ) -> str:
        return await clarify(field_key, field_selector)

    llm = ChatAnthropic(
        model=config.model,
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )

    agent = Agent(
        task=task,
        llm=llm,
        controller=controller,
        page=page,  # share the existing page instead of launching a new browser
    )
    await agent.run(max_steps=config.max_steps)
