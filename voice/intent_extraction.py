"""
Cold-open intent extraction (Sonnet 4.6) and in-flow Haiku fallback.

Two API surfaces:
- extract_cold_open(chinese_sentence) -> dict — fires once at demo start; fills
  six fields from one Chinese sentence. Uses Claude Sonnet 4.6 with structured
  outputs.
- extract_field_value_haiku(field_key, transcript) -> str | None — fallback
  when regex_match misses. Uses Claude Haiku 4.5, single-field, single-enum.

The cold-open prompt is locked tonight via the 20× stability eval (D7).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from anthropic import AsyncAnthropic

from corpus import CORPUS_FIELDS, FIELDS_BY_KEY, FieldKind

_client: Optional[AsyncAnthropic] = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _client = AsyncAnthropic(api_key=api_key)
    return _client


# ──────────────────────────────────────────────────────────────────────────
# Cold-open: Chinese sentence → six-field LLC schema
# ──────────────────────────────────────────────────────────────────────────

# Tool schema: forces Claude to return strict JSON we can validate.
_COLD_OPEN_TOOL = {
    "name": "submit_llc_intake",
    "description": (
        "Extract Illinois LLC filing fields from a Chinese-language description "
        "of a small business. Return ONLY values present or directly implied by "
        "the user's words; if a field can't be determined, omit it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_name": {
                "type": "string",
                "description": (
                    "The LLC name. If the user says '叫做 Shu Xiang', return "
                    "'Shu Xiang LLC' (append 'LLC' suffix if absent — Illinois "
                    "requires it). NEVER hallucinate a name that wasn't said."
                ),
            },
            "principal_city": {"type": "string", "description": "City of business"},
            "principal_address": {
                "type": "string",
                "description": (
                    "Street address if mentioned. Omit if user only gave city. "
                    "Do NOT invent addresses."
                ),
            },
            "principal_zip": {"type": "string"},
            "organizer_name": {"type": "string"},
            "is_sole_owner": {
                "type": "boolean",
                "description": (
                    "True if the user said they are the only owner / sole "
                    "owner / 唯一所有者 / 一个人开. False if they mentioned "
                    "partners or co-owners."
                ),
            },
        },
        "required": [],
    },
}


_COLD_OPEN_SYSTEM = """You are an intake assistant for Illinois LLC filings. Native speakers of Mandarin Chinese describe their small business in one sentence. Your job is to extract structured filing data.

Rules:
- ONLY return fields the user explicitly provided or directly implied.
- NEVER hallucinate a value (especially names or addresses).
- If a field is uncertain, omit it (the form will fall back to other defaults).
- The entity_name must include the "LLC" suffix per Illinois requirements; append it if the user only gave the brand name.
- If the user said they are the sole owner ("我是唯一所有者", "我自己一个人", "就我一个"), set is_sole_owner: true.

Return your answer by calling the submit_llc_intake tool. No prose."""


@dataclass
class ColdOpenResult:
    extracted: dict[str, Any]
    elapsed_ms: float
    raw: Any


async def extract_cold_open(chinese_sentence: str) -> ColdOpenResult:
    """
    Run the cold-open intent extraction. Tonight's 20× eval validates this
    against the EXACT scripted demo sentence.
    """
    import time

    client = _get_client()
    start = time.perf_counter()
    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=_COLD_OPEN_SYSTEM,
        tools=[_COLD_OPEN_TOOL],
        tool_choice={"type": "tool", "name": "submit_llc_intake"},
        messages=[{"role": "user", "content": chinese_sentence}],
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    extracted: dict[str, Any] = {}
    for block in msg.content:
        if block.type == "tool_use" and block.name == "submit_llc_intake":
            extracted = dict(block.input)
            break

    return ColdOpenResult(extracted=extracted, elapsed_ms=elapsed_ms, raw=msg)


# ──────────────────────────────────────────────────────────────────────────
# In-flow Haiku fallback for enum extraction
# ──────────────────────────────────────────────────────────────────────────

_HAIKU_SYSTEM = """You classify a multilingual voice answer into one of a fixed set of enum values for a US LLC filing form. Return only the matching value, exactly as listed. If none match, return "unknown"."""


async def extract_field_value_haiku(
    field_key: str, transcript: str
) -> Optional[str]:
    """
    Fallback when regex_match misses. Uses Haiku 4.5 for ~300ms latency.
    Returns the enum value or None if no match.
    """
    field = FIELDS_BY_KEY.get(field_key)
    if not field or field.kind != FieldKind.JUDGMENT or not field.enum_values:
        return None

    enum_list = ", ".join(f'"{v}"' for v in field.enum_values)
    prompt = (
        f"Field: {field.name}\n"
        f"Allowed values: [{enum_list}]\n"
        f"Question: {field.question_zh}\n"
        f"User said: {transcript}\n\n"
        f"Return ONLY one of the allowed values, or the literal string \"unknown\"."
    )

    client = _get_client()
    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=32,
        system=_HAIKU_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    text = ""
    for block in msg.content:
        if block.type == "text":
            text = block.text.strip().strip('"').strip()
            break

    if text in field.enum_values:
        return text
    return None


# ──────────────────────────────────────────────────────────────────────────
# Hybrid resolver: regex → Haiku → None
# ──────────────────────────────────────────────────────────────────────────

async def resolve_enum_answer(field_key: str, transcript: str) -> tuple[Optional[str], str]:
    """
    The actual entrypoint used by the in-flow pause clarification tool.
    Returns (value, source) where source is 'regex', 'llm', or 'miss'.
    """
    from voice.regex_match import extract_enum

    rx = extract_enum(field_key, transcript)
    if rx.value and rx.confidence >= 0.9:
        return rx.value, "regex"

    # Regex missed or low-confidence — fall back to Haiku.
    haiku_value = await extract_field_value_haiku(field_key, transcript)
    if haiku_value:
        return haiku_value, "llm"

    return None, "miss"
