"""Detect and answer spoken clarifying questions during form-filling.

The user might be ANSWERING the current form prompt, or ASKING a question
about the field / US business filing in general. Haiku classifies which.
If question, returns a useful in-language answer; if answer, returns
is_question=False so the runner can fill the field and continue.

Conversation history is supported so multi-turn back-and-forth ("what's a
registered agent?" → "do I need to be one myself?") gets context-aware
answers without repeating itself.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from agent.i18n import Language

logger = logging.getLogger("shuxiang.voice_questions")


@dataclass
class ClarifyingTurn:
    """One turn in the user-asks-AI-answers history."""
    user_utterance: str
    ai_answer: str


@dataclass
class ClarifyingAnswer:
    is_question: bool
    answer: str = ""


_QUESTION_HINTS = re.compile(
    r"(\?|what|why|how|who|when|where|which|should|can i|do i|does|is it|"
    r"什么|为什么|怎么|谁|哪里|哪|可以|需要|区别|意思|"
    r"무엇|왜|어떻게|누구|언제|어디|어느|해야|되나요|인가요)",
    re.IGNORECASE,
)


_FALLBACK_HINT_BY_LANGUAGE: dict[str, str] = {
    "zh": "我可以解释,但需要先听到你这个字段的回答才能继续。请回答屏幕上的问题。",
    "en": "I can explain, but I need your answer to the field on screen before continuing. Please answer the prompt.",
    "ko": "설명해 드릴 수 있지만 화면의 항목에 답해 주셔야 계속할 수 있습니다.",
}


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end >= start:
        return stripped[start : end + 1]
    return stripped


def _safe_parse(raw: str) -> Optional[dict]:
    """Best-effort JSON parse — never raises."""
    try:
        return json.loads(_extract_json_object(raw))
    except (json.JSONDecodeError, ValueError):
        return None


_SYSTEM_PROMPT = """\
You are a knowledgeable, friendly small-business filing assistant helping a user complete a US business form (LLC, EIN, sales tax registration, business license, etc). The user is filling out the form by voice in their own language.

For each user utterance, decide whether they are ANSWERING the current form prompt or ASKING you a clarifying question.

Rules:
- If the user is ANSWERING the form prompt: return is_question=false with empty answer. Do not echo or paraphrase their answer back. Trust the runner to handle the value.
- If the user is ASKING a question (about the field, the form, US business filing, what an option means, what to pick, why a step is needed, etc): return is_question=true. Answer concisely and practically (2-3 sentences max) in the target language. Be specific to their business profile and the current field. End with a brief invitation to answer the form prompt. Do NOT use markdown, bullet points, or formatting — this will be spoken aloud.
- If the utterance is BOTH an answer and an aside-question (e.g., "Standard, but quickly — what's series mean?"): prioritize the answer. Mark is_question=false. Don't lose form progress to a passing curiosity.
- If the utterance is unclear or just noise: return is_question=true with a short "I didn't catch that, could you repeat?" in the target language.
- Treat back-channels and acknowledgments ("hmm", "okay", "let me think") as neither — return is_question=true with a brief encouraging "Take your time" in the target language.

Output: JSON object only, no commentary, no markdown fences.
{"is_question": true|false, "answer": "..."}
"""


async def answer_if_clarifying_question(
    transcript: str,
    *,
    language: Language,
    current_prompt: str,
    field_name: str,
    explanation: str = "",
    allowed_values: Optional[list[str]] = None,
    known_context: str = "",
    history: Optional[list[ClarifyingTurn]] = None,
) -> ClarifyingAnswer:
    """Return an answer only if the utterance is a question, not a field answer.

    `history` is the running list of prior (user_utterance, ai_answer) pairs
    in the current clarification session. Pass it through so Haiku sees the
    multi-turn context and doesn't repeat earlier explanations.
    """
    text = (transcript or "").strip()
    if not text:
        return ClarifyingAnswer(False)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # Regex fallback: catch obvious questions, otherwise treat as answer.
        if _QUESTION_HINTS.search(text):
            fallback = _FALLBACK_HINT_BY_LANGUAGE.get(
                str(language), _FALLBACK_HINT_BY_LANGUAGE["en"]
            )
            return ClarifyingAnswer(True, fallback)
        return ClarifyingAnswer(False)

    from anthropic import AsyncAnthropic

    history_block = ""
    if history:
        recent = history[-4:]  # cap context — last 4 turns is plenty
        lines = []
        for turn in recent:
            lines.append(f"User asked: {turn.user_utterance}")
            lines.append(f"You answered: {turn.ai_answer}")
        history_block = "\n".join(lines)

    user_content = (
        f"Target language: {language}\n"
        f"Current form field: {field_name}\n"
        f"Current prompt: {current_prompt}\n"
        f"Explanation/context: {explanation}\n"
        f"Allowed values: {allowed_values or []}\n"
        f"Known filing context: {known_context}\n"
    )
    if history_block:
        user_content += f"Conversation so far:\n{history_block}\n"
    user_content += f"User utterance: {text}\n"

    try:
        client = AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=420,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception:
        logger.exception(
            "Haiku call failed for field=%s — falling back to treat-as-answer",
            field_name,
        )
        return ClarifyingAnswer(False)

    for block in msg.content:
        if block.type == "text":
            parsed = _safe_parse(block.text)
            if parsed is None:
                logger.warning(
                    "Haiku returned malformed JSON for field=%s utterance=%r — "
                    "treating as answer to avoid blocking",
                    field_name, text,
                )
                return ClarifyingAnswer(False)
            return ClarifyingAnswer(
                bool(parsed.get("is_question")),
                str(parsed.get("answer") or "").strip(),
            )
    return ClarifyingAnswer(False)
