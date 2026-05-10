"""
Run the demo with screenshots captured at each beat boundary.
Used to verify pacing changes actually land visibly.

Output:
    out/diag-01-opening.png       — opening prompt up, no transcript yet
    out/diag-02-typing.png        — typewriter mid-sentence
    out/diag-03-typed.png         — sentence fully typed
    out/diag-04-form-revealed.png — opening hidden, form + sidebar visible
    out/diag-05-cold-open-mid.png — cold-open cascade in progress
    out/diag-06-cold-open-done.png — all six fields populated
    out/diag-07-overlay-visible.png — in-flow overlay anchored to field
    out/diag-08-listening.png     — listening dots breathing
    out/diag-09-recorded.png      — ring greened after answer
    out/diag-10-submit.png        — confirmation page
    out/diag-11-pdf-toast.png     — PDF generating toast
    out/diag-12-closing.png       — closing scene
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright

from agent.overlay_bridge import (
    hide_opening_prompt,
    hide_overlay,
    install_overlay,
    show_closing,
    show_opening_prompt,
    show_overlay,
    show_sidebar,
    show_toast,
    type_opening_transcript,
    update_sidebar_field,
)
from agent.state import LLCSchema
from corpus import (
    CORPUS_FIELDS,
    DEMO_SEED,
    SIDEBAR_LABELS_ZH,
    FieldKind,
    get_in_flow_pause_field,
    selector_for,
)


SENTENCE = (
    "我想注册我的餐厅为有限责任公司，叫做 Shu Xiang，"
    "在芝加哥，我是唯一所有者。"
)


async def main():
    out = Path("out")
    out.mkdir(exist_ok=True)

    mock = Path(__file__).resolve().parent.parent / "demo" / "il_sos_mock.html"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        await page.goto(mock.as_uri(), wait_until="domcontentloaded")
        await install_overlay(page)

        # ── 01: opening prompt ────────────────────────────────
        await show_opening_prompt(page, "用中文告诉我你的生意")
        await asyncio.sleep(1.0)
        await page.screenshot(path=str(out / "diag-01-opening.png"))

        # ── 02: typewriter mid ─────────────────────────────────
        async def type_partial():
            # type half then screenshot then continue
            await page.evaluate(
                """async (t) => {
                    const wrap = document.querySelector('.shuxiang-opening-transcript');
                    const cursor = wrap.querySelector('.shuxiang-opening-transcript-cursor');
                    wrap.innerHTML = '';
                    const span = document.createElement('span');
                    wrap.appendChild(span);
                    if (cursor) wrap.appendChild(cursor);
                    const half = Math.floor(t.length / 2);
                    for (let i = 0; i < half; i++) {
                        span.textContent += t[i];
                        await new Promise(r => setTimeout(r, 60));
                    }
                }""",
                SENTENCE,
            )

        await type_partial()
        await page.screenshot(path=str(out / "diag-02-typing.png"))

        # finish typing
        await type_opening_transcript(page, SENTENCE, 60)
        await asyncio.sleep(0.5)
        await page.screenshot(path=str(out / "diag-03-typed.png"))

        # ── 04: form revealed ─────────────────────────────────
        await hide_opening_prompt(page)
        await asyncio.sleep(0.6)
        rows = [
            {"key": f.schema_key, "labelZh": SIDEBAR_LABELS_ZH.get(f.schema_key, f.name), "value": ""}
            for f in CORPUS_FIELDS
            if f.kind != FieldKind.LOOKUP
        ]
        await show_sidebar(page, transcript=SENTENCE, fields=rows)
        await asyncio.sleep(0.6)
        await page.screenshot(path=str(out / "diag-04-form-revealed.png"))

        # ── 05/06: cold-open cascade ──────────────────────────
        autofills = [f for f in CORPUS_FIELDS if f.kind == FieldKind.AUTOFILL]
        for i, f in enumerate(autofills):
            value = DEMO_SEED.get(f.schema_key)
            if not value:
                continue
            await page.fill(selector_for("mock", f), str(value))
            await update_sidebar_field(page, f.schema_key, str(value))
            await asyncio.sleep(0.6)
            if i == len(autofills) // 2:
                await page.screenshot(path=str(out / "diag-05-cold-open-mid.png"))
        await asyncio.sleep(0.5)
        await page.screenshot(path=str(out / "diag-06-cold-open-done.png"))

        # ── 07/08/09: in-flow pause ───────────────────────────
        await page.evaluate("() => window.shuxiang.hideSidebar()")
        await asyncio.sleep(0.4)
        field = get_in_flow_pause_field()
        await show_overlay(
            page,
            selector=selector_for("mock", field),
            question=field.question_zh,
            explanation=field.explanation_zh,
        )
        await asyncio.sleep(1.2)
        await page.screenshot(path=str(out / "diag-07-overlay-visible.png"))
        await asyncio.sleep(0.6)
        await page.screenshot(path=str(out / "diag-08-listening.png"))
        await page.evaluate("() => window.shuxiang.markListening('recorded')")
        await asyncio.sleep(0.6)
        await page.screenshot(path=str(out / "diag-09-recorded.png"))

        # fill the radio + hide overlay
        await page.click(f'{selector_for("mock", field)} input[type="radio"][value="member-managed"]')
        await asyncio.sleep(0.4)
        await hide_overlay(page)
        await asyncio.sleep(0.5)

        # ── 10: submit ────────────────────────────────────────
        await page.select_option("#duration", "perpetual")
        await page.fill("#registered_agent_name", "John Zhang")
        await page.fill("#registered_agent_address", "939 East 54th St, Chicago IL 60615")
        await page.click("#submit-btn")
        await asyncio.sleep(1.2)
        await page.screenshot(path=str(out / "diag-10-submit.png"))

        # ── 11: PDF toast ─────────────────────────────────────
        await show_toast(page, "正在生成你的 LLC 文件…", kind="info", duration_ms=3000)
        await asyncio.sleep(0.6)
        await page.screenshot(path=str(out / "diag-11-pdf-toast.png"))

        # ── 12: closing ───────────────────────────────────────
        await show_closing(page, "完成！\n你的有限责任公司文件已生成。\n请保存好作为您的记录。")
        await asyncio.sleep(0.8)
        await page.screenshot(path=str(out / "diag-12-closing.png"))

        await browser.close()
        print("Wrote 12 diagnostic screenshots to out/diag-*.png")


if __name__ == "__main__":
    asyncio.run(main())
