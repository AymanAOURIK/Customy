"""Deterministic JD gap classification against structured and source-only evidence."""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.candidate_context import build_candidate_context_from_profile_data
from app.source_signal_index import _COMPILED_TOOL_PATTERNS
from app.targeting import KEYWORD_SIGNAL_CATALOG, _DERIVED_SKILL_RULES, normalize_role_title
from app.text_utils import clean_text as _clean_text, term_matches_text as _term_matches_text

JD_GAP_CLASSIFIER_VERSION = "jd_gap_classifier.v1"

_CLASSIFICATION_ORDER = (
    "explicit_match",
    "derived_match",
    "recoverable_from_source",
    "true_gap",
)
_TERM_TYPES = ("role", "keyword_signal", "top_requirement")
_ROLE_TOKEN_EQUIVALENTS = {
    "ai": "ai",
    "ia": "ai",
    "engineer": "engineer",
    "ingénieur": "engineer",
    "lead": "lead",
    "scientist": "scientist",
    "science": "scientist",
    "manager": "manager",
    "architect": "architect",
    "developer": "developer",
    "développeur": "developer",
    "analyst": "analyst",
    "analyste": "analyst",
    "data": "data",
}
_ROLE_FAMILY_TOKENS = {"engineer", "lead", "scientist", "manager", "architect", "developer", "analyst"}
_ROLE_DOMAIN_TOKENS = {"ai", "data"}


def classify_jd_gaps(
    jd_analysis: Mapping[str, Any] | None,
    candidate_context: Mapping[str, Any] | None,
    *,
    source_coverage_report: Mapping[str, Any] | None = None,
    source_signal_index: Mapping[str, Any] | None = None,
    candidate_source: str = "jd_gap_classifier",
) -> dict[str, Any]:
    """Classify JD terms against structured profile evidence and source-only recovery signals."""
    analysis = jd_analysis if isinstance(jd_analysis, Mapping) else {}
    candidate = _coerce_candidate_context(candidate_context, candidate_source=candidate_source)
    structured_context = _build_structured_context(candidate)
    source_context = _build_source_context(source_coverage_report, source_signal_index)

    counts = {key: 0 for key in _CLASSIFICATION_ORDER}
    term_type_counts = {term_type: 0 for term_type in _TERM_TYPES}
    per_term_classifications: list[dict[str, Any]] = []

    for term_record in _collect_jd_terms(analysis):
        term_type = str(term_record["term_type"])
        term = str(term_record["term"])
        if term_type == "role":
            signal_outcomes = [_classify_role_signal(term, structured_context, source_context)]
        elif term_type == "top_requirement":
            signal_outcomes = [
                _classify_keyword_signal(signal, structured_context, source_context)
                for signal in _extract_requirement_signals(term)
            ]
        else:
            signal_outcomes = [_classify_keyword_signal(term, structured_context, source_context)]

        classification = _aggregate_classification(signal_outcomes)
        counts[classification] += 1
        term_type_counts[term_type] += 1
        per_term_classifications.append(
            {
                "term": term,
                "term_type": term_type,
                "classification": classification,
                "signals_evaluated": [outcome["signal"] for outcome in signal_outcomes],
                "signal_outcomes": signal_outcomes,
            }
        )

    return {
        "classifier_version": JD_GAP_CLASSIFIER_VERSION,
        "summary": {
            "total_terms": len(per_term_classifications),
            "counts": counts,
            "term_type_counts": term_type_counts,
            "source_aware": source_context["available"],
        },
        "per_term_classifications": per_term_classifications,
        "recommended_generation_status": _recommended_generation_status(counts),
    }


def _coerce_candidate_context(
    candidate_context: Mapping[str, Any] | None,
    *,
    candidate_source: str,
) -> dict[str, Any]:
    raw_candidate = candidate_context if isinstance(candidate_context, Mapping) else {}
    if isinstance(raw_candidate.get("personal"), Mapping):
        return dict(raw_candidate)
    return build_candidate_context_from_profile_data(
        raw_candidate,
        candidate_source=candidate_source,
    )


def _collect_jd_terms(jd_analysis: Mapping[str, Any]) -> list[dict[str, str]]:
    ordered: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def include(term_type: str, value: Any) -> None:
        cleaned = _clean_text(value)
        key = (term_type, cleaned.lower())
        if not cleaned or key in seen:
            return
        ordered.append({"term_type": term_type, "term": cleaned})
        seen.add(key)

    include("role", jd_analysis.get("role"))
    for item in jd_analysis.get("keyword_signals") or []:
        include("keyword_signal", item)
    for item in jd_analysis.get("top_requirements") or []:
        include("top_requirement", item)
    return ordered


def _build_structured_context(candidate_context: Mapping[str, Any]) -> dict[str, Any]:
    parts: list[str] = []
    roles: list[str] = []

    personal = candidate_context.get("personal") if isinstance(candidate_context.get("personal"), Mapping) else {}
    parts.extend(
        item
        for item in (
            personal.get("name"),
            personal.get("location"),
            candidate_context.get("headline"),
            candidate_context.get("summary"),
        )
        if _clean_text(item)
    )

    headline = _clean_text(candidate_context.get("headline"))
    if headline:
        roles.append(headline)

    for field_name in ("spoken_languages", "scoring_keywords"):
        for item in _string_list(candidate_context.get(field_name)):
            parts.append(item)

    skills = candidate_context.get("skills") if isinstance(candidate_context.get("skills"), Mapping) else {}
    for field_name in ("languages", "frameworks", "tools", "soft"):
        for item in _string_list(skills.get(field_name)):
            parts.append(item)

    education = candidate_context.get("education")
    if isinstance(education, list):
        for item in education:
            if not isinstance(item, Mapping):
                continue
            parts.extend(
                text
                for text in (
                    item.get("degree"),
                    item.get("institution"),
                    item.get("field"),
                )
                if _clean_text(text)
            )

    experiences = candidate_context.get("experiences")
    if isinstance(experiences, list):
        for item in experiences:
            if not isinstance(item, Mapping):
                continue
            role = _first_non_empty(item, ("role", "title", "position"))
            company = _first_non_empty(item, ("company", "organization", "employer"))
            location = _first_non_empty(item, ("location",))
            if role:
                roles.append(role)
            parts.extend(text for text in (role, company, location) if text)
            for bullet in _string_list(item.get("bullets")):
                parts.append(bullet)

    text = "\n".join(parts)
    return {
        "text": text,
        "tool_terms": _detect_tool_terms_in_text(text),
        "role_titles": roles,
        "normalized_role_titles": _normalize_role_titles(roles),
    }


def _build_source_context(
    source_coverage_report: Mapping[str, Any] | None,
    source_signal_index: Mapping[str, Any] | None,
) -> dict[str, Any]:
    report = source_coverage_report if isinstance(source_coverage_report, Mapping) else {}
    index = source_signal_index if isinstance(source_signal_index, Mapping) else {}

    text_parts: list[str] = []
    tool_terms: list[str] = []
    roles: list[str] = []

    for item in _mapping_list(report.get("missing_tool_terms")):
        term = _clean_text(item.get("term"))
        if term:
            tool_terms.append(term)
            text_parts.append(term)

    for item in _mapping_list(report.get("missing_metric_evidence")):
        text = _clean_text(item.get("text"))
        if text:
            text_parts.append(text)
        tool_terms.extend(_string_list(item.get("tool_terms")))

    for item in _mapping_list(report.get("missing_source_experiences")):
        role = _clean_text(item.get("role"))
        label = _clean_text(item.get("label"))
        if role:
            roles.append(role)
            text_parts.append(role)
        if label:
            text_parts.append(label)
        tool_terms.extend(_string_list(item.get("tool_terms")))

    for entry in _mapping_list(index.get("experience_entries")):
        role = _clean_text(entry.get("role"))
        organization = _clean_text(entry.get("organization"))
        if role:
            roles.append(role)
            text_parts.append(role)
        if organization:
            text_parts.append(organization)
        text_parts.append(_clean_text(entry.get("date_text")))
        tool_terms.extend(_string_list(entry.get("tool_system_terms")))

    for item in _mapping_list(index.get("metric_bearing_lines")):
        text = _clean_text(item.get("text"))
        if text:
            text_parts.append(text)

    for item in _mapping_list(index.get("tool_system_terms")):
        term = _clean_text(item.get("term"))
        if term:
            tool_terms.append(term)
            text_parts.append(term)

    for item in _mapping_list(index.get("sections_detected")):
        heading = _clean_text(item.get("heading"))
        if heading:
            text_parts.append(heading)

    text = "\n".join(_unique_in_order(text_parts))
    unique_tool_terms = _unique_in_order(tool_terms + _detect_tool_terms_in_text(text))
    return {
        "available": bool(report or index),
        "text": text,
        "tool_terms": unique_tool_terms,
        "role_titles": _unique_in_order(roles),
        "normalized_role_titles": _normalize_role_titles(roles),
    }


def _classify_keyword_signal(
    signal: str,
    structured_context: Mapping[str, Any],
    source_context: Mapping[str, Any],
) -> dict[str, Any]:
    explicit_evidence = _literal_support_evidence(signal, structured_context)
    if explicit_evidence:
        return _signal_result(
            signal,
            classification="explicit_match",
            structured_evidence=explicit_evidence,
        )

    rule = _derived_rule_for_term(signal)
    derived_evidence = _derived_support_evidence(signal, rule, str(structured_context.get("text") or ""))
    if derived_evidence:
        return _signal_result(
            signal,
            classification="derived_match",
            structured_evidence=derived_evidence,
        )

    source_evidence = []
    if bool(source_context.get("available")):
        source_evidence = _literal_support_evidence(signal, source_context)
        if not source_evidence:
            source_evidence = _derived_support_evidence(signal, rule, str(source_context.get("text") or ""))
    if source_evidence:
        return _signal_result(
            signal,
            classification="recoverable_from_source",
            source_evidence=source_evidence,
        )

    return _signal_result(signal, classification="true_gap")


def _classify_role_signal(
    role: str,
    structured_context: Mapping[str, Any],
    source_context: Mapping[str, Any],
) -> dict[str, Any]:
    explicit_evidence = _role_exact_support(role, _string_list(structured_context.get("role_titles")))
    if explicit_evidence:
        return _signal_result(
            role,
            classification="explicit_match",
            structured_evidence=explicit_evidence,
        )

    derived_evidence = _role_aligned_titles(role, _string_list(structured_context.get("role_titles")))
    if derived_evidence:
        return _signal_result(
            role,
            classification="derived_match",
            structured_evidence=derived_evidence,
        )

    source_evidence = []
    if bool(source_context.get("available")):
        source_evidence = _role_exact_support(role, _string_list(source_context.get("role_titles")))
        if not source_evidence:
            source_evidence = _role_aligned_titles(role, _string_list(source_context.get("role_titles")))
    if source_evidence:
        return _signal_result(
            role,
            classification="recoverable_from_source",
            source_evidence=source_evidence,
        )

    return _signal_result(role, classification="true_gap")


def _extract_requirement_signals(requirement: str) -> list[str]:
    cleaned_requirement = _clean_text(requirement)
    if not cleaned_requirement:
        return []

    signals: list[str] = []
    seen: set[str] = set()

    def include(value: str) -> None:
        cleaned = _clean_text(value)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            return
        signals.append(cleaned)
        seen.add(lowered)

    for keyword in KEYWORD_SIGNAL_CATALOG:
        if _term_matches_text(cleaned_requirement, keyword):
            include(keyword)

    for canonical, patterns in _COMPILED_TOOL_PATTERNS:
        if any(pattern.search(cleaned_requirement) for pattern in patterns):
            include(str(canonical))

    for rule in _DERIVED_SKILL_RULES:
        name = _clean_text(rule.get("name"))
        if _term_matches_text(cleaned_requirement, name):
            include(name)
        for alias in rule.get("jd_terms", ()):
            if _term_matches_text(cleaned_requirement, str(alias)):
                include(str(alias))

    return signals or [cleaned_requirement]


def _literal_support_evidence(term: str, context: Mapping[str, Any]) -> list[str]:
    cleaned_term = _clean_text(term)
    if not cleaned_term:
        return []

    evidence: list[str] = []
    canonical_tool = _canonical_tool_term(cleaned_term)
    if canonical_tool and canonical_tool in _string_list(context.get("tool_terms")):
        evidence.append(canonical_tool)
    if _term_matches_text(str(context.get("text") or ""), cleaned_term):
        evidence.append(cleaned_term)
    return _unique_in_order(evidence)


def _derived_rule_for_term(term: str) -> Mapping[str, Any] | None:
    lowered = _clean_text(term).lower()
    if not lowered:
        return None
    for rule in _DERIVED_SKILL_RULES:
        if lowered == _clean_text(rule.get("name")).lower():
            return rule
        for alias in rule.get("jd_terms", ()):
            if lowered == _clean_text(alias).lower():
                return rule
    return None


def _derived_support_evidence(
    requested_term: str,
    rule: Mapping[str, Any] | None,
    text: str,
) -> list[str]:
    if not rule:
        return []
    cleaned_text = str(text or "")
    if not cleaned_text:
        return []

    requested = _clean_text(requested_term).lower()
    evidence: list[str] = []

    rule_name = _clean_text(rule.get("name"))
    if rule_name and rule_name.lower() != requested and _term_matches_text(cleaned_text, rule_name):
        evidence.append(rule_name)

    for item in rule.get("evidence_any", ()):
        candidate = _clean_text(item)
        if candidate and _term_matches_text(cleaned_text, candidate):
            evidence.append(candidate)

    for group in rule.get("evidence_all", ()):
        cleaned_group = [_clean_text(item) for item in group if _clean_text(item)]
        if cleaned_group and all(_term_matches_text(cleaned_text, item) for item in cleaned_group):
            evidence.extend(cleaned_group)

    for alias in rule.get("jd_terms", ()):
        cleaned_alias = _clean_text(alias)
        if not cleaned_alias or cleaned_alias.lower() == requested:
            continue
        if _term_matches_text(cleaned_text, cleaned_alias):
            evidence.append(cleaned_alias)

    return _unique_in_order(evidence)


def _role_exact_support(role: str, candidate_roles: list[str]) -> list[str]:
    normalized_target = normalize_role_title(role, "en")
    if not normalized_target:
        return []
    matches = [
        candidate_role
        for candidate_role in candidate_roles
        if normalize_role_title(candidate_role, "en") == normalized_target
    ]
    return _unique_in_order(matches)


def _role_aligned_titles(role: str, candidate_roles: list[str]) -> list[str]:
    target_tokens = _role_token_set(role)
    if not target_tokens:
        return []

    aligned: list[str] = []
    for candidate_role in candidate_roles:
        candidate_tokens = _role_token_set(candidate_role)
        if not candidate_tokens or target_tokens <= candidate_tokens:
            continue

        target_domains = target_tokens & _ROLE_DOMAIN_TOKENS
        candidate_domains = candidate_tokens & _ROLE_DOMAIN_TOKENS
        target_family = target_tokens & _ROLE_FAMILY_TOKENS
        candidate_family = candidate_tokens & _ROLE_FAMILY_TOKENS
        if (
            target_domains
            and candidate_domains
            and target_family
            and candidate_family
            and (target_domains & candidate_domains)
            and (target_family & candidate_family)
        ):
            aligned.append(candidate_role)
    return _unique_in_order(aligned)


def _role_token_set(value: object) -> set[str]:
    normalized = normalize_role_title(value, "en")
    tokens: set[str] = set()
    for token in re.findall(r"[A-Za-zÀ-ÿ]+", normalized.lower()):
        canonical = _ROLE_TOKEN_EQUIVALENTS.get(token)
        if canonical:
            tokens.add(canonical)
    return tokens


def _aggregate_classification(signal_outcomes: list[Mapping[str, Any]]) -> str:
    classes = {
        _clean_text(item.get("classification")).lower()
        for item in signal_outcomes
        if _clean_text(item.get("classification"))
    }
    if "true_gap" in classes:
        return "true_gap"
    if "recoverable_from_source" in classes:
        return "recoverable_from_source"
    if "derived_match" in classes:
        return "derived_match"
    return "explicit_match"


def _recommended_generation_status(counts: Mapping[str, Any]) -> str:
    if _safe_int(counts.get("true_gap")) > 0:
        return "generate_with_true_gaps"
    if _safe_int(counts.get("recoverable_from_source")) > 0:
        return "review_before_generation"
    return "ready"


def _signal_result(
    signal: str,
    *,
    classification: str,
    structured_evidence: list[str] | None = None,
    source_evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "signal": _clean_text(signal),
        "classification": classification,
        "structured_evidence": _unique_in_order(structured_evidence or []),
        "source_evidence": _unique_in_order(source_evidence or []),
    }


def _canonical_tool_term(value: str) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    for canonical, patterns in _COMPILED_TOOL_PATTERNS:
        if any(pattern.search(cleaned) for pattern in patterns):
            return str(canonical)
    return None


def _detect_tool_terms_in_text(text: str) -> list[str]:
    cleaned_text = _clean_text(text)
    if not cleaned_text:
        return []
    found: list[str] = []
    for canonical, patterns in _COMPILED_TOOL_PATTERNS:
        if any(pattern.search(cleaned_text) for pattern in patterns):
            found.append(str(canonical))
    return found


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [cleaned for item in value if (cleaned := _clean_text(item))]


def _unique_in_order(items: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _clean_text(item)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        unique.append(cleaned)
        seen.add(lowered)
    return unique


def _normalize_role_titles(roles: list[str]) -> list[str]:
    return _unique_in_order([normalize_role_title(role, "en") for role in roles if _clean_text(role)])


def _first_non_empty(item: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _clean_text(item.get(key))
        if value:
            return value
    return ""


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
