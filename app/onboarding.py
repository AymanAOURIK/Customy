"""LLM-based resume extraction for Customy V3 onboarding.

Phase 1 — extract_draft:
  Takes raw resume text and returns a faithful structured draft plus a gap analysis
  that drives the Phase 2 question flow. Does NOT rewrite or improve bullets.

Phase 3 — enrich_draft (not yet implemented):
  Takes draft_data + user_answers and returns an enriched profile at
  candidate.yaml quality level.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from app.openai_usage import OpenAIUsageRecord, summarize_usage, usage_from_response
from app.text_utils import sanitize_text

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase 1 — Extraction
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM_PROMPT = """\
You extract structured profile data from a raw resume text.

Rules:
- Extract faithfully. Do NOT improve, rephrase, or invent any information.
- If a field is absent, set it to null or [] as appropriate.
- Dates: use "YYYY-MM" when month is known, "YYYY" when only year is known.
  Use the string "present" (lowercase) for currently-held roles.
- Skills: extract from BOTH the explicit skills section AND from every bullet
  across all experience entries. Include every specific tool, library, framework,
  or language you can identify anywhere in the resume.
- Output valid JSON only. No markdown fences. No explanation. No trailing text.

Gap analysis rules:
- resume_currency_uncertain: set to true if ANY experience has end = "present",
  or if the text contains "currently" or "current" in relation to a role.
  Resumes are frequently submitted months or years after the last update.
- bullets_missing_metrics: bullets that contain no numbers, percentages, dollar
  amounts, or scale indicators (e.g. "K leads", "X agents", "Y hours/week").
  Limit to the 5 most impactful-sounding entries. Exclude graduation projects.
- bullets_missing_tools: bullets that describe an activity but name no specific
  tools, libraries, or technologies. Same 5-entry limit. Exclude graduation projects.
- thin_skills: true if fewer than 10 specific skills are extracted in total.
- skill_count: total unique skills across all categories.
- missing_fields: list field names absent from the resume. Check: github, headline,
  summary, scoring_keywords.
"""

_EXTRACT_SCHEMA = """\
Output exactly this JSON structure (no extra top-level keys):
{
  "draft_data": {
    "full_name": "string",
    "email": "string or null",
    "phone": "string or null",
    "location": "string or null",
    "linkedin": "string or null",
    "github": "string or null",
    "headline": "string or null",
    "summary": "string or null",
    "skills": {
      "languages":  ["string"],
      "frameworks": ["string"],
      "tools":      ["string"],
      "soft":       ["string"]
    },
    "experiences": [
      {
        "company":  "string",
        "role":     "string",
        "start":    "string",
        "end":      "string",
        "location": "string or null",
        "bullets":  ["string"]
      }
    ],
    "education": [
      {
        "institution": "string",
        "degree":      "string",
        "start_year":  "integer or null",
        "end_year":    "integer or null"
      }
    ],
    "spoken_languages":  ["string"],
    "scoring_keywords":  []
  },
  "gap_analysis": {
    "resume_currency_uncertain": true,
    "last_detected_role":        "string or null",
    "last_detected_end":         "string or null",
    "missing_fields":            ["string"],
    "thin_skills":               true,
    "skill_count":               0,
    "bullets_missing_metrics": [
      { "company": "string", "bullet_index": 0, "text": "string" }
    ],
    "bullets_missing_tools": [
      { "company": "string", "bullet_index": 0, "text": "string" }
    ],
    "has_personal_projects": false,
    "experience_count":      0
  }
}
"""


class OnboardingExtractionError(ValueError):
    def __init__(self, message: str, usage_summary: dict | None = None) -> None:
        super().__init__(message)
        self.usage_summary = usage_summary or summarize_usage([])


def extract_draft(
    parsed_text: str,
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Extract a structured profile draft and gap analysis from raw resume text.

    Uses the cheaper analysis_model (gpt-4o-mini by default) at temperature 0
    with JSON mode enforced.

    Returns:
        (draft_data, gap_analysis, usage_summary) — dicts ready for storage
        and usage tracking.

    Raises:
        ValueError if the API call fails or returns unparseable output.
    """
    from openai import OpenAI

    parsed_text = sanitize_text(parsed_text, preserve_newlines=True)
    if not parsed_text:
        raise ValueError("Resume text is empty after sanitization")

    model = (
        config.get("llm", {}).get("analysis_model")
        or config.get("llm", {}).get("model")
        or "gpt-4o-mini"
    )
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)
    usage_records: list[OpenAIUsageRecord] = []

    user_message = (
        f"Extract structured data from the following resume text.\n\n"
        f"Schema:\n{_EXTRACT_SCHEMA}\n\n"
        f"Resume text:\n{parsed_text}"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
    except Exception as exc:
        raise OnboardingExtractionError(f"LLM extraction call failed: {exc}") from exc

    usage_records.append(
        usage_from_response(
            response,
            request_kind="onboarding_extract_draft",
            attempt_number=1,
            fallback_model=model,
            config=config,
        )
    )
    usage_summary = summarize_usage(usage_records)

    try:
        raw = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        raise OnboardingExtractionError(
            f"LLM extraction response was missing content: {exc}",
            usage_summary=usage_summary,
        ) from exc
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OnboardingExtractionError(
            f"LLM returned invalid JSON: {exc}\n\nRaw (first 500 chars): {raw[:500]}",
            usage_summary=usage_summary,
        ) from exc

    draft_data: dict[str, Any] = result.get("draft_data") or {}
    gap_analysis: dict[str, Any] = result.get("gap_analysis") or {}

    # scoring_keywords are always empty at extraction — filled in Phase 3 enrichment
    draft_data["scoring_keywords"] = []

    _log.info(
        "extract_draft: %d experiences, %d skills extracted, "
        "currency_uncertain=%s, thin_skills=%s",
        len(draft_data.get("experiences") or []),
        gap_analysis.get("skill_count", 0),
        gap_analysis.get("resume_currency_uncertain"),
        gap_analysis.get("thin_skills"),
    )

    return draft_data, gap_analysis, usage_summary
