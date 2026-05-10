"""
Walk the public MyTax Illinois 'Register a New Business' (Form REG-1) flow
and capture structure.

MyTax IL is a SPA — first click 'Register a New Business' on the homepage
(no login required), then walk the wizard pages capturing field structure.

Output:
  out/recon_mytax/step{NN}-{label}.png   screenshots
  out/recon_mytax/flow.json              full structured dump

Usage:
    python scripts/recon_mytax_il.py [--max-steps 5]
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
START_URL = "https://mytax.illinois.gov/"
RECON_DIR = Path("out/recon_mytax")

# Seed values for REG-1. EIN stubbed to 9-digit valid format (the user's
# real EIN was only 8 digits; using a plausible 9-digit stub for recon).
SEED_VALUES = {
    "fein": "41-2549030",
    "federal employer": "41-2549030",
    "ein": "41-2549030",
    "employer identification": "41-2549030",
    "tax id": "41-2549030",

    "legal name": "Shu Xiang LLC",
    "business name": "Shu Xiang LLC",
    "legal business": "Shu Xiang LLC",
    "entity name": "Shu Xiang LLC",
    "company name": "Shu Xiang LLC",

    "dba": "Shu Xiang Kitchen",
    "doing business as": "Shu Xiang Kitchen",
    "trade name": "Shu Xiang Kitchen",
    "assumed name": "Shu Xiang Kitchen",

    "street": "123 W Randolph St",
    "address line 1": "123 W Randolph St",
    "address1": "123 W Randolph St",
    "mailing address": "123 W Randolph St",
    "city": "Chicago",
    "zip": "60601",
    "postal": "60601",
    "state": "IL",
    "address": "123 W Randolph St",

    "owner name": "Wei Zhang",
    "responsible party": "Wei Zhang",
    "applicant": "Wei Zhang",
    "first name": "Wei",
    "last name": "Zhang",
    "email": "wei@shuxiangchicago.com",
    "phone": "3125551212",

    "start date": "01/01/2026",
    "begin date": "01/01/2026",
    "date business": "01/01/2026",

    "naics": "722511",
    "primary activity": "Restaurant",
    "business activity": "Restaurant",
    "description": "Full-service restaurant",
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
    "submit application",
    "submit registration",
    "submit filing",
    "submit reg-1",
    "file application",
    "pay now",
    "make payment",
]
HOMEPAGE_REGISTER_PATTERNS = [
    "register a new business",
    "register a business",
    "new business registration",
    "register new business",
    "form reg-1",
    "reg-1",
]


async def capture_page(page: Page, step: int, label: str) -> dict:
    RECON_DIR.mkdir(parents=True, exist_ok=True)
    title = await page.title()
    url = page.url

    await asyncio.sleep(2.0)  # SPA pages need extra settle time

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
            // Also pick up aria-label and adjacent text for SPA-style components
            if (!lbl && el.getAttribute('aria-label')) {
              lbl = el.getAttribute('aria-label');
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
          const buttons = Array.from(document.querySelectorAll('button, input[type=submit], input[type=button], a[role=button], a'))
            .map(el => ({
              tag: el.tagName.toLowerCase(),
              type: el.type || null,
              text: (el.innerText || el.value || '').trim().slice(0, 100),
              id: el.id || null,
              name: el.name || null,
              href: el.href || null,
            }))
            .filter(b => b.text && b.text.length < 80);
          const bodyText = document.body.innerText.slice(0, 3000);
          return { inputs, buttons, bodyText };
        }"""
    )

    screenshot_path = RECON_DIR / f"step{step:02d}-{label}.png"
    await page.screenshot(path=str(screenshot_path), full_page=True)

    return {
        "step": step,
        "label": label,
        "url": url,
        "title": title,
        "screenshot": str(screenshot_path),
        "inputs": info["inputs"],
        "buttons": info["buttons"],
        "body_excerpt": info["bodyText"][:800],
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


async def dismiss_modal(page: Page) -> bool:
    """Click any open validation modal's OK button so subsequent clicks work."""
    try:
        ok = page.locator('div.ui-dialog button:has-text("OK"), div[role=dialog] button:has-text("OK")').first
        if await ok.is_visible(timeout=500):
            await ok.click()
            await asyncio.sleep(0.4)
            return True
    except Exception:
        pass
    return False


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
        chosen = group[0]
        sel = f"#{chosen['id']}" if chosen.get("id") else f'input[name="{chosen["name"]}"][value="{chosen.get("value", "")}"]'
        try:
            await page.check(sel)
            actions.append({"action": "check_radio", "selector": sel, "label": chosen.get("label")})
        except Exception as e:
            actions.append({"action": "check_radio_failed", "selector": sel, "error": str(e)})

    for f in info["inputs"]:
        if not f["visible"]:
            continue
        ftype = f["type"]
        if ftype not in (None, "text", "email", "tel", "number", "date"):
            continue
        if f["tag"] not in ("input", "textarea"):
            continue
        if f.get("value"):
            continue
        sel = f"#{f['id']}" if f.get("id") else (
            f'[name="{f["name"]}"]' if f.get("name") else None
        )
        if not sel:
            continue

        # FAST Enterprises custom combobox. fill()/type() don't trigger its
        # selection handler. Recipe: click input → wait for ui-autocomplete
        # listbox → click the matching option.
        label_lower = (f.get("label") or "").lower()
        is_combobox = (
            "organization type" in label_lower
            or "type of organization" in label_lower
            or "FastCombobox" in (f.get("placeholder") or "")
        )
        if is_combobox:
            try:
                await dismiss_modal(page)
                await page.click(sel)
                await asyncio.sleep(0.4)
                option = page.locator(
                    'ul.ui-autocomplete:visible li:has-text("Limited Liability Company")'
                ).first
                await option.click(timeout=5000)
                await asyncio.sleep(0.3)
                actions.append({"action": "combobox_click", "selector": sel, "value": "Limited Liability Company", "label": f.get("label")})
            except Exception as e:
                actions.append({"action": "combobox_failed", "selector": sel, "error": str(e)[:200]})
            continue

        value = fuzzy_seed_value(f)
        if not value:
            actions.append({"action": "skipped_no_match", "label": f.get("label"), "id": f.get("id"), "name": f.get("name")})
            continue
        try:
            await page.fill(sel, value)
            actions.append({"action": "fill", "selector": sel, "value": value, "label": f.get("label")})
        except Exception as e:
            actions.append({"action": "fill_failed", "selector": sel, "error": str(e)})

    return {"actions": actions}


async def click_register_link(page: Page) -> bool:
    """On the MyTax IL homepage, find and click 'Register a New Business'."""
    info = await page.evaluate(
        r"""() => {
          const all = Array.from(document.querySelectorAll('a, button, [role=button], div[onclick]'));
          return all.map(el => ({
            tag: el.tagName.toLowerCase(),
            text: (el.innerText || el.value || '').trim().slice(0, 100),
            id: el.id || null,
            href: el.href || null,
          })).filter(x => x.text);
        }"""
    )
    for c in info:
        text = (c.get("text") or "").lower()
        if any(pat in text for pat in HOMEPAGE_REGISTER_PATTERNS):
            print(f"  → clicking homepage link: {c['text']!r}")
            try:
                # Use locator with exact text for SPA-safe click
                loc = page.locator(f'text="{c["text"]}"').first
                await loc.click(timeout=10000)
                await asyncio.sleep(3.0)
                return True
            except Exception as e:
                print(f"  [warn] click failed: {e}")
                continue
    return False


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
    parser.add_argument("--max-steps", type=int, default=5)
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
            await page.goto(START_URL, wait_until="domcontentloaded", timeout=30000)
            # Homepage capture
            info = await capture_page(page, 0, "homepage")
            steps.append(info)
            print(f"\n=== STEP 0 (homepage): {info['title']} ===")
            print(f"  URL: {info['url']}")
            print(f"  Buttons/links containing 'register' keywords:")
            for b in info["buttons"]:
                btext = (b.get("text") or "").lower()
                if "regist" in btext or "new business" in btext or "reg-1" in btext:
                    print(f"    {b['text']!r}  (tag={b['tag']}, href={b.get('href')})")

            # Try clicking the register link
            clicked = await click_register_link(page)
            if not clicked:
                print("\n[STOP] couldn't find 'Register a New Business' link on homepage")
                return

            # Now walk the wizard
            for step in range(1, args.max_steps + 1):
                # Dismiss any lingering validation modal before capturing
                await dismiss_modal(page)
                info = await capture_page(page, step, f"reg{step:02d}")
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
                for f in visible_inputs[:20]:
                    sel = f"#{f['id']}" if f.get("id") else (f'[name="{f["name"]}"]' if f.get("name") else "?")
                    print(f"    {sel}  type={f['type']}  label={f['label']!r}")
                print(f"  Buttons (first 8):")
                for b in info["buttons"][:8]:
                    print(f"    {b['text']!r}")

                fill_log = await fill_defaults(page, info)
                info["fill_actions"] = fill_log["actions"]

                btn = await find_continue_button(page)
                if not btn:
                    info["stop_reason"] = "no continue button"
                    print(f"  [STOP] no Continue button visible")
                    break
                btn_text = ((await btn.inner_text()) or "").strip()
                print(f"  [click] {btn_text!r}")
                try:
                    await btn.click()
                    await asyncio.sleep(3.0)  # SPA transitions don't fire navigation events
                except Exception as e:
                    print(f"  [warn] click failed: {e}")
                    break

        finally:
            (RECON_DIR / "flow.json").write_text(json.dumps(steps, indent=2, ensure_ascii=False))
            print(f"\nSaved {len(steps)} steps to {RECON_DIR / 'flow.json'}")
            await asyncio.sleep(2)
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
