"""
DemoRunner — locked in eng review D6.

Wraps each major demo beat in try/except. On any failure, logs the failed
stage, hides the overlay, and exits non-zero. Re-run is one Ctrl-C away.

This is the entry point invoked by main.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from corpus import (
    CORPUS_FIELDS,
    FieldKind,
    get_in_flow_pause_field,
)
from corpus.requirements import BusinessProfile, DEMO_PROFILE, requirements_for_profile
from voice.scripted import DEMO_SCRIPT, feed_voice_queue

from agent.clarification import run_clarification
from agent.cold_open import cold_open_fill, fill_judgment_field
from agent.overlay_bridge import (
    hide_checklist,
    hide_opening_prompt,
    hide_overlay,
    hide_sidebar,
    install_mic_button,
    install_overlay,
    set_language,
    set_checklist_item_state,
    set_mic_state_visual,
    show_checklist,
    show_closing,
    show_opening_prompt,
    show_sidebar,
    show_toast,
    type_opening_transcript,
    type_transcript,
    update_live_transcript,
)
from agent.i18n import (
    Language,
    language_display_name,
    language_from_utterance,
    language_from_env,
    requirement_items,
    sidebar_labels,
    t,
)
from agent.pacing import DemoPacing, get_pacing
from agent.speech import speak_text, stop_speech
from agent.state import DemoState


logger = logging.getLogger("shuxiang.demo")


@dataclass
class DemoConfig:
    target_env: str = "mock"  # 'mock' | 'live'
    form_url: str = ""
    headless: bool = False
    disable_web_security: bool = True
    cold_open_stagger_ms: int = 200
    listen_timeout_s: float = 10.0
    pdf_output: Optional[Path] = None
    use_live_voice: bool = False  # mic capture + Scribe instead of scripted feeder
    language: Language = "zh"

    @classmethod
    def from_env(cls) -> "DemoConfig":
        target_env = os.environ.get("TARGET_ENV", "mock")
        if target_env == "mock":
            mock_path = Path(__file__).resolve().parent.parent / "demo" / "il_sos_mock.html"
            form_url = mock_path.as_uri()
            # Mock can be headless without issue
            headless = os.environ.get("HEADLESS", "false").lower() == "true"
        else:
            form_url = os.environ.get(
                "IL_SOS_URL",
                "https://apps.ilsos.gov/llcarticles/",
            )
            # Live site rejects headless. Force headed regardless of env.
            headless = False

        # Live-voice opt-in: DEMO_MODE=live_walkthrough or LIVE_VOICE=true
        demo_mode = os.environ.get("DEMO_MODE", "recording").lower()
        live_voice_explicit = os.environ.get("LIVE_VOICE", "").lower() == "true"
        use_live_voice = demo_mode == "live_walkthrough" or live_voice_explicit

        return cls(
            target_env=target_env,
            form_url=form_url,
            headless=headless,
            disable_web_security=os.environ.get("DISABLE_WEB_SECURITY", "true").lower() == "true",
            pdf_output=Path("out") / "shuxiang-llc-summary.pdf",
            use_live_voice=use_live_voice,
            language=language_from_env(),
        )


class DemoStageError(RuntimeError):
    """A specific demo stage failed. Carries the stage name."""

    def __init__(self, stage: str, original: Exception):
        super().__init__(f"[stage:{stage}] {original}")
        self.stage = stage
        self.original = original


class DemoRunner:
    """
    Runs the 3-minute demo. On exception in any stage, marks failed_stage,
    hides the overlay, and re-raises as DemoStageError.
    """

    def __init__(self, config: DemoConfig, state: Optional[DemoState] = None):
        self.config = config
        self.language = config.language
        self.state = state or DemoState()
        self.state.language = self.language
        self.state.use_live_voice = config.use_live_voice
        self.pacing: DemoPacing = get_pacing()
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.live_stt = None  # set up in run() if config.use_live_voice

    def _speak_background(self, text: str, *, audio_key: str | None = None) -> None:
        if not self.page or not text:
            return
        asyncio.create_task(
            speak_text(self.page, text, language=self.language, audio_key=audio_key)
        )

    def _web_handoff_profile(self) -> dict | None:
        raw = os.environ.get("SHUXIANG_WEB_HANDOFF_JSON")
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.exception("invalid SHUXIANG_WEB_HANDOFF_JSON")
            return None
        fields = payload.get("fields") if isinstance(payload, dict) else None
        return fields if isinstance(fields, dict) else None

    def _business_profile_from_handoff(self, raw: dict) -> BusinessProfile:
        return BusinessProfile(
            entity_name=raw.get("entity_name"),
            business_type=raw.get("business_type"),
            city=raw.get("city") or raw.get("principal_city"),
            state=raw.get("state") or "IL",
            sole_owner=raw.get("sole_owner"),
            plans_to_hire=raw.get("plans_to_hire"),
            sells_food=raw.get("sells_food"),
            sells_alcohol=raw.get("sells_alcohol"),
            online_only=raw.get("online_only"),
            different_dba=raw.get("different_dba"),
        )

    # ─── Stage runners ──────────────────────────────────────────────

    async def _stage_language_selection(self) -> None:
        """First live-voice beat: ask which language to use, then localize."""
        if self._web_handoff_profile() is not None:
            logger.info("web handoff detected; skipping in-browser language selection")
            return
        if not self.config.use_live_voice or self.live_stt is None:
            return

        from voice.elevenlabs_voice import stt_language_code

        # The language-choice answer can be in any language, so let Scribe
        # auto-detect only for this first utterance.
        self.live_stt.set_language_code(None)
        await set_language(self.page, "en")
        language_prompt = t("language_prompt", "en")
        await show_opening_prompt(self.page, language_prompt)
        await speak_text(self.page, language_prompt, language="en")

        try:
            transcript = await asyncio.wait_for(self.state.voice_queue.get(), timeout=45.0)
        except asyncio.TimeoutError:
            logger.warning("language selection timed out; defaulting to English")
            transcript = "English"

        await update_live_transcript(self.page, transcript)
        selected = language_from_utterance(transcript, fallback="en")
        self.language = selected
        self.config.language = selected
        self.state.language = selected
        self.live_stt.set_language_code(stt_language_code(selected))
        await set_language(self.page, selected)
        selected_text = t("language_selected", selected, selected_language=language_display_name(selected))
        await show_toast(
            self.page,
            text_zh=selected_text,
            kind="success",
            duration_ms=2500,
        )
        await speak_text(self.page, selected_text, language=selected)
        logger.info("language selected from %r → %s", transcript, selected)
        await asyncio.sleep(0.8)
        await hide_opening_prompt(self.page)
        await asyncio.sleep(0.3)

    async def _stage_pre_flight(self) -> None:
        """
        Pre-flight as a STORY:
          1. Show the opening prompt full-screen (麦克风已开启 + transcript box)
          2. EITHER typewriter the hardcoded sentence (recording mode)
             OR wait for the user's real Chinese sentence via mic + Scribe (live)
          3. In live mode: run extract_cold_open(transcript) to populate schema
             from the user's actual words. Recording mode: seed from DEMO_SEED.
          4. Hide opening prompt — IL SOS form revealed underneath
          5. Open the sidebar with the transcript and field values
        """
        handoff_profile = self._web_handoff_profile()
        if handoff_profile is not None:
            self.state.schema.update_from(handoff_profile)
            self.state.business_profile = self._business_profile_from_handoff(handoff_profile)
            transcript_zh = self.state.schema.entity_name or t("demo_sentence", self.language)
            await show_opening_prompt(self.page, t("overlay_thinking", self.language))
            await update_live_transcript(self.page, transcript_zh)
            await speak_text(
                self.page,
                t("language_selected", self.language, selected_language=language_display_name(self.language)),
                language=self.language,
            )
            logger.info("web handoff loaded schema: %s", self.state.schema.to_dict())
        elif self.config.use_live_voice:
            # Live mode lets the phase-1 conversation ask the business question.
            # Keep this screen neutral so the user does not hear the same prompt twice.
            await show_opening_prompt(self.page, t("overlay_mic_ready", self.language))
            await asyncio.sleep(0.3)

            # LIVE MODE — Phase 1 multi-turn conversation.
            # The user clicks the mic, agent asks 4 questions one at a time,
            # Sonnet incrementally fills the BusinessProfile + LLCSchema.
            from agent.preflight_conversation import run_phase1_conversation
            live_voice_text = t("live_voice_toast", self.language)
            await show_toast(
                self.page,
                text_zh=live_voice_text,
                kind="info",
                duration_ms=4500,
            )
            try:
                profile, raw = await run_phase1_conversation(
                    self.page,
                    self.state,
                    language=self.language,
                )
                self.state.business_profile = profile
                # Apply extraction to LLCSchema for the form walk
                self.state.schema.update_from(raw)
                logger.info(
                    "phase1 done — profile: %s, schema entity=%s",
                    profile, self.state.schema.entity_name,
                )
                transcript_zh = self.state.schema.entity_name or t("demo_sentence", self.language)
            except Exception:
                logger.exception("phase1 conversation failed; using demo seed")
                self.state.seed_with_demo_data()
                self.state.business_profile = DEMO_PROFILE
                transcript_zh = t("demo_sentence", self.language)
        else:
            # Beat 1: opening prompt full-screen
            opening_prompt = t("opening_prompt", self.language)
            await show_opening_prompt(self.page, opening_prompt)
            await speak_text(self.page, opening_prompt, language=self.language)
            await asyncio.sleep(self.pacing.opening_prompt_hold_s)

            # RECORDING MODE: seed + typewriter the hardcoded sentence.
            self.state.seed_with_demo_data()
            await type_opening_transcript(
                self.page,
                t("demo_sentence", self.language),
                self.pacing.typewriter_char_ms,
            )
            transcript_zh = t("demo_sentence", self.language)

        # Beat 3: thinking pause (also gives Sonnet's response time to land)
        await asyncio.sleep(self.pacing.sentence_to_extraction_pause_s)

        # Beat 4: hide opening prompt — judge sees the IL SOS form now
        await hide_opening_prompt(self.page)
        await asyncio.sleep(0.5)

        # Beat 5: sidebar with the transcript + extracted-field rows
        sidebar_rows = []
        sidebar_label_map = sidebar_labels(
            [
                (f.schema_key, f.name)
                for f in CORPUS_FIELDS
                if f.kind != FieldKind.LOOKUP
            ],
            self.language,
        )
        for f in CORPUS_FIELDS:
            if f.kind == FieldKind.LOOKUP:
                continue
            value = getattr(self.state.schema, f.schema_key, None) or ""
            sidebar_rows.append({
                "key": f.schema_key,
                "labelZh": sidebar_label_map.get(f.schema_key, f.name),
                "value": str(value) if value else "",
            })
        await show_sidebar(
            self.page,
            transcript=transcript_zh,
            fields=sidebar_rows,
        )
        await asyncio.sleep(0.4)

    async def _stage_cold_open(self) -> None:
        """Six fields fill in cascade via deterministic Playwright."""
        await cold_open_fill(
            self.page,
            self.state.schema,
            target_env=self.config.target_env,
            stagger_ms=self.pacing.cold_open_stagger_ms,
        )
        # Hold AFTER all six populated — let the judge see the result before
        # the in-flow pause beat takes their attention.
        await asyncio.sleep(self.pacing.cold_open_after_done_pause_s)

    async def _stage_in_flow_pause(self) -> None:
        """The wow #2 moment."""
        await hide_sidebar(self.page)  # hide sidebar to avoid competing with overlay
        await asyncio.sleep(0.2)

        # In live-voice mode, the user actually speaks — no scripted feeder.
        feeder_task = None
        if not self.config.use_live_voice:
            feeder_delay_s = (
                self.pacing.in_flow_pre_voice_hold_s
                + self.pacing.in_flow_post_audio_pause_s
                + self.pacing.in_flow_listening_visible_s
                + 0.6
            )

            async def _delayed_feeder():
                await asyncio.sleep(feeder_delay_s)
                await feed_voice_queue(self.state.voice_queue, DEMO_SCRIPT)
            feeder_task = asyncio.create_task(_delayed_feeder())

        field = get_in_flow_pause_field()
        result = await run_clarification(
            self.page,
            field=field,
            target_env=self.config.target_env,
            voice_queue=self.state.voice_queue,
            listen_timeout_s=self.config.listen_timeout_s,
            pre_voice_hold_s=self.pacing.in_flow_pre_voice_hold_s,
            post_audio_pause_s=self.pacing.in_flow_post_audio_pause_s,
            listening_visible_s=self.pacing.in_flow_listening_visible_s,
            recorded_hold_s=self.pacing.in_flow_recorded_hold_s,
            language=self.language,
        )
        if feeder_task is not None:
            feeder_task.cancel()

        if result.value is None:
            raise RuntimeError(
                f"Clarification timed out / unparseable transcript for {field.name!r}"
            )

        # Single-writer: orchestrator owns the dict.
        self.state.schema.update_from({result.field_key: result.value})

        # Now fill the field on the form.
        await fill_judgment_field(
            self.page, field, result.value, target_env=self.config.target_env
        )

        logger.info(
            "in-flow pause: %s = %r (source=%s, %.0fms)",
            result.field_key, result.value, result.source, result.voice_to_value_ms,
        )

        # Hold so the judge sees the radio button select + understands the agent
        # is moving on, not stalled.
        await asyncio.sleep(self.pacing.in_flow_after_fill_pause_s)

    async def _stage_obligations_reveal(self) -> None:
        """
        Phase 2: render the obligation map specific to the user's business
        profile. The asymmetry-being-closed wow moment.
        """
        # Build the profile if Phase 1 didn't (recording mode skips Phase 1)
        profile = self.state.business_profile or DEMO_PROFILE
        reqs = requirements_for_profile(profile)
        items = requirement_items(reqs, self.language)
        # Hide the opening prompt sidebar so the checklist is the focus
        await hide_sidebar(self.page)
        await asyncio.sleep(0.2)

        # Play the AI's voice-over while the checklist animates in
        if self.config.use_live_voice:
            checklist_intro = " ".join([
                t("checklist_header", self.language),
                t("checklist_subtitle", self.language, count=len(items)),
                t("checklist_summary", self.language),
            ])
            audio_task = asyncio.create_task(
                speak_text(self.page, checklist_intro, language=self.language, audio_key="phase2_reveal")
            )
        else:
            audio_task = None

        await show_checklist(
            self.page,
            items=items,
            header_zh=t("checklist_header", self.language),
            subtitle_zh=t("checklist_subtitle", self.language, count=len(items)),
            summary_zh=t("checklist_summary", self.language),
            stagger_ms=350,
        )
        # Hold long enough for the user to read the list (every item staggered 350ms)
        reveal_duration = 0.5 + len(items) * 0.35 + 2.5
        await asyncio.sleep(reveal_duration)
        if audio_task is not None:
            try:
                await audio_task
            except Exception:
                pass

        # Mark the LLC item as ACTIVE since that's what we'll do next
        await set_checklist_item_state(self.page, "il_llc_articles", "active")
        await asyncio.sleep(1.5)

    async def _stage_chained_next_step(self) -> None:
        """
        Close-the-loop wow #3: filing complete, agent gestures at EIN as
        the next chain item. Marks LLC done in the checklist, marks EIN
        active, plays cached audio explaining why EIN matters.
        """
        await set_checklist_item_state(self.page, "il_llc_articles", "done")
        await asyncio.sleep(0.6)
        await set_checklist_item_state(self.page, "federal_ein", "active")

        next_step_text = t("next_step_toast", self.language)
        await show_toast(
            self.page,
            text_zh=next_step_text,
            kind="info",
            duration_ms=4500,
        )
        self._speak_background(next_step_text, audio_key="chained_next_ein")
        await asyncio.sleep(3.0)

        # Open IRS EIN page in a new tab to demonstrate the chain
        try:
            new_page = await self.context.new_page()
            await new_page.goto(
                "https://www.irs.gov/businesses/small-businesses-self-employed/apply-for-an-employer-identification-number-ein-online",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(2.5)
        except Exception:
            logger.exception("EIN gesture page open failed; skipping")

    async def _stage_real_site_walk(self) -> None:
        """Live-site path: walk the real IL SOS flow page-by-page."""
        from agent.real_site_runner import walk_real_site
        results = await walk_real_site(
            self.page,
            self.state,
            self.pacing,
            max_pages=16,
        )
        logger.info(
            "real-site walk: %d pages handled — %s",
            len(results),
            ", ".join(r.label for r in results),
        )

    async def _stage_continue_and_submit(self) -> None:
        """Fill remaining judgment fields from pre-flight defaults, then submit."""
        from corpus import judgment_fields
        for f in judgment_fields():
            if f.schema_key == get_in_flow_pause_field().schema_key:
                continue  # already filled in the in-flow stage
            value = getattr(self.state.schema, f.schema_key, None)
            if value:
                await fill_judgment_field(
                    self.page, f, value, target_env=self.config.target_env
                )
                await asyncio.sleep(self.pacing.judgment_fill_stagger_s)

        await asyncio.sleep(self.pacing.pre_submit_pause_s)
        # Click submit.
        if self.config.target_env == "mock":
            await self.page.click("#submit-btn")
        else:
            # Live IL SOS — captured tonight in field-corpus labeling.
            raise NotImplementedError("Live submit selector — capture tonight")

        await asyncio.sleep(self.pacing.post_submit_pause_s)

    async def _stage_pdf(self) -> None:
        from pdf.generator import generate_bilingual_pdf

        # Show generating toast first; let it breathe before kicking off
        # the actual render so the judge sees the cause→effect.
        pdf_generating_text = t("pdf_generating", self.language)
        await show_toast(
            self.page,
            text_zh=pdf_generating_text,
            kind="info",
            duration_ms=int(self.pacing.pdf_generating_toast_s * 1000) or 2500,
        )
        self._speak_background(pdf_generating_text)
        await asyncio.sleep(min(self.pacing.pdf_generating_toast_s, 1.5))

        out_path = self.config.pdf_output or Path("out/shuxiang-llc.pdf")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        await generate_bilingual_pdf(self.state.schema, out_path)

        pdf_done_text = t("pdf_done", self.language, filename=out_path.name)
        await show_toast(
            self.page,
            text_zh=pdf_done_text,
            kind="success",
            duration_ms=int(self.pacing.pdf_done_toast_s * 1000) or 4000,
        )
        self._speak_background(pdf_done_text)
        await asyncio.sleep(self.pacing.pdf_done_toast_s)

    async def _stage_closing(self) -> None:
        """Closing scene: full-screen success message in Chinese."""
        if self.pacing.closing_message_hold_s <= 0:
            return
        closing_text = t("closing_message", self.language)
        await show_closing(self.page, closing_text)
        await speak_text(self.page, closing_text, language=self.language)
        await asyncio.sleep(self.pacing.closing_message_hold_s)

    # ─── Stage harness ──────────────────────────────────────────────

    async def _run_stage(self, name: str, coro):
        try:
            logger.info("→ %s", name)
            await coro
            logger.info("✓ %s", name)
        except Exception as exc:  # noqa: BLE001
            self.state.failed_stage = name
            traceback.print_exc(file=sys.stderr)
            try:
                await hide_overlay(self.page)
            except Exception:
                pass
            try:
                error_text = t("stage_error", self.language, stage=name)
                await show_toast(
                    self.page,
                    text_zh=error_text,
                    kind="error",
                    duration_ms=6000,
                )
                self._speak_background(error_text)
            except Exception:
                pass
            raise DemoStageError(name, exc) from exc

    # ─── Entry point ────────────────────────────────────────────────

    async def run(self) -> None:
        async with async_playwright() as pw:
            launch_args = []
            if self.config.disable_web_security:
                launch_args.append("--disable-web-security")

            # Live IL SOS mode needs anti-bot mitigations: real Chrome
            # channel (not headless shell), AutomationControlled disabled,
            # and a real-looking user agent. Without these, .gov returns 403.
            # The mock form path runs fine on stock chromium — only swap
            # configs when we're actually hitting the live site.
            launch_kwargs: dict = {"args": launch_args, "headless": self.config.headless}
            context_kwargs: dict = {"viewport": {"width": 1440, "height": 900}}

            # Audio autoplay needs to bypass Chrome's user-gesture requirement,
            # otherwise the FIRST AI question (Phase 1 turn 1) plays silently
            # because no user interaction has happened yet at that point.
            launch_args.extend([
                "--autoplay-policy=no-user-gesture-required",
                "--allow-file-access-from-files",  # let Audio() load file:// URLs
            ])

            if self.config.target_env == "live":
                launch_args.append("--disable-blink-features=AutomationControlled")
                # Force headed — headless gets 403 from IL SOS
                launch_kwargs["headless"] = False
                try:
                    self.browser = await pw.chromium.launch(channel="chrome", **launch_kwargs)
                except Exception:
                    # Fall back to bundled chromium if real Chrome isn't installed
                    self.browser = await pw.chromium.launch(**launch_kwargs)
                context_kwargs["user_agent"] = (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
                )
                context_kwargs["locale"] = "en-US"
            else:
                self.browser = await pw.chromium.launch(**launch_kwargs)

            self.context = await self.browser.new_context(**context_kwargs)
            self.page = await self.context.new_page()

            try:
                await self.page.goto(self.config.form_url, wait_until="domcontentloaded")
                await install_overlay(self.page)
                await set_language(self.page, self.language)

                # Live voice setup (only when explicitly opted in via
                # DEMO_MODE=live_walkthrough or LIVE_VOICE=true).
                if self.config.use_live_voice:
                    from voice.live_stt import LiveSTT
                    loop = asyncio.get_event_loop()

                    # Live transcript: every ~1.5s while the user speaks,
                    # Scribe transcribes the buffer-so-far and we paint it
                    # into the opening prompt card. Final-on-mute still
                    # drives the conversation; partials are visual only.
                    async def _paint_partial(text: str) -> None:
                        if self.page is None:
                            return
                        try:
                            await update_live_transcript(self.page, text)
                        except Exception:
                            logger.debug("partial paint failed", exc_info=True)

                    self.live_stt = LiveSTT.attach(
                        loop=loop,
                        queue=self.state.voice_queue,
                        on_partial_transcript=_paint_partial,
                        language_code=None,
                    )
                    # Bridge: when JS calls window.toggleMic() the click handler
                    # in inject.js calls this Python coroutine.
                    async def toggle_mic_handler():
                        new_muted = self.live_stt.toggle()
                        if not new_muted:
                            await stop_speech(self.page)
                        await set_mic_state_visual(self.page, new_muted)
                        logger.info("toggleMic → muted=%s", new_muted)
                        return new_muted
                    await self.context.expose_function("toggleMic", toggle_mic_handler)
                    # Auto-install the mic button on EVERY navigation (the
                    # init script also re-runs after IL SOS form submits).
                    await self.context.add_init_script(
                        """
                        (function() {
                          const tryInstall = () => {
                            if (window.shuxiang && window.shuxiang.installMicButton) {
                              window.shuxiang.installMicButton();
                            } else {
                              setTimeout(tryInstall, 100);
                            }
                          };
                          if (document.readyState === 'loading') {
                            document.addEventListener('DOMContentLoaded', tryInstall);
                          } else {
                            tryInstall();
                          }
                        })();
                        """
                    )
                    # Manual install on the current page too
                    await install_mic_button(self.page)
                    await set_mic_state_visual(self.page, True)  # start MUTED
                    logger.info("live voice ON: mic muted, click the AMBER pill at TOP-RIGHT to unmute")

                if self.config.target_env == "live":
                    # Three-phase real-site flow:
                    #   pre_flight (Phase 1 conversation)
                    #   obligations_reveal (Phase 2 wow moment)
                    #   real_site_walk (Phase 3 LLC filing with clarifications)
                    #   chained_next_step (close-the-loop EIN gesture)
                    #   pdf + closing
                    await self._run_stage("language_selection", self._stage_language_selection())
                    await self._run_stage("pre_flight", self._stage_pre_flight())
                    await self._run_stage("obligations_reveal", self._stage_obligations_reveal())
                    await self._run_stage("real_site_walk", self._stage_real_site_walk())
                    await self._run_stage("chained_next_step", self._stage_chained_next_step())
                    await self._run_stage("pdf", self._stage_pdf())
                    await self._run_stage("closing", self._stage_closing())
                else:
                    await self._run_stage("language_selection", self._stage_language_selection())
                    await self._run_stage("pre_flight", self._stage_pre_flight())
                    await self._run_stage("cold_open", self._stage_cold_open())
                    await self._run_stage("in_flow_pause", self._stage_in_flow_pause())
                    await self._run_stage(
                        "continue_and_submit", self._stage_continue_and_submit()
                    )
                    await self._run_stage("pdf", self._stage_pdf())
                    await self._run_stage("closing", self._stage_closing())
            finally:
                # Keep the page open for a beat so the recorder catches the toast.
                await asyncio.sleep(1.5)
                if self.live_stt is not None:
                    self.live_stt.shutdown()
                await self.context.close()
                await self.browser.close()


async def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s.%(msecs)03d %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    config = DemoConfig.from_env()
    runner = DemoRunner(config)
    try:
        await runner.run()
    except DemoStageError as e:
        logger.error("Demo aborted at stage=%s: %s", e.stage, e.original)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
