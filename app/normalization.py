"""Payload normalization: unwrapping, experience ordering, skills, and final pack assembly."""
from __future__ import annotations

import re

from app.fallbacks import _build_fallback_title, _normalize_summary
from app.language import _experience_bullets_for_language, _resume_language, _text_conflicts_with_language
from app.schemas import (
    DETECTED_COMPANY_KEYS,
    EMAIL_KEYS,
    EMAIL_PATTERN,
    EXPERIENCE_FIELD_ALIASES,
    EXPERIENCE_ORDER_KEYS,
    FOCUS_AREA_KEYS,
    NUMERIC_FACT_PATTERN,
    PROFILE_UPDATE_HINT_KEYS,
    ROOT_PAYLOAD_KEYS,
    TAILORED_EXPERIENCE_KEYS,
    TAILORED_SKILLS_KEYS,
    TAILORED_SUMMARY_KEYS,
    TAILORED_TITLE_KEYS,
    TECH_TERM_PATTERN,
    TEXT_FIELD_ALIASES,
    _clean_text_list,
    _first_present,
    _has_value,
    _normalize_match_key,
    _unique_text_list,
)
from app.targeting import is_credible_role_title, normalize_role_title, prioritize_candidate_skills
from app.text_utils import clean_text as _clean_text


# ---------------------------------------------------------------------------
# Payload unwrapping
# ---------------------------------------------------------------------------


def _unwrap_payload(payload: object) -> dict:
    current = payload if isinstance(payload, dict) else {}
    while True:
        nested = None
        for key in ROOT_PAYLOAD_KEYS:
            candidate = current.get(key)
            if isinstance(candidate, dict):
                nested = candidate
                break
        if nested is None:
            return current
        current = nested


def _normalize_detected_company(payload: dict) -> str | None:
    company = _clean_text(_first_present(payload, DETECTED_COMPANY_KEYS))
    if not company:
        return None
    lowered = company.lower().strip(" .,:;|-")
    if lowered in {"unknown", "unknown company", "company", "n/a", "none", "not provided"}:
        return None
    return company.strip(" .,:;|-")


# ---------------------------------------------------------------------------
# Bullet-level helpers
# ---------------------------------------------------------------------------


def _normalized_fact_token(value: str) -> str:
    return re.sub(r"[^a-z0-9%+/$]+", "", value.lower())


def _extract_fact_tokens(text: str) -> tuple[set[str], set[str]]:
    metrics = {_normalized_fact_token(match.group(0)) for match in NUMERIC_FACT_PATTERN.finditer(text or "")}
    terms = {_normalize_match_key(match.group(0)) for match in TECH_TERM_PATTERN.finditer(text or "")}
    return metrics, terms


def _bullet_rewrite_is_safe(source_bullet: str, rewritten_bullet: str) -> bool:
    source_metrics, source_terms = _extract_fact_tokens(source_bullet)
    rewritten_metrics, rewritten_terms = _extract_fact_tokens(rewritten_bullet)
    if source_metrics and not source_metrics.issubset(rewritten_metrics):
        return False
    if rewritten_metrics and not rewritten_metrics.issubset(source_metrics):
        return False
    if source_terms and not source_terms.issubset(rewritten_terms):
        return False
    return True


# ---------------------------------------------------------------------------
# Experience ordering and normalization
# ---------------------------------------------------------------------------


def _find_fallback_experience(raw_item: object, fallback_items: list[dict], index: int) -> dict | None:
    source = raw_item if isinstance(raw_item, dict) else {}
    source_company = _normalize_match_key(_first_present(source, EXPERIENCE_FIELD_ALIASES["company"]))
    source_role = _normalize_match_key(_first_present(source, EXPERIENCE_FIELD_ALIASES["role"]))

    for candidate in fallback_items:
        if source_company and source_company != _normalize_match_key(candidate.get("company")):
            continue
        if source_role and source_role != _normalize_match_key(candidate.get("role")):
            continue
        return candidate

    if 0 <= index < len(fallback_items):
        return fallback_items[index]
    return None


def _resolve_bullet_indices(raw_indices: object, bullet_count: int) -> list[int]:
    if not isinstance(raw_indices, list):
        return []

    cleaned_indices = []
    for item in raw_indices:
        try:
            cleaned_indices.append(int(item))
        except (TypeError, ValueError):
            continue

    if not cleaned_indices:
        return []

    zero_based = any(index == 0 for index in cleaned_indices)
    resolved = []
    seen: set[int] = set()
    for index in cleaned_indices:
        normalized = index if zero_based else index - 1
        if normalized < 0 or normalized >= bullet_count or normalized in seen:
            continue
        resolved.append(normalized)
        seen.add(normalized)
    return resolved


def _match_bullet_order_from_texts(raw_bullets: object, fallback_bullets: list[str]) -> list[int]:
    if not isinstance(raw_bullets, list):
        return []

    normalized_fallback = [_normalize_match_key(item) for item in fallback_bullets]
    order = []
    seen: set[int] = set()
    for bullet in raw_bullets:
        target = _normalize_match_key(bullet)
        if not target:
            continue
        for index, fallback_value in enumerate(normalized_fallback):
            if index in seen:
                continue
            if target == fallback_value:
                order.append(index)
                seen.add(index)
                break
    return order


def _reorder_bullets(fallback_bullets: list[str], preferred_order: list[int]) -> list[str]:
    if not fallback_bullets:
        return []

    ordered = []
    seen: set[int] = set()
    for index in preferred_order:
        if index in seen or index < 0 or index >= len(fallback_bullets):
            continue
        ordered.append(_clean_text(fallback_bullets[index]))
        seen.add(index)

    for index, bullet in enumerate(fallback_bullets):
        if index in seen:
            continue
        ordered.append(_clean_text(bullet))
    return [bullet for bullet in ordered if bullet]


def _normalize_tailored_bullets(
    source_bullets: list[str],
    preferred_order: list[int],
    raw_tailored_bullets: object,
    resume_language: str,
) -> list[str]:
    ordered_source = _reorder_bullets(source_bullets, preferred_order)
    rewritten = _clean_text_list(raw_tailored_bullets)
    if len(rewritten) != len(ordered_source):
        return ordered_source

    normalized = []
    for source_bullet, rewritten_bullet in zip(ordered_source, rewritten):
        if (
            not rewritten_bullet
            or not _bullet_rewrite_is_safe(source_bullet, rewritten_bullet)
            or _text_conflicts_with_language(rewritten_bullet, resume_language)
        ):
            normalized.append(source_bullet)
            continue
        normalized.append(rewritten_bullet)
    return normalized


def _experience_start_sort_key(item: dict) -> tuple[int, int]:
    start = _clean_text((item or {}).get("start", ""))
    match = re.fullmatch(r"(\d{4})-(\d{2})", start)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (0, 0)


def _experience_identity(item: dict) -> tuple[str, str, str, str]:
    return (
        _normalize_match_key((item or {}).get("company")),
        _normalize_match_key((item or {}).get("role")),
        _clean_text((item or {}).get("start")),
        _clean_text((item or {}).get("end")),
    )


def _normalize_experiences(payload: dict, candidate_context: dict, resume_language: str) -> list[dict]:
    fallback_items = list(candidate_context.get("experiences", []))
    raw_orders = _first_present(payload, EXPERIENCE_ORDER_KEYS)
    raw_items = raw_orders if isinstance(raw_orders, list) and raw_orders else _first_present(payload, TAILORED_EXPERIENCE_KEYS)
    raw_items = raw_items if isinstance(raw_items, list) and raw_items else fallback_items

    normalized = []
    for index, item in enumerate(raw_items):
        fallback_item = _find_fallback_experience(item, fallback_items, index)
        if not fallback_item:
            continue
        source = item if isinstance(item, dict) else {}
        original_bullets = _clean_text_list(fallback_item.get("bullets"))
        localized_bullets = _experience_bullets_for_language(fallback_item, resume_language)
        preferred_order = _resolve_bullet_indices(_first_present(source, EXPERIENCE_FIELD_ALIASES["bullet_indices"]), len(original_bullets))
        if not preferred_order:
            preferred_order = _match_bullet_order_from_texts(_first_present(source, EXPERIENCE_FIELD_ALIASES["bullets"]), original_bullets)
        if not preferred_order and localized_bullets != original_bullets:
            preferred_order = _match_bullet_order_from_texts(_first_present(source, EXPERIENCE_FIELD_ALIASES["bullets"]), localized_bullets)
        raw_tailored_bullets = _first_present(source, EXPERIENCE_FIELD_ALIASES["tailored_bullets"])
        normalized_item = {
            "company": _clean_text(fallback_item.get("company")),
            "role": _clean_text(fallback_item.get("role")),
            "start": _clean_text(fallback_item.get("start")),
            "end": _clean_text(fallback_item.get("end")),
            "bullets": _normalize_tailored_bullets(localized_bullets, preferred_order, raw_tailored_bullets, resume_language)
            if isinstance(raw_tailored_bullets, list)
            else _reorder_bullets(localized_bullets, preferred_order),
        }
        if normalized_item["company"] and normalized_item["role"] and normalized_item["bullets"]:
            normalized.append(normalized_item)

    if normalized:
        seen_experiences = {_experience_identity(item) for item in normalized}
        for fallback_item in fallback_items:
            identity = _experience_identity(fallback_item)
            if identity in seen_experiences:
                continue
            bullets = _experience_bullets_for_language(fallback_item, resume_language)
            if not bullets:
                continue
            normalized.append(
                {
                    "company": _clean_text(fallback_item.get("company")),
                    "role": _clean_text(fallback_item.get("role")),
                    "start": _clean_text(fallback_item.get("start")),
                    "end": _clean_text(fallback_item.get("end")),
                    "bullets": bullets,
                }
            )
            seen_experiences.add(identity)
        normalized.sort(key=_experience_start_sort_key, reverse=True)
        return normalized

    fallback_normalized = []
    for item in fallback_items:
        bullets = _experience_bullets_for_language(item, resume_language)
        if not bullets:
            continue
        fallback_normalized.append(
            {
                "company": _clean_text(item.get("company")),
                "role": _clean_text(item.get("role")),
                "start": _clean_text(item.get("start")),
                "end": _clean_text(item.get("end")),
                "bullets": bullets,
            }
        )
    return fallback_normalized


def _normalize_skills(payload: dict, candidate_context: dict, jd_analysis: dict) -> dict:
    del payload
    return prioritize_candidate_skills(candidate_context, jd_analysis)


def _collect_detected_emails(jd_text: str, payload: dict) -> list[str]:
    detected = _clean_text_list(_first_present(payload, EMAIL_KEYS))
    seen = {item.lower() for item in detected}
    for match in EMAIL_PATTERN.findall(jd_text or ""):
        cleaned = match.strip()
        if cleaned.lower() not in seen:
            detected.append(cleaned)
            seen.add(cleaned.lower())
    return detected


def _normalize_profile_update_hints(payload: dict, jd_analysis: dict) -> list[str]:
    model_hints = _clean_text_list(_first_present(payload, PROFILE_UPDATE_HINT_KEYS))
    inferred_hints = _clean_text_list(jd_analysis.get("missing_candidate_keywords"))
    return _unique_text_list(model_hints + inferred_hints)


# ---------------------------------------------------------------------------
# Top-level normalization entry point
# ---------------------------------------------------------------------------


def _normalize_payload(payload: dict, candidate_context: dict, jd_analysis: dict, jd_text: str) -> dict:
    unwrapped = _unwrap_payload(payload)
    resume_language = _resume_language(jd_analysis)
    model_title = normalize_role_title(_first_present(unwrapped, TAILORED_TITLE_KEYS), resume_language)
    preferred_title = normalize_role_title(jd_analysis.get("role"), resume_language)
    if is_credible_role_title(preferred_title):
        title = preferred_title
    elif is_credible_role_title(model_title):
        title = model_title
    else:
        title = _build_fallback_title(candidate_context, jd_analysis, resume_language)
    summary = _normalize_summary(_first_present(unwrapped, TAILORED_SUMMARY_KEYS), candidate_context, jd_analysis, resume_language, title)
    normalized: dict = {
        "resume_language": resume_language,
        "tailored_title": title,
        "tailored_summary": summary,
        "tailored_experiences": _normalize_experiences(unwrapped, candidate_context, resume_language),
        "tailored_skills": _normalize_skills(unwrapped, candidate_context, jd_analysis),
        "focus_areas": _clean_text_list(
            _first_present(unwrapped, FOCUS_AREA_KEYS)
            or jd_analysis.get("top_requirements")
            or jd_analysis.get("keyword_signals")
            or jd_analysis.get("matched_keywords")
        ),
        "detected_emails": _collect_detected_emails(jd_text, unwrapped),
        "profile_update_hints": _normalize_profile_update_hints(unwrapped, jd_analysis),
    }
    for field, aliases in TEXT_FIELD_ALIASES.items():
        value = _first_present(unwrapped, aliases)
        normalized[field] = _clean_text(value) if _has_value(value) else None
    return normalized
