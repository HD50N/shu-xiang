"""
Phase 1 conversational intake.

Sonnet drives the dialog. After each user utterance, Sonnet decides:
  1. Which slots did the user just fill?
  2. Was anything ambiguous? (need a clarifying follow-up)
  3. Have all required slots been filled? (FINISH → Phase 2)

Each turn:
  - Wait for user transcript on voice_queue
  - Show "正在思考…" thinking indicator
  - Sonnet → { profile_updates, next_action, question_zh, reasoning }
  - Merge updates, paint sidebar
  - If ASK: live ElevenLabs TTS for the new question, play it, repeat
  - If FINISH: hide thinking, return — demo_runner's Phase 2 reveal voice-over takes over

Fallbacks:
  - No ANTHROPIC_API_KEY → fixed-script intake (legacy DEMO_TURNS path)
  - Sonnet errors / invalid output → fall back to next fixed-script question
  - ElevenLabs TTS errors → text-only (user reads the question on screen)
  - Hard cap MAX_TURNS=12 — live mode leaves unknown slots empty instead of
    backfilling demo values
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import Page

from agent.i18n import Language, localize, t
from agent.overlay_bridge import type_opening_transcript
from agent.state import DemoState
from corpus.requirements import BusinessProfile

logger = logging.getLogger("shuxiang.preflight_conv")

_AUDIO_CACHE_DIR = Path(__file__).resolve().parent.parent / "assets" / "audio_cache"

# Hard cap on turns. Sonnet can FINISH earlier; this stops a wandering
# conversation from blowing the demo budget.
MAX_TURNS = 12
DEFAULT_LISTEN_TIMEOUT_S = 25.0


# ──────────────────────────────────────────────────────────────────────
# Legacy fixed-script intake (fallback path).
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ConversationTurn:
    """One question-and-answer round of the legacy fixed-script dialog."""
    audio_key: str
    question_zh: str
    profile_field: str
    schema_field: Optional[str] = None
    skip_if_already_set: bool = True


DEMO_TURNS: list[ConversationTurn] = [
    ConversationTurn(
        audio_key="phase1_q1_business",
        question_zh="你好！告诉我你的生意 — 你做什么，公司叫什么名字？",
        profile_field="business_summary",
        schema_field="entity_name",
    ),
    ConversationTurn(
        audio_key="phase1_q2_location",
        question_zh="你的店开在哪里？地址或者大概的位置都可以。",
        profile_field="location",
        schema_field="principal_address",
    ),
    ConversationTurn(
        audio_key="phase1_q3_owner_hire",
        question_zh="你是唯一的所有者吗？打算雇人吗？",
        profile_field="owner_hire",
    ),
    ConversationTurn(
        audio_key="phase1_q4_food_alcohol",
        question_zh="餐厁卖什么？只卖食物，还是也卖酒？",
        profile_field="food_alcohol",
    ),
]


# ──────────────────────────────────────────────────────────────────────
# Sonnet-driven dynamic intake — system prompt + tool.
# ──────────────────────────────────────────────────────────────────────

_INTAKE_SYSTEM_PROMPT = """You are Shu Xiang, a multilingual AI consultant helping an immigrant business owner file an Illinois LLC. The user just unmuted their mic and is talking to you.

Your job: in 3-6 short conversational turns, gather a structured business profile so the system can generate a personalized compliance checklist. Do not front-load filing minutiae; later form steps will ask for missing filing details when needed.

REQUIRED slots (must all be filled before you FINISH):
- entity_name — the business name (string)
- business_type — restaurant / retail / salon / services / online / etc.
- city — city name in English (e.g. 芝加哥 → "Chicago")
- sole_owner — boolean
- plans_to_hire — boolean
- sells_food — boolean (matters for licensing in Illinois)

OPTIONAL slots (fill if the user volunteers them — do NOT probe):
- principal_address, principal_city, principal_zip
- organizer_name, organizer_email, organizer_phone
- registered_agent_name, registered_agent_address
- sells_alcohol — only ask if business_type=restaurant AND user might serve alcohol
- online_only — boolean (no physical location)
- different_dba — boolean (operating under a different name than entity_name)
- state — defaults to "IL"

DECISION RULES:
1. Each turn, you receive (a) the running profile and (b) the user's latest utterance.
2. Extract any slots the user just answered. If their answer was vague, leave that slot empty.
3. If a REQUIRED slot is empty OR the last answer was ambiguous → next_action="ASK", write ONE short question in the requested target conversation language for the most-important missing/ambiguous slot.
4. If all REQUIRED slots are filled clearly → next_action="FINISH".
5. Hard cap: turn_num >= 12 → FINISH regardless.

QUESTION STYLE (when ASK):
- Short, conversational, not formal.
- Use the requested target conversation language.
- ONE focus per question, but naturally-paired slots can combine: "你是唯一的所有者吗？打算雇人吗？" or "卖食物吗？也卖酒吗？" is fine.
- Don't ask about something you already heard. If the user said "我自己开" then sole_owner is true — move on.
- Clarify when vague: user says "我开店" → ask "什么样的店？餐厁还是零售？"

EXTRACTION HEURISTICS:
- If the user gives a brand name without "LLC" suffix, fill entity_name with the brand only — the system appends "LLC" later.
- City names: 芝加哥 → "Chicago", 纽约 → "New York", etc.
- If the user gives a business street address and city, also fill principal_city with that city.
- If the user says the registered agent address is the same as the business address, fill registered_agent_address with the business address.
- Do not invent organizer_name, organizer_email, organizer_phone, street address, ZIP code, or registered agent info.
- "我自己开" / "我一个人" → sole_owner=true
- "雇人" / "请人" / "找人帮忙" → plans_to_hire=true; "我自己做" / "不雇" → plans_to_hire=false
- "餐厁" / "饭店" / "卖吃的" → business_type="restaurant", sells_food=true
- Don't fabricate. Empty/missing values stay empty.

Always return your decision via the intake_turn tool. Never write prose."""


_INTAKE_TURN_TOOL = {
    "name": "intake_turn",
    "description": "Process one conversational turn. Return profile updates and the next action.",
    "input_schema": {
        "type": "object",
        "properties": {
            "profile_updates": {
                "type": "object",
                "description": "Slots extracted from the user's latest utterance. Include ONLY slots you actually heard the user answer this turn — don't re-echo prior values. Use null/omit for slots not heard.",
                "properties": {
                    "entity_name": {"type": "string"},
                    "business_type": {"type": "string"},
                    "city": {"type": "string"},
                    "state": {"type": "string"},
                    "principal_address": {"type": "string"},
                    "principal_city": {"type": "string"},
                    "principal_zip": {"type": "string"},
                    "organizer_name": {"type": "string"},
                    "organizer_email": {"type": "string"},
                    "organizer_phone": {"type": "string"},
                    "registered_agent_name": {"type": "string"},
                    "registered_agent_address": {"type": "string"},
                    "sole_owner": {"type": "boolean"},
                    "plans_to_hire": {"type": "boolean"},
                    "sells_food": {"type": "boolean"},
                    "sells_alcohol": {"type": "boolean"},
                    "online_only": {"type": "boolean"},
                    "different_dba": {"type": "boolean"},
                },
            },
            "next_action": {
                "type": "string",
                "enum": ["ASK", "FINISH"],
                "description": "ASK = ask another question; FINISH = all required slots filled, move to Phase 2.",
            },
            "question_zh": {
                "type": "string",
                "description": "If next_action=ASK, the next question in the requested target language. Empty string if FINISH.",
            },
            "reasoning": {
                "type": "string",
                "description": "One short sentence explaining why you picked this action.",
            },
        },
        "required": ["profile_updates", "next_action", "question_zh", "reasoning"],
    },
}


async def _intake_turn(
    transcript: str,
    current_profile: dict[str, Any],
    turn_num: int,
    language: Language,
) -> dict[str, Any]:
    """One round-trip with Sonnet. Returns the parsed tool input."""
    from anthropic import AsyncAnthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = AsyncAnthropic(api_key=api_key)

    user_msg = (
        f"Turn {turn_num}/{MAX_TURNS}.\n"
        f"Running profile (JSON): {json.dumps(current_profile, ensure_ascii=False)}\n"
        f"Target conversation language: {language}\n"
        f"User just said: \"{transcript}\"\n\n"
        f"Extract any slots they just filled, then decide ASK or FINISH. "
        f"If ASK, write ONE short question in the target conversation language "
        f"for the most-important missing slot."
    )
    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=_INTAKE_SYSTEM_PROMPT,
        tools=[_INTAKE_TURN_TOOL],
        tool_choice={"type": "tool", "name": "intake_turn"},
        messages=[{"role": "user", "content": user_msg}],
    )
    for block in msg.content:
        if block.type == "tool_use" and block.name == "intake_turn":
            return dict(block.input)
    raise RuntimeError("Sonnet did not call intake_turn tool")


# ──────────────────────────────────────────────────────────────────────
# Audio + UI helpers.
# ──────────────────────────────────────────────────────────────────────

async def _play_audio(page: Page, audio_key: str) -> None:
    """Play a cached mp3 from assets/audio_cache/."""
    audio_path = _AUDIO_CACHE_DIR / f"{audio_key}.mp3"
    if not audio_path.exists():
        logger.warning("audio cache miss: %s (run scripts/precache_question_audio.py)", audio_path)
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


async def _play_audio_bytes(page: Page, mp3_bytes: bytes) -> None:
    """Play mp3 bytes via a base64 data URL — no temp file."""
    b64 = base64.b64encode(mp3_bytes).decode("ascii")
    await page.evaluate(
        """(b64) => new Promise((resolve) => {
            const url = 'data:audio/mpeg;base64,' + b64;
            const a = new Audio(url);
            a.onended = resolve;
            a.onerror = resolve;
            a.play().catch(resolve);
        })""",
        b64,
    )


async def _speak_text(page: Page, text: str, *, audio_key: str | None, language: Language) -> None:
    """Use cached Chinese audio when possible; synthesize other languages live."""
    if language == "zh" and audio_key:
        await _play_audio(page, audio_key)
        return
    try:
        from voice.elevenlabs_voice import synthesize_to_bytes

        mp3 = await synthesize_to_bytes(text)
        await _play_audio_bytes(page, mp3)
    except Exception:
        logger.exception("TTS failed for %r — text-only this turn", text)


async def _set_question_text(page: Page, question_zh: str) -> None:
    """Update the opening prompt's question / clear the transcript box."""
    await page.evaluate(
        """(q) => {
            const promptEl = document.querySelector('.shuxiang-opening-prompt');
            if (promptEl) {
                promptEl.textContent = q;
                promptEl.style.opacity = '1';
                delete promptEl.dataset.originalText;
            }
            const wrap = document.querySelector('.shuxiang-opening-transcript');
            if (wrap) {
                const cursor = wrap.querySelector('.shuxiang-opening-transcript-cursor');
                wrap.innerHTML = '';
                const span = document.createElement('span');
                wrap.appendChild(span);
                if (cursor) wrap.appendChild(cursor);
                else {
                    const c = document.createElement('span');
                    c.className = 'shuxiang-opening-transcript-cursor';
                    wrap.appendChild(c);
                }
            }
        }""",
        question_zh,
    )


async def _show_thinking(page: Page, label_zh: str = "正在思考…") -> None:
    await page.evaluate(
        """(t) => {
            const promptEl = document.querySelector('.shuxiang-opening-prompt');
            if (promptEl) {
                if (!promptEl.dataset.originalText) {
                    promptEl.dataset.originalText = promptEl.textContent;
                }
                promptEl.textContent = t;
                promptEl.style.opacity = '0.6';
            }
        }""",
        label_zh,
    )


async def _hide_thinking(page: Page) -> None:
    await page.evaluate(
        """() => {
            const promptEl = document.querySelector('.shuxiang-opening-prompt');
            if (promptEl) {
                if (promptEl.dataset.originalText) {
                    promptEl.textContent = promptEl.dataset.originalText;
                    delete promptEl.dataset.originalText;
                }
                promptEl.style.opacity = '1';
            }
        }"""
    )


async def _paint_sidebar(page: Page, profile: dict[str, Any]) -> None:
    for k, v in profile.items():
        if v in (None, ""):
            continue
        try:
            await page.evaluate(
                "({k, v}) => window.shuxiang.updateSidebarField && window.shuxiang.updateSidebarField(k, String(v))",
                {"k": k, "v": v},
            )
        except Exception:
            pass


_ACK_ROTATION = ("ack_1", "ack_2", "ack_3")

_REQUIRED_PROFILE_FIELDS = (
    "entity_name",
    "business_type",
    "sole_owner",
    "plans_to_hire",
    "sells_food",
)

_MISSING_FIELD_QUESTIONS_ZH = {
    "entity_name": "公司叫什么名字？",
    "business_type": "你要做什么类型的生意？",
    "principal_address": "营业地址的街道地址是什么？",
    "principal_city": "营业地址在哪个城市？",
    "principal_zip": "营业地址的邮编是多少？",
    "organizer_name": "申请人的法定姓名是什么？",
    "organizer_email": "申请人的邮箱是什么？",
    "organizer_phone": "申请人的联系电话是什么？",
    "registered_agent_name": "注册代理人的姓名或服务公司名称是什么？",
    "registered_agent_address": "注册代理人的伊利诺伊州地址是什么？如果和营业地址一样，也请说明。",
    "sole_owner": "你是唯一所有者吗？",
    "plans_to_hire": "你打算雇员工吗？",
    "sells_food": "这个生意会卖食品吗？",
}

_MISSING_FIELD_QUESTIONS_EN = {
    "entity_name": "What is the company name?",
    "business_type": "What type of business are you starting?",
    "principal_address": "What is the street address for the business?",
    "principal_city": "What city is the business address in?",
    "principal_zip": "What is the ZIP code for the business address?",
    "organizer_name": "What is the legal name of the person filing?",
    "organizer_email": "What is the filing contact email address?",
    "organizer_phone": "What is the filing contact phone number?",
    "registered_agent_name": "What is the name of the registered agent or registered-agent service?",
    "registered_agent_address": "What is the registered agent's Illinois address? If it is the same as the business address, say that.",
    "sole_owner": "Are you the only owner?",
    "plans_to_hire": "Do you plan to hire employees?",
    "sells_food": "Will this business sell food?",
}

_MISSING_FIELD_QUESTIONS_KO = {
    "entity_name": "회사 이름은 무엇인가요?",
    "business_type": "어떤 종류의 사업을 시작하시나요?",
    "principal_address": "사업장 도로명 주소는 무엇인가요?",
    "principal_city": "사업장 주소는 어느 도시에 있나요?",
    "principal_zip": "사업장 주소의 우편번호는 무엇인가요?",
    "organizer_name": "신청하는 사람의 법적 이름은 무엇인가요?",
    "organizer_email": "신청 연락처 이메일은 무엇인가요?",
    "organizer_phone": "신청 연락처 전화번호는 무엇인가요?",
    "registered_agent_name": "등록 대리인 또는 등록 대리 서비스의 이름은 무엇인가요?",
    "registered_agent_address": "등록 대리인의 일리노이 주소는 무엇인가요? 사업장 주소와 같다면 그렇게 말씀해 주세요.",
    "sole_owner": "본인이 유일한 소유자인가요?",
    "plans_to_hire": "직원을 고용할 계획인가요?",
    "sells_food": "이 사업에서 음식을 판매하나요?",
}

_MISSING_FIELD_QUESTIONS_BY_LANG = {
    "zh": _MISSING_FIELD_QUESTIONS_ZH,
    "en": _MISSING_FIELD_QUESTIONS_EN,
    "ko": _MISSING_FIELD_QUESTIONS_KO,
}


def _missing_required_fields(profile: dict[str, Any]) -> list[str]:
    return [
        key for key in _REQUIRED_PROFILE_FIELDS
        if profile.get(key) in (None, "")
    ]


def _question_for_missing_field(field_key: str, language: Language) -> str:
    lang = language if language in _MISSING_FIELD_QUESTIONS_BY_LANG else str(language).lower()
    if lang in _MISSING_FIELD_QUESTIONS_BY_LANG:
        return _MISSING_FIELD_QUESTIONS_BY_LANG[lang].get(field_key, "Please provide the missing required information.")
    return localize(
        _MISSING_FIELD_QUESTIONS_ZH.get(field_key, "还缺少一个必填信息，请补充。"),
        language,
    )


# ──────────────────────────────────────────────────────────────────────
# Profile finalization (shared by both paths).
# ──────────────────────────────────────────────────────────────────────

def _finalize_profile(profile: dict[str, Any]) -> tuple[BusinessProfile, dict[str, Any]]:
    """Normalize live intake without inventing missing user-provided values."""
    name = profile.get("entity_name") or ""
    if name and not name.upper().endswith(("LLC", "L.L.C.")):
        profile["entity_name"] = f"{name} LLC"
    if profile.get("city") and not profile.get("principal_city"):
        profile["principal_city"] = profile["city"]

    bp = BusinessProfile(
        entity_name=profile.get("entity_name"),
        business_type=profile.get("business_type"),
        city=profile.get("city") or profile.get("principal_city"),
        state=profile.get("state") or "IL",
        sole_owner=profile.get("sole_owner"),
        plans_to_hire=profile.get("plans_to_hire"),
        sells_food=profile.get("sells_food"),
        sells_alcohol=profile.get("sells_alcohol"),
        online_only=profile.get("online_only"),
        different_dba=profile.get("different_dba"),
    )
    return bp, profile


# ──────────────────────────────────────────────────────────────────────
# Dynamic intake — Sonnet drives every question.
# ──────────────────────────────────────────────────────────────────────

async def _run_dynamic_intake(
    page: Page,
    state: DemoState,
    *,
    listen_timeout_s: float,
    inter_turn_pause_s: float,
    language: Language,
) -> tuple[BusinessProfile, dict[str, Any]]:
    profile: dict[str, Any] = {}

    # Greeting — cached. Same audio file we use in the legacy script. The text
    # is open-ended ("tell me about your business — what do you do, what's the
    # company called?") so the user can fill 2-3 slots in their first answer.
    greeting = localize("你好！告诉我你的生意 — 你做什么，公司叫什么名字？", language)
    await _set_question_text(page, greeting)
    await asyncio.sleep(0.3)
    await _speak_text(page, greeting, audio_key="phase1_q1_business", language=language)
    await asyncio.sleep(0.3)

    for turn_num in range(1, MAX_TURNS + 1):
        # Wait for the user's voice answer.
        try:
            transcript = await asyncio.wait_for(
                state.voice_queue.get(), timeout=listen_timeout_s
            )
        except asyncio.TimeoutError:
            logger.warning("phase1 turn %d timed out — ending intake", turn_num)
            break
        logger.info("phase1 turn %d transcript: %r", turn_num, transcript)

        await type_opening_transcript(page, transcript, 0)
        await asyncio.sleep(0.4)

        # Thinking indicator covers the Sonnet round-trip + TTS synth.
        await _show_thinking(page, t("overlay_thinking", language))

        # Sonnet decides next action.
        try:
            result = await _intake_turn(transcript, profile, turn_num, language)
        except Exception:
            logger.exception("phase1 sonnet turn %d failed — finalizing", turn_num)
            break

        updates = result.get("profile_updates") or {}
        for k, v in updates.items():
            if v is None or v == "":
                continue
            profile[k] = v
        await _paint_sidebar(page, profile)

        action = (result.get("next_action") or "ASK").upper()
        question_zh = (result.get("question_zh") or "").strip()
        missing = _missing_required_fields(profile)
        if missing:
            action = "ASK"
            if not question_zh or (result.get("next_action") or "").upper() == "FINISH":
                question_zh = _question_for_missing_field(missing[0], language)
        reasoning = result.get("reasoning") or ""
        logger.info("phase1 turn %d → %s missing=%s [%s]", turn_num, action, missing, reasoning)

        # FINISH: Phase 2 reveal voice-over (in demo_runner) handles the
        # transition. Just clear the thinking indicator and exit.
        if (action == "FINISH" and not missing) or turn_num >= MAX_TURNS or not question_zh:
            await _hide_thinking(page)
            break

        # ASK: short ack, then synthesize and play the AI's next question.
        ack_key = _ACK_ROTATION[(turn_num - 1) % len(_ACK_ROTATION)]
        await _play_audio(page, ack_key)
        await _hide_thinking(page)

        await _set_question_text(page, question_zh)
        await asyncio.sleep(0.2)

        try:
            await _speak_text(page, question_zh, audio_key=None, language=language)
        except Exception:
            # TTS failure is non-fatal — user reads the question text on screen.
            logger.exception("live TTS failed for %r — text-only this turn", question_zh)

        await asyncio.sleep(inter_turn_pause_s)

    return _finalize_profile(profile)


# ──────────────────────────────────────────────────────────────────────
# Fixed-script intake — fallback when Sonnet isn't available.
# ──────────────────────────────────────────────────────────────────────

_PROFILE_EXTRACTION_SYSTEM = """You are a multilingual business intake assistant for an LLC filing agent. You are running ONE turn of a multi-turn conversation — extract just the fields covered by the current question.

You receive: the current question, the user's spoken response transcript, and the profile-so-far (JSON).

Your job: return an updated profile JSON that incorporates whatever the user said in this turn. Do NOT make up values. If the user didn't answer a particular field clearly, leave it null/missing.

The profile schema is:
- entity_name: string (LLC name; append "LLC" suffix if the user gave just a brand name)
- business_type: string (e.g. "restaurant", "retail", "salon")
- city: string (city name in English; e.g. 芝加哥 → "Chicago")
- state: string (US state code; default "IL")
- principal_address: string (street address only if explicitly given)
- principal_city: string (matches city)
- principal_zip: string (only if given)
- organizer_name: string (legal name of the person filing)
- organizer_email: string
- organizer_phone: string
- registered_agent_name: string
- registered_agent_address: string
- sole_owner: bool (true if user said they are the only owner)
- plans_to_hire: bool (true if user mentioned hiring or having employees)
- sells_food: bool
- sells_alcohol: bool
- online_only: bool
- different_dba: bool

Return your answer by calling the update_profile tool. No prose."""


_UPDATE_PROFILE_TOOL = {
    "name": "update_profile",
    "description": "Merge fields extracted from the user's latest answer into the running business profile.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_name": {"type": "string"},
            "business_type": {"type": "string"},
            "city": {"type": "string"},
            "state": {"type": "string"},
            "principal_address": {"type": "string"},
            "principal_city": {"type": "string"},
            "principal_zip": {"type": "string"},
            "organizer_name": {"type": "string"},
            "organizer_email": {"type": "string"},
            "organizer_phone": {"type": "string"},
            "registered_agent_name": {"type": "string"},
            "registered_agent_address": {"type": "string"},
            "sole_owner": {"type": "boolean"},
            "plans_to_hire": {"type": "boolean"},
            "sells_food": {"type": "boolean"},
            "sells_alcohol": {"type": "boolean"},
            "online_only": {"type": "boolean"},
            "different_dba": {"type": "boolean"},
        },
        "required": [],
    },
}


async def _extract_turn(
    question: str,
    transcript: str,
    current_profile: dict[str, Any],
) -> dict[str, Any]:
    from anthropic import AsyncAnthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = AsyncAnthropic(api_key=api_key)

    user_msg = (
        f"Current question: {question}\n"
        f"User's spoken answer: {transcript}\n"
        f"Profile so far (JSON): {json.dumps(current_profile, ensure_ascii=False)}\n\n"
        f"Extract whatever fields the user just answered. Merge into the profile. "
        f"Call update_profile with the FULL merged profile (existing values + new ones)."
    )
    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=_PROFILE_EXTRACTION_SYSTEM,
        tools=[_UPDATE_PROFILE_TOOL],
        tool_choice={"type": "tool", "name": "update_profile"},
        messages=[{"role": "user", "content": user_msg}],
    )
    extracted: dict[str, Any] = {}
    for block in msg.content:
        if block.type == "tool_use" and block.name == "update_profile":
            extracted = dict(block.input)
            break
    return {**current_profile, **{k: v for k, v in extracted.items() if v not in (None, "")}}


async def _run_fixed_script_intake(
    page: Page,
    state: DemoState,
    *,
    turns: list[ConversationTurn],
    listen_timeout_s: float,
    inter_turn_pause_s: float,
    language: Language,
) -> tuple[BusinessProfile, dict[str, Any]]:
    profile: dict[str, Any] = {}

    for i, turn in enumerate(turns, start=1):
        logger.info("phase1 fixed turn %d/%d: %s", i, len(turns), turn.profile_field)

        question = localize(turn.question_zh, language)
        await _set_question_text(page, question)
        await asyncio.sleep(0.3)
        await _speak_text(page, question, audio_key=turn.audio_key, language=language)
        await asyncio.sleep(0.3)

        try:
            transcript = await asyncio.wait_for(
                state.voice_queue.get(), timeout=listen_timeout_s
            )
        except asyncio.TimeoutError:
            logger.warning("phase1 turn %d timed out — skipping", i)
            continue
        logger.info("phase1 turn %d transcript: %r", i, transcript)

        await type_opening_transcript(page, transcript, 0)
        await asyncio.sleep(0.4)

        await _show_thinking(page, t("overlay_thinking", language))

        try:
            profile = await _extract_turn(question, transcript, profile)
            logger.info("phase1 profile after turn %d: %s", i, profile)
        except Exception:
            logger.exception("phase1 turn %d extraction failed", i)

        await _paint_sidebar(page, profile)

        if i < len(turns):
            ack_key = _ACK_ROTATION[(i - 1) % len(_ACK_ROTATION)]
            await _play_audio(page, ack_key)
            await _hide_thinking(page)
        else:
            await _hide_thinking(page)

        await asyncio.sleep(inter_turn_pause_s)

    return _finalize_profile(profile)


# ──────────────────────────────────────────────────────────────────────
# Public entry point — picks dynamic intake when possible, falls back.
# ──────────────────────────────────────────────────────────────────────

async def run_phase1_conversation(
    page: Page,
    state: DemoState,
    *,
    turns: Optional[list[ConversationTurn]] = None,
    listen_timeout_s: float = DEFAULT_LISTEN_TIMEOUT_S,
    inter_turn_pause_s: float = 0.7,
    language: Language = "zh",
) -> tuple[BusinessProfile, dict[str, Any]]:
    """
    Run Phase 1 intake. Sonnet-driven dynamic conversation when an
    ANTHROPIC_API_KEY is available; falls back to the fixed 4-question script
    otherwise.

    Returns (BusinessProfile, raw_profile_dict). Caller is responsible for
    having shown the opening prompt and installed the mic button.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            return await _run_dynamic_intake(
                page,
                state,
                listen_timeout_s=listen_timeout_s,
                inter_turn_pause_s=inter_turn_pause_s,
                language=language,
            )
        except Exception:
            logger.exception("dynamic intake failed — falling back to fixed script")

    return await _run_fixed_script_intake(
        page,
        state,
        turns=turns or DEMO_TURNS,
        listen_timeout_s=listen_timeout_s,
        inter_turn_pause_s=inter_turn_pause_s,
        language=language,
    )
