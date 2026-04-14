"""Deterministic generation-readiness gate derived from profile quality."""
from __future__ import annotations

from typing import Any, Mapping

from app.candidate_context import build_candidate_context_from_profile_data
from app.profile_enrichment import build_profile_enrichment_plan
from app.profile_quality import build_profile_quality_report

_ALLOWED_STATUSES = {"ready", "review"}
_RECOGNIZED_STATUSES = _ALLOWED_STATUSES | {"blocked"}


def build_saved_profile_quality_report(profile_data: Mapping[str, Any] | None) -> dict[str, object]:
    """Build the quality report from the canonical saved-profile shape."""
    candidate_context = build_candidate_context_from_profile_data(
        profile_data,
        candidate_source="postgres",
    )
    return build_profile_quality_report(candidate_context)


def build_profile_readiness_gate(profile_quality_report: Mapping[str, Any] | None) -> dict[str, object]:
    """Map profile quality status to a generation gate decision."""
    report = profile_quality_report if isinstance(profile_quality_report, Mapping) else {}
    raw_status = str(report.get("overall_status") or "blocked").strip().lower()
    status = raw_status if raw_status in _RECOGNIZED_STATUSES else "blocked"
    return {
        "decision": "allow" if status in _ALLOWED_STATUSES else "blocked",
        "status": status,
        "rule": "profile_quality_report.overall_status",
    }


def build_saved_profile_enrichment_plan(
    profile_data: Mapping[str, Any] | None,
    profile_quality_report: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    """Build the enrichment plan from the canonical saved-profile shape."""
    report = profile_quality_report if isinstance(profile_quality_report, Mapping) else {}
    return build_profile_enrichment_plan(
        report,
        profile_data,
        candidate_source="postgres",
    )


def evaluate_saved_profile_readiness(profile_data: Mapping[str, Any] | None) -> dict[str, dict[str, object]]:
    """Return the gate payload and the underlying quality-derived reports."""
    profile_quality_report = build_saved_profile_quality_report(profile_data)
    return {
        "profile_readiness_gate": build_profile_readiness_gate(profile_quality_report),
        "profile_quality_report": profile_quality_report,
        "profile_enrichment_plan": build_saved_profile_enrichment_plan(
            profile_data,
            profile_quality_report,
        ),
    }
