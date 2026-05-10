"""
Bilingual PDF generator.

Uses Playwright page.pdf() to render template.html with the LLC schema +
the Chinese explanation copy from corpus.judgment_fields(). Noto Sans SC
and Noto Serif SC are bundled locally to avoid Google Fonts CDN dependency
during demo recording.

Tonight's task: download the four .ttf files into pdf/fonts/ and run
scripts/render_test_pdf.py to verify Mandarin renders correctly (no tofu).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright

from corpus import CORPUS_FIELDS, FieldKind, judgment_fields

from agent.state import LLCSchema

_TEMPLATE_DIR = Path(__file__).resolve().parent
_FONTS_DIR = _TEMPLATE_DIR / "fonts"


def _build_context(schema: LLCSchema) -> dict[str, Any]:
    """Map the schema into the template's render variables."""
    english_label = {
        "entity_name": "Entity Name",
        "principal_address": "Principal Place of Business",
        "principal_city": "City",
        "principal_zip": "ZIP",
        "management_structure": "Management Structure",
        "duration": "Duration",
        "registered_agent_name": "Registered Agent",
        "registered_agent_address": "Registered Office Address",
        "organizer_name": "Organizer",
        "organizer_email": "Organizer Email",
    }

    english_fields = []
    address_parts = [schema.principal_address, schema.principal_city, schema.principal_zip]
    address_str = ", ".join(p for p in address_parts if p)

    english_fields.append({"label": english_label["entity_name"], "value": schema.entity_name or "—"})
    english_fields.append({"label": "Principal Place of Business", "value": address_str or "—"})
    english_fields.append({"label": english_label["management_structure"], "value": (schema.management_structure or "—").replace("-", " ").title()})
    english_fields.append({"label": english_label["duration"], "value": (schema.duration or "—").title()})
    english_fields.append({"label": english_label["registered_agent_name"], "value": schema.registered_agent_name or "—"})
    english_fields.append({"label": english_label["registered_agent_address"], "value": schema.registered_agent_address or "—"})
    english_fields.append({"label": english_label["organizer_name"], "value": schema.organizer_name or "—"})
    english_fields.append({"label": english_label["organizer_email"], "value": schema.organizer_email or "—"})

    # Chinese judgment explanations: the user's actual answer rendered in
    # Chinese with the trade-off context that was shown during the in-flow
    # pause. This is the closing-the-loop wow.
    judgment_explanations = []
    for f in judgment_fields():
        chosen = getattr(schema, f.schema_key, None)
        if not chosen:
            continue
        # Map the enum back to the Chinese explanation of WHAT WAS CHOSEN.
        chosen_zh = _zh_for_choice(f.schema_key, chosen)
        judgment_explanations.append({
            "label_zh": _zh_label(f.schema_key),
            "body_zh": chosen_zh,
        })

    return {
        "entity_name": schema.entity_name or "(Unnamed Entity)",
        "filing_date": datetime.now().strftime("%B %d, %Y"),
        "english_fields": english_fields,
        "judgment_explanations": judgment_explanations,
    }


def _zh_label(schema_key: str) -> str:
    return {
        "management_structure": "管理结构",
        "duration": "存续期",
        "registered_agent_name": "注册代理人",
        "registered_agent_address": "注册地址",
    }.get(schema_key, schema_key)


def _zh_for_choice(schema_key: str, value: str) -> str:
    """Render the Chinese explanation of the user's chosen value."""
    table: dict[tuple[str, str], str] = {
        ("management_structure", "member-managed"):
            "你选择了 Member-Managed (成员管理)，由你本人作为唯一所有者运营公司。",
        ("management_structure", "manager-managed"):
            "你选择了 Manager-Managed (经理管理)，由你雇佣的经理来运营公司。",
        ("duration", "perpetual"):
            "你选择了 Perpetual (永久存续)，公司没有自动结束日期。适合长期经营。",
        ("duration", "fixed"):
            "你选择了 Fixed (固定期限)，公司在指定日期自动解散。",
    }
    return table.get((schema_key, value), value)


async def generate_bilingual_pdf(schema: LLCSchema, output: Path) -> Path:
    """
    Render the template against the schema and write a PDF to `output`.
    Returns the output path.
    """
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("template.html")
    html = template.render(**_build_context(schema))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Use a file:// base URL so @font-face URLs resolve to fonts/*.ttf
        # in the same directory as the template.
        base_url = (_TEMPLATE_DIR / "template.html").as_uri()
        await page.goto(base_url, wait_until="domcontentloaded")
        await page.set_content(html, wait_until="domcontentloaded")
        # Give web fonts a beat to load.
        await page.evaluate("document.fonts && document.fonts.ready")
        await page.pdf(
            path=str(output),
            format="Letter",
            margin={"top": "0in", "right": "0in", "bottom": "0in", "left": "0in"},
            print_background=True,
        )
        await browser.close()

    return output


# CLI for the tonight render-test task.
async def _cli():
    import sys

    schema = LLCSchema(
        entity_name="Shu Xiang LLC",
        principal_address="939 East 54th St",
        principal_city="Chicago",
        principal_zip="60615",
        management_structure="member-managed",
        duration="perpetual",
        registered_agent_name="John Zhang",
        registered_agent_address="939 East 54th St, Chicago IL 60615",
        organizer_name="John Zhang",
        organizer_email="wei@shuxiangchicago.com",
    )
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/test-pdf.pdf")
    path = await generate_bilingual_pdf(schema, out)
    print(f"Wrote {path}")


if __name__ == "__main__":
    asyncio.run(_cli())
