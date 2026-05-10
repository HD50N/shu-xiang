"""
The single-writer LLC schema dict — the authoritative state for the demo.

Locked in eng review D3: orchestrator owns the dict; browser-use reads via
get_field_value(); the in-flow clarification tool writes before returning;
PDF generator reads the dict after the agent returns.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from corpus import DEMO_SEED


@dataclass
class LLCSchema:
    """The authoritative business state. Mutated only by the orchestrator."""
    # Real IL SOS page 1
    llc_type: Optional[str] = None  # "standard" | "series"
    # Real IL SOS page 2
    provisions_agreed: Optional[str] = None  # "yes" | "no"
    # Entity data (mock + later pages on real site)
    entity_name: Optional[str] = None
    principal_address: Optional[str] = None
    principal_city: Optional[str] = None
    principal_zip: Optional[str] = None
    management_structure: Optional[str] = None  # judgment field
    duration: Optional[str] = None
    registered_agent_name: Optional[str] = None
    registered_agent_address: Optional[str] = None
    organizer_name: Optional[str] = None
    organizer_email: Optional[str] = None
    organizer_phone: Optional[str] = None
    # Expedited service choice from page 12 in-flow pause
    expedited: Optional[str] = None  # "standard" | "expedited"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    def update_from(self, other: dict[str, Any]) -> list[str]:
        """Merge values from other dict; return list of keys that changed."""
        changed = []
        for k, v in other.items():
            if v is None or v == "":
                continue
            if hasattr(self, k) and getattr(self, k) != v:
                setattr(self, k, v)
                changed.append(k)
        return changed

    def is_complete(self) -> bool:
        """Every required field has a value."""
        required = (
            "entity_name",
            "principal_address",
            "principal_city",
            "principal_zip",
            "management_structure",
            "duration",
            "registered_agent_name",
            "registered_agent_address",
            "organizer_name",
            "organizer_email",
        )
        return all(getattr(self, k) for k in required)


@dataclass
class DemoState:
    """Runtime state passed across the three async tasks."""
    schema: LLCSchema = field(default_factory=LLCSchema)
    voice_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    overlay_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    failed_stage: Optional[str] = None
    # True when the live mic loop is active (user actually speaks). False
    # when the scripted feeder drives the demo. Page handlers read this to
    # decide whether to wait for real input vs use defaults.
    use_live_voice: bool = False
    # Phase 1 output — the BusinessProfile that drives Phase 2 obligation map.
    # Set by run_phase1_conversation() in live mode, or DEMO_PROFILE otherwise.
    business_profile: Any = None
    language: str = "zh"

    def seed_with_demo_data(self) -> None:
        """Populate from corpus.DEMO_SEED — used in recording mode."""
        self.schema.update_from(DEMO_SEED)
