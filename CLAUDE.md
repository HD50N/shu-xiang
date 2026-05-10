# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Shu Xiang — a hackathon demo of a bilingual operator agent that drives the Illinois SOS LLC filing form for Mandarin-speaking users via voice. Single Python asyncio process; Playwright drives Chromium; an injected vanilla CSS+JS overlay paints the bilingual UI on top of whatever page is loaded.

## Common commands

```bash
# Setup (uv-based)
uv venv && source .venv/bin/activate
uv pip install -e .
playwright install chromium

# End-to-end demo (recording mode against the local mock — no API keys needed)
python main.py

# Live IL SOS site (real form, scripted voice)
TARGET_ENV=live python main.py

# Full live walkthrough (real mic + real site, requires ANTHROPIC_API_KEY + ELEVENLABS_API_KEY)
DEMO_MODE=live_walkthrough TARGET_ENV=live python main.py

# Change demo language (zh default; en built-in; others translated via Anthropic)
SHUXIANG_LANGUAGE=en python main.py
SHUXIANG_LANGUAGE=Spanish ANTHROPIC_API_KEY=... python main.py

# Standalone artifact tests
python -m pdf.generator out/test.pdf            # render bilingual PDF in isolation
python scripts/screenshot_overlay.py out/o.png  # screenshot overlay against the mock

# Pre-cache Chinese question audio (run once with ELEVENLABS_API_KEY in .env)
python scripts/precache_question_audio.py

# De-risking gates (run when validating against real IL SOS)
python scripts/derisk_csp.py "https://apps.ilsos.gov/llcarticles/"
ANTHROPIC_API_KEY=... python scripts/derisk_async_hooks.py
ANTHROPIC_API_KEY=... python scripts/derisk_cold_open_eval.py 20

# Tests (pytest-asyncio, asyncio_mode=auto)
pytest                                # all tests
pytest tests/test_regex_match.py      # one file
pytest tests/test_regex_match.py::test_management_structure_hits   # one test
```

Headless override: `HEADLESS=true python main.py` (mock only — live IL SOS rejects headless and is force-headed).

## Architecture

Single asyncio event loop. The orchestrator owns the only mutable state (`LLCSchema`) and coordinates three concerns: the **voice loop** (scripted feeder OR live ElevenLabs Scribe STT), the **browser agent** (Playwright + injected overlay; optionally browser-use for the live walk), and the **PDF generator** (read-only consumer at the end).

Communication between concerns is via `asyncio.Queue` (voice → orchestrator) and `page.evaluate` (orchestrator → overlay JS). Single-writer rule: only the orchestrator mutates `LLCSchema`. See `agent/state.py`.

The demo is split into **stages** by `agent/demo_runner.py::DemoRunner`. Each stage is wrapped by `_run_stage`, which on failure logs the stage name, hides the overlay, shows an error toast, and re-raises as `DemoStageError`. Stage list differs by `target_env`:
- **mock**: language_selection → pre_flight → cold_open → in_flow_pause → continue_and_submit → pdf → closing
- **live**: language_selection → pre_flight → obligations_reveal → real_site_walk → chained_next_step → pdf → closing

### Field corpus (`corpus/il_llc_corpus.py`)

Every IL SOS form field is labeled with `FieldKind`:
- `AUTOFILL` — filled deterministically from the schema during cold_open.
- `JUDGMENT` — needs user input; one (`management_structure`) is the in-flow pause centerpiece, others come from pre-flight defaults.
- `LOOKUP` — derived from external data.

Each `FieldSpec` carries `selector_mock` (against `demo/il_sos_mock.html`) and `selector_live` (live IL SOS — populated as the live site is mapped). `DEMO_SEED` is the deterministic restaurant-owner profile used in recording mode. `IN_FLOW_PAUSE_FIELD` names the one field whose fill is paused-on so the bilingual overlay can demo the wow moment.

### Overlay bridge (`agent/overlay_bridge.py` ↔ `overlay/inject.js`)

`overlay/inject.js` (~vanilla JS, no build step) is injected via `page.evaluate` after `install_overlay`. Python calls `window.shuxiang.<fn>` from `overlay_bridge.py` to drive the UI: opening prompt, sidebar, highlight ring + annotation card, listening indicator, checklist, toasts, closing screen, mic button. In live-voice mode an `add_init_script` reinstalls the mic button on every navigation (IL SOS submits between pages).

### Voice pipeline (`voice/`)

- `regex_match.py` — sub-millisecond enum extraction; the first thing tried on every transcript.
- `intent_extraction.py` — `extract_cold_open` (Sonnet 4.6, six fields from one Chinese sentence) and `extract_field_value_haiku` (Haiku 4.5 fallback for the in-flow pause when regex misses).
- `scripted.py` — recording-mode deterministic feeder; pushes pre-canned transcripts into `voice_queue`.
- `elevenlabs_voice.py` — TTS (Multilingual v2, pre-cached question audio) + STT (Scribe).
- `live_stt.py` + `mic_capture.py` — mic capture loop (sounddevice, PCM 16k mono) feeding chunks to Scribe; emits partial transcripts (painted into the opening prompt) and final-on-mute (drives the conversation).

### Demo modes

- `recording` (default): seeds from `DEMO_SEED`, scripted voice feeder, runs against `demo/il_sos_mock.html`.
- `live_walkthrough`: real microphone, ElevenLabs voice both ways, live IL SOS — set `DEMO_MODE=live_walkthrough TARGET_ENV=live`.
- Independent toggles: `TARGET_ENV={mock,live}`, `LIVE_VOICE=true` (live mic without forcing live site).

### PDF (`pdf/`)

`generator.py` renders `template.html` (Jinja, with `@font-face` to bundled Noto Sans/Serif SC under `pdf/fonts/`) using Playwright `page.pdf()`. Read-only consumer of `LLCSchema` — runs after the agent stage chain finishes. Self-contained: no CDN dependency at recording time.

### Pacing (`agent/pacing.py`)

All sleeps/timeouts in the demo flow come from a `DemoPacing` object — change demo timing centrally, not by editing stage code.

## Important conventions

- **Single-writer for `LLCSchema`**: only the orchestrator mutates it (via `schema.update_from(...)`). Browser-use tools and PDF generator are read-only consumers.
- **Live IL SOS launch differs from mock**: forces `headless=False`, prefers `channel="chrome"` over bundled chromium (falls back if not installed), sets a real-looking macOS Safari UA, adds `--disable-blink-features=AutomationControlled`. Don't lose these — without them `.gov` returns 403.
- **Audio autoplay**: launch args include `--autoplay-policy=no-user-gesture-required` and `--allow-file-access-from-files` so the first AI question plays before any user gesture and `Audio()` can load `file://` URLs.
- **Localization**: Chinese is the source copy. `agent/i18n.py` resolves a language code from `SHUXIANG_LANGUAGE` (aliases for "Spanish", "中文", "English", etc.) and translates unknown languages on the fly via Anthropic, cached in-process. Sidebar labels live in `corpus.SIDEBAR_LABELS_ZH`; UI strings in `agent.i18n.t()`.
- **Selectors**: when adding a new IL SOS field, update both `selector_mock` and `selector_live` in the FieldSpec — most stage code dispatches on `target_env`.
- **Don't add a build step for the overlay**: `overlay/inject.js` is intentionally vanilla and injected as-is. Hackathon constraint.
