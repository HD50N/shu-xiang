# Shu Xiang — Cross-Language Operator Agent

Bilingual agent that operates the Illinois LLC filing form for Mandarin-speaking
business owners. Hackathon demo: a Chinese-speaking restaurant owner files an
Illinois LLC by voice in 3 minutes.

## What's working today

- Vanilla CSS+JS overlay (highlight ring + Chinese annotation card + listening
  indicator + sidebar) — injected via `page.evaluate`. No build step, no React.
- Local IL SOS LLC form mock at `demo/il_sos_mock.html`.
- Field corpus + selector map at `corpus/il_llc_corpus.py` (mock selectors
  populated; live IL SOS selectors are tonight's task).
- Cold-open: deterministic Playwright fill of all autofill fields (1.8s for six
  fields).
- In-flow pause: bilingual overlay anchored to the field, scripted voice answer
  via `voice/scripted.py`, regex-first / Haiku-fallback enum extraction.
- Bilingual PDF generator with bundled Noto Sans SC + Noto Serif SC fonts. No
  CDN dependency at recording time.
- DemoRunner with stage-by-stage try/except + visible toast on failure.
- Browser-use integration scaffolded for live walkthrough mode (`agent/browser_loop.py`).
- ElevenLabs voice pipeline (`voice/elevenlabs_voice.py`) — Multilingual v2 for the scripted Chinese question (pre-cached), Scribe for live STT. Single voice vendor.
- End-to-end smoke run: 6.7 seconds wall-clock from start to PDF written.

## Run it

```bash
# Setup
uv venv && source .venv/bin/activate
uv pip install -e .
playwright install chromium

# End-to-end demo against the local mock (no API keys needed for recording mode
# because the regex hits on the scripted answer)
python main.py

# Change the demo language. Chinese is the default; English is built in.
# Other language names/codes use Anthropic translation when ANTHROPIC_API_KEY is set.
SHUXIANG_LANGUAGE=en python main.py
SHUXIANG_LANGUAGE=Spanish ANTHROPIC_API_KEY=... python main.py

# Render the bilingual PDF in isolation (sanity check Mandarin renders)
python -m pdf.generator out/test.pdf

# Render an overlay screenshot against the mock form
python scripts/screenshot_overlay.py out/overlay.png

# Tonight's de-risking gates
python scripts/derisk_csp.py "https://apps.ilsos.gov/llcarticles/"  # gate 1
ANTHROPIC_API_KEY=... python scripts/derisk_async_hooks.py          # gate 2
ANTHROPIC_API_KEY=... python scripts/derisk_cold_open_eval.py 20    # gate 5
```

## Architecture

Single Python asyncio event loop with three async tasks coordinating via
`asyncio.Queue`. Orchestrator owns the `LLCSchema` dict (single writer);
browser-use reads field values via tool calls; PDF generator reads the dict
after the agent returns.

```
                  +--------------------------------+
                  |     Python Orchestrator        |
                  |  (single asyncio event loop)   |
                  |   LLCSchema (in-memory dict)   |
                  |    [SINGLE WRITER]             |
                  +---+----------+-----------+-----+
                      |          |           |
        reads/writes  |  events  |   reads   |
                      v          v           v
              +-------+----+  +--+--------+  +-----------+
              | Voice Loop |  | Browser   |  | PDF       |
              | (asyncio)  |  | Agent     |  | Generator |
              | scripted/  |  | browser-  |  | Playwright|
              | realtime   |  | use       |  | page.pdf  |
              +-----+------+  +-----+-----+  +-----+-----+
                    |               |              ^
                    |               v              |
                    |        +------+-----+        |
                    |        | Playwright |        |
                    |        | + Chromium |        |
                    |        +------+-----+        |
                    |               |              |
                    |               v              |
                    |        +------+-----+        |
                    |        | IL SOS LLC |        |
                    |        | form       |        |
                    |        +------+-----+        |
                    |               |              |
                    |               | page.evaluate|
                    |               v              |
                    |        +------+-----+        |
                    +------->| Vanilla    |<-------+
                              localized  | overlay    |
                             +------------+
```

## Modules

| Path | What it does |
|------|--------------|
| `main.py` | Entry point. Loads .env, runs DemoRunner. |
| `agent/demo_runner.py` | Stage-by-stage demo flow with try/except wrapper. |
| `agent/state.py` | `LLCSchema` (the single-writer dict) + `DemoState`. |
| `agent/cold_open.py` | Deterministic `page.fill()` cascade for autofill fields. |
| `agent/clarification.py` | The in-flow pause beat: overlay + voice + extract + fill. |
| `agent/overlay_bridge.py` | Python ↔ overlay JS bridge. |
| `agent/browser_loop.py` | Live walkthrough mode (browser-use integration). |
| `agent/preflight.py` | Live cold-open extraction (Sonnet 4.6 → schema). |
| `voice/regex_match.py` | Regex-first enum extraction (sub-millisecond). |
| `voice/intent_extraction.py` | Sonnet 4.6 (cold-open) + Haiku 4.5 (in-flow fallback). |
| `voice/scripted.py` | Recording-mode voice feeder: deterministic clock. |
| `voice/elevenlabs_voice.py` | TTS (Multilingual v2) + STT (Scribe) — both sides of voice. |
| `overlay/inject.js` | Vanilla CSS+JS overlay (~150 lines, no build step). |
| `corpus/il_llc_corpus.py` | Field metadata, Chinese copy, selector map, demo seed. |
| `pdf/template.html` | Bilingual PDF Jinja template + @font-face. |
| `pdf/generator.py` | `page.pdf()` rendering pipeline. |
| `pdf/fonts/` | Bundled Noto SC fonts (Sans + Serif, Regular + Bold). |
| `demo/il_sos_mock.html` | Local IL SOS form mock. |
| `scripts/derisk_*.py` | Tonight's pass/fail gates. |
| `scripts/screenshot_overlay.py` | Visual smoke test of the overlay. |

## Locked design tokens (from /plan-design-review)

| Token | Value |
|-------|-------|
| `--ring-color` | `#D97706` (amber 600) |
| `--ring-glow` | `rgba(217,119,6,0.25)` |
| `--success-green` | `#10B981` |
| `--card-bg` | `#FFFFFF` |
| `--card-border` | `#E5E5E5` |
| `--card-shadow` | `0 4px 12px rgba(0,0,0,0.06)` |
| Question font | Noto Sans SC 700 / 20px |
| Explanation font | Noto Sans SC 400 / 14px |
| PDF Chinese | Noto Serif SC 400 / 12px |

## Tonight's checklist

Run in this order. CSP gate (1) and async hooks gate (2) decide whether the
demo architecture survives — if either fails, fall back to Plan B.

- [ ] **Gate 1 — CSP test on real IL SOS.** `python scripts/derisk_csp.py <url>`
- [ ] **Gate 2 — browser-use async hooks.** `python scripts/derisk_async_hooks.py`
- [ ] **Gate 3 — Field corpus labeling on real IL SOS.** Walk every field on the
  live site, label autofill/judgment/lookup, capture selectors. Update
  `corpus/il_llc_corpus.py` `selector_live` fields.
- [ ] **Gate 4 — Voice pipeline smoke.** Pre-cache the Chinese question audio:
  `ELEVENLABS_API_KEY=... python scripts/precache_question_audio.py`
  Then verify `assets/audio_cache/management_structure.mp3` plays cleanly with a native voice.
- [ ] **Gate 5 — Cold-open eval.** `python scripts/derisk_cold_open_eval.py 20`
  (100% pass required)
- [ ] **Gate 6 — Stagehand vs browser-use eval.** 30-min hard time-box.
- [ ] **Gate 7 — Hello-world overlay stub on real IL SOS.** Already covered by
  Gate 1 — the CSP probe IS the hello-world.
- [ ] **Gate 8 — Sample PDF Chinese render.** Already validated via
  `python -m pdf.generator out/test.pdf` (Mandarin renders cleanly).
- [ ] **Gate 9 — 180s storyboard** word-for-word.
- [ ] **Gate 10 — Recording tooling** (OBS, mic input, macOS audio routing).
- [ ] **Gate 11 — Native Chinese speaker confirmed.**
- [ ] **Gate 12 — Lock the demo Chinese script word-for-word and freeze.**

## Demo modes

```bash
# Recording mode (default): seeded data, scripted voice, local mock
python main.py

# Recording mode against live IL SOS (after corpus labeling)
TARGET_ENV=live python main.py

# Live walkthrough — REAL microphone + REAL IL SOS site
DEMO_MODE=live_walkthrough TARGET_ENV=live python main.py
#   Requirements: ANTHROPIC_API_KEY + ELEVENLABS_API_KEY in .env, working mic.
#   Flow: floating "点击说话" mic button appears bottom-right.
#         1. Click to unmute, speak the cold-open Chinese sentence, click to mute.
#            Sonnet extracts your sentence into the LLC schema.
#         2. Demo walks 13 IL SOS pages. On the provisions agreement page,
#            overlay shows + cached Chinese audio plays. Click mic, speak
#            "同意" (or "不同意"), click mic. regex/Haiku resolves the answer.
#         3. Demo continues to payment processor, stops there.
```

## Web front door

The user-facing entry point lives in `web/`. It is a Next.js TypeScript app that
hosts the initial planning conversation: a founder chooses a language, answers
the high-level business questions by voice or text, gets a structured filing
packet, and then hands off to the filing destination.

```bash
cd web
npm install
npm run dev

# Optional: override the destination opened by "Continue with Shu Xiang"
NEXT_PUBLIC_FILING_URL="https://apps.ilsos.gov/llcarticles/" npm run dev
```

For the hackathon, the web app owns planning and the Python/Playwright demo owns
execution: once the packet exists, the guided filing session proves the agent
can operate the live form and ask only form-specific follow-ups.

## What's NOT done

- Live IL SOS selectors in `corpus.selector_live` (tonight's gate 3).
- Mic capture wiring on macOS — `voice/elevenlabs_voice.stream_transcripts` takes
  an `audio_chunks` async iterator; the mic-capture loop that produces it is a
  tonight task (sounddevice or pyaudio, PCM 16k mono).
- Pre-cached question audio mp3s in `assets/audio_cache/` — generated by
  `scripts/precache_question_audio.py` once `ELEVENLABS_API_KEY` is in `.env`.
  Recording mode runs silent until then (overlay still shows; user just doesn't
  hear the question).
- Stagehand evaluation (30-min time-box tonight).
- Browser-use Controller decorator API check — `agent/browser_loop.py` uses
  the canonical pattern but exact decorator may have evolved.
