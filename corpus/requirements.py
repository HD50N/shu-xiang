"""
Curated obligations database for the Phase 2 obligation map.

Scope: Chicago single-member restaurant LLC, sole owner, planning to hire 2 staff,
serves food (no alcohol). Each entry has a real citation URL where verifiable;
where I couldn't fully verify in the time budget, the entry is marked
verified=False so the demo can either skip it or flag it for human review.

The database is keyed by `requirement_id` and queryable via the eligibility
predicate functions below. The ChecklistView UI consumes the list returned by
`requirements_for_profile(profile)`.

Sources consulted (May 2026):
- IRS — https://www.irs.gov/businesses/small-businesses-self-employed/employer-id-numbers
- FinCEN BOI — https://www.fincen.gov/boi
- Illinois DOR — https://tax.illinois.gov/businesses/registration.html
- Illinois SOS — https://apps.ilsos.gov/llcarticles/
- Chicago BACP — https://www.chicago.gov/city/en/depts/bacp/
- Chicago CDPH Food — https://www.chicago.gov/city/en/depts/cdph/provdrs/food_safety/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class BusinessProfile:
    """The structured profile produced by Phase 1 conversation."""
    entity_name: Optional[str] = None
    business_type: Optional[str] = None  # "restaurant" | "retail" | etc.
    city: Optional[str] = None
    state: Optional[str] = None
    sole_owner: Optional[bool] = None
    plans_to_hire: Optional[bool] = None
    sells_food: Optional[bool] = None
    sells_alcohol: Optional[bool] = None
    online_only: Optional[bool] = None
    different_dba: Optional[bool] = None  # operating under a name different from LLC name


@dataclass
class Requirement:
    """One bureaucratic obligation surfaced in the Phase 2 checklist."""
    id: str
    title_en: str
    title_zh: str
    jurisdiction: str             # "Federal" | "Illinois" | "Cook County" | "Chicago"
    description_zh: str           # 1-2 sentence Chinese explanation
    why_zh: str                   # why this matters (the "asymmetry-closing" insight)
    citation_url: str             # link to the underlying regulation / portal
    portal_url: str               # where you actually file
    sequencing_priority: int      # 1 = do first, higher = depends on lower
    estimated_time_minutes: int
    estimated_cost_usd: int
    verified: bool                # True if I verified the citation; False = demo-day check
    eligibility: Callable[[BusinessProfile], bool] = field(default=lambda p: True)


# Hardcoded for the demo profile (sole-owner Chicago restaurant LLC, hiring, food only).
# These predicates are deliberately simple — for the demo, eligibility is mostly True.
def _always(p: BusinessProfile) -> bool:
    return True


def _if_hiring(p: BusinessProfile) -> bool:
    return p.plans_to_hire is True


def _if_food(p: BusinessProfile) -> bool:
    return p.sells_food is True


def _if_chicago(p: BusinessProfile) -> bool:
    return (p.city or "").lower() in ("chicago", "芝加哥")


def _if_alcohol(p: BusinessProfile) -> bool:
    return p.sells_alcohol is True


def _if_dba(p: BusinessProfile) -> bool:
    return p.different_dba is True


REQUIREMENTS: list[Requirement] = [
    Requirement(
        id="il_llc_articles",
        title_en="Illinois LLC Articles of Organization",
        title_zh="伊利诺伊州 LLC 注册",
        jurisdiction="Illinois",
        description_zh="向伊利诺伊州州务卿提交 LLC-1.36 表，正式成立你的有限责任公司。",
        why_zh="这是所有其他申请的前提 — 没有 LLC 编号你无法申请 EIN、营业执照或税务登记。",
        citation_url="https://www.ilsos.gov/publications/business_services/llcarticles.html",
        portal_url="https://apps.ilsos.gov/llcarticles/",
        sequencing_priority=1,
        estimated_time_minutes=15,
        estimated_cost_usd=150,
        verified=True,
        eligibility=_always,
    ),
    Requirement(
        id="federal_ein",
        title_en="Federal EIN (Employer Identification Number)",
        title_zh="联邦 EIN (雇主识别号)",
        jurisdiction="Federal",
        description_zh="向 IRS 申请 EIN，这是你公司的联邦税号。LLC 必须有 EIN 才能开商业银行账户。",
        why_zh="即使你不打算雇人，几乎所有银行都要求 LLC 提供 EIN 才能开公司账户。线上申请免费，5分钟拿到。",
        citation_url="https://www.irs.gov/businesses/small-businesses-self-employed/employer-id-numbers",
        portal_url="https://www.irs.gov/businesses/small-businesses-self-employed/apply-for-an-employer-identification-number-ein-online",
        sequencing_priority=2,
        estimated_time_minutes=5,
        estimated_cost_usd=0,
        verified=True,
        eligibility=_always,
    ),
    Requirement(
        id="federal_boi",
        title_en="FinCEN Beneficial Ownership Information (BOI) Report",
        title_zh="联邦受益所有人信息报告 (BOI)",
        jurisdiction="Federal",
        description_zh="自2024年起，几乎所有 LLC 必须向 FinCEN 提交受益所有人信息。新公司有 30 天提交期限，否则每天 $591 罚款。",
        why_zh="这是 2024 新规，很多人不知道。家人朋友很可能没听说过 — 错过会有重罚。",
        citation_url="https://www.fincen.gov/boi",
        portal_url="https://boiefiling.fincen.gov/",
        sequencing_priority=3,
        estimated_time_minutes=20,
        estimated_cost_usd=0,
        verified=True,
        eligibility=_always,
    ),
    Requirement(
        id="il_business_registration",
        title_en="Illinois Business Registration (REG-1)",
        title_zh="伊利诺伊州商业税务登记 (REG-1)",
        jurisdiction="Illinois",
        description_zh="向伊利诺伊州税务局 (DOR) 申请营业税登记。这一份表同时处理销售税许可证。",
        why_zh="伊利诺伊州不发统一的'营业执照' — 这份税务登记起到类似作用,是你向州里报销售税的前提。",
        citation_url="https://tax.illinois.gov/businesses/registration.html",
        portal_url="https://mytax.illinois.gov/_/",
        sequencing_priority=4,
        estimated_time_minutes=30,
        estimated_cost_usd=0,
        verified=True,
        eligibility=_always,
    ),
    Requirement(
        id="il_sales_tax",
        title_en="Illinois Sales Tax Permit",
        title_zh="伊利诺伊州销售税许可",
        jurisdiction="Illinois",
        description_zh="餐厁需要收销售税并按月或按季向州里申报。销售税许可在 REG-1 表里同时申请。",
        why_zh="餐厁卖食物默认需要销售税许可。Cook County 餐饮税另算 (1.25%),Chicago 餐厁税另算 (0.5%)。",
        citation_url="https://tax.illinois.gov/research/taxinformation/sales/rot.html",
        portal_url="https://mytax.illinois.gov/_/",
        sequencing_priority=4,
        estimated_time_minutes=0,  # bundled with REG-1
        estimated_cost_usd=0,
        verified=True,
        eligibility=_if_food,
    ),
    Requirement(
        id="il_withholding",
        title_en="Illinois Withholding Tax Registration",
        title_zh="伊利诺伊州预扣税登记",
        jurisdiction="Illinois",
        description_zh="只要雇佣员工就必须向伊利诺伊州登记预扣税。同样在 REG-1 表里勾选。",
        why_zh="你打算雇 2 个员工 — 这意味着你必须代扣他们的州所得税并按期申报 IL-941。",
        citation_url="https://tax.illinois.gov/research/taxinformation/withholding.html",
        portal_url="https://mytax.illinois.gov/_/",
        sequencing_priority=5,
        estimated_time_minutes=0,  # bundled with REG-1
        estimated_cost_usd=0,
        verified=True,
        eligibility=_if_hiring,
    ),
    Requirement(
        id="chicago_business_license",
        title_en="Chicago Business License (BACP)",
        title_zh="芝加哥市营业执照 (BACP)",
        jurisdiction="Chicago",
        description_zh="芝加哥市要求所有营业地点持有市营业执照,由 BACP (商业事务和消费者保护局) 颁发。",
        why_zh="州里没有营业执照 ≠ 市里也不需要。Chicago 是必须的,2 年期。",
        citation_url="https://www.chicago.gov/city/en/depts/bacp/supp_info/license_applicationrequirementsinformation.html",
        portal_url="https://www.chicago.gov/city/en/depts/bacp/",
        sequencing_priority=6,
        estimated_time_minutes=45,
        estimated_cost_usd=250,
        verified=True,
        eligibility=_if_chicago,
    ),
    Requirement(
        id="chicago_retail_food",
        title_en="Chicago Retail Food Establishment License",
        title_zh="芝加哥零售食品店执照",
        jurisdiction="Chicago",
        description_zh="餐厁单独需要零售食品执照,从市卫生局拿。0-1000 平方英尺的店两年费用 $660。",
        why_zh="这是餐厁专用执照,普通商业执照不够。在开业前必须通过卫生检查。",
        citation_url="https://www.chicago.gov/city/en/depts/bacp/supp_info/retailfoodestablishment0.html",
        portal_url="https://www.chicago.gov/city/en/depts/bacp/",
        sequencing_priority=7,
        estimated_time_minutes=60,
        estimated_cost_usd=660,
        verified=True,
        eligibility=lambda p: _if_food(p) and _if_chicago(p),
    ),
    Requirement(
        id="chicago_food_sanitation_cert",
        title_en="Food Service Sanitation Manager Certificate",
        title_zh="食品卫生管理员证书",
        jurisdiction="Chicago",
        description_zh="店内必须至少有一名持有 CDPH 食品卫生管理员证的人员在场。需要参加并通过认证课程。",
        why_zh="检查时必须有持证人在场,否则当场关店。每个证 $15,你或你雇的某人必须考。",
        citation_url="https://www.chicago.gov/city/en/depts/cdph/provdrs/food_safety/svcs/enroll_in_a_foodsanitationcertificationcourse.html",
        portal_url="https://www.chicago.gov/city/en/depts/cdph/provdrs/food_safety/",
        sequencing_priority=8,
        estimated_time_minutes=480,  # ~8h course
        estimated_cost_usd=15,
        verified=True,
        eligibility=lambda p: _if_food(p) and _if_chicago(p),
    ),
    Requirement(
        id="federal_employer_taxes",
        title_en="Federal Employer Tax Setup (Form 941, FUTA)",
        title_zh="联邦雇主税务设置 (Form 941, FUTA)",
        jurisdiction="Federal",
        description_zh="一旦雇人,你需要按季报联邦工资税 (Form 941) 和按年报失业税 (FUTA)。EIN 申请时已自动登记。",
        why_zh="这不是单独的'登记',但是个常被忽略的合规义务。第一次申报截止日不会提醒,错过会罚款。",
        citation_url="https://www.irs.gov/businesses/small-businesses-self-employed/employment-taxes",
        portal_url="https://www.irs.gov/payments/eftps-the-electronic-federal-tax-payment-system",
        sequencing_priority=9,
        estimated_time_minutes=15,
        estimated_cost_usd=0,
        verified=True,
        eligibility=_if_hiring,
    ),
    # Conditional / often-overlooked items
    Requirement(
        id="cook_county_dba",
        title_en="Cook County Assumed Business Name (DBA)",
        title_zh="Cook County 假名注册 (DBA)",
        jurisdiction="Cook County",
        description_zh="如果你的餐厁招牌名 ≠ LLC 注册名,你需要在 Cook County 登记假名 (DBA)。",
        why_zh="比如 LLC 叫 'Shu Xiang Holdings LLC' 但餐厁叫 'Shu Xiang Restaurant', 那你需要 DBA。同名不需要。",
        citation_url="https://www.cookcountyclerkil.gov/service/assumed-business-name-faq",
        portal_url="https://www.cookcountyclerkil.gov/",
        sequencing_priority=6,
        estimated_time_minutes=20,
        estimated_cost_usd=50,
        verified=False,  # quick verification — fee + URL needs confirmation
        eligibility=_if_dba,
    ),
    Requirement(
        id="il_workers_comp",
        title_en="Illinois Workers' Compensation Insurance",
        title_zh="伊利诺伊州工伤保险",
        jurisdiction="Illinois",
        description_zh="伊利诺伊州法律要求所有有员工的雇主购买工伤保险。雇佣前必须有效。",
        why_zh="不买保险被发现:每天每员工 $500 罚款 + 个人责任。这不是'登记',是要找保险公司买。",
        citation_url="https://www2.illinois.gov/sites/iwcc/Pages/default.aspx",
        portal_url="https://www2.illinois.gov/sites/iwcc/employers/Pages/default.aspx",
        sequencing_priority=10,
        estimated_time_minutes=120,  # shop quotes
        estimated_cost_usd=600,  # rough annual premium estimate
        verified=False,  # estimate only
        eligibility=_if_hiring,
    ),
]


def requirements_for_profile(profile: BusinessProfile) -> list[Requirement]:
    """Filter the master list against the profile's eligibility predicates."""
    return [r for r in REQUIREMENTS if r.eligibility(profile)]


# Demo seed profile — the canonical case the demo demonstrates.
# (Sole-owner Chicago restaurant, planning to hire, sells food, no alcohol.)
DEMO_PROFILE = BusinessProfile(
    entity_name="Shu Xiang LLC",
    business_type="restaurant",
    city="Chicago",
    state="IL",
    sole_owner=True,
    plans_to_hire=True,
    sells_food=True,
    sells_alcohol=False,
    online_only=False,
    different_dba=False,
)
