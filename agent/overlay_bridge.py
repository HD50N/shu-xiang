"""
Python ↔ overlay bridge.

The overlay is a single JS file (overlay/inject.js) injected into the form page
via Playwright. This module wraps page.evaluate() calls so the orchestrator
talks to it through typed Python functions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import Page

from agent.i18n import Language, overlay_copy

_OVERLAY_JS_PATH = Path(__file__).resolve().parent.parent / "overlay" / "inject.js"


async def install_overlay(page: Page) -> None:
    """Inject the overlay script into the page. Idempotent."""
    if not _OVERLAY_JS_PATH.exists():
        raise FileNotFoundError(f"Overlay JS not found: {_OVERLAY_JS_PATH}")
    js = _OVERLAY_JS_PATH.read_text(encoding="utf-8")
    await page.add_init_script(js)
    # Also inject into the current page so we don't have to navigate first.
    await page.evaluate(js)


async def show_overlay(
    page: Page,
    selector: str,
    question: str,
    explanation: str,
    listening_label: Optional[str] = None,
) -> bool:
    return await page.evaluate(
        """({ selector, q, e, l }) => window.shuxiang.showOverlay({
            selector, questionZh: q, explanationZh: e, listeningLabelZh: l
        })""",
        {
            "selector": selector,
            "q": question,
            "e": explanation,
            "l": listening_label,
        },
    )


async def mark_listening(page: Page, state_label: str) -> None:
    await page.evaluate(
        "(s) => window.shuxiang.markListening(s)",
        state_label,
    )


async def hide_overlay(page: Page) -> None:
    await page.evaluate("() => window.shuxiang.hideOverlay()")


async def show_sidebar(page: Page, transcript: str, fields: list[dict]) -> None:
    """
    `fields` is a list of {"key": schema_key, "labelZh": str, "value": str | None}.
    `key` (the schema key) is the stable identifier for update_sidebar_field.
    """
    await page.evaluate(
        """({ t, f }) => window.shuxiang.showSidebar({ transcript: t, fields: f })""",
        {"t": transcript, "f": fields},
    )


async def update_sidebar_field(page: Page, schema_key: str, value: str) -> None:
    """Update a sidebar row by its stable schema_key (not display label)."""
    await page.evaluate(
        """({ k, v }) => window.shuxiang.updateSidebarField(k, v)""",
        {"k": schema_key, "v": value},
    )


async def hide_sidebar(page: Page) -> None:
    await page.evaluate("() => window.shuxiang.hideSidebar()")


async def show_toast(
    page: Page,
    text_zh: str,
    kind: str = "info",
    duration_ms: int = 3000,
) -> None:
    await page.evaluate(
        """({ k, t, d }) => window.shuxiang.showToast({ kind: k, textZh: t, durationMs: d })""",
        {"k": kind, "t": text_zh, "d": duration_ms},
    )


async def set_language(page: Page, language: Language) -> None:
    await page.evaluate(
        "(config) => window.shuxiang.setLanguage && window.shuxiang.setLanguage(config)",
        {"code": language, "copy": overlay_copy(language)},
    )


async def show_opening_prompt(page: Page, prompt: str) -> None:
    await page.evaluate(
        "(p) => window.shuxiang.showOpeningPrompt({ promptZh: p })",
        prompt,
    )


async def hide_opening_prompt(page: Page) -> None:
    await page.evaluate("() => window.shuxiang.hideOpeningPrompt()")


async def type_opening_transcript(page: Page, full_text: str, per_char_ms: int) -> None:
    """Type the user's sentence inside the opening prompt's transcript box."""
    await page.evaluate(
        """async ({ t, m }) => {
            await window.shuxiang.typeOpeningTranscript({ fullText: t, perCharMs: m });
        }""",
        {"t": full_text, "m": per_char_ms},
    )


async def update_live_transcript(page: Page, partial_text: str) -> None:
    """Replace the visible transcript-so-far in the opening prompt card.

    Called from the live-STT partial dispatcher to give the user real-time
    feedback as they speak (before they click mute to finalize). Bypasses the
    typewriter — just sets textContent directly on the existing span.
    No-op if the opening prompt isn't visible (e.g., during Phase 2)."""
    await page.evaluate(
        """(t) => {
            const wrap = document.querySelector('.shuxiang-opening-transcript');
            if (!wrap) return;
            const cursor = wrap.querySelector('.shuxiang-opening-transcript-cursor');
            let span = wrap.querySelector('span:not(.shuxiang-opening-transcript-cursor)');
            if (!span) {
                span = document.createElement('span');
                if (cursor) wrap.insertBefore(span, cursor);
                else wrap.appendChild(span);
            }
            span.textContent = t;
        }""",
        partial_text,
    )


async def type_transcript(page: Page, full_text: str, per_char_ms: int) -> None:
    """Type the transcript char-by-char in the sidebar (visible during demo)."""
    await page.evaluate(
        """async ({ t, m }) => {
            await window.shuxiang.typeTranscript({ fullText: t, perCharMs: m });
        }""",
        {"t": full_text, "m": per_char_ms},
    )


async def show_closing(page: Page, message: str) -> None:
    await page.evaluate(
        "(m) => window.shuxiang.showClosing({ messageZh: m })",
        message,
    )


async def install_mic_button(page: Page) -> None:
    """Render the floating mute/unmute button on the overlay."""
    await page.evaluate("() => window.shuxiang.installMicButton()")


async def set_mic_state_visual(page: Page, muted: bool) -> None:
    """Update the mic button's visual state (called when Python toggles state)."""
    await page.evaluate(
        "(m) => window.shuxiang.setMicState(m)",
        muted,
    )


async def hide_mic_button(page: Page) -> None:
    await page.evaluate("() => window.shuxiang.hideMicButton()")


async def show_checklist(
    page: Page,
    items: list[dict],
    *,
    header_zh: str = "为你的餐厅定制的清单",
    subtitle_zh: Optional[str] = None,
    summary_zh: Optional[str] = None,
    stagger_ms: int = 250,
) -> None:
    """
    Render the Phase 2 obligation map as a slide-in panel from the right.
    `items` is a list of dicts: {id, titleZh, titleEn, jurisdiction,
    descZh, citationUrl, timeMin, costUsd}.
    """
    await page.evaluate(
        """({items, h, s, sum, st}) => window.shuxiang.showChecklist({
            items, headerZh: h, subtitleZh: s, summaryZh: sum, staggerMs: st
        })""",
        {"items": items, "h": header_zh, "s": subtitle_zh, "sum": summary_zh, "st": stagger_ms},
    )


async def set_checklist_item_state(page: Page, item_id: str, state: Optional[str]) -> None:
    """Mark a checklist item as 'active' (highlighted) or 'done' (green check)."""
    await page.evaluate(
        "({id, st}) => window.shuxiang.setChecklistItemState(id, st)",
        {"id": item_id, "st": state},
    )


async def hide_checklist(page: Page) -> None:
    await page.evaluate("() => window.shuxiang.hideChecklist()")
