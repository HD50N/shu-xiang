"""
Walk the IL SOS LLC Assumed Name (DBA) filing flow and capture structure.

Forked from recon_il_sos.py. Same anti-bot strategy (real Chrome + UA), same
capture+JSON dump pattern. Stops at any terminal/payment button OR validation
failure (which is likely on page 1 since we don't have a real LLC file number).

Output:
  out/recon_assumed_name/step{NN}-{label}.png   screenshots
  out/recon_assumed_name/flow.json              full structured dump

Usage:
    python scripts/recon_il_assumed_name.py [--max-steps 3]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright


UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)
START_URL = "https://apps.ilsos.gov/llcassumedadoptname/"
RECON_DIR = Path("out/recon_assumed_name")

# Seed values — same restaurant LLC story as the existing demo. File number
# is stubbed; the form will reject it on submit but we stop well before that.
SEED_VALUES = {
    # The likely-required page-1 field
    "file number": "12345678",
    "file no": "12345678",
    "filing number": "12345678",

    "llcname": "Shu Xiang LLC",
    "llc name": "Shu Xiang LLC",
    "company name": "Shu Xiang LLC",
    "entity name": "Shu Xiang LLC",

    # The assumed name itself — the restaurant's storefront brand
    "assumed name": "Shu Xiang Kitchen",
    "dba": "Shu Xiang Kitchen",
    "doing business as": "Shu Xiang Kitchen",

    "principal place": "123 W Randolph St",
    "address1": "123 W Randolph St",
    "street": "123 W Randolph St",
    "city": "Chicago",
    "zip": "60601",
    "state": "IL",
    "address": "123 W Randolph St",

    "organizer name": "Wei Zhang",
    "applicant name": "Wei Zhang",
    "email": "wei@shuxiangchicago.com",
    "phone": "3125551212",
}


PAYMENT_INPUT_PATTERNS = [
    r"card[_-]?number",
    r"creditcard",
    r"cc[_-]?num",
    r"\bcvv\b",
    r"\bcvc\b",
    r"expir",
    r"cardholder",
]
TERMINAL_BUTTON_TEXT = [
    "submit filing",
    "submit application",
    "file assumed name",
    "pay now",
    "make payment",
    "process payment",
]


async def capture_page(page: Page, step: int, label: str) -> dict:
    RECON_DIR.mkdir(parents=True, exist_ok=True)
    title = await page.title()
    url = page.url

    await asyncio.sleep(1.0)

    info = await page.evaluate(
        r"""() => {
          const labelFor = (el) => {
            let lbl = '';
            if (el.id) {
              const l = document.querySelector(`label[for="${el.id}"]`);
              if (l) lbl = l.innerText.trim();
            }
            if (!lbl) {
              const pl = el.closest('label');
              if (pl) lbl = pl.innerText.trim();
            }
            return lbl.replace(/\s+/g, ' ').slice(0, 200);
          };
          const inputs = Array.from(document.querySelectorAll('input, select, textarea')).map(el => ({
            tag: el.tagName.toLowerCase(),
            type: el.type || null,
            name: el.name || null,
            id: el.id || null,
            value: (el.value || '').slice(0, 100),
            placeholder: el.placeholder || null,
            label: labelFor(el),
            required: !!el.required,
            visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
          }));
          const buttons = Array.from(document.querySelectorAll('button, input[type=submit], input[type=button], a[role=button]'))
            .map(el => ({
              tag: el.tagName.toLowerCase(),
              type: el.type || null,
              text: (el.innerText || el.value || '').trim().slice(0, 100),
              id: el.id || null,
              name: el.name || null,
            }))
            .filter(b => b.text);
          const bodyText = document.body.innerText.slice(0, 2000);
          return { inputs, buttons, bodyText };
        }"""
    )

    screenshot_path = RECON_DIR / f"step{step:02d}-{label}.png"
    await page.screenshot(path=str(screenshot_path))

    return {
        "step": step,
        "label": label,
        "url": url,
        "title": title,
        "screenshot": str(screenshot_path),
        "inputs": info["inputs"],
        "buttons": info["buttons"],
        "body_excerpt": info["bodyText"][:600],
    }


def fuzzy_seed_value(field: dict) -> str | None:
    haystacks = [
        (field.get("id") or "").lower(),
        (field.get("name") or "").lower(),
        (field.get("label") or "").lower(),
        (field.get("placeholder") or "").lower(),
    ]
    for key, value in SEED_VALUES.items():
        for h in haystacks:
            if not h:
                continue
            if key in h:
                return value
    return None


async def fill_defaults(page: Page, info: dict) -> dict:
    actions = []
    radio_groups: dict[str, list[dict]] = {}
    for f in info["inputs"]:
        if not f["visible"]:
            continue
        if f["type"] == "radio":
            radio_groups.setdefault(f["name"] or "_unnamed", []).append(f)

    for name, group in radio_groups.items():
        already = await page.evaluate(
            f"""() => Array.from(document.querySelectorAll('input[type=radio][name="{name}"]'))
                       .some(r => r.checked)"""
        )
        if already:
            continue
        chosen = None
        for r in group:
            label = (r.get("label") or "").lower()
            if any(kw in label for kw in [" yes", "yes ", "agree", "accept", "standard"]):
                chosen = r
                break
        chosen = chosen or group[0]
        sel = f"#{chosen['id']}" if chosen.get("id") else f'input[name="{chosen["name"]}"][value="{chosen.get("value", "")}"]'
        try:
            await page.check(sel)
            actions.append({"action": "check_radio", "selector": sel, "label": chosen.get("label")})
        except Exception as e:
            actions.append({"action": "check_radio_failed", "selector": sel, "error": str(e)})

    has_errors = await page.evaluate(
        """() => Array.from(document.querySelectorAll('.error, .errorMessage, [class*=error]'))
                  .some(e => /required|invalid|must|please/i.test(e.innerText || ''))"""
    )

    for f in info["inputs"]:
        if not f["visible"]:
            continue
        ftype = f["type"]
        if ftype not in (None, "text", "email", "tel", "number"):
            continue
        if f["tag"] != "input":
            if f["tag"] != "textarea":
                continue
        if f.get("value") and not has_errors:
            continue
        sel = f"#{f['id']}" if f.get("id") else (
            f'[name="{f["name"]}"]' if f.get("name") else None
        )
        if not sel:
            continue
        value = fuzzy_seed_value(f)
        if not value:
            actions.append({"action": "skipped_no_match", "label": f.get("label"), "id": f.get("id"), "name": f.get("name")})
            continue
        try:
            if f.get("value"):
                await page.fill(sel, "")
            await page.fill(sel, value)
            actions.append({"action": "fill", "selector": sel, "value": value, "label": f.get("label")})
        except Exception as e:
            actions.append({"action": "fill_failed", "selector": sel, "error": str(e)})

    PLACEHOLDER_RX = re.compile(r"^(\s*-+\s*|select\s+one|please\s+select|choose|--.*--)\s*$", re.I)
    for f in info["inputs"]:
        if f["tag"] != "select" or not f["visible"]:
            continue
        sel = f"#{f['id']}" if f.get("id") else f'[name="{f["name"]}"]'
        if not sel:
            continue
        haystack = " ".join([(f.get("id") or ""), (f.get("name") or ""), (f.get("label") or "")]).lower()
        try:
            options = await page.evaluate(
                f"""() => Array.from(document.querySelector('{sel}').options)
                                .map(o => ({{ value: o.value, text: o.text }}))"""
            )
            real = [
                o for o in options
                if o["value"].strip()
                and not PLACEHOLDER_RX.match(o["text"] or "")
                and not PLACEHOLDER_RX.match(o["value"] or "")
            ]
            if not real:
                continue
            if "state" in haystack:
                pick = next(
                    (o for o in real if o["value"].upper() in ("IL", "ILLINOIS") or "illinois" in (o["text"] or "").lower()),
                    real[0],
                )
            elif "country" in haystack:
                pick = next(
                    (o for o in real if o["value"].upper() in ("US", "USA", "UNITED STATES") or "united states" in (o["text"] or "").lower()),
                    real[0],
                )
            else:
                pick = real[0]
            await page.select_option(sel, pick["value"])
            actions.append({"action": "select", "selector": sel, "value": pick["value"], "text": pick["text"]})
        except Exception as e:
            actions.append({"action": "select_failed", "selector": sel, "error": str(e)})

    return {"actions": actions}


async def find_continue_button(page: Page) -> Any | None:
    candidates = await page.query_selector_all(
        'button, input[type="submit"], input[type="button"], a[role="button"]'
    )
    for btn in candidates:
        try:
            text = ((await btn.inner_text()) or (await btn.get_attribute("value")) or "").strip().lower()
        except Exception:
            text = ""
        if not text:
            continue
        if any(kw in text for kw in TERMINAL_BUTTON_TEXT):
            return None
        if any(kw in text for kw in ["continue", "next", "proceed"]):
            return btn
    return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-steps", type=int, default=3)
    args = parser.parse_args()

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
        steps: list[dict] = []

        try:
            await page.goto(START_URL, wait_until="domcontentloaded", timeout=20000)
            for step in range(1, args.max_steps + 1):
                info = await capture_page(page, step, f"page{step:02d}")
                steps.append(info)

                payment_input_hit = None
                for f in info["inputs"]:
                    if not f["visible"]:
                        continue
                    haystack = " ".join([(f.get("id") or ""), (f.get("name") or ""), (f.get("label") or "")]).lower()
                    for pat in PAYMENT_INPUT_PATTERNS:
                        if re.search(pat, haystack):
                            payment_input_hit = (pat, f)
                            break
                    if payment_input_hit:
                        break
                terminal_btn = None
                for b in info["buttons"]:
                    btext = (b.get("text") or "").lower()
                    if any(kw in btext for kw in TERMINAL_BUTTON_TEXT):
                        terminal_btn = b
                        break
                if payment_input_hit or terminal_btn:
                    info["stop_reason"] = (
                        f"payment input: {payment_input_hit[0]}" if payment_input_hit
                        else f"terminal button: {terminal_btn['text']!r}"
                    )
                    print(f"\n[STOP] step {step}: {info['stop_reason']}")
                    break

                print(f"\n=== STEP {step}: {info['title']} ===")
                print(f"  URL: {info['url']}")
                visible_inputs = [f for f in info['inputs'] if f['visible']]
                print(f"  Inputs ({len(visible_inputs)}):")
                for f in visible_inputs:
                    sel = f"#{f['id']}" if f.get("id") else (f'[name="{f["name"]}"]' if f.get("name") else "?")
                    print(f"    {sel}  type={f['type']}  label={f['label']!r}")
                print(f"  Buttons:")
                for b in info["buttons"][:8]:
                    print(f"    {b['text']!r}")

                fill_log = await fill_defaults(page, info)
                info["fill_actions"] = fill_log["actions"]

                btn = await find_continue_button(page)
                if not btn:
                    info["stop_reason"] = "no continue button"
                    print(f"  [STOP] no Continue button — likely review/submit page")
                    break
                btn_text = ((await btn.inner_text()) or "").strip()
                print(f"  [click] {btn_text!r}")
                try:
                    async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                        await btn.click()
                except Exception as e:
                    print(f"  [warn] no nav after click: {e}")
                    await asyncio.sleep(1.5)
                    new_url = page.url
                    if new_url == info["url"]:
                        info["stop_reason"] = "stuck on same URL after fill (likely file number validation failed)"
                        print(f"  [STOP] stuck on same page — file number probably rejected")
                        errors = await page.evaluate(
                            "() => Array.from(document.querySelectorAll('.error, .errorMessage, [class*=error]'))"
                            "       .map(e => e.innerText.trim()).filter(t => t).slice(0, 5)"
                        )
                        info["validation_errors"] = errors
                        print(f"  validation errors: {errors}")
                        break

        finally:
            (RECON_DIR / "flow.json").write_text(json.dumps(steps, indent=2, ensure_ascii=False))
            print(f"\nSaved {len(steps)} steps to {RECON_DIR / 'flow.json'}")
            await asyncio.sleep(2)
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
