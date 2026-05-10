"""
DERISK GATE 5: Cold-open intent extraction stability eval.

Run the EXACT scripted Chinese demo sentence through Sonnet 4.6 with structured
outputs N times, schema-validate each result, report pass rate.

Eng-review D7 requires 100% pass at N=20 before recording starts.

Usage:
    ANTHROPIC_API_KEY=... python scripts/derisk_cold_open_eval.py [N=20]
"""

from __future__ import annotations

import asyncio
import os
import sys

from voice.intent_extraction import extract_cold_open

# WORD-FOR-WORD frozen demo sentence. Any change re-triggers this eval.
DEMO_SENTENCE = (
    "我想注册我的餐厅为有限责任公司，叫做 Shu Xiang，"
    "在芝加哥，我是唯一所有者。"
)

# What we expect after extraction. We tolerate variations on entity_name
# (LLC suffix may or may not be appended depending on Sonnet's reading).
REQUIRED_KEYS = {"entity_name", "principal_city"}
EXPECTED_VALUES = {
    "principal_city": ("Chicago", "芝加哥"),
    "is_sole_owner": (True,),
}


async def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set. Skipping eval.")
        sys.exit(2)

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    print(f"Running cold-open eval ×{n} on:\n  {DEMO_SENTENCE}\n")

    passes = 0
    failures = []
    latencies = []

    for i in range(1, n + 1):
        result = await extract_cold_open(DEMO_SENTENCE)
        latencies.append(result.elapsed_ms)
        extracted = result.extracted
        ok = True
        reasons = []

        # Required keys present
        for k in REQUIRED_KEYS:
            if k not in extracted:
                ok = False
                reasons.append(f"missing {k}")

        # Expected values match (any of the alternatives)
        for k, allowed in EXPECTED_VALUES.items():
            if k in extracted:
                if extracted[k] not in allowed:
                    ok = False
                    reasons.append(f"{k}={extracted[k]!r} not in {allowed}")

        # entity_name must end in LLC (per Illinois requirement)
        name = extracted.get("entity_name", "")
        if not name or not (name.upper().endswith("LLC") or name.upper().endswith("L.L.C.")):
            ok = False
            reasons.append(f"entity_name={name!r} missing LLC suffix")

        if ok:
            passes += 1
            print(f"  [{i:02d}/{n}] ✓ {result.elapsed_ms:.0f}ms — {extracted}")
        else:
            failures.append((i, extracted, reasons))
            print(f"  [{i:02d}/{n}] ✗ {result.elapsed_ms:.0f}ms — {'; '.join(reasons)}")
            print(f"           got: {extracted}")

    print()
    print(f"Pass rate: {passes}/{n} = {100*passes/n:.0f}%")
    print(f"Latency: mean={sum(latencies)/len(latencies):.0f}ms, max={max(latencies):.0f}ms")
    if passes == n:
        print("\n✓ GATE PASSED — demo sentence is stable. Lock the script.")
        sys.exit(0)
    else:
        print(f"\n✗ GATE FAILED — {len(failures)} variance(s). Iterate the prompt or rephrase the line.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
