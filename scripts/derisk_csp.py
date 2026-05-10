"""
DERISK GATE 1: CSP test on overlay injection.

Pass = page.evaluate inserts a fixed-position div on the IL SOS LLC page.
Fail = browser blocks the inline script. Switch to packaged Chrome extension.

Usage:
    python scripts/derisk_csp.py [URL]

Default URL is the local mock; pass the real IL SOS URL to run the actual gate.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = (Path(__file__).resolve().parent.parent / "demo" / "il_sos_mock.html").as_uri()

    print(f"Testing CSP on: {url}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-web-security"],
        )
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        # Capture any CSP violations.
        violations = []
        page.on(
            "console",
            lambda msg: violations.append(msg.text)
            if "Content Security Policy" in msg.text or "Refused" in msg.text
            else None,
        )

        await page.goto(url, wait_until="domcontentloaded")

        # Try injecting via page.evaluate (the actual mechanism the demo uses).
        result = await page.evaluate(
            """() => {
              try {
                const div = document.createElement('div');
                div.id = 'derisk-csp-probe';
                div.textContent = 'CSP-PROBE-OK';
                div.style.cssText = 'position:fixed;top:8px;right:8px;padding:8px 16px;background:#10B981;color:#fff;font-family:monospace;z-index:99999;';
                document.body.appendChild(div);
                return { ok: !!document.getElementById('derisk-csp-probe') };
              } catch (e) {
                return { ok: false, error: String(e) };
              }
            }"""
        )

        await asyncio.sleep(1.5)  # let any console violations land

        print("\n--- RESULTS ---")
        print(f"page.evaluate result: {result}")
        print(f"Console violations: {len(violations)}")
        for v in violations:
            print(f"  - {v}")

        if result.get("ok") and not violations:
            print("\n✓ PASS — overlay injection works on this page.")
            print("  Demo path: page.evaluate is safe.")
            sys.exit(0)
        else:
            print("\n✗ FAIL — switch to packaged Chrome extension.")
            print("  See: https://playwright.dev/docs/chrome-extensions")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
