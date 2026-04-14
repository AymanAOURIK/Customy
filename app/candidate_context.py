"""Helpers for building canonical candidate_context dicts from profile-like data."""
from __future__ import annotations

import json
from typing import Any, Mapping


def _clean_scalar(value: Any) -> str:
    return str(value or "").strip()


def _copy_list(items: Any) -> list[Any]:
    if not isinstance(items, list):
        return []
    copied: list[Any] = []
    for item in items:
        copied.append(item.copy() if isinstance(item, dict) else item)
    return copied


def _decode_json_field(value: Any, *, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return fallback
        try:
            return json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def _string_list(value: Any) -> list[str]:
    parsed = _decode_json_field(value, fallback=[])
    if not isinstance(parsed, list):
        return []
    return [cleaned for item in parsed if (cleaned := _clean_scalar(item))]


def build_candidate_context_from_profile_data(
    profile_data: Mapping[str, Any] | None,
    *,
    candidate_source: str,
) -> dict[str, Any]:
    """Return the canonical candidate_context shape used across the app."""
    source = profile_data if isinstance(profile_data, Mapping) else {}
    personal = source.get("personal") if isinstance(source.get("personal"), Mapping) else {}

    skills = _decode_json_field(source.get("skills"), fallback={})
    if not isinstance(skills, dict):
        skills = {}

    experiences = _decode_json_field(source.get("experiences"), fallback=[])
    education = _decode_json_field(source.get("education"), fallback=[])
    spoken_languages = _decode_json_field(source.get("spoken_languages"), fallback=[])
    scoring_keywords = _decode_json_field(source.get("scoring_keywords"), fallback=[])

    return {
        "personal": {
            "name": _clean_scalar(source.get("full_name") or source.get("name") or personal.get("name")),
            "email": _clean_scalar(source.get("email") or personal.get("email")),
            "phone": _clean_scalar(source.get("phone") or personal.get("phone")),
            "location": _clean_scalar(source.get("location") or personal.get("location")),
            "linkedin": _clean_scalar(source.get("linkedin") or personal.get("linkedin")),
            "github": _clean_scalar(source.get("github") or personal.get("github")),
        },
        "headline": _clean_scalar(source.get("headline") or personal.get("headline")),
        "summary": _clean_scalar(source.get("summary")),
        "skills": {
            "languages": _string_list(skills.get("languages")),
            "frameworks": _string_list(skills.get("frameworks")),
            "tools": _string_list(skills.get("tools")),
            "soft": _string_list(skills.get("soft")),
        },
        "experiences": _copy_list(experiences),
        "education": _copy_list(education),
        "spoken_languages": _string_list(spoken_languages),
        "scoring_keywords": _string_list(scoring_keywords),
        "source_resume_text": _clean_scalar(source.get("source_resume_text")),
        "candidate_source": _clean_scalar(source.get("candidate_source")) or candidate_source,
    }
