"""Apply-assist: generate a fill plan and browser-runnable JS snippet.

The JS snippet is the primary mechanism — user opens the job URL, opens DevTools
(F12 → Console), pastes the snippet, and the form fills. They review and submit.

Playwright is optional — only attempted if `playwright` is importable AND the
server is told to use it via the API request body.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.db import get_answer_bank

_log = logging.getLogger(__name__)

# ── Field mapping catalogue ───────────────────────────────────────────────────
# Keyed by ATS vendor. Each field has:
#   "selector"  — CSS/attribute selector tried first
#   "answer_key" — answer_bank question_key to pull
#   "label"     — human-readable name for the fill plan

_GREENHOUSE_FIELDS: list[dict] = [
    {"selector": "#first_name",                   "answer_key": "first_name",        "label": "First name"},
    {"selector": "#last_name",                    "answer_key": "last_name",         "label": "Last name"},
    {"selector": "#email",                        "answer_key": "email",             "label": "Email"},
    {"selector": "#phone",                        "answer_key": "phone_number",      "label": "Phone"},
    {"selector": "#job_application_answers_work_authorization", "answer_key": "work_authorization", "label": "Work authorization"},
]

_LEVER_FIELDS: list[dict] = [
    {"selector": '[name="name"]',                          "answer_key": "full_name",         "label": "Full name"},
    {"selector": '[name="email"]',                         "answer_key": "email",             "label": "Email"},
    {"selector": '[name="phone"]',                         "answer_key": "phone_number",      "label": "Phone"},
    {"selector": '[name="org"]',                           "answer_key": "current_company",   "label": "Current company"},
    {"selector": '[name="urls[LinkedIn]"]',                "answer_key": "linkedin_url",      "label": "LinkedIn URL"},
    {"selector": '[name="urls[LinkedIn URL]"]',            "answer_key": "linkedin_url",      "label": "LinkedIn URL (alt)"},
    {"selector": '[name="urls[Portfolio]"]',               "answer_key": "github_url",        "label": "Portfolio URL"},
    {"selector": '[name="urls[GitHub]"]',                  "answer_key": "github_url",        "label": "GitHub URL"},
    {"selector": 'textarea[name="comments"]',              "answer_key": "cover_letter_text", "label": "Cover letter / comments"},
]

_WORKDAY_FIELDS: list[dict] = [
    {"selector": '[data-automation-id="legalNameSection_firstName"]', "answer_key": "first_name", "label": "First name"},
    {"selector": '[data-automation-id="legalNameSection_lastName"]',  "answer_key": "last_name",  "label": "Last name"},
    {"selector": '[data-automation-id="email"]',                      "answer_key": "email",      "label": "Email"},
    {"selector": '[data-automation-id="phone-number"]',               "answer_key": "phone_number", "label": "Phone"},
]

_ASHBY_FIELDS: list[dict] = [
    {"selector": 'input[placeholder*="First"]',   "answer_key": "first_name",        "label": "First name"},
    {"selector": 'input[placeholder*="Last"]',    "answer_key": "last_name",         "label": "Last name"},
    {"selector": 'input[type="email"]',           "answer_key": "email",             "label": "Email"},
    {"selector": 'input[type="tel"]',             "answer_key": "phone_number",      "label": "Phone"},
]

_GENERIC_FIELDS: list[dict] = [
    {"selector": 'input[name*="first" i], input[id*="first" i], input[placeholder*="first" i]',
     "answer_key": "first_name", "label": "First name"},
    {"selector": 'input[name*="last" i], input[id*="last" i], input[placeholder*="last" i]',
     "answer_key": "last_name", "label": "Last name"},
    {"selector": 'input[type="email"], input[name*="email" i], input[id*="email" i]',
     "answer_key": "email", "label": "Email"},
    {"selector": 'input[type="tel"], input[name*="phone" i], input[id*="phone" i]',
     "answer_key": "phone_number", "label": "Phone"},
    {"selector": 'input[name*="linkedin" i], input[id*="linkedin" i]',
     "answer_key": "linkedin_url", "label": "LinkedIn URL"},
    {"selector": 'input[name*="github" i], input[id*="github" i]',
     "answer_key": "github_url", "label": "GitHub URL"},
]

_ATS_FIELD_MAP: dict[str, list[dict]] = {
    "greenhouse": _GREENHOUSE_FIELDS,
    "lever":      _LEVER_FIELDS,
    "workday":    _WORKDAY_FIELDS,
    "ashby":      _ASHBY_FIELDS,
}


def _answer_lookup(db_path: str) -> dict[str, str]:
    """Return {question_key: answer_text} from the answer bank."""
    rows = get_answer_bank(db_path)
    return {r["question_key"]: r["answer_text"] for r in rows}


def _derive_name_keys(answers: dict[str, str]) -> None:
    """Populate first_name / last_name / full_name from contact_name if absent."""
    name = answers.get("contact_name") or answers.get("full_name") or ""
    if name:
        parts = name.strip().split()
        if "first_name" not in answers:
            answers["first_name"] = parts[0] if parts else ""
        if "last_name" not in answers:
            answers["last_name"] = " ".join(parts[1:]) if len(parts) > 1 else ""
        if "full_name" not in answers:
            answers["full_name"] = name


def build_fill_plan(
    db_path: str,
    ats_vendor: str | None,
    market: str | None = None,
    cover_letter_text: str | None = None,
) -> dict[str, Any]:
    """Return a structured fill plan and a browser-runnable JS snippet.

    Args:
        db_path: SQLite db path.
        ats_vendor: Detected ATS vendor string (greenhouse, lever, …) or None.
        market: Geographic market key (morocco, europe, uae) for salary selection.
        cover_letter_text: Generated cover letter text to insert into comment fields.

    Returns:
        {
          "vendor": str,
          "fields": [{"label": str, "selector": str, "value": str, "found": bool}],
          "js_snippet": str,
          "missing": [str],   # answer keys with no value
        }
    """
    answers = _answer_lookup(db_path)
    _derive_name_keys(answers)

    # Inject cover letter text if provided
    if cover_letter_text:
        answers["cover_letter_text"] = cover_letter_text

    # Pick salary by market
    if market:
        salary_key = f"salary_{market}"
        if salary_key in answers:
            answers["salary"] = answers[salary_key]
    # Fallback to general salary
    if "salary" not in answers and "salary_general" in answers:
        answers["salary"] = answers["salary_general"]

    vendor = ats_vendor or "generic"
    field_defs = _ATS_FIELD_MAP.get(vendor, _GENERIC_FIELDS)

    fields: list[dict] = []
    missing: list[str] = []

    for fdef in field_defs:
        value = answers.get(fdef["answer_key"], "")
        found = bool(value)
        if not found:
            missing.append(fdef["answer_key"])
        fields.append({
            "label":    fdef["label"],
            "selector": fdef["selector"],
            "value":    value,
            "found":    found,
        })

    js_snippet = _build_js_snippet(fields, vendor)

    return {
        "vendor":     vendor,
        "fields":     fields,
        "js_snippet": js_snippet,
        "missing":    missing,
    }


def _build_js_snippet(fields: list[dict], vendor: str) -> str:
    """Generate a self-contained JS snippet to fill the form."""
    fill_calls: list[str] = []

    for f in fields:
        if not f["value"]:
            continue
        value_json = json.dumps(f["value"])
        selector_json = json.dumps(f["selector"])
        label_json = json.dumps(f["label"])
        fill_calls.append(
            f"  _fill({selector_json}, {value_json}, {label_json});"
        )

    calls_str = "\n".join(fill_calls) if fill_calls else "  console.log('No answers available.');"

    snippet = f"""\
/* Customy Auto-fill — {vendor} — paste in DevTools Console */
(function () {{
  function _fill(selector, value, label) {{
    var el = document.querySelector(selector);
    if (!el) {{ console.warn('[Customy] NOT FOUND: ' + label + ' (' + selector + ')'); return; }}
    var nativeInput = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')
      || Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
    if (nativeInput && nativeInput.set) {{
      nativeInput.set.call(el, value);
    }} else {{
      el.value = value;
    }}
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    console.log('[Customy] Filled: ' + label);
  }}
{calls_str}
  console.log('[Customy] Done. Review every field before submitting!');
}})();"""

    return snippet


# ── Optional Playwright execution ─────────────────────────────────────────────

def run_playwright_fill(
    application_url: str,
    fill_plan: dict[str, Any],
) -> dict[str, Any]:
    """Attempt Playwright-based auto-fill. Returns result dict.

    Only runs if playwright is installed. The browser launches in headed mode
    so the user can review and submit. Never submits automatically.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return {"ok": False, "error": "playwright not installed", "filled": [], "skipped": []}

    filled: list[str] = []
    skipped: list[str] = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False, slow_mo=80)
            page = browser.new_page()
            page.goto(application_url, timeout=30_000)

            for field in fill_plan.get("fields", []):
                if not field["value"]:
                    skipped.append(field["label"])
                    continue
                try:
                    selector = field["selector"]
                    # Try each comma-separated selector
                    for sel in [s.strip() for s in selector.split(",")]:
                        locator = page.locator(sel).first
                        if locator.count() > 0:
                            locator.fill(field["value"])
                            filled.append(field["label"])
                            break
                    else:
                        skipped.append(field["label"])
                except Exception as exc:
                    _log.debug("Playwright fill skipped %s: %s", field["label"], exc)
                    skipped.append(field["label"])

            _log.info("Playwright: filled=%s skipped=%s — waiting for user to submit.", filled, skipped)
            # Keep browser open; user submits manually
            # browser.close() intentionally omitted — user owns the window

        return {"ok": True, "filled": filled, "skipped": skipped}

    except Exception as exc:
        _log.warning("Playwright fill failed: %s", exc)
        return {"ok": False, "error": str(exc), "filled": filled, "skipped": skipped}
