"""
Walk the real Illinois SOS LLC filing flow end-to-end and capture structure.

Fills reasonable defaults at each page so we can map the full sequence.
Stops at any page with payment / submit-filing / captcha keywords.

Output:
  out/recon/step{NN}-{label}.png     screenshot of every page
  out/recon/flow.json                full structured dump of every step

Usage:
    python scripts/recon_il_sos.py [--max-steps 20]
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
START_URL = "https://apps.ilsos.gov/llcarticles/"
RECON_DIR = Path("out/recon")

# Reasonable defaults for the demo seed (sole-owner Chicago restaurant).
# Order matters — first match wins, so put more-specific keys before generic.
SEED_VALUES = {
    # text inputs we expect on data-entry pages — keys are tried as fuzzy
    # matches against id/name/label
    "llcname": "Shu Xiang LLC",
    "company name": "Shu Xiang LLC",
    "name of llc": "Shu Xiang LLC",
    "entity name": "Shu Xiang LLC",

    "principal place": "123 W Randolph St",
    "principal office": "123 W Randolph St",
    "address1": "123 W Randolph St",
    "street": "123 W Randolph St",
    "city": "Chicago",
    "zip": "60601",
    "state": "IL",
    # Bare "address" — must come AFTER more-specific keys so e.g. "agent address"
    # wins. For our demo seed both addresses are the same (sole owner).
    "address": "123 W Randolph St",

    "registered agent name": "Wei Zhang",
    "agent name": "Wei Zhang",
    "agent first": "Wei",
    "agent last": "Zhang",
    "registered office": "123 W Randolph St",
    "agent address": "123 W Randolph St",
    # bare "agent:*" labels (without "name") — must come AFTER the more
    # specific keys above so we don't shadow them
    "agent": "Wei Zhang",

    "organizer name": "Wei Zhang",
    "organizer first": "Wei",
    "organizer last": "Zhang",
    "organizer address": "123 W Randolph St",
    "organizer email": "wei@shuxiangchicago.com",
    "email": "wei@shuxiangchicago.com",
    "phone": "3125551212",

    "duration": "perpetual",
    "members": "1",
    "managers": "0",
    "purpose": "Restaurant",
}


# Match in INPUT id/name only — these signal a real payment form, not text mentions
PAYMENT_INPUT_PATTERNS = [
    r"card[_-]?number",
    r"creditcard",
    r"cc[_-]?num",
    r"\bcvv\b",
    r"\bcvc\b",
    r"expir",
    r"cardholder",
]
# Match in BUTTON text — a button labeled this is the point of no return
TERMINAL_BUTTON_TEXT = [
    "submit filing",
    "submit articles",
    "file articles",
    "pay now",
    "make payment",
    "process payment",
]


async def capture_page(page: Page, step: int, label: str) -> dict:
    RECON_DIR.mkdir(parents=True, exist_ok=True)
    title = await page.title()
    url = page.url

    await asyncio.sleep(1.0)  # let the page settle

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
    """Match an input's id/name/label against SEED_VALUES."""
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
    """Fill all visible inputs with reasonable defaults. Returns audit log."""
    actions = []
    # Group radios by name so we only check ONE per group.
    radio_groups: dict[str, list[dict]] = {}
    for f in info["inputs"]:
        if not f["visible"]:
            continue
        if f["type"] == "radio":
            radio_groups.setdefault(f["name"] or "_unnamed", []).append(f)

    # Default radio selection — prefer "Yes" / "Standard" / first option.
    for name, group in radio_groups.items():
        # Don't overwrite if something already checked
        already = await page.evaluate(
            f"""() => Array.from(document.querySelectorAll('input[type=radio][name="{name}"]'))
                       .some(r => r.checked)"""
        )
        if already:
            continue
        # Look for Yes / Standard / Member-managed first, else first option
        chosen = None
        for r in group:
            label = (r.get("label") or "").lower()
            if any(kw in label for kw in [" yes", "yes ", "agree", "accept", "standard", "member"]):
                chosen = r
                break
        chosen = chosen or group[0]
        sel = f"#{chosen['id']}" if chosen.get("id") else f'input[name="{chosen["name"]}"][value="{chosen.get("value", "")}"]'
        try:
            await page.check(sel)
            actions.append({"action": "check_radio", "selector": sel, "label": chosen.get("label")})
        except Exception as e:
            actions.append({"action": "check_radio_failed", "selector": sel, "error": str(e)})

    # Detect validation errors — if any are visible, we must REFILL even
    # fields that have stale values (the form rejected them last time).
    has_errors = await page.evaluate(
        """() => Array.from(document.querySelectorAll('.error, .errorMessage, [class*=error]'))
                  .some(e => /required|invalid|must|please/i.test(e.innerText || ''))"""
    )

    # Fill text inputs.
    for f in info["inputs"]:
        if not f["visible"]:
            continue
        ftype = f["type"]
        if ftype not in (None, "text", "email", "tel", "number"):
            continue
        if f["tag"] != "input":
            # textarea also OK
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
            # Clear first if there's a stale value from a previous step
            if f.get("value"):
                await page.fill(sel, "")
            await page.fill(sel, value)
            actions.append({"action": "fill", "selector": sel, "value": value, "label": f.get("label")})
        except Exception as e:
            actions.append({"action": "fill_failed", "selector": sel, "error": str(e)})

    # Fill selects with sensible defaults — context-aware by id/name/label.
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
            # Drop placeholder options
            real = [
                o for o in options
                if o["value"].strip()
                and not PLACEHOLDER_RX.match(o["text"] or "")
                and not PLACEHOLDER_RX.match(o["value"] or "")
            ]
            if not real:
                continue
            # State dropdown? Prefer Illinois.
            if "state" in haystack:
                pick = next(
                    (o for o in real if o["value"].upper() in ("IL", "ILLINOIS") or "illinois" in (o["text"] or "").lower()),
                    real[0],
                )
            elif "duration" in haystack or "perpet" in haystack:
                pick = next((o for o in real if "perpet" in (o["value"] or "").lower() or "perpet" in (o["text"] or "").lower()), real[0])
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
    """Find a Continue/Next button that ISN'T a final submit."""
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
        # Stop on terminal buttons
        if any(kw in text for kw in ["submit filing", "pay now", "make payment", "submit articles", "file articles"]):
            return None
        if any(kw in text for kw in ["continue", "next", "proceed"]):
            return btn
    return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-steps", type=int, default=15)
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

                # Stop check — only on actual payment form INPUTS or terminal BUTTONS.
                # Text mentions of "credit card" or "review" don't trigger.
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
                    print("\n=== STEP", step, "===")
                    print(f"  URL: {info['url']}")
                    print(f"  Title: {info['title']!r}")
                    print(f"  Inputs ({len([i for i in info['inputs'] if i['visible']])}):")
                    for f in info["inputs"]:
                        if f["visible"]:
                            sel = f"#{f['id']}" if f.get("id") else f'[name="{f["name"]}"]'
                            print(f"    {sel}  type={f['type']}  label={f['label']!r}")
                    print(f"  Buttons:")
                    for b in info["buttons"][:6]:
                        print(f"    {b['text']!r}")
                    break

                print(f"\n=== STEP {step}: {info['title']} ===")
                print(f"  URL: {info['url']}")
                visible_inputs = [f for f in info['inputs'] if f['visible']]
                print(f"  Inputs ({len(visible_inputs)}):")
                for f in visible_inputs:
                    sel = f"#{f['id']}" if f.get("id") else (f'[name="{f["name"]}"]' if f.get("name") else "?")
                    print(f"    {sel}  type={f['type']}  label={f['label']!r}")

                # Fill defaults
                fill_log = await fill_defaults(page, info)
                info["fill_actions"] = fill_log["actions"]

                # Click Continue
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
                    # Same-page submit (validation error or AJAX)
                    print(f"  [warn] no nav after click: {e}")
                    await asyncio.sleep(1.5)
                    # Check if URL changed even without nav event
                    new_url = page.url
                    if new_url == info["url"]:
                        info["stop_reason"] = "stuck on same URL after fill"
                        print(f"  [STOP] stuck on same page after fill")
                        # Capture validation errors if any
                        errors = await page.evaluate(
                            "() => Array.from(document.querySelectorAll('.error, .errorMessage, [class*=error]'))"
                            "       .map(e => e.innerText.trim()).filter(t => t).slice(0, 5)"
                        )
                        info["validation_errors"] = errors
                        print(f"  validation errors: {errors}")
                        break

        finally:
            (RECON_DIR / "flow.json").write_text(json.dumps(steps, indent=2, ensure_ascii=False))
            print(f"\n✓ Saved {len(steps)} steps to {RECON_DIR / 'flow.json'}")
            await asyncio.sleep(2)
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
