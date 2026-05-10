"""
MyTax Illinois REG-1 (new business / sales tax registration) field corpus.

Wow #3 of the demo — the dependency-recognition beat. Agent navigates to
MyTax IL, autonomously starts the REG-1 form, fills the obvious autofill
fields on page 1, then pauses at FEIN with a bilingual annotation
explaining that the EIN dependency must be resolved first.

REG-1 bundles three checklist items (il_business_registration,
il_sales_tax, il_withholding) into a single filing, so this single
walkthrough represents three of the twelve obligations at once.

Selectors captured from live recon (scripts/recon_mytax_il.py). The Dp-N
IDs are GenTax widget identifiers — stable for a single recording session
but should be re-confirmed before demo day if MyTax IL ships a UI change.
"""

from __future__ import annotations

from dataclasses import dataclass


START_URL = "https://mytax.illinois.gov/_/"

# The homepage link that opens the REG-1 wizard (no login required).
REGISTER_LINK_TEXT = "Register a New Business (Form REG-1)"

# Page 1 selectors (captured 2026-05-10 via scripts/recon_mytax_il.py).
SEL_ORG_TYPE = "#Dp-3"      # FAST Enterprises combobox
SEL_FEIN = "#Dp-4"          # Federal EIN — the STOPPING POINT
SEL_FEIN_CONFIRM = "#Dp-5"  # Confirm FEIN
SEL_LEGAL_NAME = "#Dp-6"
SEL_DBA = "#Dp-7"


@dataclass(frozen=True)
class ReG1Field:
    """A REG-1 field the agent fills autonomously before the FEIN pause."""
    schema_key: str          # field on LLCSchema we read from (or constant if combobox)
    selector: str
    label_en: str
    is_combobox: bool = False
    combobox_value: str = ""  # literal listbox option text


# Order matters — demo fills these top-down so the cascade is readable.
# FEIN and Confirm FEIN are deliberately excluded — they're the stopping
# point. The annotation overlay anchors on SEL_FEIN.
REG1_AUTOFILL_FIELDS: tuple[ReG1Field, ...] = (
    ReG1Field(
        schema_key="llc_type",  # mapped to the literal combobox option below
        selector=SEL_ORG_TYPE,
        label_en="Organization Type",
        is_combobox=True,
        combobox_value="Limited Liability Company",
    ),
    ReG1Field(
        schema_key="entity_name",
        selector=SEL_LEGAL_NAME,
        label_en="Legal Name",
    ),
    ReG1Field(
        schema_key="dba",
        selector=SEL_DBA,
        label_en="DBA",
    ),
)
