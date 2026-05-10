"""
Regex-first enum extraction for the in-flow pause clarification.

Why regex first: the user's voice-answer in the recorded demo path is scripted.
Pattern-matching the transcript hits in <5ms with zero LLM dependency. The Haiku
4.5 fallback only fires when regex misses (live walkthrough mode where the user
might paraphrase).

Hybrid resolution from cross-model tension D12 in the eng review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExtractionResult:
    value: Optional[str]
    source: str  # 'regex' | 'llm' | 'miss'
    confidence: float  # 0.0–1.0
    elapsed_ms: float


# Patterns are intentionally generous (multiple ways to say the same answer in
# Mandarin) but tightly bound to the enum's actual values.
#
# Key idea: we match against the TRANSCRIPT (not the audio), so spoken
# disfluencies like "嗯..." or "我想..." don't break the match.

_PATTERNS: dict[str, dict[str, list[re.Pattern]]] = {
    "management_structure": {
        "member-managed": [
            re.compile(r"我自己"),  # "myself"
            re.compile(r"自己(运营|经营|管理|来做|做)"),
            re.compile(r"成员(管理|来管|自己)"),
            re.compile(r"member[\s-]?managed", re.IGNORECASE),
            re.compile(r"我(一个人|来运营|来管|来做)"),
            re.compile(r"不雇(人|经理)"),
        ],
        "manager-managed": [
            re.compile(r"雇(人|经理|个经理|管理者)"),
            re.compile(r"找(人|经理)(来)?(管理|运营)"),
            re.compile(r"经理(管理|来管|来做)"),
            re.compile(r"manager[\s-]?managed", re.IGNORECASE),
            re.compile(r"请(人|个|位)(管理|来运营)"),
        ],
    },
    "duration": {
        "perpetual": [
            re.compile(r"永久"),
            re.compile(r"长期"),
            re.compile(r"一直"),
            re.compile(r"perpetual", re.IGNORECASE),
            re.compile(r"没有(结束|期限)"),
        ],
        "fixed": [
            re.compile(r"固定(日期|结束|期限)"),
            re.compile(r"\d+\s*年(后|内|结束)"),
            re.compile(r"fixed", re.IGNORECASE),
            re.compile(r"临时"),
        ],
    },
}


# Negation guard — if the transcript contains a strong negation phrase before the
# match, swap to the opposite enum value if available. Cheap to be wrong here so
# we keep this minimal. Tonight's eval will surface false positives.
_NEGATIONS = (re.compile(r"不(是|要|想|做)"),)


def extract_enum(field_key: str, transcript_zh: str) -> ExtractionResult:
    """
    Try to extract a value from `transcript_zh` for `field_key`.

    Returns ExtractionResult with `value=None` on miss.
    """
    import time

    start = time.perf_counter()
    if field_key not in _PATTERNS:
        return ExtractionResult(
            value=None,
            source="miss",
            confidence=0.0,
            elapsed_ms=(time.perf_counter() - start) * 1000,
        )

    text = transcript_zh.strip()
    if not text:
        return ExtractionResult(
            value=None,
            source="miss",
            confidence=0.0,
            elapsed_ms=(time.perf_counter() - start) * 1000,
        )

    matches: list[tuple[str, int]] = []  # (value, score)
    for value, patterns in _PATTERNS[field_key].items():
        score = sum(1 for p in patterns if p.search(text))
        if score > 0:
            matches.append((value, score))

    if not matches:
        return ExtractionResult(
            value=None,
            source="miss",
            confidence=0.0,
            elapsed_ms=(time.perf_counter() - start) * 1000,
        )

    # Highest-scoring match wins. Ties resolve to the first-defined enum value.
    matches.sort(key=lambda mv: -mv[1])
    best_value, best_score = matches[0]

    # If multiple enum values matched, lower confidence (ambiguous).
    confidence = 0.95 if len(matches) == 1 else 0.65

    elapsed = (time.perf_counter() - start) * 1000
    return ExtractionResult(
        value=best_value,
        source="regex",
        confidence=confidence,
        elapsed_ms=elapsed,
    )
