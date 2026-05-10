"""
Field corpus for the Illinois LLC-1.36 Articles of Organization form.

Each field is labeled:
  - autofill: agent fills from pre-flight intent extraction with no user input
  - judgment: requires the user's input to decide; one of these becomes the
              in-flow pause centerpiece, the rest are resolved during pre-flight
  - lookup: derived from a known data source (e.g., NAICS code, address geocoding)

The selector strings target the LOCAL MOCK at demo/il_sos_mock.html.
Tonight's task: capture equivalent selectors on the LIVE IL SOS site and replace
the SELECTORS_LIVE entries below.

The Chinese explanation copy here is the EXACT text that flows into the in-flow
pause overlay's annotation card. Native-speaker review tonight before recording.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FieldKind(str, Enum):
    AUTOFILL = "autofill"
    JUDGMENT = "judgment"
    LOOKUP = "lookup"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: FieldKind
    selector_mock: str  # selector on demo/il_sos_mock.html
    selector_live: Optional[str]  # selector on live IL SOS — captured tonight
    schema_key: str  # key in the LLC schema dict
    question_zh: Optional[str] = None  # Chinese question (for judgment fields)
    explanation_zh: Optional[str] = None  # Chinese explanation (for judgment fields)
    enum_values: Optional[tuple[str, ...]] = None  # allowed values for radio/select


# Single-member-LLC, sole-proprietor restaurant in Chicago demo seed.
# Hardcoded so the demo never depends on user typing during recording.
DEMO_SEED = {
    "entity_name": "Shu Xiang LLC",
    "principal_address": "123 W Randolph St",
    "principal_city": "Chicago",
    "principal_zip": "60601",
    "management_structure": None,  # judgment — set during in-flow pause
    "duration": "perpetual",  # default for restaurants, set in pre-flight
    "registered_agent_name": "Wei Zhang",  # set in pre-flight
    "registered_agent_address": "123 W Randolph St, Chicago IL 60601",
    "organizer_name": "Wei Zhang",
    "organizer_email": "wei@shuxiangchicago.com",
    # Storefront brand — used by REG-1 sales tax registration walkthrough
    "dba": "Shu Xiang Kitchen",
}


# The ONE in-flow pause centerpiece. Picked from `corpus_fields` below where kind=JUDGMENT.
IN_FLOW_PAUSE_FIELD = "management_structure"


# Sidebar display labels in Chinese (overlay/sidebar consumes these).
SIDEBAR_LABELS_ZH: dict[str, str] = {
    "entity_name": "公司名",
    "principal_address": "地址",
    "principal_city": "城市",
    "principal_zip": "邮编",
    "management_structure": "管理结构",
    "duration": "存续期",
    "registered_agent_name": "注册代理人",
    "registered_agent_address": "代理人地址",
    "organizer_name": "申请人",
    "organizer_email": "邮箱",
    "organizer_phone": "电话",
}


# Authoritative-calm Chinese copy locked in design review.
# Keep it short — overlay card has a budget. Native-speaker review pending.
CORPUS_FIELDS: list[FieldSpec] = [
    # ──── PAGE 1 (real IL SOS): standard LLC vs series LLC ────
    # NOT in the mock — the mock skips this because it's only a question
    # for advanced users. On the real site, EVERY user faces this first.
    # Recon captured:
    #   url:    https://apps.ilsos.gov/llcarticles/
    #   #llcNo  -> "I wish to form a 'standard' limited liability company..."
    #   #llcYes -> "...with the ability to establish series."
    FieldSpec(
        name="LLC Type (Standard vs Series)",
        kind=FieldKind.JUDGMENT,
        selector_mock="",  # not present on the mock
        selector_live="#llcNo",  # default to standard for restaurants
        schema_key="llc_type",
        enum_values=("standard", "series"),
        question_zh="标准 LLC 还是系列 LLC？",
        explanation_zh=(
            "Standard LLC = 普通有限责任公司 (推荐, 餐厅几乎都选这个)。\n"
            "Series LLC = 系列 LLC, 一个公司下可以有多个独立子公司,\n"
            "适合管理多个房产或多个品牌, 不适合单店餐厅。"
        ),
    ),
    # ──── PAGE 1 IN-FLOW CLARIFICATION: standard vs series LLC ────
    # Already exists as a JUDGMENT field above (llc_type) but this entry
    # adds the cached audio key for the in-flow pause beat.
    # ──── PAGE 12 IN-FLOW CLARIFICATION: expedited service ────
    # ──── PAGE 6 IN-FLOW CLARIFICATION: registered agent (you vs service) ────
    # The corpus entries are added directly below. Each has question_zh
    # + explanation_zh that match the cached audio script.

    # ──── PAGE 2 (real IL SOS): "Provisions" agreement ────
    # 5 dense English legal statements + one Yes/No. The most dangerous
    # page for non-English speakers — clicking "Yes" without understanding
    # what was agreed to has real legal consequences. This is the core
    # judgment beat our product exists to solve.
    # Recon captured:
    #   url:                  https://apps.ilsos.gov/llcarticles/index.do
    #   #userSelectionYes
    #   #userSelectionNo
    FieldSpec(
        name="Provisions Agreement (page 2)",
        kind=FieldKind.JUDGMENT,
        selector_mock="",
        selector_live="#userSelectionYes",
        schema_key="provisions_agreed",
        enum_values=("yes", "no"),
        question_zh="同意以下 5 条条款吗？",
        explanation_zh=(
            "你即将同意 5 条法律条款:\n"
            "1. 文件提交日生效\n"
            "2. 公司用途为'任何合法业务'\n"
            "3. 提交时已有 1 名或更多成员\n"
            "4. 公司永久存续\n"
            "5. 不需要可选条款\n"
            "对单店餐厅 + 唯一所有者: 5 条都合理, 推荐选 Yes。"
        ),
    ),
    # ──── ENTITY DATA (in our mock; live selectors TBD) ────
    FieldSpec(
        name="Entity Name",
        kind=FieldKind.AUTOFILL,
        selector_mock="#entity_name",
        selector_live=None,  # appears on a later page in real flow
        schema_key="entity_name",
    ),
    FieldSpec(
        name="Principal Street Address",
        kind=FieldKind.AUTOFILL,
        selector_mock="#principal_address",
        selector_live=None,
        schema_key="principal_address",
    ),
    FieldSpec(
        name="Principal City",
        kind=FieldKind.AUTOFILL,
        selector_mock="#principal_city",
        selector_live=None,
        schema_key="principal_city",
    ),
    FieldSpec(
        name="Principal ZIP",
        kind=FieldKind.AUTOFILL,
        selector_mock="#principal_zip",
        selector_live=None,
        schema_key="principal_zip",
    ),
    FieldSpec(
        name="Organizer Name",
        kind=FieldKind.AUTOFILL,
        selector_mock="#organizer_name",
        selector_live=None,
        schema_key="organizer_name",
    ),
    FieldSpec(
        name="Organizer Email",
        kind=FieldKind.AUTOFILL,
        selector_mock="#organizer_email",
        selector_live=None,
        schema_key="organizer_email",
    ),
    # ──── JUDGMENT FIELDS ────
    FieldSpec(
        name="Management Structure",
        kind=FieldKind.JUDGMENT,
        # Radio group — selector points at the group container; the fill function
        # picks the radio whose value matches the schema value.
        selector_mock="#management_structure_group",
        selector_live=None,
        schema_key="management_structure",
        enum_values=("member-managed", "manager-managed"),
        # Authoritative-calm copy locked in the visual design spec.
        question_zh="请选择管理结构：你想自己运营还是雇人来管理？",
        explanation_zh=(
            "Member-Managed = 你自己运营公司。\n"
            "Manager-Managed = 雇佣经理来运营。\n"
            "餐厅业主通常选择 Member-Managed 因为你是唯一所有者。"
        ),
    ),
    FieldSpec(
        name="Duration",
        kind=FieldKind.JUDGMENT,
        selector_mock="#duration",
        selector_live=None,
        schema_key="duration",
        enum_values=("perpetual", "fixed"),
        question_zh="公司存续期？",
        explanation_zh=(
            "Perpetual = 永久 (推荐, 适合长期经营的餐厅).\n"
            "Fixed = 固定结束日期 (如临时项目)。\n"
            "餐厅通常选择 Perpetual。"
        ),
    ),
    FieldSpec(
        name="Registered Agent Name",
        kind=FieldKind.JUDGMENT,
        selector_mock="#registered_agent_name",
        selector_live="#agent",
        schema_key="registered_agent_name",
        enum_values=("self", "service"),
        question_zh="你自己作为注册代理人，还是雇用专业服务？",
        explanation_zh=(
            "Registered Agent 接收法律文件，必须有伊利诺伊州地址。\n"
            "自己 = 免费，但你的住址会公开。\n"
            "服务 = $100-300/年，地址保密。\n"
            "餐厁老板大多选自己。"
        ),
    ),
    FieldSpec(
        name="Expedited Processing",
        kind=FieldKind.JUDGMENT,
        selector_mock="",
        selector_live="#noRadioButton",  # picks "no expedited" by default
        schema_key="expedited",
        enum_values=("standard", "expedited"),
        question_zh="标准处理 10 天免费，还是加急 24 小时多花 100 美元？",
        explanation_zh=(
            "Standard = 10 个工作日，免费 (推荐 — 你的 EIN 可以并行申请)。\n"
            "Expedited = 24 小时内审批，加 $100。\n"
            "对绝大多数餐厁，标准就够了。"
        ),
    ),
    FieldSpec(
        name="Registered Agent Address",
        kind=FieldKind.LOOKUP,
        selector_mock="#registered_agent_address",
        selector_live=None,
        schema_key="registered_agent_address",
    ),
]


# Quick lookups
FIELDS_BY_KEY: dict[str, FieldSpec] = {f.schema_key: f for f in CORPUS_FIELDS}


def autofill_fields() -> list[FieldSpec]:
    return [f for f in CORPUS_FIELDS if f.kind == FieldKind.AUTOFILL]


def judgment_fields() -> list[FieldSpec]:
    return [f for f in CORPUS_FIELDS if f.kind == FieldKind.JUDGMENT]


def get_in_flow_pause_field() -> FieldSpec:
    return FIELDS_BY_KEY[IN_FLOW_PAUSE_FIELD]


def selector_for(target: str, field: FieldSpec) -> str:
    """Pick the right selector for the target environment ('mock' or 'live')."""
    if target == "live":
        if field.selector_live is None:
            raise RuntimeError(
                f"Live selector for {field.name!r} not captured yet. "
                "Run tonight's field-corpus labeling on the real IL SOS site."
            )
        return field.selector_live
    return field.selector_mock
