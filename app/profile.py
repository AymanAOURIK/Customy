from __future__ import annotations

from config import load_candidate


def _copy_list(items: list | None) -> list:
    return [item.copy() if isinstance(item, dict) else item for item in (items or [])]


def build_candidate_context(candidate_yaml_path: str) -> dict:
    """
    Builds the runtime candidate profile.
    candidate.yaml is the only runtime source of truth.
    """

    candidate = load_candidate(candidate_yaml_path)
    personal = candidate.get("personal", {}) or {}
    skills = candidate.get("skills", {}) or {}
    return {
        "personal": {
            "name": str(personal.get("name", "")).strip(),
            "email": str(personal.get("email", "")).strip(),
            "phone": str(personal.get("phone", "")).strip(),
            "location": str(personal.get("location", "")).strip(),
            "linkedin": str(personal.get("linkedin", "")).strip(),
            "github": str(personal.get("github", "")).strip(),
        },
        "headline": str(candidate.get("headline", "")).strip(),
        "summary": str(candidate.get("summary", "")).strip(),
        "skills": {
            "languages": [str(item).strip() for item in skills.get("languages", []) if str(item).strip()],
            "frameworks": [str(item).strip() for item in skills.get("frameworks", []) if str(item).strip()],
            "tools": [str(item).strip() for item in skills.get("tools", []) if str(item).strip()],
            "soft": [str(item).strip() for item in skills.get("soft", []) if str(item).strip()],
        },
        "experiences": _copy_list(candidate.get("experiences", [])),
        "education": _copy_list(candidate.get("education", [])),
        "spoken_languages": [str(item).strip() for item in candidate.get("spoken_languages", []) if str(item).strip()],
        "scoring_keywords": [str(item).strip() for item in candidate.get("scoring_keywords", []) if str(item).strip()],
        "source_resume_text": "",
        "candidate_source": "candidate_yaml",
    }
