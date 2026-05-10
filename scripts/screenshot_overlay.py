"""
Render the overlay against the mock form and take a screenshot.
Used to visually verify the locked design tokens at runtime.

Usage:
  python scripts/screenshot_overlay.py [output.png]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from agent.overlay_bridge import (
    install_overlay,
    show_overlay,
    show_sidebar,
)
from corpus import DEMO_SEED, get_in_flow_pause_field, selector_for


async def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/overlay-smoke.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    mock = Path(__file__).resolve().parent.parent / "demo" / "il_sos_mock.html"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        await page.goto(mock.as_uri(), wait_until="domcontentloaded")
        await install_overlay(page)

        # Pre-populate the form so the screenshot shows a realistic mid-flow state.
        for key in ("entity_name", "principal_address", "principal_city", "principal_zip"):
            sel = f"#{key}"
            if DEMO_SEED.get(key):
                await page.fill(sel, DEMO_SEED[key])

        # Sidebar (sells the cold-open story).
        await show_sidebar(
            page,
            transcript="我想注册我的餐厅为有限责任公司，叫做 Shu Xiang，在芝加哥，我是唯一所有者。",
            fields={
                "Entity Name": "Shu Xiang LLC",
                "City": "Chicago",
                "Address": "939 East 54th St",
                "Organizer": "John Zhang",
                "Email": "wei@shuxiangchicago.com",
                "Management": "—",
            },
        )

        # The main event: in-flow pause overlay anchored to the management
        # structure radio group.
        field = get_in_flow_pause_field()
        await show_overlay(
            page,
            selector=selector_for("mock", field),
            question=field.question_zh,
            explanation=field.explanation_zh,
            listening_label="正在聆听…",
        )
        # Let entrance animation complete.
        await asyncio.sleep(0.7)

        await page.screenshot(path=str(out), full_page=False)
        await browser.close()
        print(f"Wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
