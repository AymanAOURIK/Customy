"""Rule-based comparison of source resume signals against structured candidate data.

This module detects source evidence that was likely lost between resume upload and
structured draft/profile storage. It is deterministic, does not use any LLM, and
does not change generation or UI behavior.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.candidate_context import build_candidate_context_from_profile_data
from app.source_signal_index import _COMPILED_TOOL_PATTERNS, _metric_tokens_for_line, _normalize_text
from app.text_utils import clean_text as _clean_text

REPORT_VERSION = "source_coverage_report.v1"

_OPTIONAL_SECTION_FIELD_ALIASES = {
    "projects": ("projects", "selected_projects", "personal_projects"),
    "certifications": ("certifications", "certificates", "certificate", "licenses", "credentials"),
}

_EXPERIENCE_ROLE_KEYS = ("role", "title", "position")
_EXPERIENCE_ORGANIZATION_KEYS = ("company", "organization", "employer")
_EXPERIENCE_BULLET_KEYS = ("bullets", "highlights", "achievements", "details")
_EXPERIENCE_START_KEYS = ("start", "start_date", "start_year")
_EXPERIENCE_END_KEYS = ("end", "end_date", "end_year")
_GENERIC_MATCH_TOKENS = {
    "analyst",
    "and",
    "data",
    "consultant",
    "developer",
    "engineer",
    "group",
    "inc",
    "labs",
    "lead",
    "llc",
    "ltd",
    "manager",
    "role",
    "sa",
    "sas",
    "scientist",
    "senior",
    "specialist",
    "solutions",
    "systems",
    "team",
    "tech",
    "technologies",
}
_PRESENT_MARKER_PATTERN = re.compile(r"\b(?:present|current|présent)\b", re.IGNORECASE)
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


def build_source_coverage_report(
    source_signal_index: Mapping[str, Any] | None,
    candidate_data: Mapping[str, Any] | None,
    *,
    candidate_source: str = "source_coverage_report",
) -> dict[str, Any]:
    """Compare source signals against canonical candidate_context or raw profile data."""
    candidate_context, raw_candidate = _coerce_candidate_input(candidate_data, candidate_source=candidate_source)
    source_index = source_signal_index if isinstance(source_signal_index, Mapping) else {}

    source_signals = _build_source_signals(source_index)
    candidate_signals = _build_candidate_signals(candidate_context, raw_candidate)

    experience_matches, experience_match_lookup = _match_source_experiences(
        source_signals["experience_entries"],
        candidate_signals["experiences"],
    )
    matched_source_positions = {
        int(item["source_experience_position"])
        for item in experience_matches
    }
    missing_source_experiences = [
        _missing_experience_record(entry)
        for entry in source_signals["experience_entries"]
        if int(entry["position"]) not in matched_source_positions
    ]

    missing_optional_sections = _detect_missing_optional_sections(
        source_signals["optional_sections"],
        candidate_signals["optional_sections_present"],
        candidate_signals["optional_section_support"],
    )
    missing_tool_terms = _detect_missing_tool_terms(
        source_signals["tool_terms"],
        candidate_signals["tool_terms_present"],
    )
    missing_metric_evidence = _detect_missing_metric_evidence(
        source_signals["metric_lines"],
        experience_match_lookup,
        candidate_signals["metric_segments"],
    )

    counts = {
        "source_experience_entries": len(source_signals["experience_entries"]),
        "candidate_experience_entries": len(candidate_signals["experiences"]),
        "matched_source_experience_entries": len(experience_matches),
        "missing_source_experience_entries": len(missing_source_experiences),
        "source_optional_sections": len(source_signals["optional_sections"]),
        "candidate_optional_sections_present": len(candidate_signals["optional_sections_present"]),
        "missing_optional_sections": len(missing_optional_sections),
        "source_tool_terms": len(source_signals["tool_terms"]),
        "candidate_detected_tool_terms": len(candidate_signals["tool_terms_present"]),
        "missing_tool_terms": len(missing_tool_terms),
        "source_metric_lines": len(source_signals["metric_lines"]),
        "candidate_metric_segments": len(candidate_signals["metric_segments"]),
        "matched_metric_lines": len(source_signals["metric_lines"]) - len(missing_metric_evidence),
        "missing_metric_lines": len(missing_metric_evidence),
    }

    blockers, warnings = _build_issues(
        source_signals=source_signals,
        candidate_signals=candidate_signals,
        source_index=source_index,
        missing_optional_sections=missing_optional_sections,
    )
    overall_status = _overall_status(
        blockers=blockers,
        warnings=warnings,
        missing_source_experiences=missing_source_experiences,
        missing_optional_sections=missing_optional_sections,
        missing_tool_terms=missing_tool_terms,
        missing_metric_evidence=missing_metric_evidence,
    )

    return {
        "report_version": REPORT_VERSION,
        "source_index_version": _clean_text(source_index.get("index_version")),
        "source_text_sha256": _clean_text(source_index.get("source_text_sha256")),
        "candidate_source": _clean_text(candidate_context.get("candidate_source")) or candidate_source,
        "overall_status": overall_status,
        "counts": counts,
        "experience_matches": experience_matches,
        "missing_source_experiences": missing_source_experiences,
        "missing_optional_sections": missing_optional_sections,
        "missing_tool_terms": missing_tool_terms,
        "missing_metric_evidence": missing_metric_evidence,
        "blockers": blockers,
        "warnings": warnings,
    }


def build_source_coverage_report_from_profile_data(
    source_signal_index: Mapping[str, Any] | None,
    profile_data: Mapping[str, Any] | None,
    *,
    candidate_source: str = "source_coverage_report",
) -> dict[str, Any]:
    """Wrapper for raw extracted draft/profile payloads."""
    return build_source_coverage_report(
        source_signal_index,
        profile_data,
        candidate_source=candidate_source,
    )


def _coerce_candidate_input(
    candidate_data: Mapping[str, Any] | None,
    *,
    candidate_source: str,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    raw_candidate = candidate_data if isinstance(candidate_data, Mapping) else {}
    if _looks_like_candidate_context(raw_candidate):
        return dict(raw_candidate), raw_candidate
    return (
        build_candidate_context_from_profile_data(raw_candidate, candidate_source=candidate_source),
        raw_candidate,
    )


def _looks_like_candidate_context(candidate_data: Mapping[str, Any]) -> bool:
    return isinstance(candidate_data.get("personal"), Mapping)


def _build_source_signals(source_index: Mapping[str, Any]) -> dict[str, Any]:
    sections = [
        dict(item)
        for item in (source_index.get("sections_detected") or [])
        if isinstance(item, Mapping)
    ]
    optional_sections = [
        _clean_text(item).lower()
        for item in (source_index.get("optional_sections_detected") or [])
        if _clean_text(item)
    ]
    experience_entries = [
        _prepare_source_experience(item)
        for item in (source_index.get("experience_entries") or [])
        if isinstance(item, Mapping)
    ]
    tool_terms = [
        _prepare_source_tool_term(item)
        for item in (source_index.get("tool_system_terms") or [])
        if isinstance(item, Mapping)
    ]
    metric_lines = [
        _prepare_source_metric_line(item)
        for item in (source_index.get("metric_bearing_lines") or [])
        if isinstance(item, Mapping)
    ]
    optional_section_records = []
    for section in sections:
        section_key = _clean_text(section.get("section_key")).lower()
        if section_key not in optional_sections:
            continue
        optional_section_records.append(
            {
                "section_key": section_key,
                "heading": _clean_text(section.get("heading")),
                "line_number": _safe_int(section.get("line_number")),
            }
        )
    optional_section_records.sort(key=lambda item: (item["line_number"], item["section_key"]))
    return {
        "sections": sections,
        "optional_sections": optional_section_records,
        "experience_entries": experience_entries,
        "tool_terms": tool_terms,
        "metric_lines": metric_lines,
    }


def _prepare_source_experience(entry: Mapping[str, Any]) -> dict[str, Any]:
    role = _clean_text(entry.get("role"))
    organization = _clean_text(entry.get("organization"))
    tool_terms = _clean_string_list(entry.get("tool_system_terms"))
    return {
        "position": _safe_int(entry.get("position")),
        "role": role,
        "organization": organization,
        "date_text": _clean_text(entry.get("date_text")),
        "line_start": _safe_int(entry.get("line_start")),
        "line_end": _safe_int(entry.get("line_end")),
        "metric_line_count": _safe_int(entry.get("metric_line_count")),
        "tool_terms": tool_terms,
        "label": _experience_label(role=role, organization=organization),
    }


def _prepare_source_tool_term(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "term": _clean_text(item.get("term")),
        "line_numbers": sorted(_clean_int_list(item.get("line_numbers"))),
        "sections": sorted(_clean_string_list(item.get("sections"))),
        "experience_positions": sorted(_clean_int_list(item.get("experience_positions"))),
    }


def _prepare_source_metric_line(item: Mapping[str, Any]) -> dict[str, Any]:
    text = _clean_text(item.get("text"))
    return {
        "line_number": _safe_int(item.get("line_number")),
        "section_key": _clean_text(item.get("section_key")).lower() or None,
        "experience_position": (
            _safe_int(item.get("experience_position"))
            if item.get("experience_position") is not None
            else None
        ),
        "text": text,
        "matched_tokens": _normalized_metric_tokens(item.get("matched_tokens") or _metric_tokens_for_line(text)),
        "tool_terms": _detect_tool_terms_in_text(text),
        "significant_tokens": _significant_text_tokens(text),
    }


def _build_candidate_signals(
    candidate_context: Mapping[str, Any],
    raw_candidate: Mapping[str, Any],
) -> dict[str, Any]:
    experiences = _build_candidate_experiences(candidate_context.get("experiences"))
    optional_sections_present, optional_section_support = _detect_candidate_optional_sections(
        candidate_context,
        raw_candidate,
    )
    structured_text_parts = _candidate_structured_text_parts(candidate_context, raw_candidate, experiences)
    structured_text = "\n".join(part for part in structured_text_parts if part)
    tool_terms_present = _detect_tool_terms_in_text(structured_text)
    metric_segments = _build_candidate_metric_segments(candidate_context, raw_candidate, experiences)
    return {
        "structured_text": structured_text,
        "experiences": experiences,
        "optional_sections_present": optional_sections_present,
        "optional_section_support": optional_section_support,
        "tool_terms_present": tool_terms_present,
        "metric_segments": metric_segments,
    }


def _build_candidate_experiences(experiences: Any) -> list[dict[str, Any]]:
    if not isinstance(experiences, list):
        return []
    prepared: list[dict[str, Any]] = []
    for position, item in enumerate(experiences):
        if not isinstance(item, Mapping):
            continue
        role = _first_non_empty(item, _EXPERIENCE_ROLE_KEYS)
        organization = _first_non_empty(item, _EXPERIENCE_ORGANIZATION_KEYS)
        bullets = _experience_bullets(item)
        text_parts = [
            role,
            organization,
            _first_non_empty(item, ("location",)),
            *bullets,
        ]
        text = "\n".join(part for part in text_parts if part)
        tool_terms = _detect_tool_terms_in_text(text)
        metric_bullets = []
        for bullet_index, bullet in enumerate(bullets):
            metric_tokens = _normalized_metric_tokens(_metric_tokens_for_line(bullet))
            if not metric_tokens:
                continue
            metric_bullets.append(
                {
                    "text": bullet,
                    "metric_tokens": metric_tokens,
                    "tool_terms": _detect_tool_terms_in_text(bullet),
                    "significant_tokens": _significant_text_tokens(bullet),
                    "experience_position": position,
                    "segment_type": "experience_bullet",
                    "bullet_index": bullet_index,
                }
            )
        prepared.append(
            {
                "position": position,
                "role": role,
                "organization": organization,
                "start": _first_non_empty(item, _EXPERIENCE_START_KEYS),
                "end": _first_non_empty(item, _EXPERIENCE_END_KEYS),
                "bullets": bullets,
                "text": text,
                "label": _experience_label(role=role, organization=organization),
                "tool_terms": tool_terms,
                "metric_bullets": metric_bullets,
                "metric_bullet_count": len(metric_bullets),
            }
        )
    return prepared


def _detect_candidate_optional_sections(
    candidate_context: Mapping[str, Any],
    raw_candidate: Mapping[str, Any],
) -> tuple[list[str], dict[str, bool]]:
    present: list[str] = []
    support: dict[str, bool] = {}
    for section_key, field_aliases in _OPTIONAL_SECTION_FIELD_ALIASES.items():
        supported = any(alias in raw_candidate or alias in candidate_context for alias in field_aliases)
        support[section_key] = supported
        if any(_has_content(raw_candidate.get(alias)) or _has_content(candidate_context.get(alias)) for alias in field_aliases):
            present.append(section_key)
    present.sort()
    return present, support


def _candidate_structured_text_parts(
    candidate_context: Mapping[str, Any],
    raw_candidate: Mapping[str, Any],
    experiences: list[dict[str, Any]],
) -> list[str]:
    skills = candidate_context.get("skills") if isinstance(candidate_context.get("skills"), Mapping) else {}
    parts = [
        _clean_text(candidate_context.get("headline")),
        _clean_text(candidate_context.get("summary")),
        *(_clean_string_list(candidate_context.get("spoken_languages"))),
        *(_clean_string_list(candidate_context.get("scoring_keywords"))),
        *(_clean_string_list(skills.get("languages"))),
        *(_clean_string_list(skills.get("frameworks"))),
        *(_clean_string_list(skills.get("tools"))),
        *(_clean_string_list(skills.get("soft"))),
    ]

    education = candidate_context.get("education")
    if isinstance(education, list):
        for item in education:
            if not isinstance(item, Mapping):
                continue
            parts.extend(
                [
                    _clean_text(item.get("degree")),
                    _clean_text(item.get("institution")),
                    _clean_text(item.get("field")),
                ]
            )

    parts.extend(entry["text"] for entry in experiences if entry["text"])

    for field_aliases in _OPTIONAL_SECTION_FIELD_ALIASES.values():
        for alias in field_aliases:
            parts.extend(_flatten_strings(raw_candidate.get(alias)))
            parts.extend(_flatten_strings(candidate_context.get(alias)))
    return [part for part in parts if part]


def _build_candidate_metric_segments(
    candidate_context: Mapping[str, Any],
    raw_candidate: Mapping[str, Any],
    experiences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for experience in experiences:
        segments.extend(experience["metric_bullets"])

    for segment_type, value in (
        ("headline", candidate_context.get("headline")),
        ("summary", candidate_context.get("summary")),
    ):
        text = _clean_text(value)
        metric_tokens = _normalized_metric_tokens(_metric_tokens_for_line(text))
        if not metric_tokens:
            continue
        segments.append(
            {
                "text": text,
                "metric_tokens": metric_tokens,
                "tool_terms": _detect_tool_terms_in_text(text),
                "significant_tokens": _significant_text_tokens(text),
                "experience_position": None,
                "segment_type": segment_type,
            }
        )

    for field_aliases in _OPTIONAL_SECTION_FIELD_ALIASES.values():
        for alias in field_aliases:
            for text in _flatten_strings(raw_candidate.get(alias)):
                metric_tokens = _normalized_metric_tokens(_metric_tokens_for_line(text))
                if not metric_tokens:
                    continue
                segments.append(
                    {
                        "text": text,
                        "metric_tokens": metric_tokens,
                        "tool_terms": _detect_tool_terms_in_text(text),
                        "significant_tokens": _significant_text_tokens(text),
                        "experience_position": None,
                        "segment_type": alias,
                    }
                )
    return segments


def _match_source_experiences(
    source_experiences: list[dict[str, Any]],
    candidate_experiences: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    candidates: list[tuple[int, int, int, dict[str, Any]]] = []
    for source_entry in source_experiences:
        for candidate_entry in candidate_experiences:
            match = _experience_match(source_entry, candidate_entry)
            if not match:
                continue
            candidates.append(
                (
                    -int(match["score"]),
                    int(source_entry["position"]),
                    int(candidate_entry["position"]),
                    match,
                )
            )

    candidates.sort()
    matched_source_positions: set[int] = set()
    matched_candidate_positions: set[int] = set()
    matches: list[dict[str, Any]] = []
    match_lookup: dict[int, int] = {}
    for _, source_position, candidate_position, match in candidates:
        if source_position in matched_source_positions or candidate_position in matched_candidate_positions:
            continue
        matched_source_positions.add(source_position)
        matched_candidate_positions.add(candidate_position)
        matches.append(match)
        match_lookup[source_position] = candidate_position
    matches.sort(key=lambda item: (int(item["source_experience_position"]), int(item["candidate_experience_position"])))
    return matches, match_lookup


def _experience_match(
    source_entry: Mapping[str, Any],
    candidate_entry: Mapping[str, Any],
) -> dict[str, Any] | None:
    role_match = _field_match(source_entry.get("role"), candidate_entry.get("role"))
    organization_match = _field_match(source_entry.get("organization"), candidate_entry.get("organization"))
    date_match = _date_match(
        _clean_text(source_entry.get("date_text")),
        _clean_text(candidate_entry.get("start")),
        _clean_text(candidate_entry.get("end")),
    )
    shared_tool_terms = sorted(
        set(_clean_string_list(source_entry.get("tool_terms"))) & set(_clean_string_list(candidate_entry.get("tool_terms")))
    )
    metric_support = bool(source_entry.get("metric_line_count")) and bool(candidate_entry.get("metric_bullet_count"))

    score = 0
    if organization_match:
        score += 4
    if role_match:
        score += 4
    if date_match:
        score += 2
    if shared_tool_terms:
        score += 1
    if metric_support:
        score += 1

    accept = False
    confidence = "high"
    if organization_match and role_match:
        accept = True
    elif organization_match and date_match and (not source_entry.get("role") or not candidate_entry.get("role") or bool(shared_tool_terms)):
        accept = True
        confidence = "medium"
    elif role_match and date_match and (not source_entry.get("organization") or not candidate_entry.get("organization") or bool(shared_tool_terms)):
        accept = True
        confidence = "medium"
    elif date_match and organization_match and shared_tool_terms and metric_support:
        accept = True
        confidence = "medium"

    if not accept:
        return None

    matched_on = []
    if organization_match:
        matched_on.append("organization")
    if role_match:
        matched_on.append("role")
    if date_match:
        matched_on.append("dates")
    if shared_tool_terms:
        matched_on.append("tool_terms")
    if metric_support:
        matched_on.append("metric_support")

    return {
        "source_experience_position": int(source_entry["position"]),
        "candidate_experience_position": int(candidate_entry["position"]),
        "source_label": _clean_text(source_entry.get("label")),
        "candidate_label": _clean_text(candidate_entry.get("label")),
        "match_confidence": confidence,
        "matched_on": matched_on,
        "shared_tool_terms": shared_tool_terms,
        "source_metric_line_count": _safe_int(source_entry.get("metric_line_count")),
        "candidate_metric_bullet_count": _safe_int(candidate_entry.get("metric_bullet_count")),
        "score": score,
    }


def _detect_missing_optional_sections(
    source_optional_sections: list[dict[str, Any]],
    candidate_optional_sections_present: list[str],
    candidate_optional_section_support: Mapping[str, bool],
) -> list[dict[str, Any]]:
    candidate_present = set(candidate_optional_sections_present)
    missing: list[dict[str, Any]] = []
    for section in source_optional_sections:
        section_key = _clean_text(section.get("section_key")).lower()
        if not section_key or section_key in candidate_present:
            continue
        missing.append(
            {
                "section_key": section_key,
                "heading": _clean_text(section.get("heading")),
                "line_number": _safe_int(section.get("line_number")),
                "reason": "section_missing_from_structured_candidate_data",
                "target_field_supported": bool(candidate_optional_section_support.get(section_key, False)),
            }
        )
    return missing


def _detect_missing_tool_terms(
    source_tool_terms: list[dict[str, Any]],
    candidate_tool_terms_present: list[str],
) -> list[dict[str, Any]]:
    candidate_terms = set(candidate_tool_terms_present)
    missing: list[dict[str, Any]] = []
    for item in source_tool_terms:
        term = _clean_text(item.get("term"))
        if not term or term in candidate_terms:
            continue
        missing.append(
            {
                "term": term,
                "line_numbers": _clean_int_list(item.get("line_numbers")),
                "sections": _clean_string_list(item.get("sections")),
                "experience_positions": _clean_int_list(item.get("experience_positions")),
                "reason": "term_missing_from_structured_candidate_data",
            }
        )
    return missing


def _detect_missing_metric_evidence(
    source_metric_lines: list[dict[str, Any]],
    experience_match_lookup: Mapping[int, int],
    candidate_metric_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for source_line in source_metric_lines:
        expected_experience_position = source_line.get("experience_position")
        matched_candidate_experience = (
            experience_match_lookup.get(int(expected_experience_position))
            if expected_experience_position is not None
            else None
        )

        pool = candidate_metric_segments
        if matched_candidate_experience is not None:
            matched_segments = [
                segment
                for segment in candidate_metric_segments
                if segment.get("experience_position") == matched_candidate_experience
            ]
            if matched_segments:
                pool = matched_segments

        if any(_metric_segment_matches(source_line, segment, matched_candidate_experience) for segment in pool):
            continue
        missing.append(
            {
                "line_number": _safe_int(source_line.get("line_number")),
                "experience_position": (
                    _safe_int(source_line.get("experience_position"))
                    if source_line.get("experience_position") is not None
                    else None
                ),
                "text": _clean_text(source_line.get("text")),
                "matched_tokens": _clean_string_list(source_line.get("matched_tokens")),
                "tool_terms": _clean_string_list(source_line.get("tool_terms")),
                "reason": "metric_evidence_missing_from_structured_candidate_data",
            }
        )
    return missing


def _metric_segment_matches(
    source_line: Mapping[str, Any],
    candidate_segment: Mapping[str, Any],
    matched_candidate_experience: int | None,
) -> bool:
    source_metric_tokens = set(_clean_string_list(source_line.get("matched_tokens")))
    candidate_metric_tokens = set(_clean_string_list(candidate_segment.get("metric_tokens")))
    shared_metric_tokens = source_metric_tokens & candidate_metric_tokens
    if not shared_metric_tokens:
        return False

    source_tool_terms = set(_clean_string_list(source_line.get("tool_terms")))
    candidate_tool_terms = set(_clean_string_list(candidate_segment.get("tool_terms")))
    if source_tool_terms and source_tool_terms & candidate_tool_terms:
        return True

    source_significant_tokens = set(_clean_string_list(source_line.get("significant_tokens")))
    candidate_significant_tokens = set(_clean_string_list(candidate_segment.get("significant_tokens")))
    if len(source_significant_tokens & candidate_significant_tokens) >= 2:
        return True

    if (
        matched_candidate_experience is not None
        and candidate_segment.get("experience_position") == matched_candidate_experience
        and len(shared_metric_tokens) >= 2
    ):
        return True

    if (
        matched_candidate_experience is not None
        and candidate_segment.get("experience_position") == matched_candidate_experience
        and len(source_significant_tokens & candidate_significant_tokens) >= 1
    ):
        return True

    return False


def _build_issues(
    *,
    source_signals: Mapping[str, Any],
    candidate_signals: Mapping[str, Any],
    source_index: Mapping[str, Any],
    missing_optional_sections: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not source_index:
        blockers.append(
            _issue(
                code="missing_source_signal_index",
                severity="blocker",
                message="A source_signal_index payload is required to build the source coverage report.",
            )
        )
    elif not _clean_text(source_index.get("index_version")):
        warnings.append(
            _issue(
                code="source_signal_index_missing_version",
                severity="warning",
                message="The source_signal_index payload has no index_version field.",
            )
        )

    if not _clean_text(candidate_signals.get("structured_text")) and not candidate_signals.get("experiences"):
        blockers.append(
            _issue(
                code="empty_structured_candidate_data",
                severity="blocker",
                message="Structured candidate data is empty, so source coverage cannot be assessed reliably.",
            )
        )

    if not source_signals.get("experience_entries"):
        warnings.append(
            _issue(
                code="source_experience_signals_empty",
                severity="warning",
                message="The source_signal_index contains no experience entries to compare.",
            )
        )

    if not candidate_signals.get("experiences") and source_signals.get("experience_entries"):
        warnings.append(
            _issue(
                code="candidate_experience_entries_empty",
                severity="warning",
                message="The structured candidate data contains no experience entries.",
            )
        )

    unsupported_missing_sections = [
        item["section_key"]
        for item in missing_optional_sections
        if not bool(item.get("target_field_supported"))
    ]
    if unsupported_missing_sections:
        warnings.append(
            _issue(
                code="optional_section_fields_not_modeled",
                severity="warning",
                message="Some source optional sections do not have dedicated structured fields yet.",
                details={"section_keys": unsupported_missing_sections},
            )
        )

    return blockers, warnings


def _overall_status(
    *,
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    missing_source_experiences: list[dict[str, Any]],
    missing_optional_sections: list[dict[str, Any]],
    missing_tool_terms: list[dict[str, Any]],
    missing_metric_evidence: list[dict[str, Any]],
) -> str:
    if blockers:
        return "blocked"
    if warnings or missing_source_experiences or missing_optional_sections or missing_tool_terms or missing_metric_evidence:
        return "review"
    return "covered"


def _missing_experience_record(source_entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_experience_position": _safe_int(source_entry.get("position")),
        "label": _clean_text(source_entry.get("label")),
        "role": _clean_text(source_entry.get("role")),
        "organization": _clean_text(source_entry.get("organization")),
        "date_text": _clean_text(source_entry.get("date_text")),
        "line_start": _safe_int(source_entry.get("line_start")),
        "line_end": _safe_int(source_entry.get("line_end")),
        "metric_line_count": _safe_int(source_entry.get("metric_line_count")),
        "tool_terms": _clean_string_list(source_entry.get("tool_terms")),
        "reason": "no_confident_structured_experience_match",
    }


def _detect_tool_terms_in_text(text: str) -> list[str]:
    cleaned_text = _clean_text(text)
    if not cleaned_text:
        return []
    found: list[str] = []
    for canonical, patterns in _COMPILED_TOOL_PATTERNS:
        if any(pattern.search(cleaned_text) for pattern in patterns):
            found.append(str(canonical))
    return found


def _date_match(source_date_text: str, candidate_start: str, candidate_end: str) -> bool:
    source_years = _extract_years(source_date_text)
    candidate_start_years = _extract_years(candidate_start)
    candidate_end_years = _extract_years(candidate_end)
    source_has_present = _PRESENT_MARKER_PATTERN.search(source_date_text) is not None
    candidate_has_present = _PRESENT_MARKER_PATTERN.search(candidate_end) is not None

    if source_has_present and candidate_has_present:
        return True
    if source_years and candidate_start_years and source_years[0] == candidate_start_years[0]:
        return True
    if len(source_years) >= 2 and candidate_end_years and source_years[-1] == candidate_end_years[-1]:
        return True
    if source_years and candidate_end_years and source_years[-1] == candidate_end_years[-1]:
        return True
    return False


def _extract_years(text: str) -> list[int]:
    return [int(match.group(0)) for match in _YEAR_PATTERN.finditer(text or "")]


def _field_match(left: Any, right: Any) -> bool:
    left_normalized = _normalize_text(_clean_text(left))
    right_normalized = _normalize_text(_clean_text(right))
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True

    left_tokens = _significant_match_tokens(left_normalized)
    right_tokens = _significant_match_tokens(right_normalized)
    if not left_tokens or not right_tokens:
        return False

    shared_tokens = left_tokens & right_tokens
    if not shared_tokens:
        return False

    smaller_size = min(len(left_tokens), len(right_tokens))
    if len(shared_tokens) == smaller_size:
        return True
    return smaller_size >= 2 and (len(shared_tokens) / smaller_size) >= 0.75


def _significant_match_tokens(text: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9+#./]+", text)
        if len(token) >= 3 and token not in _GENERIC_MATCH_TOKENS
    }
    return tokens


def _significant_text_tokens(text: str) -> list[str]:
    return sorted(
        {
            token
            for token in re.findall(r"[a-z0-9+#./]+", _normalize_text(text))
            if len(token) >= 4 and not token.isdigit() and token not in _GENERIC_MATCH_TOKENS
        }
    )


def _normalized_metric_tokens(tokens: Any) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for token in tokens or []:
        cleaned = _normalize_metric_token(token)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _normalize_metric_token(token: Any) -> str:
    value = _clean_text(token).lower().replace(",", "")
    if not value:
        return ""
    value = re.sub(r"\s+", "", value)
    value = value.replace("thousand", "k").replace("million", "m").replace("billion", "b")
    value = value.replace("/month", "permonth").replace("/day", "perday").replace("/week", "perweek")
    return value


def _experience_label(*, role: str, organization: str) -> str:
    if role and organization:
        return f"{role} @ {organization}"
    return role or organization


def _experience_bullets(item: Mapping[str, Any]) -> list[str]:
    for key in _EXPERIENCE_BULLET_KEYS:
        value = item.get(key)
        if isinstance(value, list):
            return [cleaned for bullet in value if (cleaned := _clean_text(bullet))]
    return []


def _first_non_empty(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        cleaned = _clean_text(mapping.get(key))
        if cleaned:
            return cleaned
    return ""


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = _clean_text(value)
        return [cleaned] if cleaned else []
    if isinstance(value, Mapping):
        flattened: list[str] = []
        for item in value.values():
            flattened.extend(_flatten_strings(item))
        return flattened
    if isinstance(value, list):
        flattened = []
        for item in value:
            flattened.extend(_flatten_strings(item))
        return flattened
    return []


def _clean_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [cleaned for item in values if (cleaned := _clean_text(item))]


def _clean_int_list(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    cleaned: list[int] = []
    for item in values:
        try:
            cleaned.append(int(item))
        except (TypeError, ValueError):
            continue
    return cleaned


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _has_content(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_clean_text(value))
    if isinstance(value, Mapping):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    return value not in (None, "")


def _issue(
    *,
    code: str,
    severity: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    item = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    if details:
        item["details"] = dict(details)
    return item
