"""
Cold-open beat: deterministic Playwright fill of the autofill fields after
intent extraction returns the LLC schema.

Eng-review D10: cold-open uses page.fill() via corpus selectors, NOT
browser-use's perception loop. Total wall-clock target: under 2 seconds for
all six autofill fields.
"""

from __future__ import annotations

import asyncio
from typing import Iterable

from playwright.async_api import Page

from corpus import CORPUS_FIELDS, FieldKind, FieldSpec, selector_for

from agent.overlay_bridge import update_sidebar_field
from agent.state import LLCSchema


async def cold_open_fill(
    page: Page,
    schema: LLCSchema,
    target_env: str = "mock",
    stagger_ms: int = 200,
) -> list[str]:
    """
    Fill all autofill fields one by one with a small stagger so the cascade
    reads as an animation in the recording. Returns list of field keys filled.
    """
    filled: list[str] = []
    for field in CORPUS_FIELDS:
        if field.kind != FieldKind.AUTOFILL:
            continue
        value = getattr(schema, field.schema_key, None)
        if not value:
            continue
        sel = selector_for(target_env, field)
        await page.fill(sel, str(value))
        # Use schema_key (stable) so the sidebar row is found correctly.
        await update_sidebar_field(page, field.schema_key, str(value))
        filled.append(field.schema_key)
        if stagger_ms:
            await asyncio.sleep(stagger_ms / 1000)
    return filled


async def fill_judgment_field(
    page: Page,
    field: FieldSpec,
    value: str,
    target_env: str = "mock",
) -> None:
    """
    Fill a single judgment field. Handles radio groups, selects, and text
    inputs by inspecting the actual element rather than relying on
    enum_values metadata (which is also used for regex matching, not just
    form structure).
    """
    sel = selector_for(target_env, field)

    # Radio group: pick the radio whose value matches.
    if field.enum_values and "group" in sel:
        await page.click(f'{sel} input[type="radio"][value="{value}"]')
        return

    # Detect element type at runtime — corpus enum_values is for regex
    # matching, NOT a guarantee that the form element is a select.
    try:
        tag = await page.evaluate(
            f"() => document.querySelector({sel!r})?.tagName?.toLowerCase() || ''"
        )
    except Exception:
        tag = ""

    if tag == "select":
        await page.select_option(sel, value)
    else:
        # Default: text input or unknown — use fill()
        await page.fill(sel, str(value))
