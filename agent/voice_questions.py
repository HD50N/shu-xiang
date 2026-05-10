"""Detect and answer spoken clarifying questions during form-filling."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

from agent.i18n import Language


@dataclass
class ClarifyingAnswer:
    is_question: bool
    answer: str = ""


_QUESTION_HINTS = re.compile(
    r"(\?|what|why|how|who|when|where|which|should|can i|do i|does|is it|"
    r"什么|为什么|怎么|谁|哪里|哪|可以|需要|"
    r"무엇|왜|어떻게|누구|언제|어디|어느|해야|되나요|인가요)",
    re.IGNORECASE,
)


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


async def answer_if_clarifying_question(
    transcript: str,
    *,
    language: Language,
    current_prompt: str,
    field_name: str,
    explanation: str = "",
    allowed_values: Optional[list[str]] = None,
    known_context: str = "",
) -> ClarifyingAnswer:
    """Return an answer only if the utterance is a question, not a field answer."""
    text = (transcript or "").strip()
    if not text:
        return ClarifyingAnswer(False)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        if _QUESTION_HINTS.search(text):
            return ClarifyingAnswer(
                True,
                "I can explain, but I need the missing field value to continue. Please answer the question on screen.",
            )
        return ClarifyingAnswer(False)

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)
    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=420,
        system=(
            "You are a multilingual voice assistant helping a user complete a US business filing form. "
            "Decide whether the user's utterance is a clarifying question or an answer to the current form prompt. "
            "If it is a clarifying question, answer it briefly and practically in the target language, then invite them to answer the original prompt. "
            "If it is an answer, do not answer it; return is_question=false. "
            "Return JSON only: {\"is_question\": true|false, \"answer\": \"...\"}."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Target language: {language}\n"
                    f"Current form field: {field_name}\n"
                    f"Current prompt: {current_prompt}\n"
                    f"Explanation/context: {explanation}\n"
                    f"Allowed values: {allowed_values or []}\n"
                    f"Known filing context: {known_context}\n"
                    f"User utterance: {text}\n"
                ),
            }
        ],
    )

    for block in msg.content:
        if block.type == "text":
            parsed = json.loads(_extract_json_object(block.text))
            return ClarifyingAnswer(
                bool(parsed.get("is_question")),
                str(parsed.get("answer") or "").strip(),
            )
    return ClarifyingAnswer(False)
