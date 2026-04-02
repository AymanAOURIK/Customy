from __future__ import annotations

from dataclasses import dataclass


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        text = _clean_text(item)
        if text:
            cleaned.append(text)
    return cleaned


@dataclass
class TailoredExperience:
    company: str
    role: str
    start: str
    end: str
    bullets: list[str]

    @classmethod
    def model_validate(cls, data: dict) -> "TailoredExperience":
        if not isinstance(data, dict):
            raise ValueError("Experience item must be an object.")
        company = _clean_text(data.get("company"))
        role = _clean_text(data.get("role"))
        start = _clean_text(data.get("start"))
        end = _clean_text(data.get("end"))
        bullets = _clean_list(data.get("bullets"))
        if not company or not role:
            raise ValueError("Each tailored experience requires company and role.")
        if not bullets:
            raise ValueError(f"Tailored experience for {company} requires at least one bullet.")
        return cls(company=company, role=role, start=start, end=end, bullets=bullets)

    def model_dump(self) -> dict:
        return {
            "company": self.company,
            "role": self.role,
            "start": self.start,
            "end": self.end,
            "bullets": list(self.bullets),
        }


@dataclass
class ApplicationPack:
    resume_language: str
    tailored_title: str
    tailored_summary: str
    tailored_experiences: list[TailoredExperience]
    tailored_skills: dict
    cover_letter: str | None
    linkedin_message: str | None
    email_draft: str | None
    focus_areas: list[str]
    detected_emails: list[str]
    profile_update_hints: list[str]

    @classmethod
    def model_validate(cls, data: dict) -> "ApplicationPack":
        if not isinstance(data, dict):
            raise ValueError("Model response must be a JSON object.")
        resume_language = _clean_text(data.get("resume_language")).lower() or "en"
        title = _clean_text(data.get("tailored_title"))
        summary = _clean_text(data.get("tailored_summary"))
        experiences_raw = data.get("tailored_experiences")
        skills_raw = data.get("tailored_skills")
        if resume_language not in {"en", "fr"}:
            resume_language = "en"
        if not title:
            raise ValueError("Model returned an empty tailored_title.")
        if not summary:
            raise ValueError(
                "Model returned an empty tailored_summary. "
                "Check that your candidate.yaml has a non-empty 'summary' field — "
                "it is used as a fallback when the model does not generate one."
            )
        if not isinstance(experiences_raw, list) or not experiences_raw:
            raise ValueError("Missing tailored_experiences in model response.")
        if not isinstance(skills_raw, dict):
            raise ValueError("Missing tailored_skills in model response.")
        experiences = [TailoredExperience.model_validate(item) for item in experiences_raw]
        tailored_skills = {
            "languages": _clean_list(skills_raw.get("languages")),
            "frameworks": _clean_list(skills_raw.get("frameworks")),
            "tools": _clean_list(skills_raw.get("tools")),
        }
        return cls(
            resume_language=resume_language,
            tailored_title=title,
            tailored_summary=summary,
            tailored_experiences=experiences,
            tailored_skills=tailored_skills,
            cover_letter=str(data.get("cover_letter")).strip() if data.get("cover_letter") else None,
            linkedin_message=str(data.get("linkedin_message")).strip() if data.get("linkedin_message") else None,
            email_draft=str(data.get("email_draft")).strip() if data.get("email_draft") else None,
            focus_areas=_clean_list(data.get("focus_areas")),
            detected_emails=_clean_list(data.get("detected_emails")),
            profile_update_hints=_clean_list(data.get("profile_update_hints")),
        )

    def model_dump(self) -> dict:
        return {
            "resume_language": self.resume_language,
            "tailored_title": self.tailored_title,
            "tailored_summary": self.tailored_summary,
            "tailored_experiences": [item.model_dump() for item in self.tailored_experiences],
            "tailored_skills": {
                "languages": list(self.tailored_skills.get("languages", [])),
                "frameworks": list(self.tailored_skills.get("frameworks", [])),
                "tools": list(self.tailored_skills.get("tools", [])),
            },
            "cover_letter": self.cover_letter,
            "linkedin_message": self.linkedin_message,
            "email_draft": self.email_draft,
            "focus_areas": list(self.focus_areas),
            "detected_emails": list(self.detected_emails),
            "profile_update_hints": list(self.profile_update_hints),
        }
