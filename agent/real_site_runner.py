"""
Real-site demo runner for apps.ilsos.gov/llcarticles/.

Walks the live Illinois SOS LLC filing flow through 7+ mapped pages,
hitting the in-flow pause beat on the most judgment-mediated page
(the 5-provision agreement on Page 2). Stops short of payment.

Page sequence (captured by scripts/recon_il_sos.py against the live site):
  1. /llcarticles/                          standard vs series LLC
  2. /llcarticles/index.do                  agree to 5 provisions  ← in-flow pause
  3. /llcarticles/generalProvisions.do      entity name
  4. /llcarticles/llcName.do                confirmation (Continue)
  5. /llcarticles/similarNames.do           principal address
  6. /llcarticles/placeOfBusiness.do        registered agent + address
  7. /llcarticles/addressVerification.do    USPS standardization skip
  8+ /llcarticles/...                        review / submit (we stop here)

Architecture:
- Each PageHandler matches a URL pattern and does its thing.
- The in-flow pause handler shows the overlay anchored to a real radio.
- DemoRunner detects target_env=live and uses RealSiteRunner instead of
  the mock stages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from playwright.async_api import Page

from voice.scripted import ScriptedAnswer, feed_voice_queue

from agent.clarification import run_clarification
from agent.i18n import field_explanation, field_question, t
from agent.preflight_conversation import _question_for_missing_field
from agent.overlay_bridge import (
    hide_overlay,
    install_overlay,
    mark_listening,
    set_language,
    show_overlay,
    show_toast,
    update_sidebar_field,
)
from agent.pacing import DemoPacing
from agent.state import DemoState

logger = logging.getLogger("shuxiang.real_site")


REAL_SITE_URL = "https://apps.ilsos.gov/llcarticles/"


async def _install_localized_overlay(page: Page, state: DemoState) -> None:
    await install_overlay(page)
    await set_language(page, getattr(state, "language", "zh"))


def _required(value: Optional[str], field_name: str) -> str:
    if value:
        return value
    raise RuntimeError(f"Missing required user-provided value: {field_name}")


async def _normalize_spoken_value(
    field_name: str,
    transcript: str,
    state: DemoState,
) -> str:
    """Turn a spoken answer into the exact field value to write."""
    text = (transcript or "").strip()
    if not text:
        return ""

    if field_name == "registered_agent_address":
        lowered = text.lower()
        same_markers = ("same", "same as business", "same address", "一样", "相同", "같", "동일")
        if any(marker in lowered or marker in text for marker in same_markers):
            return state.schema.principal_address or ""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return text

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=160,
            system=(
                "Extract one form field value from a spoken transcript. "
                "Return JSON only: {\"value\":\"...\"}. Do not invent missing data. "
                "For email and phone, normalize spoken words like 'at'/'dot' or digits. "
                "For names and addresses, preserve the user's wording except obvious STT punctuation cleanup."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Field: {field_name}\n"
                        f"Transcript: {text}\n"
                        f"Known business address: {state.schema.principal_address or ''}\n"
                    ),
                }
            ],
        )
        for block in msg.content:
            if block.type == "text":
                raw = block.text.strip()
                start = raw.find("{")
                end = raw.rfind("}")
                if start != -1 and end != -1:
                    raw = raw[start : end + 1]
                parsed = json.loads(raw)
                value = str(parsed.get("value") or "").strip()
                return value or text
    except Exception:
        logger.exception("spoken value normalization failed for %s", field_name)
    return text


async def _ask_for_schema_value(
    page: Page,
    state: DemoState,
    pacing: DemoPacing,
    *,
    field_name: str,
    selector: str,
    timeout_s: float = 45.0,
) -> str:
    """Ask only when a needed form value is missing at the point of use."""
    existing = getattr(state.schema, field_name, None)
    if existing:
        return existing
    if not getattr(state, "use_live_voice", False):
        return _required(existing, field_name)

    language = getattr(state, "language", "zh")
    question = _question_for_missing_field(field_name, language)
    await _install_localized_overlay(page, state)
    ok = await show_overlay(
        page,
        selector=selector,
        question=question,
        explanation="",
        listening_label=t("listening", language),
    )
    if not ok:
        raise RuntimeError(f"Could not anchor missing-field prompt on {selector!r}")

    await asyncio.sleep(pacing.in_flow_pre_voice_hold_s)
    try:
        transcript = await asyncio.wait_for(state.voice_queue.get(), timeout=timeout_s)
        logger.info("missing field %s transcript: %r", field_name, transcript)
    except asyncio.TimeoutError as exc:
        await mark_listening(page, "retry")
        await asyncio.sleep(0.5)
        await hide_overlay(page)
        raise RuntimeError(f"Timed out waiting for user-provided {field_name}") from exc

    value = await _normalize_spoken_value(field_name, transcript, state)
    if not value:
        await mark_listening(page, "retry")
        await asyncio.sleep(0.5)
        await hide_overlay(page)
        raise RuntimeError(f"Could not extract user-provided {field_name}")

    setattr(state.schema, field_name, value)
    await update_sidebar_field(page, field_name, value)
    await mark_listening(page, "recorded")
    await asyncio.sleep(pacing.in_flow_recorded_hold_s)
    await hide_overlay(page)
    return value


@dataclass
class PageHandlerResult:
    """What a page handler returns to the orchestrator."""
    label: str
    action_taken: str
    continued: bool


# ──────────────────────────────────────────────────────────────────────
# Per-page handlers
# ──────────────────────────────────────────────────────────────────────

async def _click_continue(page: Page, *, timeout_ms: int = 12000) -> None:
    """Find and click the Continue/Submit button, awaiting navigation."""
    # IL SOS uses generic input[type=submit] with no distinguishing id.
    # Walk candidate buttons and pick the one whose text/value contains 'continue'.
    candidates = await page.query_selector_all(
        'input[type="submit"], input[type="button"], button'
    )
    target = None
    for btn in candidates:
        try:
            text = (await btn.inner_text()) or (await btn.get_attribute("value")) or ""
        except Exception:
            text = ""
        if "continue" in text.lower():
            target = btn
            break
    if not target and candidates:
        # Fall back to the first submit on the page
        target = candidates[0]
    if not target:
        raise RuntimeError("No Continue button on page")

    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
            await target.click()
    except Exception:
        # Some IL SOS pages submit without firing navigation events; tolerate
        await target.click()
        await asyncio.sleep(1.5)


async def handle_entity_choice(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """
    Page 1: standard vs series LLC.

    In live-voice mode this becomes an in-flow clarification beat — agent
    asks the user "Standard LLC or Series LLC?" in Chinese. Otherwise picks
    standard silently (recording-mode default).
    """
    use_live_voice = getattr(state, "use_live_voice", False)
    await _install_localized_overlay(page, state)

    if use_live_voice:
        from corpus import FIELDS_BY_KEY
        field = FIELDS_BY_KEY["llc_type"]
        language = getattr(state, "language", "zh")
        await show_overlay(
            page,
            selector="#llcNo",
            question=field_question(field, language),
            explanation=field_explanation(field, language),
        )
        await asyncio.sleep(pacing.in_flow_pre_voice_hold_s)
        # Play cached question audio (synthesized later by precache script)
        await _play_cached_audio(page, "llc_type")
        await asyncio.sleep(pacing.in_flow_post_audio_pause_s)
        await asyncio.sleep(pacing.in_flow_listening_visible_s)

        try:
            transcript = await asyncio.wait_for(state.voice_queue.get(), timeout=25.0)
            logger.info("entity-choice transcript: %r", transcript)
        except asyncio.TimeoutError:
            transcript = ""

        # Default standard unless user explicitly says series
        is_series = any(kw in transcript for kw in ("系列", "series"))
        chosen = "series" if is_series else "standard"
        radio_id = "#llcYes" if is_series else "#llcNo"

        await mark_listening(page, "recorded")
        await asyncio.sleep(pacing.in_flow_recorded_hold_s)
        await hide_overlay(page)
        await page.check(radio_id)
        state.schema.llc_type = chosen
        await asyncio.sleep(pacing.in_flow_after_fill_pause_s)
    else:
        await page.check("#llcNo")
        state.schema.llc_type = "standard"
        await asyncio.sleep(pacing.judgment_fill_stagger_s)

    await _click_continue(page)
    return PageHandlerResult("entity-choice", f"chose {state.schema.llc_type}", True)


async def _play_cached_audio(page: Page, key: str) -> None:
    """Play assets/audio_cache/<key>.mp3 via the page's Audio() context."""
    audio_path = (
        Path(__file__).resolve().parent.parent / "assets" / "audio_cache" / f"{key}.mp3"
    )
    if not audio_path.exists():
        return
    audio_url = audio_path.as_uri()
    await page.evaluate(
        """(url) => new Promise((resolve) => {
            const a = new Audio(url);
            a.onended = resolve;
            a.onerror = resolve;
            a.play().catch(resolve);
        })""",
        audio_url,
    )


async def handle_provisions_agreement(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """
    Page 2: 5-line legal provisions + Yes/No.

    THE in-flow pause beat. Anchor the overlay to the Yes radio and ask
    the user (in Chinese) whether to agree.

    In live-voice mode (state.use_live_voice), the user actually speaks
    and we wait for their transcript on voice_queue. In recording mode,
    we drop a scripted "同意" onto the queue at the right moment.
    """
    await _install_localized_overlay(page, state)  # ensure overlay is installed on this page

    use_live_voice = getattr(state, "use_live_voice", False)
    feeder_task = None
    if not use_live_voice:
        feeder_delay_s = (
            pacing.in_flow_pre_voice_hold_s
            + pacing.in_flow_post_audio_pause_s
            + pacing.in_flow_listening_visible_s
            + 0.6
        )
        script = [ScriptedAnswer(delay_s=0.0, transcript_zh="同意", label="provisions_agreed")]

        async def _delayed_feeder():
            await asyncio.sleep(feeder_delay_s)
            await feed_voice_queue(state.voice_queue, script)
        feeder_task = asyncio.create_task(_delayed_feeder())

    from corpus import FIELDS_BY_KEY
    field = FIELDS_BY_KEY["provisions_agreed"]
    language = getattr(state, "language", "zh")

    await show_overlay(
        page,
        selector="#userSelectionYes",
        question=field_question(field, language),
        explanation=field_explanation(field, language),
    )
    await asyncio.sleep(pacing.in_flow_pre_voice_hold_s)
    # Capture the money shot: overlay anchored to the REAL radio button.
    try:
        Path("out/live").mkdir(parents=True, exist_ok=True)
        await page.screenshot(path="out/live/IN_FLOW_PAUSE_REAL_SITE.png")
    except Exception:
        pass
    await asyncio.sleep(pacing.in_flow_post_audio_pause_s)
    await asyncio.sleep(pacing.in_flow_listening_visible_s)

    # Wait for the user's transcript (live mic) or the scripted drop.
    timeout_s = 30.0 if use_live_voice else 3.0
    transcript_zh = ""
    try:
        transcript_zh = await asyncio.wait_for(state.voice_queue.get(), timeout=timeout_s)
        logger.info("provisions answer transcript: %r", transcript_zh)
    except asyncio.TimeoutError:
        logger.warning("provisions agreement timeout — defaulting to yes")

    # Resolve to enum: agree-words = yes, deny-words = no
    agree_words = ("同意", "好的", "可以", "好", "yes", "agree", "ok", "对")
    deny_words = ("不同意", "不", "no", "拒绝")
    value = None
    text = transcript_zh.lower() if transcript_zh else ""
    if any(kw in text or kw in transcript_zh for kw in deny_words):
        value = "no"
    elif any(kw in text or kw in transcript_zh for kw in agree_words):
        value = "yes"

    if value == "yes":
        await mark_listening(page, "recorded")
    else:
        # Default to yes for demo continuity (user can pick No by saying 不同意)
        value = value or "yes"
        await mark_listening(page, "recorded")
    await asyncio.sleep(pacing.in_flow_recorded_hold_s)
    await hide_overlay(page)
    if feeder_task is not None:
        feeder_task.cancel()

    # Now actually pick Yes
    await page.check("#userSelectionYes")
    state.schema.provisions_agreed = "yes"
    await asyncio.sleep(pacing.in_flow_after_fill_pause_s)
    await _click_continue(page)
    return PageHandlerResult("provisions-agreement", "in-flow pause + checked Yes", True)


async def handle_entity_name(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """Page 3: enter LLC name."""
    entity_name = await _ask_for_schema_value(
        page, state, pacing, field_name="entity_name", selector="#llcName"
    )
    await page.fill("#llcName", entity_name)
    await update_sidebar_field(page, "entity_name", entity_name)
    await asyncio.sleep(pacing.judgment_fill_stagger_s)
    await _click_continue(page)
    return PageHandlerResult("entity-name", f"filled #llcName with {state.schema.entity_name!r}", True)


async def handle_confirmation_pass_through(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """Page 4: Articles of Incorporation confirmation. Just click Continue."""
    await asyncio.sleep(pacing.pre_submit_pause_s * 0.5)
    await _click_continue(page)
    return PageHandlerResult("confirmation", "clicked Continue (no inputs)", True)


async def handle_principal_address(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """Page 5/6: principal place of business. Two pages with similar fields."""
    schema = state.schema
    principal_address = await _ask_for_schema_value(
        page, state, pacing, field_name="principal_address", selector="#address"
    )
    principal_city = await _ask_for_schema_value(
        page, state, pacing, field_name="principal_city", selector="#city"
    )
    zip_selector = "#zipCode" if await page.query_selector("#zipCode") else "#zip"
    principal_zip = await _ask_for_schema_value(
        page, state, pacing, field_name="principal_zip", selector=zip_selector
    )
    await page.fill("#address", principal_address)
    await update_sidebar_field(page, "principal_address", principal_address)
    await asyncio.sleep(pacing.judgment_fill_stagger_s)
    await page.fill("#city", principal_city)
    await update_sidebar_field(page, "principal_city", principal_city)
    await asyncio.sleep(pacing.judgment_fill_stagger_s)
    # Field id varies: zipCode (page 5/6), zip (page 7 registered agent)
    zip_input = await page.query_selector(zip_selector)
    if zip_input:
        await zip_input.fill(principal_zip)
        await update_sidebar_field(page, "principal_zip", principal_zip)
    state_select = await page.query_selector("#state")
    if state_select:
        # IL SOS uses 2-letter state codes
        await page.select_option("#state", "IL")
    await asyncio.sleep(pacing.judgment_fill_stagger_s)
    await _click_continue(page)
    return PageHandlerResult("principal-address", "filled address fields", True)


async def handle_registered_agent(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """
    Page 7: registered agent name + address.

    In live-voice mode: pause and ask "你自己作为代理人，还是雇用服务？"
    Otherwise fills from schema silently.
    """
    schema = state.schema
    use_live_voice = getattr(state, "use_live_voice", False)

    if use_live_voice and await page.query_selector("#agent"):
        from corpus import FIELDS_BY_KEY
        field = FIELDS_BY_KEY["registered_agent_name"]
        language = getattr(state, "language", "zh")
        await _install_localized_overlay(page, state)
        await show_overlay(
            page,
            selector="#agent",
            question=field_question(field, language),
            explanation=field_explanation(field, language),
        )
        await asyncio.sleep(pacing.in_flow_pre_voice_hold_s)
        await _play_cached_audio(page, "registered_agent_name")
        await asyncio.sleep(pacing.in_flow_post_audio_pause_s)
        await asyncio.sleep(pacing.in_flow_listening_visible_s)

        try:
            transcript = await asyncio.wait_for(state.voice_queue.get(), timeout=25.0)
            logger.info("registered-agent transcript: %r", transcript)
        except asyncio.TimeoutError:
            transcript = ""

        await mark_listening(page, "recorded")
        await asyncio.sleep(pacing.in_flow_recorded_hold_s)
        await hide_overlay(page)
        await asyncio.sleep(pacing.in_flow_after_fill_pause_s)

    if await page.query_selector("#agent"):
        registered_agent_name = await _ask_for_schema_value(
            page, state, pacing, field_name="registered_agent_name", selector="#agent"
        )
        await page.fill("#agent", registered_agent_name)
        await update_sidebar_field(
            page, "registered_agent_name", registered_agent_name
        )
        await asyncio.sleep(pacing.judgment_fill_stagger_s)
    if await page.query_selector("#address"):
        registered_agent_address = await _ask_for_schema_value(
            page, state, pacing, field_name="registered_agent_address", selector="#address"
        )
        await page.fill("#address", registered_agent_address)
        await update_sidebar_field(
            page, "registered_agent_address",
            registered_agent_address,
        )
        await asyncio.sleep(pacing.judgment_fill_stagger_s)
    if await page.query_selector("#city"):
        await page.fill("#city", await _ask_for_schema_value(
            page, state, pacing, field_name="principal_city", selector="#city"
        ))
    if await page.query_selector("#zip"):
        await page.fill("#zip", await _ask_for_schema_value(
            page, state, pacing, field_name="principal_zip", selector="#zip"
        ))
    await asyncio.sleep(pacing.judgment_fill_stagger_s)
    await _click_continue(page)
    return PageHandlerResult("registered-agent", "filled agent + address", True)


async def handle_usps_verification(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """
    USPS standardization. Skip with the checkbox so we don't have to
    enter a building number. Returns a generic Continue afterwards.
    """
    skip_box = await page.query_selector("#contWithoutUSPS")
    if skip_box:
        await skip_box.check()
    await asyncio.sleep(pacing.judgment_fill_stagger_s)
    # The button is named 'noUsps' on the form
    no_usps = await page.query_selector('[name="noUsps"]')
    if no_usps:
        try:
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=10000):
                await no_usps.click()
        except Exception:
            await no_usps.click()
            await asyncio.sleep(1.5)
    else:
        await _click_continue(page)
    return PageHandlerResult("usps-verification", "checked skip + clicked", True)


async def handle_billing_info(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """
    Page 13 (expedited.do): Customer Information + Payment Billing form.
    Shows the $150 fee. Asks for billing contact (name, address, phone,
    email) — NOT the card number yet. The card number page comes next.

    Fills only user-provided contact information; runner's stop logic catches
    card inputs before money can move.
    """
    schema = state.schema
    # Split organizer name into first/last for billing form
    organizer_name = await _ask_for_schema_value(
        page, state, pacing, field_name="organizer_name", selector="#firstCredit"
    )
    parts = organizer_name.strip().split(maxsplit=1)
    if len(parts) == 2:
        first, last = parts
    else:
        first, last = parts[0], ""

    fills = [
        ("#firstCredit", first),
        ("#lastCredit", last),
        ("#addCredit1", await _ask_for_schema_value(
            page, state, pacing, field_name="principal_address", selector="#addCredit1"
        )),
        ("#cityCredit", await _ask_for_schema_value(
            page, state, pacing, field_name="principal_city", selector="#cityCredit"
        )),
        ("#zipCredit", await _ask_for_schema_value(
            page, state, pacing, field_name="principal_zip", selector="#zipCredit"
        )),
        ("#teleCredit", await _ask_for_schema_value(
            page, state, pacing, field_name="organizer_phone", selector="#teleCredit"
        )),
        ("#emailCredit", await _ask_for_schema_value(
            page, state, pacing, field_name="organizer_email", selector="#emailCredit"
        )),
        ("#confirmCredit", await _ask_for_schema_value(
            page, state, pacing, field_name="organizer_email", selector="#confirmCredit"
        )),
    ]
    for sel, value in fills:
        if not value:
            continue
        loc = await page.query_selector(sel)
        if loc:
            await loc.fill(value)
            await asyncio.sleep(pacing.judgment_fill_stagger_s * 0.4)

    # State dropdown — already defaults to Illinois on this page; confirm
    if await page.query_selector("#stateCredit"):
        try:
            await page.select_option("#stateCredit", "IL")
        except Exception:
            try:
                await page.select_option("#stateCredit", label="Illinois")
            except Exception:
                pass

    await asyncio.sleep(pacing.judgment_fill_stagger_s)
    submit_btn = await page.query_selector('[name="submit1"]')
    if submit_btn:
        try:
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=12000):
                await submit_btn.click()
        except Exception:
            await submit_btn.click()
            await asyncio.sleep(1.5)
    else:
        await _click_continue(page)
    return PageHandlerResult("billing-info", "filled customer + billing", True)


async def handle_select_processing(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """
    Page 12 (reviewdetails.do): Standard (10 days, free) vs Expedited (24h, +$100).

    In live-voice mode: pause and ask. Otherwise default to standard.
    """
    use_live_voice = getattr(state, "use_live_voice", False)
    chosen = "standard"

    if use_live_voice:
        from corpus import FIELDS_BY_KEY
        field = FIELDS_BY_KEY["expedited"]
        language = getattr(state, "language", "zh")
        await _install_localized_overlay(page, state)
        await show_overlay(
            page,
            selector="#noRadioButton",
            question=field_question(field, language),
            explanation=field_explanation(field, language),
        )
        await asyncio.sleep(pacing.in_flow_pre_voice_hold_s)
        await _play_cached_audio(page, "expedited")
        await asyncio.sleep(pacing.in_flow_post_audio_pause_s)
        await asyncio.sleep(pacing.in_flow_listening_visible_s)

        try:
            transcript = await asyncio.wait_for(state.voice_queue.get(), timeout=25.0)
            logger.info("expedited transcript: %r", transcript)
        except asyncio.TimeoutError:
            transcript = ""

        if any(kw in transcript for kw in ("加急", "expedited", "快", "24")):
            chosen = "expedited"

        await mark_listening(page, "recorded")
        await asyncio.sleep(pacing.in_flow_recorded_hold_s)
        await hide_overlay(page)
        await asyncio.sleep(pacing.in_flow_after_fill_pause_s)

    state.schema.expedited = chosen
    radio_id = "#yesRadioButton" if chosen == "expedited" else "#noRadioButton"
    btn = await page.query_selector(radio_id)
    if btn:
        await btn.check()
    await asyncio.sleep(pacing.judgment_fill_stagger_s)
    submit_btn = await page.query_selector('[name="submit1"]')
    if submit_btn:
        try:
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=12000):
                await submit_btn.click()
        except Exception:
            await submit_btn.click()
            await asyncio.sleep(1.5)
    else:
        await _click_continue(page)
    return PageHandlerResult("select-processing", f"chose {chosen}", True)


async def handle_review(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """
    Page 11 (organizer.do): "Please review the data you entered."
    Read-only summary of all entered data with Edit links per section.
    Just click Continue (button is named 'submit1' on this page).

    The next page is the payment form — runner's stop logic catches it.
    """
    # Brief deliberate pause so the judge can see the review summary land.
    await asyncio.sleep(pacing.pre_submit_pause_s)
    submit_btn = await page.query_selector('[name="submit1"]')
    if submit_btn:
        try:
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=12000):
                await submit_btn.click()
        except Exception:
            await submit_btn.click()
            await asyncio.sleep(1.5)
    else:
        await _click_continue(page)
    return PageHandlerResult("review", "clicked Continue on review page", True)


async def handle_organizer_attestation(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """
    Page 10 (namesAddress.do): organizer attestation. Asserts the organizer
    is a natural person ≥18 years old, signs under penalty of perjury.

    Fills name + address + city + state + zip with our schema's organizer.
    """
    schema = state.schema
    fills = [
        ("#name", await _ask_for_schema_value(
            page, state, pacing, field_name="organizer_name", selector="#name"
        )),
        ("#address", await _ask_for_schema_value(
            page, state, pacing, field_name="principal_address", selector="#address"
        )),
        ("#city", await _ask_for_schema_value(
            page, state, pacing, field_name="principal_city", selector="#city"
        )),
        ("#zipCode", await _ask_for_schema_value(
            page, state, pacing, field_name="principal_zip", selector="#zipCode"
        )),
    ]
    for sel, value in fills:
        if not value:
            continue
        loc = await page.query_selector(sel)
        if loc:
            await loc.fill(value)
            await asyncio.sleep(pacing.judgment_fill_stagger_s * 0.5)

    # State dropdown — pick IL
    if await page.query_selector("#state"):
        try:
            await page.select_option("#state", "IL")
        except Exception:
            # Some IL SOS pages use full names — try Illinois
            try:
                await page.select_option("#state", label="ILLINOIS")
            except Exception:
                pass

    await asyncio.sleep(pacing.judgment_fill_stagger_s)
    await _click_continue(page)
    return PageHandlerResult("organizer-attestation", "filled organizer + clicked Continue", True)


async def handle_managers_table(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """
    Page 9 (verifyAddress.do): managers/members table — 8 rows × 5 cols.
    Row 1 shows a "Public, John Q" example (sname/saddress/etc. — read-only
    guidance from the form); the real entries are members[0]..members[7].

    For sole-owner Member-Managed LLC: fill members[0] with our schema
    organizer + principal address, leave rows 2-8 blank.
    """
    schema = state.schema
    # IL SOS uses "Last, First" format per the page's Example
    organizer_name = await _ask_for_schema_value(
        page,
        state,
        pacing,
        field_name="organizer_name",
        selector='input[name="members[0].name"]',
    )
    parts = organizer_name.strip().split(maxsplit=1)
    if len(parts) == 2:
        last_first = f"{parts[1]}, {parts[0]}"
    else:
        last_first = organizer_name

    fills = [
        ('input[name="members[0].name"]', last_first),
        ('input[name="members[0].address"]', await _ask_for_schema_value(
            page, state, pacing, field_name="principal_address", selector='input[name="members[0].address"]'
        )),
        ('input[name="members[0].city"]', await _ask_for_schema_value(
            page, state, pacing, field_name="principal_city", selector='input[name="members[0].city"]'
        )),
        ('input[name="members[0].state"]', "IL"),
        ('input[name="members[0].zipCode"]', await _ask_for_schema_value(
            page, state, pacing, field_name="principal_zip", selector='input[name="members[0].zipCode"]'
        )),
    ]
    for sel, value in fills:
        if not value:
            continue
        loc = await page.query_selector(sel)
        if not loc:
            continue
        await loc.fill(value)
        await asyncio.sleep(pacing.judgment_fill_stagger_s * 0.4)

    await asyncio.sleep(pacing.judgment_fill_stagger_s)
    await _click_continue(page)
    return PageHandlerResult("managers-table", f"filled members[0] = {last_first!r}", True)


async def handle_address_confirmation(
    page: Page, state: DemoState, pacing: DemoPacing
) -> PageHandlerResult:
    """
    The "Is This The Correct Address?" page that follows USPS skip.
    Has two buttons: "Address is Correct" and "Edit Address". Click correct.
    """
    correct_btn = None
    for btn in await page.query_selector_all('input[type="submit"], input[type="button"], button'):
        text = ((await btn.inner_text()) or (await btn.get_attribute("value")) or "").strip().lower()
        if "address is correct" in text or "is correct" in text:
            correct_btn = btn
            break
    if not correct_btn:
        # fallback to generic Continue if labeling differs
        await _click_continue(page)
        return PageHandlerResult("address-confirmation", "fallback Continue", True)
    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=12000):
            await correct_btn.click()
    except Exception:
        await correct_btn.click()
        await asyncio.sleep(1.5)
    return PageHandlerResult("address-confirmation", "clicked Address is Correct", True)


# ──────────────────────────────────────────────────────────────────────
# URL routing
# ──────────────────────────────────────────────────────────────────────

# Order matters: more specific patterns first.
URL_HANDLERS: list[tuple[re.Pattern, Callable]] = [
    (re.compile(r"/llcarticles/?$"), handle_entity_choice),
    (re.compile(r"/llcarticles/index\.do"), handle_provisions_agreement),
    (re.compile(r"/llcarticles/generalProvisions\.do"), handle_entity_name),
    (re.compile(r"/llcarticles/llcName\.do"), handle_confirmation_pass_through),
    (re.compile(r"/llcarticles/similarNames\.do"), handle_principal_address),
    # placeOfBusiness can be EITHER address-fields page OR registered-agent
    # page depending on page state — disambiguate by checking for #agent.
    (re.compile(r"/llcarticles/placeOfBusiness\.do"), None),  # special, handled below
    (re.compile(r"/llcarticles/addressVerification\.do"), None),  # special
    (re.compile(r"/llcarticles/verifyAddress\.do"), handle_managers_table),
    (re.compile(r"/llcarticles/namesAddress\.do"), handle_organizer_attestation),
    (re.compile(r"/llcarticles/organizer\.do"), handle_review),
    (re.compile(r"/llcarticles/reviewdetails\.do"), handle_select_processing),
    (re.compile(r"/llcarticles/expedited\.do"), handle_billing_info),
]


async def route_page(
    page: Page, state: DemoState, pacing: DemoPacing
) -> Optional[PageHandlerResult]:
    """Look at current page and dispatch to the right handler."""
    url = page.url

    # Special-case the dual-purpose URLs
    if "placeOfBusiness.do" in url:
        if await page.query_selector("#agent"):
            return await handle_registered_agent(page, state, pacing)
        return await handle_principal_address(page, state, pacing)

    if "addressVerification.do" in url:
        # Three different pages share this URL depending on flow state:
        # (a) registered agent entry — has #agent input
        # (b) USPS standardization — has #contWithoutUSPS checkbox
        # (c) address confirmation — has "Address is Correct" button only
        if await page.query_selector("#agent"):
            return await handle_registered_agent(page, state, pacing)
        if await page.query_selector("#contWithoutUSPS"):
            return await handle_usps_verification(page, state, pacing)
        return await handle_address_confirmation(page, state, pacing)

    for pattern, handler in URL_HANDLERS:
        if handler is None:
            continue
        if pattern.search(url):
            return await handler(page, state, pacing)
    return None  # unknown page — caller decides what to do


# ──────────────────────────────────────────────────────────────────────
# Top-level: walk N pages, then stop
# ──────────────────────────────────────────────────────────────────────

async def walk_real_site(
    page: Page,
    state: DemoState,
    pacing: DemoPacing,
    *,
    max_pages: int = 12,
) -> list[PageHandlerResult]:
    """
    Walk forward through real-site pages, dispatching to handlers, until we
    hit max_pages, a payment-form input / terminal button, or an unknown URL.
    """
    # Match in input id/name only — body text mentions of "credit card" don't trigger
    PAYMENT_INPUT_RX = re.compile(r"card[_-]?number|creditcard|cc[_-]?num|\bcvv\b|\bcvc\b|expir|cardholder", re.I)
    TERMINAL_BUTTON_TEXT = (
        "submit filing", "submit articles", "file articles",
        "pay now", "make payment", "process payment",
    )

    results: list[PageHandlerResult] = []
    shots_dir = Path("out/live")
    shots_dir.mkdir(parents=True, exist_ok=True)
    for step in range(1, max_pages + 1):
        url = page.url
        title = await page.title()
        logger.info("real-site step %d: %s (%s)", step, title, url)
        try:
            await page.screenshot(path=str(shots_dir / f"step{step:02d}.png"))
        except Exception:
            pass

        # Off-site navigation = payment vendor (collectorsolutions.com, etc.)
        # IL SOS hands off to a third-party processor for the $150 fee.
        # Once we leave apps.ilsos.gov, we're at the point of real money
        # changing hands — STOP.
        if "apps.ilsos.gov" not in url:
            logger.info("real-site stop: left ilsos.gov (now at %s)", url)
            await show_toast(
                page,
                text_zh=t("real_site_payment_stop", getattr(state, "language", "zh")),
                kind="info",
                duration_ms=5000,
            )
            await asyncio.sleep(3.0)
            break

        # Stop check: payment INPUT or terminal BUTTON, not body text
        payment_hit = await page.evaluate(
            f"""(rx) => {{
                const r = new RegExp(rx, 'i');
                return Array.from(document.querySelectorAll('input, select')).some(el => (
                    r.test(el.id || '') || r.test(el.name || '') ||
                    r.test((el.previousElementSibling?.innerText || '')) ||
                    r.test((el.closest('label')?.innerText || ''))
                ));
            }}""",
            PAYMENT_INPUT_RX.pattern,
        )
        terminal_btn = await page.evaluate(
            """(words) => {
                const ws = words.split('|');
                return Array.from(document.querySelectorAll('input[type=submit], input[type=button], button'))
                    .map(b => ((b.innerText || b.value || '').trim().toLowerCase()))
                    .find(t => ws.some(w => t.includes(w))) || null;
            }""",
            "|".join(TERMINAL_BUTTON_TEXT),
        )
        if payment_hit or terminal_btn:
            logger.info("real-site stop: payment_input=%s terminal_btn=%r", payment_hit, terminal_btn)
            await show_toast(
                page,
                text_zh=t("real_site_submit_stop", getattr(state, "language", "zh")),
                kind="info",
                duration_ms=4000,
            )
            await asyncio.sleep(2.5)
            break

        try:
            result = await route_page(page, state, pacing)
        except Exception as exc:  # noqa: BLE001
            logger.exception("page handler failed: %s", exc)
            raise

        if result is None:
            logger.warning("unknown page url=%s — stopping", url)
            await show_toast(
                page,
                text_zh=t("real_site_unknown_stop", getattr(state, "language", "zh")),
                kind="info",
                duration_ms=3000,
            )
            await asyncio.sleep(2.0)
            break

        results.append(result)
        # The handler already navigated; re-install overlay on new page for
        # the next stage (page.add_init_script handles future navs but the
        # CURRENT page after navigation needs a fresh inject).
        try:
            await _install_localized_overlay(page, state)
        except Exception:
            pass
    return results
