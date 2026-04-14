"""Rule-based evaluator for thin or weak final tailored resumes.

This report is intentionally non-blocking in Phase 2. It looks at the final
normalized resume payload before artifact write and estimates two separate
risks:

- visual thinness: the resume may look sparse on the page
- substance weakness: the resume may lack strong evidence density
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.candidate_context import build_candidate_context_from_profile_data
from app.models import ApplicationPack
from app.schemas import NUMERIC_FACT_PATTERN, ROOT_PAYLOAD_KEYS, TECH_TERM_PATTERN
from app.text_utils import clean_text as _clean_text
from app.text_utils import term_matches_text as _term_matches_text

REPORT_VERSION = "resume_fullness_risk.v1"

_WORD_PATTERN = re.compile(r"\b[\w%+/#.-]+\b", re.UNICODE)
_OPTIONAL_SUPPORTING_SECTION_KEYS = (
    "projects",
    "certifications",
    "awards",
    "publications",
    "volunteering",
)


def build_resume_fullness_risk(
    candidate_context: Mapping[str, Any] | None,
    application_pack: Mapping[str, Any] | ApplicationPack | None,
    *,
    jd_analysis: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic report for the final tailored resume payload."""
    candidate, raw_candidate = _coerce_candidate_input(candidate_context)
    pack = _coerce_pack_input(application_pack)

    experiences = _ordered_pack_experiences(pack.get("tailored_experiences"))
    all_bullets = _collect_pack_bullets(experiences)
    recent_experiences = experiences[:2]
    recent_bullets = _collect_pack_bullets(recent_experiences)

    skill_terms = _hard_skill_terms(candidate, pack)
    technical_skill_count = len(_tailored_skill_terms(pack))
    soft_skill_count = len(_clean_string_list((candidate.get("skills") or {}).get("soft")))
    spoken_language_count = len(_clean_string_list(candidate.get("spoken_languages")))
    education_entry_count = len(_clean_mapping_list(candidate.get("education")))
    supporting_section_count = sum(
        1
        for present in (
            education_entry_count > 0,
            spoken_language_count > 0,
            soft_skill_count > 0,
        )
        if present
    )
    available_optional_section_keys = _available_optional_sections(raw_candidate)

    rendered_work_bullet_count = len(all_bullets)
    recent_role_count = len(recent_experiences)
    recent_role_bullet_count = len(recent_bullets)
    quantified_bullet_count = sum(1 for bullet in all_bullets if _bullet_has_metric(bullet))
    recent_quantified_bullet_count = sum(1 for bullet in recent_bullets if _bullet_has_metric(bullet))
    named_system_tool_bullet_count = sum(
        1 for bullet in all_bullets if _bullet_has_named_system_or_tool(bullet, skill_terms)
    )
    recent_named_system_tool_bullet_count = sum(
        1 for bullet in recent_bullets if _bullet_has_named_system_or_tool(bullet, skill_terms)
    )
    estimated_resume_word_count = _estimated_resume_word_count(candidate, pack, experiences)

    counters = {
        "experience_count": len(experiences),
        "rendered_work_bullet_count": rendered_work_bullet_count,
        "recent_role_count": recent_role_count,
        "recent_role_bullet_count": recent_role_bullet_count,
        "recent_role_bullet_density": _rounded_ratio(recent_role_bullet_count, recent_role_count),
        "quantified_bullet_count": quantified_bullet_count,
        "quantified_bullet_density": _rounded_ratio(quantified_bullet_count, rendered_work_bullet_count),
        "recent_quantified_bullet_count": recent_quantified_bullet_count,
        "named_system_tool_bullet_count": named_system_tool_bullet_count,
        "named_system_tool_bullet_density": _rounded_ratio(
            named_system_tool_bullet_count,
            rendered_work_bullet_count,
        ),
        "recent_named_system_tool_bullet_count": recent_named_system_tool_bullet_count,
        "technical_skill_count": technical_skill_count,
        "soft_skill_count": soft_skill_count,
        "spoken_language_count": spoken_language_count,
        "education_entry_count": education_entry_count,
        "supporting_section_count": supporting_section_count,
        "available_optional_section_count": len(available_optional_section_keys),
        "estimated_resume_word_count": estimated_resume_word_count,
    }
    if isinstance(jd_analysis, Mapping):
        counters["jd_top_requirement_count"] = len(_clean_string_list(jd_analysis.get("top_requirements")))

    visual_fill_score = _visual_fill_score(
        rendered_work_bullet_count=rendered_work_bullet_count,
        recent_role_bullet_count=recent_role_bullet_count,
        estimated_resume_word_count=estimated_resume_word_count,
        technical_skill_count=technical_skill_count,
        supporting_section_count=supporting_section_count,
    )
    substance_score = _substance_score(
        rendered_work_bullet_count=rendered_work_bullet_count,
        recent_role_bullet_count=recent_role_bullet_count,
        quantified_bullet_count=quantified_bullet_count,
        recent_quantified_bullet_count=recent_quantified_bullet_count,
        named_system_tool_bullet_count=named_system_tool_bullet_count,
        recent_named_system_tool_bullet_count=recent_named_system_tool_bullet_count,
        technical_skill_count=technical_skill_count,
    )

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    _apply_visual_fill_rules(
        rendered_work_bullet_count=rendered_work_bullet_count,
        recent_role_count=recent_role_count,
        recent_role_bullet_count=recent_role_bullet_count,
        estimated_resume_word_count=estimated_resume_word_count,
        supporting_section_count=supporting_section_count,
        available_optional_section_keys=available_optional_section_keys,
        blockers=blockers,
        warnings=warnings,
    )
    _apply_substance_rules(
        rendered_work_bullet_count=rendered_work_bullet_count,
        recent_role_bullet_count=recent_role_bullet_count,
        quantified_bullet_count=quantified_bullet_count,
        recent_quantified_bullet_count=recent_quantified_bullet_count,
        named_system_tool_bullet_count=named_system_tool_bullet_count,
        recent_named_system_tool_bullet_count=recent_named_system_tool_bullet_count,
        technical_skill_count=technical_skill_count,
        blockers=blockers,
        warnings=warnings,
    )

    overall_status = "elevated_risk" if blockers else ("review" if warnings else "clear")
    return {
        "report_version": REPORT_VERSION,
        "overall_status": overall_status,
        "visual_fill_score": visual_fill_score,
        "substance_score": substance_score,
        "counters": counters,
        "blockers": blockers,
        "warnings": warnings,
        "recommended_action": _recommended_action(
            blockers=blockers,
            warnings=warnings,
            available_optional_section_keys=available_optional_section_keys,
        ),
    }


def evaluate_resume_fullness_risk(
    candidate_context: Mapping[str, Any] | None,
    application_pack: Mapping[str, Any] | ApplicationPack | None,
    *,
    jd_analysis: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Alias kept for readability at call sites."""
    return build_resume_fullness_risk(candidate_context, application_pack, jd_analysis=jd_analysis)


def _coerce_candidate_input(
    candidate_data: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    raw_candidate = candidate_data if isinstance(candidate_data, Mapping) else {}
    if _looks_like_candidate_context(raw_candidate):
        return dict(raw_candidate), raw_candidate
    return (
        build_candidate_context_from_profile_data(raw_candidate, candidate_source="resume_fullness_risk"),
        raw_candidate,
    )


def _looks_like_candidate_context(candidate_data: Mapping[str, Any]) -> bool:
    return isinstance(candidate_data.get("personal"), Mapping)


def _coerce_pack_input(application_pack: Mapping[str, Any] | ApplicationPack | None) -> dict[str, Any]:
    if isinstance(application_pack, ApplicationPack):
        return application_pack.model_dump()
    current = application_pack if isinstance(application_pack, Mapping) else {}
    while True:
        nested = None
        for key in ROOT_PAYLOAD_KEYS:
            candidate = current.get(key)
            if isinstance(candidate, Mapping):
                nested = candidate
                break
        if nested is None:
            break
        current = nested
    skills = current.get("tailored_skills")
    if not isinstance(skills, Mapping):
        skills = current.get("skills") if isinstance(current.get("skills"), Mapping) else {}
    experiences = current.get("tailored_experiences")
    if not isinstance(experiences, list):
        experiences = current.get("experiences") if isinstance(current.get("experiences"), list) else []
    return {
        "resume_language": _clean_text(current.get("resume_language")),
        "tailored_title": _clean_text(current.get("tailored_title") or current.get("title")),
        "tailored_summary": _clean_text(current.get("tailored_summary") or current.get("summary")),
        "tailored_experiences": experiences,
        "tailored_skills": {
            "languages": _clean_string_list(skills.get("languages")),
            "frameworks": _clean_string_list(skills.get("frameworks")),
            "tools": _clean_string_list(skills.get("tools")),
        },
    }


def _ordered_pack_experiences(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    indexed = [
        (
            index,
            {
                "company": _clean_text((item or {}).get("company")),
                "role": _clean_text((item or {}).get("role")),
                "start": _clean_text((item or {}).get("start")),
                "end": _clean_text((item or {}).get("end")),
                "bullets": _clean_string_list((item or {}).get("bullets")),
            },
        )
        for index, item in enumerate(value)
        if isinstance(item, Mapping)
    ]
    ordered = sorted(
        indexed,
        key=lambda pair: (_experience_sort_key(pair[1]), -pair[0]),
        reverse=True,
    )
    return [item for _, item in ordered if item["company"] or item["role"] or item["bullets"]]


def _experience_sort_key(item: Mapping[str, Any]) -> tuple[int, int]:
    cleaned = _clean_text(item.get("start"))
    match = re.fullmatch(r"(\d{4})-(\d{2})", cleaned)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.fullmatch(r"(\d{4})", cleaned)
    if match:
        return int(match.group(1)), 0
    return 0, 0


def _collect_pack_bullets(experiences: list[dict[str, Any]]) -> list[str]:
    bullets: list[str] = []
    for item in experiences:
        for bullet in item.get("bullets", []):
            cleaned = _clean_text(bullet)
            if cleaned:
                bullets.append(cleaned)
    return bullets


def _tailored_skill_terms(pack: Mapping[str, Any]) -> list[str]:
    skills = pack.get("tailored_skills") if isinstance(pack.get("tailored_skills"), Mapping) else {}
    ordered: list[str] = []
    seen = set()
    for category in ("languages", "frameworks", "tools"):
        for item in skills.get(category, []) or []:
            cleaned = _clean_text(item)
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            ordered.append(cleaned)
            seen.add(key)
    return ordered


def _hard_skill_terms(candidate: Mapping[str, Any], pack: Mapping[str, Any]) -> list[str]:
    skills = candidate.get("skills") if isinstance(candidate.get("skills"), Mapping) else {}
    ordered: list[str] = []
    seen = set()
    for category in ("languages", "frameworks", "tools"):
        for source in (skills.get(category, []), (pack.get("tailored_skills") or {}).get(category, [])):
            for item in source or []:
                cleaned = _clean_text(item)
                key = cleaned.lower()
                if not cleaned or len(cleaned) < 2 or key in seen:
                    continue
                ordered.append(cleaned)
                seen.add(key)
    return ordered


def _estimated_resume_word_count(
    candidate: Mapping[str, Any],
    pack: Mapping[str, Any],
    experiences: list[dict[str, Any]],
) -> int:
    personal = candidate.get("personal") if isinstance(candidate.get("personal"), Mapping) else {}
    skills = pack.get("tailored_skills") if isinstance(pack.get("tailored_skills"), Mapping) else {}
    parts: list[str] = [
        _clean_text(personal.get("name")),
        _clean_text(pack.get("tailored_title")),
        _clean_text(pack.get("tailored_summary")),
        _clean_text(personal.get("location")),
        _clean_text(personal.get("linkedin")),
    ]
    for item in experiences:
        parts.extend(
            [
                _clean_text(item.get("role")),
                _clean_text(item.get("company")),
                _clean_text(item.get("start")),
                _clean_text(item.get("end")),
            ]
        )
        parts.extend(item.get("bullets", []))
    for category in ("languages", "frameworks", "tools"):
        parts.extend(_clean_string_list(skills.get(category)))
    for item in _clean_string_list((candidate.get("skills") or {}).get("soft")):
        parts.append(item)
    for item in _clean_string_list(candidate.get("spoken_languages")):
        parts.append(item)
    for item in _clean_mapping_list(candidate.get("education")):
        parts.extend(
            [
                _clean_text(item.get("degree")),
                _clean_text(item.get("institution")),
                _clean_text(item.get("details")),
                _clean_text(item.get("start_year")),
                _clean_text(item.get("end_year")),
                _clean_text(item.get("year")),
            ]
        )
    text = "\n".join(part for part in parts if part)
    return len(_WORD_PATTERN.findall(text))


def _bullet_has_metric(text: str) -> bool:
    return bool(NUMERIC_FACT_PATTERN.search(_clean_text(text)))


def _bullet_has_named_system_or_tool(text: str, hard_skill_terms: list[str]) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return False
    if TECH_TERM_PATTERN.search(cleaned):
        return True
    return any(_term_matches_text(cleaned, term) for term in hard_skill_terms)


def _visual_fill_score(
    *,
    rendered_work_bullet_count: int,
    recent_role_bullet_count: int,
    estimated_resume_word_count: int,
    technical_skill_count: int,
    supporting_section_count: int,
) -> int:
    score = 0.0
    score += 30.0 * _progress(rendered_work_bullet_count, 10)
    score += 20.0 * _progress(recent_role_bullet_count, 6)
    score += 25.0 * _progress(estimated_resume_word_count, 320)
    score += 10.0 * _progress(technical_skill_count, 8)
    score += 15.0 * _progress(supporting_section_count, 2)
    return int(round(min(score, 100.0)))


def _substance_score(
    *,
    rendered_work_bullet_count: int,
    recent_role_bullet_count: int,
    quantified_bullet_count: int,
    recent_quantified_bullet_count: int,
    named_system_tool_bullet_count: int,
    recent_named_system_tool_bullet_count: int,
    technical_skill_count: int,
) -> int:
    score = 0.0
    score += 15.0 * _progress(rendered_work_bullet_count, 10)
    score += 15.0 * _progress(recent_role_bullet_count, 6)
    score += 20.0 * _progress(quantified_bullet_count, 4)
    score += 15.0 * _progress(recent_quantified_bullet_count, 2)
    score += 20.0 * _progress(named_system_tool_bullet_count, 4)
    score += 10.0 * _progress(recent_named_system_tool_bullet_count, 2)
    score += 5.0 * _progress(technical_skill_count, 8)
    return int(round(min(score, 100.0)))


def _apply_visual_fill_rules(
    *,
    rendered_work_bullet_count: int,
    recent_role_count: int,
    recent_role_bullet_count: int,
    estimated_resume_word_count: int,
    supporting_section_count: int,
    available_optional_section_keys: list[str],
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    if rendered_work_bullet_count < 6:
        blockers.append(
            _issue(
                code="very_low_work_bullet_count",
                severity="blocker",
                dimension="visual_fill",
                message="The final resume has too few work bullets to reliably fill a one-page layout.",
                details={"rendered_work_bullet_count": rendered_work_bullet_count, "minimum_required": 6},
            )
        )
    elif rendered_work_bullet_count < 9:
        warnings.append(
            _issue(
                code="low_work_bullet_count",
                severity="warning",
                dimension="visual_fill",
                message="The final resume has a light work-bullet count for a strong one-page layout.",
                details={"rendered_work_bullet_count": rendered_work_bullet_count, "recommended_minimum": 9},
            )
        )

    if recent_role_count > 0 and recent_role_bullet_count < 4:
        blockers.append(
            _issue(
                code="recent_roles_visually_thin",
                severity="blocker",
                dimension="visual_fill",
                message="The most recent roles do not provide enough bullet content for the top half of the resume.",
                details={"recent_role_bullet_count": recent_role_bullet_count, "minimum_required": 4},
            )
        )
    elif recent_role_count > 0 and recent_role_bullet_count < 6:
        warnings.append(
            _issue(
                code="recent_roles_need_more_depth",
                severity="warning",
                dimension="visual_fill",
                message="The most recent roles look thin for a strong one-page resume.",
                details={"recent_role_bullet_count": recent_role_bullet_count, "recommended_minimum": 6},
            )
        )

    if estimated_resume_word_count < 120:
        blockers.append(
            _issue(
                code="very_low_estimated_word_count",
                severity="blocker",
                dimension="visual_fill",
                message="The estimated resume word count is very low for a full one-page resume.",
                details={"estimated_resume_word_count": estimated_resume_word_count, "minimum_required": 120},
            )
        )
    elif estimated_resume_word_count < 170:
        warnings.append(
            _issue(
                code="low_estimated_word_count",
                severity="warning",
                dimension="visual_fill",
                message="The estimated resume word count is light for a full one-page resume.",
                details={"estimated_resume_word_count": estimated_resume_word_count, "recommended_minimum": 170},
            )
        )

    if supporting_section_count == 0:
        warnings.append(
            _issue(
                code="no_supporting_sections",
                severity="warning",
                dimension="visual_fill",
                message="The resume has no supporting sections beyond core work history and technical skills.",
            )
        )
    elif supporting_section_count < 2 and rendered_work_bullet_count < 10:
        warnings.append(
            _issue(
                code="limited_supporting_sections",
                severity="warning",
                dimension="visual_fill",
                message="Supporting sections are limited, so the resume depends heavily on work bullets to look full.",
                details={"supporting_section_count": supporting_section_count},
            )
        )

    if available_optional_section_keys and estimated_resume_word_count < 300:
        warnings.append(
            _issue(
                code="unused_optional_supporting_sections_available",
                severity="warning",
                dimension="visual_fill",
                message="Additional supporting sections exist in candidate data and could help if the resume looks thin.",
                details={"available_optional_sections": available_optional_section_keys},
            )
        )


def _apply_substance_rules(
    *,
    rendered_work_bullet_count: int,
    recent_role_bullet_count: int,
    quantified_bullet_count: int,
    recent_quantified_bullet_count: int,
    named_system_tool_bullet_count: int,
    recent_named_system_tool_bullet_count: int,
    technical_skill_count: int,
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    if rendered_work_bullet_count > 0 and quantified_bullet_count == 0:
        blockers.append(
            _issue(
                code="no_quantified_proof",
                severity="blocker",
                dimension="substance",
                message="The final resume contains no quantified bullet-level evidence.",
            )
        )
    elif rendered_work_bullet_count >= 6 and quantified_bullet_count < 3:
        warnings.append(
            _issue(
                code="low_quantified_proof_density",
                severity="warning",
                dimension="substance",
                message="The final resume has limited quantified proof for its bullet count.",
                details={
                    "quantified_bullet_count": quantified_bullet_count,
                    "recommended_minimum": 3,
                },
            )
        )

    if recent_role_bullet_count >= 4 and recent_quantified_bullet_count == 0:
        blockers.append(
            _issue(
                code="no_recent_quantified_proof",
                severity="blocker",
                dimension="substance",
                message="The most recent roles do not contain quantified proof.",
            )
        )
    elif recent_role_bullet_count >= 4 and recent_quantified_bullet_count < 2:
        warnings.append(
            _issue(
                code="low_recent_quantified_proof",
                severity="warning",
                dimension="substance",
                message="The most recent roles contain limited quantified proof.",
                details={"recent_quantified_bullet_count": recent_quantified_bullet_count},
            )
        )

    if technical_skill_count >= 4 and rendered_work_bullet_count > 0 and named_system_tool_bullet_count == 0:
        blockers.append(
            _issue(
                code="no_named_system_tool_proof",
                severity="blocker",
                dimension="substance",
                message="The final resume does not name specific systems, tools, or platforms in work bullets.",
            )
        )
    elif technical_skill_count >= 4 and rendered_work_bullet_count >= 6 and named_system_tool_bullet_count < 3:
        warnings.append(
            _issue(
                code="low_named_system_tool_density",
                severity="warning",
                dimension="substance",
                message="The final resume names too few systems, tools, or platforms for its bullet count.",
                details={
                    "named_system_tool_bullet_count": named_system_tool_bullet_count,
                    "recommended_minimum": 3,
                },
            )
        )

    if technical_skill_count >= 4 and recent_role_bullet_count >= 4 and recent_named_system_tool_bullet_count == 0:
        blockers.append(
            _issue(
                code="no_recent_named_system_tool_proof",
                severity="blocker",
                dimension="substance",
                message="The most recent roles do not name specific systems, tools, or platforms.",
            )
        )
    elif technical_skill_count >= 4 and recent_role_bullet_count >= 4 and recent_named_system_tool_bullet_count < 2:
        warnings.append(
            _issue(
                code="low_recent_named_system_tool_proof",
                severity="warning",
                dimension="substance",
                message="The most recent roles contain limited named systems or tools.",
                details={"recent_named_system_tool_bullet_count": recent_named_system_tool_bullet_count},
            )
        )

    if technical_skill_count < 4:
        warnings.append(
            _issue(
                code="thin_skills_section",
                severity="warning",
                dimension="substance",
                message="The tailored skills section is thin for a one-page tailored resume.",
                details={"technical_skill_count": technical_skill_count, "recommended_minimum": 4},
            )
        )


def _recommended_action(
    *,
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    available_optional_section_keys: list[str],
) -> dict[str, str]:
    prioritized = _prioritized_issues(blockers or warnings)
    if not prioritized:
        return {
            "code": "none",
            "message": "No immediate fullness action is recommended.",
        }

    lead_code = _clean_text(prioritized[0].get("code")).lower()
    action_map = {
        "very_low_work_bullet_count": (
            "expand_work_bullet_coverage",
            "Recover one or two more high-value bullets, especially from the most recent roles.",
        ),
        "recent_roles_visually_thin": (
            "expand_recent_role_depth",
            "Add more bullet depth to the most recent roles before enabling any future gate.",
        ),
        "very_low_estimated_word_count": (
            "increase_resume_content_density",
            "Increase bullet and section content so the one-page resume does not look sparse.",
        ),
        "no_quantified_proof": (
            "surface_quantified_proof",
            "Prioritize bullet variants that keep concrete metrics or measurable outcomes.",
        ),
        "no_recent_quantified_proof": (
            "surface_recent_quantified_proof",
            "Recover at least one quantified bullet from the most recent roles.",
        ),
        "no_named_system_tool_proof": (
            "surface_named_systems_and_tools",
            "Name specific systems, tools, or platforms inside work bullets, not only in the skills section.",
        ),
        "no_recent_named_system_tool_proof": (
            "surface_recent_named_systems_and_tools",
            "Recover named systems or platform proof in the most recent roles.",
        ),
        "thin_skills_section": (
            "broaden_prioritized_skills",
            "Surface a few more relevant hard skills in the tailored skills section.",
        ),
    }
    code, message = action_map.get(
        lead_code,
        ("review_resume_fullness", "Review the final resume content before enabling any future quality gate."),
    )
    if lead_code in {
        "very_low_work_bullet_count",
        "recent_roles_visually_thin",
        "very_low_estimated_word_count",
    } and available_optional_section_keys:
        message += f" Optional supporting sections already exist in candidate data: {', '.join(available_optional_section_keys)}."
    return {"code": code, "message": message}


def _available_optional_sections(raw_candidate: Mapping[str, Any]) -> list[str]:
    sections: list[str] = []
    for key in _OPTIONAL_SUPPORTING_SECTION_KEYS:
        value = raw_candidate.get(key)
        if _has_content(value):
            sections.append(key)
    return sections


def _has_content(value: object) -> bool:
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    if isinstance(value, Mapping):
        return any(_has_content(item) for item in value.values())
    return bool(_clean_text(value))


def _clean_mapping_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _clean_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen = set()
    for item in value:
        text = _clean_text(item)
        key = text.lower()
        if not text or key in seen:
            continue
        cleaned.append(text)
        seen.add(key)
    return cleaned


def _progress(value: int, target: int) -> float:
    if target <= 0:
        return 1.0
    return min(max(float(value), 0.0) / float(target), 1.0)


def _rounded_ratio(value: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(float(value) / float(total), 2)


def _issue(
    *,
    code: str,
    severity: str,
    dimension: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "dimension": dimension,
        "message": message,
    }
    if details:
        payload["details"] = dict(details)
    return payload


def _prioritized_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority_map = {
        "no_quantified_proof": 0,
        "no_recent_quantified_proof": 1,
        "no_named_system_tool_proof": 2,
        "no_recent_named_system_tool_proof": 3,
        "very_low_work_bullet_count": 4,
        "recent_roles_visually_thin": 5,
        "very_low_estimated_word_count": 6,
        "thin_skills_section": 7,
    }
    return sorted(
        issues,
        key=lambda item: (
            priority_map.get(_clean_text(item.get("code")).lower(), 100),
            _clean_text(item.get("dimension")).lower(),
            _clean_text(item.get("code")).lower(),
        ),
    )
