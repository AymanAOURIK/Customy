"""Rule-based planner for turning profile quality gaps into enrichment targets."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.candidate_context import build_candidate_context_from_profile_data
from app.profile_quality import (
    _bullet_has_metric,
    _bullet_has_named_system_or_tool,
    _collect_bullets,
    _hard_skill_terms,
    _ordered_experiences,
    _recent_substantive_experiences,
)
from app.schemas import EMAIL_PATTERN, NUMERIC_FACT_PATTERN, TECH_TERM_PATTERN
from app.text_utils import clean_text as _clean_text

PLAN_VERSION = "profile_enrichment_plan.v2"

_RECOGNIZED_STATUSES = {"blocked", "review", "ready"}
_CLASSIFICATION_COUNTS = {
    "auto_derive": 0,
    "recover_from_source_with_confirmation": 0,
    "ask_user": 0,
}
_PRIORITY_LABELS = (
    (90, "critical"),
    (75, "high"),
    (60, "medium"),
)


def build_profile_enrichment_plan(
    profile_quality_report: Mapping[str, Any] | None,
    profile_data: Mapping[str, Any] | None = None,
    *,
    source_coverage_report: Mapping[str, Any] | None = None,
    candidate_source: str = "profile_enrichment",
) -> dict[str, object]:
    """Map quality-report issues to deterministic enrichment targets."""
    report = profile_quality_report if isinstance(profile_quality_report, Mapping) else {}
    source_report = source_coverage_report if isinstance(source_coverage_report, Mapping) else {}
    candidate_context = build_candidate_context_from_profile_data(
        profile_data,
        candidate_source=candidate_source,
    )
    issues = _issue_index(report)
    signals = _build_plan_signals(candidate_context, report, source_report)

    targets: list[dict[str, Any]] = []
    _append_if_present(targets, _build_full_name_target(issues))
    _append_if_present(targets, _build_experience_foundation_target(issues, signals))
    _append_if_present(targets, _build_recent_role_depth_target(issues, signals))
    _append_if_present(targets, _build_recent_metric_target(issues, signals))
    _append_if_present(targets, _build_recent_named_system_target(issues, signals))
    _append_if_present(targets, _build_scoring_keywords_target(issues, signals))
    _append_if_present(targets, _build_hard_skill_inventory_target(issues, signals))
    _append_if_present(targets, _build_summary_target(issues, signals))
    _append_if_present(targets, _build_headline_target(issues, signals))
    _append_if_present(targets, _build_email_target(issues, signals))
    _append_if_present(targets, _build_education_target(issues, signals))
    _append_if_present(targets, _build_spoken_languages_target(issues))

    targets.sort(key=lambda item: (-int(item["priority"]), str(item["target_key"])))
    for index, target in enumerate(targets, start=1):
        target["priority_rank"] = index

    classification_counts = dict(_CLASSIFICATION_COUNTS)
    covered_issue_codes: set[str] = set()
    for target in targets:
        classification_counts[str(target["classification"])] += 1
        covered_issue_codes.update(str(code) for code in target.get("issue_codes") or [])

    overall_status = _clean_text(report.get("overall_status")).lower()
    if overall_status not in _RECOGNIZED_STATUSES:
        overall_status = "blocked"

    return {
        "plan_version": PLAN_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_report_version": _clean_text(report.get("report_version")),
        "quality_report_version": _clean_text(report.get("report_version")),
        "source_coverage_report_version": signals["source_coverage_report_version"],
        "source_index_version": signals["source_index_version"],
        "source_awareness": {
            "enabled": signals["source_coverage_available"],
            "overall_status": signals["source_coverage_status"],
            "gap_counts": dict(signals["source_gap_counts"]),
        },
        "overall_status": overall_status,
        "summary": {
            "total_targets": len(targets),
            "classification_counts": classification_counts,
            "issue_codes_covered": sorted(covered_issue_codes),
            "unmapped_issue_codes": sorted(code for code in issues if code not in covered_issue_codes),
        },
        "targets": targets,
    }


def _build_plan_signals(
    candidate_context: Mapping[str, Any],
    report: Mapping[str, Any],
    source_coverage_report: Mapping[str, Any],
) -> dict[str, Any]:
    experiences = _ordered_experiences(candidate_context.get("experiences"))
    recent_experiences = _recent_substantive_experiences(experiences, limit=2)
    all_bullets = _collect_bullets(experiences)
    recent_bullets = _collect_bullets(recent_experiences)
    hard_skill_terms = _hard_skill_terms(candidate_context)
    source_resume_text = _clean_text(candidate_context.get("source_resume_text"))
    source_report = source_coverage_report if isinstance(source_coverage_report, Mapping) else {}
    source_experience_matches = _mapping_records(source_report.get("experience_matches"))
    missing_source_experiences = _mapping_records(source_report.get("missing_source_experiences"))
    missing_optional_sections = _mapping_records(source_report.get("missing_optional_sections"))
    missing_tool_terms = _mapping_records(source_report.get("missing_tool_terms"))
    missing_metric_evidence = _mapping_records(source_report.get("missing_metric_evidence"))
    recent_source_positions = _recent_source_positions(
        source_report,
        source_experience_matches=source_experience_matches,
        missing_source_experiences=missing_source_experiences,
        missing_tool_terms=missing_tool_terms,
        missing_metric_evidence=missing_metric_evidence,
    )
    recent_source_position_set = set(recent_source_positions)
    missing_recent_source_experiences = [
        item
        for item in missing_source_experiences
        if _source_position(item.get("source_experience_position")) in recent_source_position_set
    ]
    missing_recent_metric_evidence = [
        item
        for item in missing_metric_evidence
        if _source_position(item.get("experience_position")) in recent_source_position_set
    ]
    missing_recent_tool_terms = [
        item
        for item in missing_tool_terms
        if recent_source_position_set & set(_source_position_list(item.get("experience_positions")))
    ]
    missing_recent_metric_from_unmatched_roles = [
        item
        for item in missing_recent_source_experiences
        if _safe_int(item.get("metric_line_count")) > 0
    ]
    missing_recent_tool_from_unmatched_roles = [
        item
        for item in missing_recent_source_experiences
        if _clean_string_count(item.get("tool_terms")) > 0
    ]
    missing_recent_metric_evidence_count = (
        len(missing_recent_metric_evidence)
        + len(missing_recent_metric_from_unmatched_roles)
    )
    missing_recent_tool_evidence_count = (
        len(missing_recent_tool_terms)
        + len(missing_recent_tool_from_unmatched_roles)
        + sum(1 for item in missing_recent_metric_evidence if _clean_string_count(item.get("tool_terms")) > 0)
    )
    source_gap_counts = {
        "missing_source_experiences": _source_count(
            source_report,
            "missing_source_experience_entries",
            fallback=len(missing_source_experiences),
        ),
        "missing_optional_sections": _source_count(
            source_report,
            "missing_optional_sections",
            fallback=len(missing_optional_sections),
        ),
        "missing_tool_terms": _source_count(
            source_report,
            "missing_tool_terms",
            fallback=len(missing_tool_terms),
        ),
        "missing_metric_evidence": _source_count(
            source_report,
            "missing_metric_lines",
            fallback=len(missing_metric_evidence),
        ),
    }
    has_recent_metric_source_gap = missing_recent_metric_evidence_count > 0
    has_recent_tool_source_gap = missing_recent_tool_evidence_count > 0
    has_recent_role_source_gap = bool(
        missing_recent_source_experiences
        or has_recent_metric_source_gap
        or has_recent_tool_source_gap
    )

    return {
        "experience_count": len(experiences),
        "recent_role_labels": [_experience_label(item) for item in recent_experiences if _experience_label(item)],
        "total_bullets": _int_counter(report, "total_bullets", fallback=len(all_bullets)),
        "recent_two_roles_bullet_count": len(recent_bullets),
        "metric_bearing_bullets": _int_counter(
            report,
            "metric_bearing_bullets",
            fallback=sum(1 for bullet in all_bullets if _bullet_has_metric(bullet)),
        ),
        "recent_metric_bearing_bullets": sum(1 for bullet in recent_bullets if _bullet_has_metric(bullet)),
        "named_system_or_tool_bullets": _int_counter(
            report,
            "named_system_or_tool_bullets",
            fallback=sum(
                1
                for bullet in all_bullets
                if _bullet_has_named_system_or_tool(bullet, hard_skill_terms)
            ),
        ),
        "recent_named_system_or_tool_bullets": sum(
            1
            for bullet in recent_bullets
            if _bullet_has_named_system_or_tool(bullet, hard_skill_terms)
        ),
        "scoring_keyword_count": _int_counter(
            report,
            "scoring_keyword_count",
            fallback=_unique_clean_count(candidate_context.get("scoring_keywords")),
        ),
        "hard_skill_count": len(hard_skill_terms),
        "has_source_resume_text": bool(source_resume_text),
        "has_source_metrics": bool(NUMERIC_FACT_PATTERN.search(source_resume_text)),
        "has_source_tech_terms": bool(TECH_TERM_PATTERN.search(source_resume_text)),
        "has_source_email": bool(EMAIL_PATTERN.search(source_resume_text)),
        "has_positioning_signal": bool(experiences or hard_skill_terms or source_resume_text),
        "has_structured_keyword_signal": bool(
            hard_skill_terms
            or candidate_context.get("scoring_keywords")
            or sum(
                1
                for bullet in all_bullets
                if _bullet_has_named_system_or_tool(bullet, hard_skill_terms)
            )
        ),
        "source_coverage_available": bool(source_report),
        "source_coverage_report_version": _clean_text(source_report.get("report_version")),
        "source_index_version": _clean_text(source_report.get("source_index_version")),
        "source_coverage_status": _clean_text(source_report.get("overall_status")).lower(),
        "source_gap_counts": source_gap_counts,
        "recent_source_positions": recent_source_positions,
        "missing_recent_source_experience_count": len(missing_recent_source_experiences),
        "missing_recent_metric_evidence_count": missing_recent_metric_evidence_count,
        "missing_recent_tool_evidence_count": missing_recent_tool_evidence_count,
        "has_experience_source_recovery_signal": bool(
            _source_count(source_report, "source_experience_entries", fallback=0) > 0
        ),
        "has_recent_role_source_gap": has_recent_role_source_gap,
        "has_recent_metric_source_gap": has_recent_metric_source_gap,
        "has_recent_tool_source_gap": has_recent_tool_source_gap,
        "has_keyword_source_gap": source_gap_counts["missing_tool_terms"] > 0,
        "has_positioning_source_gap": bool(
            source_gap_counts["missing_source_experiences"] > 0
            or source_gap_counts["missing_tool_terms"] > 0
            or source_gap_counts["missing_metric_evidence"] > 0
        ),
    }


def _build_full_name_target(issues: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    matched = _matched_issue_codes(issues, "missing_full_name")
    if not matched:
        return None
    return _target(
        issues=issues,
        target_key="full_name",
        base_priority=96,
        matched_issue_codes=matched,
        classification="ask_user",
        fields=("personal.name",),
        title="Add the candidate's full name",
        action_key="collect_full_name_from_user",
        instruction="Ask the user for the exact full name that should appear across the profile and generated materials.",
        context={},
    )


def _build_experience_foundation_target(
    issues: dict[str, dict[str, Any]],
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    matched = _matched_issue_codes(issues, "missing_experience_entries", "no_experience_bullets")
    if not matched:
        return None

    if signals["source_coverage_available"]:
        has_recovery_signal = signals["has_experience_source_recovery_signal"]
    else:
        has_recovery_signal = signals["has_source_resume_text"]

    if has_recovery_signal:
        classification = "recover_from_source_with_confirmation"
        action_key = "recover_experience_history_from_source"
        instruction = (
            "Recover missing experience entries and bullets from the source resume text, "
            "then ask the user to confirm the reconstructed role history before saving it."
        )
    else:
        classification = "ask_user"
        action_key = "collect_experience_history_from_user"
        instruction = (
            "Ask the user to provide role titles, companies, dates, and bullet-level achievements "
            "for the missing experience history."
        )

    return _target(
        issues=issues,
        target_key="experience_foundation",
        base_priority=95,
        matched_issue_codes=matched,
        classification=classification,
        fields=("experiences",),
        title="Restore structured experience entries",
        action_key=action_key,
        instruction=instruction,
        context={
            "experience_count": signals["experience_count"],
            "total_bullets": signals["total_bullets"],
            "source_aware": signals["source_coverage_available"],
            "missing_source_experience_count": signals["source_gap_counts"]["missing_source_experiences"],
        },
    )


def _build_recent_role_depth_target(
    issues: dict[str, dict[str, Any]],
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    matched = _matched_issue_codes(
        issues,
        "recent_roles_too_thin",
        "recent_roles_need_more_depth",
        "low_total_bullet_count",
    )
    if not matched:
        return None

    if signals["source_coverage_available"]:
        has_recovery_signal = signals["has_recent_role_source_gap"]
    else:
        has_recovery_signal = signals["has_source_resume_text"]

    if has_recovery_signal:
        classification = "recover_from_source_with_confirmation"
        action_key = "recover_recent_role_depth_from_source"
        instruction = (
            "Re-scan the source resume for omitted bullets in the two most recent substantive roles, "
            "then ask the user to confirm the recovered bullet-level proof."
        )
    else:
        classification = "ask_user"
        action_key = "collect_recent_role_depth_from_user"
        instruction = (
            "Ask the user to add 1 to 3 more bullets for each recent role, focused on distinct projects, "
            "scope, and outcomes."
        )

    return _target(
        issues=issues,
        target_key="recent_role_depth",
        base_priority=90,
        matched_issue_codes=matched,
        classification=classification,
        fields=("experiences",),
        title="Deepen the two most recent roles",
        action_key=action_key,
        instruction=instruction,
        context={
            "recent_role_labels": signals["recent_role_labels"],
            "recent_two_roles_bullet_count": signals["recent_two_roles_bullet_count"],
            "minimum_required": 4,
            "recommended_minimum": 7,
            "source_aware": signals["source_coverage_available"],
            "missing_recent_source_experience_count": signals["missing_recent_source_experience_count"],
            "missing_recent_metric_evidence_count": signals["missing_recent_metric_evidence_count"],
            "missing_recent_tool_evidence_count": signals["missing_recent_tool_evidence_count"],
        },
    )


def _build_recent_metric_target(
    issues: dict[str, dict[str, Any]],
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    matched = _matched_issue_codes(
        issues,
        "no_recent_metric_proof",
        "low_recent_metric_proof",
        "low_metric_coverage",
    )
    if not matched:
        return None

    if signals["source_coverage_available"]:
        has_recovery_signal = signals["has_recent_metric_source_gap"]
    else:
        has_recovery_signal = signals["has_source_metrics"]

    if has_recovery_signal:
        classification = "recover_from_source_with_confirmation"
        action_key = "recover_recent_role_metrics_from_source"
        instruction = (
            "Look for metric-bearing facts in the source resume that can be tied to recent roles, "
            "then ask the user to confirm the exact numbers before promoting them into bullets."
        )
    else:
        classification = "ask_user"
        action_key = "collect_recent_role_metrics_from_user"
        instruction = (
            "Ask the user for concrete scale, throughput, savings, latency, team-size, or percentage-change "
            "metrics for the two most recent substantive roles."
        )

    return _target(
        issues=issues,
        target_key="recent_quantified_proof",
        base_priority=88,
        matched_issue_codes=matched,
        classification=classification,
        fields=("experiences",),
        title="Add quantified proof to recent roles",
        action_key=action_key,
        instruction=instruction,
        context={
            "recent_role_labels": signals["recent_role_labels"],
            "recent_metric_bearing_bullets": signals["recent_metric_bearing_bullets"],
            "metric_bearing_bullets": signals["metric_bearing_bullets"],
            "recommended_recent_minimum": 2,
            "source_aware": signals["source_coverage_available"],
            "missing_metric_evidence_count": signals["source_gap_counts"]["missing_metric_evidence"],
        },
    )


def _build_recent_named_system_target(
    issues: dict[str, dict[str, Any]],
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    matched = _matched_issue_codes(
        issues,
        "no_recent_named_system_proof",
        "low_recent_named_system_proof",
        "low_named_system_coverage",
    )
    if not matched:
        return None

    if signals["source_coverage_available"]:
        has_recovery_signal = signals["has_recent_tool_source_gap"]
    else:
        has_recovery_signal = signals["has_source_tech_terms"] or signals["hard_skill_count"] > 0

    if has_recovery_signal:
        classification = "recover_from_source_with_confirmation"
        action_key = "recover_recent_role_tools_from_profile_and_source"
        instruction = (
            "Recover likely systems, tools, and platforms from the source resume or existing hard-skill inventory, "
            "then ask the user to confirm which ones belong in each recent role."
        )
    else:
        classification = "ask_user"
        action_key = "collect_recent_role_tools_from_user"
        instruction = (
            "Ask the user which systems, tools, frameworks, platforms, or data stores were used in the "
            "two most recent substantive roles."
        )

    return _target(
        issues=issues,
        target_key="recent_named_system_proof",
        base_priority=86,
        matched_issue_codes=matched,
        classification=classification,
        fields=("experiences",),
        title="Restore named systems and tools in recent roles",
        action_key=action_key,
        instruction=instruction,
        context={
            "recent_role_labels": signals["recent_role_labels"],
            "recent_named_system_or_tool_bullets": signals["recent_named_system_or_tool_bullets"],
            "named_system_or_tool_bullets": signals["named_system_or_tool_bullets"],
            "recommended_recent_minimum": 2,
            "source_aware": signals["source_coverage_available"],
            "missing_recent_tool_evidence_count": signals["missing_recent_tool_evidence_count"],
        },
    )


def _build_scoring_keywords_target(
    issues: dict[str, dict[str, Any]],
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    matched = _matched_issue_codes(
        issues,
        "empty_keyword_inventory",
        "missing_scoring_keywords",
        "thin_scoring_keywords",
    )
    if not matched:
        return None

    if signals["source_coverage_available"]:
        if signals["has_keyword_source_gap"]:
            classification = "recover_from_source_with_confirmation"
            action_key = "recover_scoring_keywords_from_source"
            instruction = (
                "Recover source terms that are missing from the structured profile, "
                "then ask the user to confirm which ones should become scoring keywords."
            )
        elif signals["has_structured_keyword_signal"]:
            classification = "auto_derive"
            action_key = "derive_scoring_keywords_from_profile_signals"
            instruction = (
                "Derive a grounded scoring keyword list from the structured skill inventory, recent role titles, "
                "and technical evidence already present in the profile."
            )
        else:
            classification = "ask_user"
            action_key = "collect_scoring_keywords_from_user"
            instruction = (
                "Ask the user for 5 to 10 keywords that best describe their expertise and target positions."
            )
    elif signals["has_structured_keyword_signal"]:
        classification = "auto_derive"
        action_key = "derive_scoring_keywords_from_profile_signals"
        instruction = (
            "Derive a grounded scoring keyword list from the structured skill inventory, recent role titles, "
            "and technical evidence already present in the profile."
        )
    elif signals["has_source_tech_terms"]:
        classification = "recover_from_source_with_confirmation"
        action_key = "recover_scoring_keywords_from_source"
        instruction = (
            "Scan the source resume for technical terms missing from the structured profile, "
            "then ask the user to confirm the recovered scoring keywords."
        )
    else:
        classification = "ask_user"
        action_key = "collect_scoring_keywords_from_user"
        instruction = (
            "Ask the user for 5 to 10 keywords that best describe their expertise and target positions."
        )

    return _target(
        issues=issues,
        target_key="scoring_keywords",
        base_priority=80,
        matched_issue_codes=matched,
        classification=classification,
        fields=("scoring_keywords",),
        title="Build a stronger scoring keyword inventory",
        action_key=action_key,
        instruction=instruction,
        context={
            "scoring_keyword_count": signals["scoring_keyword_count"],
            "hard_skill_count": signals["hard_skill_count"],
            "recommended_minimum": 8,
            "source_aware": signals["source_coverage_available"],
            "missing_tool_term_count": signals["source_gap_counts"]["missing_tool_terms"],
        },
    )


def _build_hard_skill_inventory_target(
    issues: dict[str, dict[str, Any]],
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    matched = _matched_issue_codes(issues, "thin_hard_skill_inventory")
    if not matched:
        return None

    if signals["source_coverage_available"]:
        if signals["has_keyword_source_gap"]:
            classification = "recover_from_source_with_confirmation"
            action_key = "recover_hard_skill_inventory_from_source"
            instruction = (
                "Recover hard-skill signals that are missing from the structured profile, "
                "then ask the user to confirm which tools and frameworks belong in the inventory."
            )
        elif signals["has_structured_keyword_signal"]:
            classification = "auto_derive"
            action_key = "derive_hard_skill_inventory_from_profile_signals"
            instruction = (
                "Derive a fuller hard-skill inventory from named tools, technologies, and repeated technical signals "
                "already present in the structured profile."
            )
        else:
            classification = "ask_user"
            action_key = "collect_hard_skill_inventory_from_user"
            instruction = (
                "Ask the user to list the main languages, frameworks, platforms, and tools they want reflected in the profile."
            )
    elif signals["has_structured_keyword_signal"]:
        classification = "auto_derive"
        action_key = "derive_hard_skill_inventory_from_profile_signals"
        instruction = (
            "Derive a fuller hard-skill inventory from named tools, technologies, and repeated technical signals "
            "already present in the structured profile."
        )
    elif signals["has_source_tech_terms"]:
        classification = "recover_from_source_with_confirmation"
        action_key = "recover_hard_skill_inventory_from_source"
        instruction = (
            "Recover missing hard skills from the source resume and ask the user to confirm the tools and frameworks "
            "that should become part of the structured inventory."
        )
    else:
        classification = "ask_user"
        action_key = "collect_hard_skill_inventory_from_user"
        instruction = (
            "Ask the user to list the main languages, frameworks, platforms, and tools they want reflected in the profile."
        )

    return _target(
        issues=issues,
        target_key="hard_skill_inventory",
        base_priority=76,
        matched_issue_codes=matched,
        classification=classification,
        fields=("skills.languages", "skills.frameworks", "skills.tools"),
        title="Strengthen the hard-skill inventory",
        action_key=action_key,
        instruction=instruction,
        context={
            "hard_skill_count": signals["hard_skill_count"],
            "recommended_minimum": 8,
            "source_aware": signals["source_coverage_available"],
            "missing_tool_term_count": signals["source_gap_counts"]["missing_tool_terms"],
        },
    )


def _build_summary_target(
    issues: dict[str, dict[str, Any]],
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    matched = _matched_issue_codes(issues, "missing_summary")
    if not matched:
        return None

    if signals["source_coverage_available"] and signals["has_positioning_source_gap"]:
        classification = "recover_from_source_with_confirmation"
        action_key = "recover_summary_inputs_from_source"
        instruction = (
            "Recover missing role, metric, and tool signals from source coverage gaps, "
            "ask the user to confirm them, then derive the summary from the grounded profile."
        )
    elif signals["has_positioning_signal"]:
        classification = "auto_derive"
        action_key = "derive_summary_from_profile_signals"
        instruction = (
            "Compose a 2 to 3 sentence summary from recent role scope, strongest skill cluster, "
            "and proven outcomes already present in the profile."
        )
    else:
        classification = "ask_user"
        action_key = "collect_summary_inputs_from_user"
        instruction = (
            "Ask the user for a short positioning statement covering their current level, core domain, "
            "and strongest business outcomes."
        )

    return _target(
        issues=issues,
        target_key="summary",
        base_priority=72,
        matched_issue_codes=matched,
        classification=classification,
        fields=("summary",),
        title="Create a profile summary",
        action_key=action_key,
        instruction=instruction,
        context={
            "recent_role_labels": signals["recent_role_labels"],
            "hard_skill_count": signals["hard_skill_count"],
            "source_aware": signals["source_coverage_available"],
            "source_positioning_gap_count": (
                signals["source_gap_counts"]["missing_source_experiences"]
                + signals["source_gap_counts"]["missing_tool_terms"]
                + signals["source_gap_counts"]["missing_metric_evidence"]
            ),
        },
    )


def _build_headline_target(
    issues: dict[str, dict[str, Any]],
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    matched = _matched_issue_codes(issues, "missing_headline")
    if not matched:
        return None

    if signals["source_coverage_available"] and signals["has_positioning_source_gap"]:
        classification = "recover_from_source_with_confirmation"
        action_key = "recover_headline_inputs_from_source"
        instruction = (
            "Recover missing role, metric, and tool signals from source coverage gaps, "
            "ask the user to confirm them, then derive the headline from the grounded profile."
        )
    elif signals["has_positioning_signal"]:
        classification = "auto_derive"
        action_key = "derive_headline_from_profile_signals"
        instruction = (
            "Derive a concise headline from the strongest recent role, seniority signal, "
            "and core skill cluster already present in the profile."
        )
    else:
        classification = "ask_user"
        action_key = "collect_headline_inputs_from_user"
        instruction = (
            "Ask the user for the role label and focus area they want used as the headline."
        )

    return _target(
        issues=issues,
        target_key="headline",
        base_priority=70,
        matched_issue_codes=matched,
        classification=classification,
        fields=("headline",),
        title="Create a profile headline",
        action_key=action_key,
        instruction=instruction,
        context={
            "recent_role_labels": signals["recent_role_labels"],
            "hard_skill_count": signals["hard_skill_count"],
            "source_aware": signals["source_coverage_available"],
            "source_positioning_gap_count": (
                signals["source_gap_counts"]["missing_source_experiences"]
                + signals["source_gap_counts"]["missing_tool_terms"]
                + signals["source_gap_counts"]["missing_metric_evidence"]
            ),
        },
    )


def _build_email_target(
    issues: dict[str, dict[str, Any]],
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    matched = _matched_issue_codes(issues, "missing_email")
    if not matched:
        return None

    if signals["has_source_email"]:
        classification = "recover_from_source_with_confirmation"
        action_key = "recover_email_from_source"
        instruction = (
            "Recover the email address from the source resume text, then ask the user to confirm it before saving."
        )
    else:
        classification = "ask_user"
        action_key = "collect_email_from_user"
        instruction = "Ask the user for the preferred email address to use in the profile."

    return _target(
        issues=issues,
        target_key="email",
        base_priority=60,
        matched_issue_codes=matched,
        classification=classification,
        fields=("personal.email",),
        title="Add a contact email",
        action_key=action_key,
        instruction=instruction,
        context={"source_email_detected": signals["has_source_email"]},
    )


def _build_education_target(
    issues: dict[str, dict[str, Any]],
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    matched = _matched_issue_codes(issues, "missing_education")
    if not matched:
        return None

    if signals["has_source_resume_text"]:
        classification = "recover_from_source_with_confirmation"
        action_key = "recover_education_from_source"
        instruction = (
            "Recover the education section from the source resume text, then ask the user to confirm the degree, "
            "institution, and year before saving."
        )
    else:
        classification = "ask_user"
        action_key = "collect_education_from_user"
        instruction = "Ask the user for degree, institution, and graduation year details."

    return _target(
        issues=issues,
        target_key="education",
        base_priority=55,
        matched_issue_codes=matched,
        classification=classification,
        fields=("education",),
        title="Restore education details",
        action_key=action_key,
        instruction=instruction,
        context={},
    )


def _build_spoken_languages_target(issues: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    matched = _matched_issue_codes(issues, "missing_spoken_languages")
    if not matched:
        return None
    return _target(
        issues=issues,
        target_key="spoken_languages",
        base_priority=54,
        matched_issue_codes=matched,
        classification="ask_user",
        fields=("spoken_languages",),
        title="Add spoken languages",
        action_key="collect_spoken_languages_from_user",
        instruction="Ask the user which languages they speak and the proficiency level for each one.",
        context={},
    )


def _target(
    *,
    issues: dict[str, dict[str, Any]],
    target_key: str,
    base_priority: int,
    matched_issue_codes: list[str],
    classification: str,
    fields: tuple[str, ...],
    title: str,
    action_key: str,
    instruction: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    priority = min(base_priority + _blocker_bonus(issues, matched_issue_codes), 100)
    return {
        "target_key": target_key,
        "priority": priority,
        "priority_label": _priority_label(priority),
        "classification": classification,
        "fields": list(fields),
        "issue_codes": matched_issue_codes,
        "title": title,
        "action_key": action_key,
        "instruction": instruction,
        "context": context,
    }


def _append_if_present(targets: list[dict[str, Any]], target: dict[str, Any] | None) -> None:
    if target is not None:
        targets.append(target)


def _issue_index(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for bucket in ("blockers", "warnings"):
        for issue in report.get(bucket) or []:
            if not isinstance(issue, Mapping):
                continue
            code = _clean_text(issue.get("code"))
            if not code:
                continue
            indexed[code] = dict(issue)
    return indexed


def _matched_issue_codes(issues: dict[str, dict[str, Any]], *codes: str) -> list[str]:
    return [code for code in codes if code in issues]


def _blocker_bonus(issues: dict[str, dict[str, Any]], matched_issue_codes: list[str]) -> int:
    for code in matched_issue_codes:
        severity = _clean_text(issues.get(code, {}).get("severity")).lower()
        if severity == "blocker":
            return 5
    return 0


def _priority_label(priority: int) -> str:
    for minimum, label in _PRIORITY_LABELS:
        if priority >= minimum:
            return label
    return "low"


def _int_counter(report: Mapping[str, Any], key: str, *, fallback: int) -> int:
    counters = report.get("counters") if isinstance(report.get("counters"), Mapping) else {}
    value = counters.get(key, fallback)
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return max(int(fallback), 0)


def _unique_clean_count(value: object) -> int:
    if not isinstance(value, list):
        return 0
    seen = set()
    count = 0
    for item in value:
        cleaned = _clean_text(item)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        count += 1
    return count


def _mapping_records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _source_count(source_report: Mapping[str, Any], key: str, *, fallback: int) -> int:
    counts = source_report.get("counts") if isinstance(source_report.get("counts"), Mapping) else {}
    value = counts.get(key, fallback)
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return max(int(fallback), 0)


def _recent_source_positions(
    source_report: Mapping[str, Any],
    *,
    source_experience_matches: list[dict[str, Any]],
    missing_source_experiences: list[dict[str, Any]],
    missing_tool_terms: list[dict[str, Any]],
    missing_metric_evidence: list[dict[str, Any]],
) -> list[int]:
    positions: set[int] = set()
    for item in source_experience_matches:
        position = _source_position(item.get("source_experience_position"))
        if position is not None:
            positions.add(position)
    for item in missing_source_experiences:
        position = _source_position(item.get("source_experience_position"))
        if position is not None:
            positions.add(position)
    for item in missing_metric_evidence:
        position = _source_position(item.get("experience_position"))
        if position is not None:
            positions.add(position)
    for item in missing_tool_terms:
        positions.update(_source_position_list(item.get("experience_positions")))
    if positions:
        return sorted(positions)[:2]
    source_experience_entries = _source_count(source_report, "source_experience_entries", fallback=0)
    return list(range(min(source_experience_entries, 2)))


def _source_position(value: object) -> int | None:
    try:
        position = int(value)
    except (TypeError, ValueError):
        return None
    if position < 0:
        return None
    return position


def _source_position_list(value: object) -> list[int]:
    if isinstance(value, list):
        positions = [_source_position(item) for item in value]
        return [item for item in positions if item is not None]
    return []


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_string_count(value: object) -> int:
    if not isinstance(value, list):
        return 0
    return sum(1 for item in value if _clean_text(item))


def _experience_label(item: Mapping[str, Any]) -> str:
    role = _clean_text(item.get("role"))
    company = _clean_text(item.get("company"))
    if role and company:
        return f"{role} @ {company}"
    return role or company
