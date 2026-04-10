"""Seed the answer_bank table from candidate.yaml profile data at startup.

Rules:
- Only writes entries with answer_source = 'profile'.
- Never overwrites an entry whose answer_source = 'manual' (user-entered data wins).
- Safe to call on every startup — idempotent for profile-sourced entries.
"""
from __future__ import annotations

import logging

from app.db import get_answer_bank, upsert_answer

_log = logging.getLogger(__name__)


def _js(val: object) -> str:
    return str(val or "").strip()


def _pick_salary_text(market: dict) -> str:
    lo = market.get("min", "")
    hi = market.get("max", "")
    curr = market.get("currency", "")
    period = market.get("period", "month")
    note = _js(market.get("note", ""))
    if lo == hi:
        text = f"{lo} {curr}/{period}"
    else:
        text = f"{lo}–{hi} {curr}/{period}"
    if note:
        text += f". {note}"
    return text


def seed_answer_bank(db_path: str, candidate_context: dict) -> None:
    """Build answer bank entries from candidate profile. Called at server startup."""

    existing = {row["question_key"]: row for row in get_answer_bank(db_path)}

    def _seed(key: str, question: str, answer: str, category: str, language: str = "en") -> None:
        if not answer.strip():
            return
        prev = existing.get(key)
        if prev and prev.get("answer_source") == "manual":
            return  # manual entry wins — never overwrite
        upsert_answer(
            db_path,
            question_key=key,
            question_text=question,
            answer_text=answer,
            category=category,
            language=language,
            source="profile",
        )

    personal = candidate_context.get("personal", {})

    # ── Contact ───────────────────────────────────────────────────────────────
    name = _js(personal.get("name"))
    if name:
        _seed("full_name", "Full name", name, "contact")
        parts = name.strip().split()
        if parts:
            _seed("first_name", "First name", parts[0], "contact")
            _seed("last_name", "Last name", " ".join(parts[1:]) if len(parts) > 1 else "", "contact")

    email = _js(personal.get("email"))
    if email:
        _seed("email", "Email address", email, "contact")

    phone = _js(personal.get("phone"))
    if phone:
        _seed("phone_number", "Phone number", phone, "contact")

    linkedin = _js(personal.get("linkedin"))
    if linkedin and "linkedin.com" in linkedin:
        _seed("linkedin_url", "LinkedIn profile URL", linkedin, "linkedin")
    elif linkedin:
        full = f"https://www.linkedin.com/{linkedin.lstrip('/')}"
        _seed("linkedin_url", "LinkedIn profile URL", full, "linkedin")

    github = _js(personal.get("github"))
    if github:
        _seed("github_url", "GitHub / portfolio URL", github, "github")

    location = _js(personal.get("location"))
    if location:
        _seed("location", "City / location", location, "location")

    # Most recent employer (for "Current company" fields on ATS forms)
    experiences = candidate_context.get("experiences", [])
    if experiences:
        current_company = _js(experiences[0].get("company", ""))
        if current_company:
            _seed("current_company", "Current company / organization", current_company, "contact")

    # ── Work authorization ────────────────────────────────────────────────────
    work_auth = candidate_context.get("work_authorization", {})
    if work_auth:
        countries = work_auth.get("authorized_countries", [])
        requires = work_auth.get("requires_sponsorship", False)
        note = _js(work_auth.get("note", ""))

        if note:
            auth_text = note
        elif countries and requires:
            auth_text = (
                f"I am authorized to work in {', '.join(countries)}. "
                "I require visa sponsorship to work in any other country."
            )
        elif countries:
            auth_text = f"I am authorized to work in {', '.join(countries)}."
        else:
            auth_text = "Please confirm work authorization requirements."

        _seed("work_authorization", "Are you authorized to work in this country?", auth_text, "work_authorization")
        _seed(
            "visa_sponsorship",
            "Do you require visa sponsorship?",
            "Yes" if requires else "No",
            "work_authorization",
        )

    # ── Salary — multi-market ─────────────────────────────────────────────────
    salary = candidate_context.get("salary_expectations", {})
    markets = salary.get("markets", {})

    if markets:
        for market_key, market_data in markets.items():
            text = _pick_salary_text(market_data)
            _seed(
                f"salary_{market_key}",
                f"Salary expectations ({market_key})",
                text,
                "salary",
            )
        _log.info("Seeder: salary entries for markets: %s", list(markets.keys()))
    else:
        # Flat salary fallback
        lo = salary.get("min", "")
        hi = salary.get("max", "")
        curr = salary.get("currency", "")
        if lo and hi:
            text = f"{lo}–{hi} {curr}" if lo != hi else f"{lo} {curr}"
            note = _js(salary.get("note", ""))
            if note:
                text += f". {note}"
            _seed("salary_general", "Salary expectations", text, "salary")

    # ── Availability ──────────────────────────────────────────────────────────
    avail = candidate_context.get("availability", {})
    if avail:
        notice = _js(avail.get("notice_period", ""))
        start = _js(avail.get("preferred_start", ""))
        parts = []
        if notice:
            parts.append(f"Notice period: {notice}")
        if start:
            parts.append(f"Earliest start: {start}")
        if parts:
            _seed("availability", "When can you start / notice period?", ". ".join(parts) + ".", "availability")

    # ── Relocation ────────────────────────────────────────────────────────────
    reloc = candidate_context.get("relocation", {})
    if reloc:
        willing = reloc.get("willing", False)
        preferred = reloc.get("preferred_locations", [])
        note = _js(reloc.get("note", ""))
        if willing:
            text = "Yes, I am willing to relocate."
            if preferred:
                text += f" Preferred locations: {', '.join(preferred)}."
            if note:
                text += f" {note}."
        else:
            text = "No, I prefer not to relocate."
        _seed("relocation", "Are you willing to relocate?", text, "relocation")

    _log.info("Seeder: answer bank seeded from candidate profile.")
