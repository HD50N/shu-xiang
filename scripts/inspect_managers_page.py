"""
Walk the live IL SOS flow up to the managers/members table page using the
real-site runner's existing handlers, then dump the DOM of the unknown page
so we can write a handler for it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from agent.overlay_bridge import install_overlay
from agent.pacing import PRESET_FAST
from agent.real_site_runner import REAL_SITE_URL, route_page
from agent.state import DemoState
from corpus import DEMO_SEED


UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)


async def main():
    state = DemoState()
    state.seed_with_demo_data()
    pacing = PRESET_FAST

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                channel="chrome",
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            browser = await pw.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )

        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=UA,
            locale="en-US",
        )
        page = await ctx.new_page()
        await page.goto(REAL_SITE_URL, wait_until="domcontentloaded")
        await install_overlay(page)

        # Walk handler-by-handler until we hit unmapped
        for step in range(1, 15):
            url = page.url
            print(f"step {step}: {url}")
            try:
                result = await route_page(page, state, pacing)
            except Exception as exc:
                print(f"  handler error: {exc}")
                break
            if result is None:
                print(f"  UNMAPPED — dumping DOM")
                # Dump full input/button/textarea structure
                dom = await page.evaluate(
                    r"""() => {
                      const fmt = (el) => {
                        let lbl = '';
                        if (el.id) {
                          const l = document.querySelector(`label[for="${el.id}"]`);
                          if (l) lbl = l.innerText.trim();
                        }
                        if (!lbl) {
                          const pl = el.closest('label');
                          if (pl) lbl = pl.innerText.trim();
                        }
                        return {
                          tag: el.tagName.toLowerCase(),
                          type: el.type || null,
                          name: el.name || null,
                          id: el.id || null,
                          value: (el.value || '').slice(0, 100),
                          placeholder: el.placeholder || null,
                          label: lbl.replace(/\s+/g, ' ').slice(0, 200),
                          visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                          row: (() => {
                            const tr = el.closest('tr');
                            return tr ? Array.from(tr.parentNode.children).indexOf(tr) : null;
                          })(),
                          col: (() => {
                            const td = el.closest('td');
                            if (!td) return null;
                            return Array.from(td.parentNode.children).indexOf(td);
                          })(),
                        };
                      };
                      return {
                        inputs: Array.from(document.querySelectorAll('input, select, textarea')).map(fmt),
                        buttons: Array.from(document.querySelectorAll('button, input[type=submit], input[type=button], a[role=button]'))
                          .map(b => ({ text: (b.innerText || b.value || '').trim().slice(0, 80), id: b.id || null, name: b.name || null, type: b.type || null }))
                          .filter(b => b.text),
                        title: document.title,
                        h1: Array.from(document.querySelectorAll('h1, h2, h3')).map(h => h.innerText.trim()).slice(0, 5),
                        bodyExcerpt: document.body.innerText.slice(0, 800),
                      };
                    }"""
                )
                dump_path = Path("out/live") / f"unmapped-step{step:02d}.json"
                dump_path.parent.mkdir(parents=True, exist_ok=True)
                dump_path.write_text(json.dumps(dom, indent=2, ensure_ascii=False))
                print(f"  dumped to {dump_path}")
                # Print summary
                print(f"  title: {dom['title']}")
                print(f"  headings: {dom['h1']}")
                print(f"  inputs (visible only):")
                for f in dom["inputs"]:
                    if not f["visible"]:
                        continue
                    sel = "#" + f["id"] if f["id"] else (f"[name={f['name']}]" if f["name"] else "?")
                    print(f"    {sel}  type={f['type']}  row={f['row']} col={f['col']}  value={f['value']!r:30}  label={f['label'][:60]!r}")
                print(f"  buttons:")
                for b in dom["buttons"]:
                    print(f"    {b}")
                # Take a screenshot too
                shot = Path("out/live") / f"unmapped-step{step:02d}.png"
                await page.screenshot(path=str(shot))
                print(f"  screenshot: {shot}")
                break

        await asyncio.sleep(2)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
