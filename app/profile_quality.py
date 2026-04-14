"""Rule-based profile quality evaluator for Phase 2 readiness reporting.

Takes a canonical candidate_context dict and returns a structured
profile_quality_report without changing generation or onboarding behavior.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

from app.schemas import NUMERIC_FACT_PATTERN, TECH_TERM_PATTERN
from app.text_utils import clean_text as _clean_text
from app.text_utils import term_matches_text as _term_matches_text

REPORT_VERSION = "profile_quality_report.v1"

_NON_SUBSTANTIVE_ROLE_PATTERN = re.compile(
    r"\b("
    r"graduation project|intern|internship|trainee|apprentice|"
    r"stage|stagiaire|student|alternance|apprentissage"
    r")\b",
    re.IGNORECASE,
)

_STRUCTURE_WEIGHTS = {
    "full_name": 20,
    "email": 10,
    "headline": 15,
    "summary": 15,
    "experiences": 20,
    "education": 10,
    "spoken_languages": 10,
}

_KEYWORD_TARGETS = {
    "hard_skills": 12,
    "scoring_keywords": 20,
}

_EVIDENCE_TARGETS = {
    "total_bullets": 16,
    "recent_two_role_bullets": 8,
    "recent_two_role_metric_bullets": 3,
    "recent_two_role_named_system_bullets": 3,
}


def build_profile_quality_report(candidate_context: dict) -> dict:
    """Return a rule-based quality report for a canonical candidate profile."""
    candidate = candidate_context if isinstance(candidate_context, dict) else {}
    personal = candidate.get("personal") if isinstance(candidate.get("personal"), dict) else {}
    experiences = _ordered_experiences(candidate.get("experiences"))
    all_bullets = _collect_bullets(experiences)
    substantive_recent = _recent_substantive_experiences(experiences, limit=2)
    recent_bullets = _collect_bullets(substantive_recent)
    hard_skill_terms = _hard_skill_terms(candidate)

    total_bullets = len(all_bullets)
    recent_two_roles_bullet_count = len(recent_bullets)
    metric_bearing_bullets = sum(1 for bullet in all_bullets if _bullet_has_metric(bullet))
    named_system_or_tool_bullets = sum(
        1 for bullet in all_bullets if _bullet_has_named_system_or_tool(bullet, hard_skill_terms)
    )
    recent_metric_bearing_bullets = sum(1 for bullet in recent_bullets if _bullet_has_metric(bullet))
    recent_named_system_or_tool_bullets = sum(
        1 for bullet in recent_bullets if _bullet_has_named_system_or_tool(bullet, hard_skill_terms)
    )
    scoring_keyword_count = _unique_count(candidate.get("scoring_keywords"))
    hard_skill_count = len(hard_skill_terms)

    counters = {
        "total_bullets": total_bullets,
        "recent_two_roles_bullet_count": recent_two_roles_bullet_count,
        "metric_bearing_bullets": metric_bearing_bullets,
        "named_system_or_tool_bullets": named_system_or_tool_bullets,
        "scoring_keyword_count": scoring_keyword_count,
    }

    blockers: list[dict] = []
    warnings: list[dict] = []

    _apply_structure_rules(
        candidate=candidate,
        personal=personal,
        experiences=experiences,
        total_bullets=total_bullets,
        blockers=blockers,
        warnings=warnings,
    )
    _apply_evidence_rules(
        total_bullets=total_bullets,
        recent_two_roles_bullet_count=recent_two_roles_bullet_count,
        metric_bearing_bullets=metric_bearing_bullets,
        named_system_or_tool_bullets=named_system_or_tool_bullets,
        recent_metric_bearing_bullets=recent_metric_bearing_bullets,
        recent_named_system_or_tool_bullets=recent_named_system_or_tool_bullets,
        blockers=blockers,
        warnings=warnings,
    )
    _apply_keyword_rules(
        hard_skill_count=hard_skill_count,
        scoring_keyword_count=scoring_keyword_count,
        blockers=blockers,
        warnings=warnings,
    )

    dimensions = {
        "structure": _structure_score(candidate, personal, experiences, total_bullets),
        "evidence_density": _evidence_density_score(
            total_bullets=total_bullets,
            recent_two_roles_bullet_count=recent_two_roles_bullet_count,
            recent_metric_bearing_bullets=recent_metric_bearing_bullets,
            recent_named_system_or_tool_bullets=recent_named_system_or_tool_bullets,
        ),
        "keyword_richness": _keyword_richness_score(
            hard_skill_count=hard_skill_count,
            scoring_keyword_count=scoring_keyword_count,
        ),
    }

    overall_status = "blocked" if blockers else ("review" if warnings else "ready")
    return {
        "report_version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "dimensions": dimensions,
        "counters": counters,
        "blockers": blockers,
        "warnings": warnings,
    }


def evaluate_profile_quality(candidate_context: dict) -> dict:
    """Alias kept for readability at call sites."""
    return build_profile_quality_report(candidate_context)


def _apply_structure_rules(
    *,
    candidate: dict,
    personal: dict,
    experiences: list[dict],
    total_bullets: int,
    blockers: list[dict],
    warnings: list[dict],
) -> None:
    if not _clean_text(personal.get("name")):
        blockers.append(
            _issue(
                code="missing_full_name",
                severity="blocker",
                dimension="structure",
                message="The profile is missing the candidate's full name.",
            )
        )
    if not experiences:
        blockers.append(
            _issue(
                code="missing_experience_entries",
                severity="blocker",
                dimension="structure",
                message="The profile has no experience entries.",
            )
        )
    if total_bullets == 0:
        blockers.append(
            _issue(
                code="no_experience_bullets",
                severity="blocker",
                dimension="structure",
                message="The profile has no usable experience bullets.",
            )
        )
    if not _clean_text(personal.get("email")):
        warnings.append(
            _issue(
                code="missing_email",
                severity="warning",
                dimension="structure",
                message="The profile is missing an email address.",
            )
        )
    if not _clean_text(candidate.get("headline")):
        warnings.append(
            _issue(
                code="missing_headline",
                severity="warning",
                dimension="structure",
                message="The profile is missing a headline.",
            )
        )
    if not _clean_text(candidate.get("summary")):
        warnings.append(
            _issue(
                code="missing_summary",
                severity="warning",
                dimension="structure",
                message="The profile is missing a summary.",
            )
        )
    if not isinstance(candidate.get("education"), list) or not candidate.get("education"):
        warnings.append(
            _issue(
                code="missing_education",
                severity="warning",
                dimension="structure",
                message="The profile has no education entries.",
            )
        )
    if not isinstance(candidate.get("spoken_languages"), list) or not candidate.get("spoken_languages"):
        warnings.append(
            _issue(
                code="missing_spoken_languages",
                severity="warning",
                dimension="structure",
                message="The profile has no spoken languages listed.",
            )
        )


def _apply_evidence_rules(
    *,
    total_bullets: int,
    recent_two_roles_bullet_count: int,
    metric_bearing_bullets: int,
    named_system_or_tool_bullets: int,
    recent_metric_bearing_bullets: int,
    recent_named_system_or_tool_bullets: int,
    blockers: list[dict],
    warnings: list[dict],
) -> None:
    if recent_two_roles_bullet_count < 4:
        blockers.append(
            _issue(
                code="recent_roles_too_thin",
                severity="blocker",
                dimension="evidence_density",
                message="The two most recent substantive roles do not contain enough bullet-level proof.",
                details={
                    "recent_two_roles_bullet_count": recent_two_roles_bullet_count,
                    "minimum_required": 4,
                },
            )
        )
    elif recent_two_roles_bullet_count < 7:
        warnings.append(
            _issue(
                code="recent_roles_need_more_depth",
                severity="warning",
                dimension="evidence_density",
                message="The two most recent substantive roles look thin for a strong tailored resume.",
                details={
                    "recent_two_roles_bullet_count": recent_two_roles_bullet_count,
                    "recommended_minimum": 7,
                },
            )
        )
    if recent_metric_bearing_bullets == 0:
        blockers.append(
            _issue(
                code="no_recent_metric_proof",
                severity="blocker",
                dimension="evidence_density",
                message="The two most recent substantive roles have no metric-bearing bullets.",
            )
        )
    elif recent_metric_bearing_bullets < 2:
        warnings.append(
            _issue(
                code="low_recent_metric_proof",
                severity="warning",
                dimension="evidence_density",
                message="The two most recent substantive roles have limited quantified proof.",
                details={"recent_metric_bearing_bullets": recent_metric_bearing_bullets},
            )
        )
    if recent_named_system_or_tool_bullets == 0:
        blockers.append(
            _issue(
                code="no_recent_named_system_proof",
                severity="blocker",
                dimension="evidence_density",
                message="The two most recent substantive roles do not name specific systems, tools, or platforms.",
            )
        )
    elif recent_named_system_or_tool_bullets < 2:
        warnings.append(
            _issue(
                code="low_recent_named_system_proof",
                severity="warning",
                dimension="evidence_density",
                message="The two most recent substantive roles contain limited named systems or tools.",
                details={"recent_named_system_or_tool_bullets": recent_named_system_or_tool_bullets},
            )
        )
    if total_bullets < 12:
        warnings.append(
            _issue(
                code="low_total_bullet_count",
                severity="warning",
                dimension="evidence_density",
                message="The total bullet count is low for a strong one-page resume.",
                details={"total_bullets": total_bullets, "recommended_minimum": 12},
            )
        )
    if metric_bearing_bullets < 3:
        warnings.append(
            _issue(
                code="low_metric_coverage",
                severity="warning",
                dimension="evidence_density",
                message="The profile contains limited metric-bearing bullets overall.",
                details={"metric_bearing_bullets": metric_bearing_bullets},
            )
        )
    if named_system_or_tool_bullets < 3:
        warnings.append(
            _issue(
                code="low_named_system_coverage",
                severity="warning",
                dimension="evidence_density",
                message="The profile contains limited named system or tool proof overall.",
                details={"named_system_or_tool_bullets": named_system_or_tool_bullets},
            )
        )


def _apply_keyword_rules(
    *,
    hard_skill_count: int,
    scoring_keyword_count: int,
    blockers: list[dict],
    warnings: list[dict],
) -> None:
    if hard_skill_count == 0 and scoring_keyword_count == 0:
        blockers.append(
            _issue(
                code="empty_keyword_inventory",
                severity="blocker",
                dimension="keyword_richness",
                message="The profile has no hard-skill inventory and no scoring keywords.",
            )
        )
    if scoring_keyword_count == 0:
        warnings.append(
            _issue(
                code="missing_scoring_keywords",
                severity="warning",
                dimension="keyword_richness",
                message="The profile has no scoring keywords.",
            )
        )
    elif scoring_keyword_count < 8:
        warnings.append(
            _issue(
                code="thin_scoring_keywords",
                severity="warning",
                dimension="keyword_richness",
                message="The scoring keyword inventory is thin.",
                details={"scoring_keyword_count": scoring_keyword_count, "recommended_minimum": 8},
            )
        )
    if hard_skill_count < 8:
        warnings.append(
            _issue(
                code="thin_hard_skill_inventory",
                severity="warning",
                dimension="keyword_richness",
                message="The hard-skill inventory is thin.",
                details={"hard_skill_count": hard_skill_count, "recommended_minimum": 8},
            )
        )


def _structure_score(candidate: dict, personal: dict, experiences: list[dict], total_bullets: int) -> int:
    score = 0
    if _clean_text(personal.get("name")):
        score += _STRUCTURE_WEIGHTS["full_name"]
    if _clean_text(personal.get("email")):
        score += _STRUCTURE_WEIGHTS["email"]
    if _clean_text(candidate.get("headline")):
        score += _STRUCTURE_WEIGHTS["headline"]
    if _clean_text(candidate.get("summary")):
        score += _STRUCTURE_WEIGHTS["summary"]
    if experiences and total_bullets > 0:
        score += _STRUCTURE_WEIGHTS["experiences"]
    if isinstance(candidate.get("education"), list) and candidate.get("education"):
        score += _STRUCTURE_WEIGHTS["education"]
    if isinstance(candidate.get("spoken_languages"), list) and candidate.get("spoken_languages"):
        score += _STRUCTURE_WEIGHTS["spoken_languages"]
    return min(score, 100)


def _evidence_density_score(
    *,
    total_bullets: int,
    recent_two_roles_bullet_count: int,
    recent_metric_bearing_bullets: int,
    recent_named_system_or_tool_bullets: int,
) -> int:
    score = 0.0
    score += 10.0 * _progress(total_bullets, _EVIDENCE_TARGETS["total_bullets"])
    score += 40.0 * _progress(recent_two_roles_bullet_count, _EVIDENCE_TARGETS["recent_two_role_bullets"])
    score += 30.0 * _progress(
        recent_metric_bearing_bullets,
        _EVIDENCE_TARGETS["recent_two_role_metric_bullets"],
    )
    score += 20.0 * _progress(
        recent_named_system_or_tool_bullets,
        _EVIDENCE_TARGETS["recent_two_role_named_system_bullets"],
    )
    return int(round(min(score, 100.0)))


def _keyword_richness_score(*, hard_skill_count: int, scoring_keyword_count: int) -> int:
    score = 0.0
    score += 30.0 * _progress(hard_skill_count, _KEYWORD_TARGETS["hard_skills"])
    score += 70.0 * _progress(scoring_keyword_count, _KEYWORD_TARGETS["scoring_keywords"])
    return int(round(min(score, 100.0)))


def _ordered_experiences(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    indexed = [(index, item) for index, item in enumerate(value) if isinstance(item, dict)]
    return [
        item
        for _, item in sorted(
            indexed,
            key=lambda pair: (_experience_sort_key(pair[1]), -pair[0]),
            reverse=True,
        )
    ]


def _experience_sort_key(item: dict) -> tuple[int, int]:
    cleaned = _clean_text(item.get("start"))
    match = re.fullmatch(r"(\d{4})-(\d{2})", cleaned)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.fullmatch(r"(\d{4})", cleaned)
    if match:
        return int(match.group(1)), 0
    return 0, 0


def _recent_substantive_experiences(experiences: list[dict], *, limit: int) -> list[dict]:
    substantive = [item for item in experiences if _is_substantive_experience(item)]
    if substantive:
        return substantive[:limit]
    return experiences[:limit]


def _is_substantive_experience(item: dict) -> bool:
    role = _clean_text(item.get("role"))
    company = _clean_text(item.get("company"))
    label = f"{role} {company}".strip()
    return bool(label) and _NON_SUBSTANTIVE_ROLE_PATTERN.search(label) is None


def _collect_bullets(experiences: list[dict]) -> list[str]:
    bullets: list[str] = []
    for item in experiences:
        raw_bullets = item.get("bullets")
        if not isinstance(raw_bullets, list):
            continue
        for bullet in raw_bullets:
            cleaned = _clean_text(bullet)
            if cleaned:
                bullets.append(cleaned)
    return bullets


def _bullet_has_metric(text: str) -> bool:
    return bool(NUMERIC_FACT_PATTERN.search(_clean_text(text)))


def _bullet_has_named_system_or_tool(text: str, hard_skill_terms: list[str]) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return False
    if TECH_TERM_PATTERN.search(cleaned):
        return True
    return any(_term_matches_text(cleaned, term) for term in hard_skill_terms)


def _hard_skill_terms(candidate: dict) -> list[str]:
    skills = candidate.get("skills") if isinstance(candidate.get("skills"), dict) else {}
    ordered: list[str] = []
    seen = set()
    for category in ("languages", "frameworks", "tools"):
        for item in skills.get(category, []) or []:
            cleaned = _clean_text(item)
            key = cleaned.lower()
            if not cleaned or len(cleaned) < 2 or key in seen:
                continue
            ordered.append(cleaned)
            seen.add(key)
    return ordered


def _unique_count(value: object) -> int:
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


def _progress(value: int, target: int) -> float:
    if target <= 0:
        return 1.0
    return min(max(float(value), 0.0) / float(target), 1.0)


def _issue(
    *,
    code: str,
    severity: str,
    dimension: str,
    message: str,
    details: dict | None = None,
) -> dict:
    issue = {
        "code": code,
        "severity": severity,
        "dimension": dimension,
        "message": message,
    }
    if details:
        issue["details"] = details
    return issue
