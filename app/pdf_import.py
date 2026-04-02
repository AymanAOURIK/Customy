from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

from config import load_candidate
from app.resume_source import extract_pdf_text, has_meaningful_candidate_data


_PARSE_SYSTEM_PROMPT = """\
You are a resume parser. Extract every detail from the resume text and return ONLY a valid JSON object
with this exact structure — no preamble, no markdown fences:

{
  "personal": {
    "name": "Full Name",
    "email": "email@example.com",
    "phone": "+1 555 000 0000",
    "location": "City, Country",
    "linkedin": "linkedin.com/in/handle",
    "github": "github.com/handle"
  },
  "summary": "Professional summary from the resume.",
  "skills": {
    "languages": ["Python", "SQL"],
    "frameworks": ["FastAPI", "React"],
    "tools": ["Docker", "Git"],
    "soft": ["Leadership", "Communication"]
  },
  "experiences": [
    {
      "company": "Company Name",
      "role": "Job Title",
      "start": "YYYY-MM",
      "end": "YYYY-MM",
      "location": "City, Country",
      "bullets": ["Achievement or responsibility."]
    }
  ],
  "education": [
    {
      "institution": "University Name",
      "degree": "Degree Name",
      "year": 2020
    }
  ],
  "scoring_keywords": ["python", "sql", "data engineering"]
}

Rules:
- Extract ALL work experiences and keep ALL bullets verbatim from the resume.
- Dates in YYYY-MM format. Use "present" for current roles. Use YYYY-01 if only the year is known.
- Split skills into: languages (programming/query), frameworks (libraries/platforms), tools (devops/software), soft (interpersonal).
- scoring_keywords: 15-25 lowercase technical skills, domains, and job-relevant terms from the resume.
- Use empty string "" for any missing text field; empty array [] for missing lists.
- year in education must be an integer (e.g. 2020).
- Return ONLY the JSON object.\
"""

def _call_openai(pdf_text: str, api_key: str, model: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=4000,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _PARSE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Parse this resume:\n\n{pdf_text}"},
        ],
    )
    content = (response.choices[0].message.content or "").strip()
    return json.loads(content)


def _str(value: object, default: str = "") -> str:
    if value is None:
        return default
    cleaned = str(value).strip()
    return cleaned if cleaned else default


def _list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _clean(raw: dict) -> dict:
    personal = raw.get("personal") or {}
    skills = raw.get("skills") or {}

    experiences = []
    for item in raw.get("experiences") or []:
        if not isinstance(item, dict):
            continue
        bullets = _list(item.get("bullets"))
        if not bullets:
            continue
        experiences.append(
            {
                "company": _str(item.get("company")),
                "role": _str(item.get("role")),
                "start": _str(item.get("start")),
                "end": _str(item.get("end")),
                "location": _str(item.get("location")),
                "bullets": bullets,
            }
        )

    education = []
    for item in raw.get("education") or []:
        if not isinstance(item, dict):
            continue
        try:
            year = int(item.get("year") or 0)
        except (TypeError, ValueError):
            year = 0
        education.append(
            {
                "institution": _str(item.get("institution")),
                "degree": _str(item.get("degree")),
                "year": year,
            }
        )

    return {
        "personal": {
            "name": _str(personal.get("name")),
            "email": _str(personal.get("email")),
            "phone": _str(personal.get("phone")),
            "location": _str(personal.get("location")),
            "linkedin": _str(personal.get("linkedin")),
            "github": _str(personal.get("github")),
        },
        "summary": _str(raw.get("summary")),
        "skills": {
            "languages": _list(skills.get("languages")),
            "frameworks": _list(skills.get("frameworks")),
            "tools": _list(skills.get("tools")),
            "soft": _list(skills.get("soft")),
        },
        "experiences": experiences,
        "education": education,
        "scoring_keywords": _list(raw.get("scoring_keywords")),
    }


def _write_yaml(data: dict, path: str) -> None:
    Path(path).write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120),
        encoding="utf-8",
    )


def _needs_import(pdf_path: Path, yaml_path: Path) -> bool:
    """
    Return True when the PDF should refresh candidate.yaml.
    Import when candidate.yaml is missing, placeholder, malformed, or older than the PDF.
    """
    if not yaml_path.exists():
        return True
    try:
        current = load_candidate(str(yaml_path))
    except Exception:
        return True
    if not has_meaningful_candidate_data(current):
        return True
    return pdf_path.stat().st_mtime > yaml_path.stat().st_mtime


def import_candidate_from_pdf(pdf_path: str, candidate_yaml_path: str, config: dict) -> bool:
    """
    Parses a PDF resume with OpenAI and writes the result to candidate.yaml.
    Runs when candidate.yaml is missing, placeholder, malformed, or older than the PDF.
    Returns True on success, False when skipped or failed (non-fatal).
    """
    pdf_file = Path(pdf_path)
    yaml_file = Path(candidate_yaml_path)

    if not pdf_file.exists():
        print(f"  source_pdf not found: {pdf_path}", file=sys.stderr)
        return False

    if not _needs_import(pdf_file, yaml_file):
        return False  # Already up-to-date, silent skip

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("  OPENAI_API_KEY not set — skipping PDF import", file=sys.stderr)
        return False

    model = (config.get("llm") or {}).get("model", "gpt-4o-mini")

    try:
        print(f"  Importing candidate data from {pdf_file.name} ...")
        pdf_text = extract_pdf_text(str(pdf_file))
        if not pdf_text.strip():
            print("  PDF yielded no text — skipping import", file=sys.stderr)
            return False
        raw = _call_openai(pdf_text, api_key, model)
        data = _clean(raw)
        _write_yaml(data, candidate_yaml_path)
        name = (data.get("personal") or {}).get("name") or "candidate"
        exps = len(data.get("experiences") or [])
        print(f"  candidate.yaml updated  ({name}, {exps} experience(s))")
        return True
    except ImportError as exc:
        print(f"  {exc}", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"  PDF import failed: {exc}", file=sys.stderr)
        return False
