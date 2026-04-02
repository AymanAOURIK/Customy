from __future__ import annotations

import re
from pathlib import Path


_PLACEHOLDER_TEXTS = {
    "",
    "your name",
    "full name",
    "you@example.com",
    "city, country",
    "linkedin.com/in/yourhandle",
    "github.com/yourhandle",
    "one or two sentence professional summary here.",
    "university name",
    "company a",
    "company b",
}

_LANGUAGE_SKILLS = {
    "python",
    "sql",
    "javascript",
    "typescript",
    "java",
    "go",
    "c++",
    "r",
    "bash",
    "scala",
}

_FRAMEWORK_SKILLS = {
    "fastapi",
    "react",
    "dbt",
    "langchain",
    "pydantic",
    "chromadb",
    "xgboost",
    "airflow",
}

_TOOL_SKILLS = {
    "docker",
    "git",
    "postgresql",
    "openai",
    "power bi",
    "rag",
    "lora fine-tuning",
    "llm-as-judge",
    "llm",
}

_SOFT_SKILL_HINTS = (
    "lead",
    "leadership",
    "ownership",
    "stakeholder",
    "communication",
    "translation",
    "delivery",
    "roadmap",
    "cross-functional",
)

_SUMMARY_HEADERS = ("summary",)
_EXPERIENCE_HEADERS = ("work experience", "w ork experience", "experience")
_EDUCATION_HEADERS = ("education",)
_SKILLS_HEADERS = ("skills",)
_LANGUAGE_HEADERS = ("languages",)
_DATE_LINE_PATTERN = re.compile(r"^(?P<start>\d{4}[/-]\d{2})\s*[–-]\s*(?P<end>present|\d{4}[/-]\d{2})$", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_LINKEDIN_PATTERN = re.compile(r"(?:https?://)?(?:www\.)?(linkedin\.com/)?(in/[A-Za-z0-9._-]+/?)(?=\s|$)", re.IGNORECASE)
_GITHUB_PATTERN = re.compile(r"(?:https?://)?(?:www\.)?(github\.com/[A-Za-z0-9._-]+/?)(?=\s|$)", re.IGNORECASE)
_NAME_TITLE_PATTERN = re.compile(
    r"^(?P<name>[A-Z][A-Za-z'`.-]+(?:\s+[A-Z][A-Za-z'`.-]+){1,4})\s+(?P<headline>.+)$"
)
_TITLE_MARKERS = (
    "engineer",
    "lead",
    "scientist",
    "manager",
    "analyst",
    "developer",
    "architect",
    "consultant",
    "specialist",
    "data",
    "ai",
    "machine learning",
)
_SPOKEN_LANGUAGE_PATTERN = re.compile(r"([A-Za-z]+(?:\s+[A-Za-z]+)?\s*\([^)]+\))")


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned = []
    for item in values:
        text = _clean_text(item)
        if text:
            cleaned.append(text)
    return cleaned


def _is_placeholder_text(value: object) -> bool:
    normalized = _clean_text(value).lower()
    return not normalized or normalized in _PLACEHOLDER_TEXTS


def has_meaningful_candidate_data(raw: dict | None) -> bool:
    if not isinstance(raw, dict) or not raw:
        return False

    personal = raw.get("personal") or {}
    if _is_placeholder_text(personal.get("name")) or _is_placeholder_text(personal.get("email")):
        return False

    summary = _clean_text(raw.get("summary"))
    if _is_placeholder_text(summary):
        return False

    experiences = raw.get("experiences") or []
    meaningful_experiences = 0
    for item in experiences:
        if not isinstance(item, dict):
            continue
        company = _clean_text(item.get("company"))
        role = _clean_text(item.get("role"))
        bullets = _clean_list(item.get("bullets"))
        if company and role and bullets and not _is_placeholder_text(company):
            meaningful_experiences += 1
    return meaningful_experiences > 0


def merge_candidate_data(primary: dict | None, fallback: dict | None) -> dict:
    primary = primary or {}
    fallback = fallback or {}
    primary_is_meaningful = has_meaningful_candidate_data(primary)

    primary_personal = primary.get("personal") or {}
    fallback_personal = fallback.get("personal") or {}
    merged_personal = {}
    for field in ("name", "email", "phone", "location", "linkedin", "github"):
        primary_value = _clean_text(primary_personal.get(field))
        fallback_value = _clean_text(fallback_personal.get(field))
        if primary_is_meaningful and primary_value and not _is_placeholder_text(primary_value):
            merged_personal[field] = primary_value
        else:
            merged_personal[field] = fallback_value or (primary_value if not _is_placeholder_text(primary_value) else "")

    primary_skills = primary.get("skills") or {}
    fallback_skills = fallback.get("skills") or {}
    merged_skills = {}
    for field in ("languages", "frameworks", "tools", "soft"):
        merged = []
        seen = set()
        sources = []
        if primary_is_meaningful:
            sources.extend(_clean_list(primary_skills.get(field)))
        sources.extend(_clean_list(fallback_skills.get(field)))
        for item in sources:
            key = item.lower()
            if key in seen:
                continue
            merged.append(item)
            seen.add(key)
        merged_skills[field] = merged

    experiences = _merge_experiences(primary.get("experiences"), fallback.get("experiences")) if primary_is_meaningful else None
    if not experiences:
        experiences = fallback.get("experiences") or []

    education = primary.get("education") or fallback.get("education") or []
    spoken_languages = _clean_list(primary.get("spoken_languages")) if primary_is_meaningful else []
    if not spoken_languages:
        spoken_languages = _clean_list(fallback.get("spoken_languages"))

    scoring_keywords = []
    seen_keywords = set()
    for item in _clean_list(primary.get("scoring_keywords")) + _clean_list(fallback.get("scoring_keywords")):
        key = item.lower()
        if key in seen_keywords:
            continue
        scoring_keywords.append(item)
        seen_keywords.add(key)

    merged = {
        "personal": merged_personal,
        "headline": (
            _clean_text(primary.get("headline"))
            if primary_is_meaningful and not _is_placeholder_text(primary.get("headline"))
            else _clean_text(fallback.get("headline"))
        ),
        "summary": (
            _clean_text(primary.get("summary"))
            if primary_is_meaningful and not _is_placeholder_text(primary.get("summary"))
            else _clean_text(fallback.get("summary"))
        ),
        "skills": merged_skills,
        "experiences": experiences,
        "education": education,
        "spoken_languages": spoken_languages,
        "scoring_keywords": scoring_keywords,
    }

    source_resume_text = str(primary.get("source_resume_text") or fallback.get("source_resume_text") or "").strip()
    if source_resume_text:
        merged["source_resume_text"] = source_resume_text
    return merged


def _experience_key(item: dict | None) -> tuple[str, str]:
    if not isinstance(item, dict):
        return "", ""
    return (_clean_text(item.get("company")).lower(), _clean_text(item.get("role")).lower())


def _merge_experiences(primary_items: object, fallback_items: object) -> list[dict]:
    primary_list = [item for item in (primary_items or []) if isinstance(item, dict)]
    fallback_list = [item for item in (fallback_items or []) if isinstance(item, dict)]
    if not primary_list:
        return fallback_list
    if not fallback_list:
        return primary_list

    merged = []
    for index, primary in enumerate(primary_list):
        fallback = None
        primary_key = _experience_key(primary)
        for candidate in fallback_list:
            if primary_key == _experience_key(candidate) and any(primary_key):
                fallback = candidate
                break
        if fallback is None and index < len(fallback_list):
            fallback = fallback_list[index]

        merged_item = dict(fallback or {})
        merged_item.update(primary)
        if fallback and not _clean_text(merged_item.get("duration")):
            merged_item["duration"] = _clean_text(fallback.get("duration"))
        if fallback and not _clean_text(merged_item.get("location")):
            merged_item["location"] = _clean_text(fallback.get("location"))
        if fallback and not _clean_list(merged_item.get("bullets")):
            merged_item["bullets"] = _clean_list(fallback.get("bullets"))
        merged.append(merged_item)
    return merged


def extract_pdf_text(pdf_path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError("pypdf is required for PDF import. Run: pip install pypdf") from exc

    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def _normalize_date(value: str) -> str:
    cleaned = _clean_text(value).replace("/", "-")
    if cleaned.lower() == "present":
        return "present"
    return cleaned


def _repair_text_spacing(text: str) -> str:
    repaired = text.replace("\u00a0", " ")
    repaired = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", repaired)
    repaired = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", repaired)
    repaired = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", repaired)
    repaired = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", repaired)
    repaired = re.sub(r"\s+", " ", repaired)
    repaired = repaired.replace("$ ", "$").replace("~ ", "~")
    repaired = repaired.replace("Lo RA", "LoRA").replace("Postgre SQL", "PostgreSQL").replace("Fast API", "FastAPI")
    return repaired.strip()


def _clean_line(value: str) -> str:
    return _repair_text_spacing(_clean_text(value.replace("\t", " ")))


def _slice_section(text: str, starts: tuple[str, ...], stops: tuple[str, ...]) -> str:
    start_pattern = "|".join(re.escape(item) for item in starts)
    stop_pattern = "|".join(re.escape(item) for item in stops)
    pattern = re.compile(
        rf"(?is)(?:^|\n)\s*(?:{start_pattern})\s*\n(?P<body>.*?)(?=\n\s*(?:{stop_pattern})\s*\n|\Z)"
    )
    match = pattern.search(text)
    return match.group("body").strip() if match else ""


def _parse_name_and_headline(lines: list[str]) -> tuple[str, str]:
    if not lines:
        return "", ""
    first_line = _clean_text(lines[0])
    tokens = first_line.split()
    for index in range(2, len(tokens)):
        title_candidate = " ".join(tokens[index:])
        if any(marker in title_candidate.lower() for marker in _TITLE_MARKERS):
            return " ".join(tokens[:index]), title_candidate
    match = _NAME_TITLE_PATTERN.match(first_line)
    if match:
        return _clean_text(match.group("name")), _clean_text(match.group("headline"))
    return first_line, ""


def _parse_personal(lines: list[str], full_text: str) -> dict:
    name, headline = _parse_name_and_headline(lines)
    email_match = _EMAIL_PATTERN.search(full_text)
    phone_match = _PHONE_PATTERN.search(full_text)
    linkedin_match = _LINKEDIN_PATTERN.search(full_text)
    github_match = _GITHUB_PATTERN.search(full_text)

    location = ""
    for line in lines[1:4]:
        location_line = _EMAIL_PATTERN.sub("", line)
        location_line = _PHONE_PATTERN.sub("", location_line)
        location_line = _LINKEDIN_PATTERN.sub("", location_line)
        location_line = _GITHUB_PATTERN.sub("", location_line)
        candidate_location = _clean_text(location_line.strip(" |,-"))
        if "@" in line and "," not in candidate_location:
            continue
        if candidate_location and ("," in candidate_location or len(candidate_location.split()) >= 2):
            location = candidate_location
            break

    return {
        "personal": {
            "name": name,
            "email": email_match.group(0) if email_match else "",
            "phone": _clean_text(phone_match.group(0)) if phone_match else "",
            "location": location,
            "linkedin": linkedin_match.group(2) if linkedin_match else "",
            "github": github_match.group(1) if github_match else "",
        },
        "headline": headline,
    }


def _parse_experiences(section_text: str) -> list[dict]:
    if not section_text:
        return []

    parsed_lines = []
    for raw_line in section_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        parsed_lines.append(
            {
                "text": _clean_line(stripped.lstrip("•").strip()),
                "is_bullet": stripped.startswith("•"),
            }
        )
    lines = [line for line in parsed_lines if line["text"]]
    experiences = []
    index = 0

    while index < len(lines):
        match = _DATE_LINE_PATTERN.match(lines[index]["text"])
        if not match:
            index += 1
            continue

        start = _normalize_date(match.group("start"))
        end = _normalize_date(match.group("end"))
        index += 1

        location = ""
        if index < len(lines) and not _DATE_LINE_PATTERN.match(lines[index]["text"]) and not lines[index]["is_bullet"]:
            location = lines[index]["text"]
            index += 1

        role_line = lines[index]["text"] if index < len(lines) else ""
        if index < len(lines) and lines[index]["is_bullet"]:
            role_line = ""
        else:
            index += 1

        role = ""
        company = ""
        duration = ""
        duration_match = re.search(r"\(([^()]*)\)\s*$", role_line)
        if duration_match:
            duration = _clean_line(duration_match.group(1))
        cleaned_role_line = re.sub(r"\([^)]*\)$", "", role_line).strip()
        if ":" in cleaned_role_line:
            role, company = [_clean_line(part) for part in cleaned_role_line.split(":", 1)]
        elif " at " in cleaned_role_line.lower():
            split_parts = re.split(r"\bat\b", cleaned_role_line, maxsplit=1, flags=re.IGNORECASE)
            if len(split_parts) == 2:
                role, company = [_clean_line(part) for part in split_parts]
        else:
            role = cleaned_role_line

        bullets = []
        while index < len(lines) and not _DATE_LINE_PATTERN.match(lines[index]["text"]):
            raw_line = lines[index]
            text = raw_line["text"]
            if raw_line["is_bullet"]:
                bullets.append(text)
            elif bullets:
                bullets[-1] = _clean_line(f"{bullets[-1]} {text}")
            index += 1

        if company or role or bullets:
            experiences.append(
                {
                    "company": company,
                    "role": role,
                    "start": start,
                    "end": end,
                    "location": location,
                    "duration": duration,
                    "bullets": [bullet for bullet in bullets if bullet],
                }
            )

    return [item for item in experiences if item.get("company") and item.get("role") and item.get("bullets")]


def _parse_education(section_text: str) -> list[dict]:
    if not section_text:
        return []

    lines = [_clean_line(line) for line in section_text.splitlines()]
    education = []
    for line in lines:
        if not line:
            continue
        match = re.match(r"^(?P<start>\d{4})\s*[–-]\s*(?P<end>\d{4}|present)\s+(?P<details>.+)$", line, re.IGNORECASE)
        if not match:
            continue
        details = match.group("details")
        degree = details
        institution = ""
        if "," in details:
            degree, institution = [part.strip() for part in details.split(",", 1)]
        try:
            year = int(match.group("end")) if match.group("end").isdigit() else int(match.group("start"))
        except ValueError:
            year = 0
        start_year = int(match.group("start")) if match.group("start").isdigit() else 0
        end_year = int(match.group("end")) if match.group("end").isdigit() else year
        education.append(
            {
                "institution": institution,
                "degree": degree,
                "year": year,
                "start_year": start_year,
                "end_year": end_year,
            }
        )
    return education


def _parse_skills(skills_text: str) -> dict:
    normalized = re.sub(r"([A-Za-z]{2,})-\s*\n\s*([A-Za-z]{2,})", r"\1\2", skills_text or "")
    lines = [_clean_line(line) for line in normalized.splitlines() if _clean_line(line)]
    tokens = []
    for line in lines:
        for part in re.split(r"[·|]", line):
            token = _clean_line(part)
            if token:
                tokens.extend(_split_skill_token(token))

    skills = {"languages": [], "frameworks": [], "tools": [], "soft": []}
    for token in tokens:
        lowered = token.lower()
        if lowered in _LANGUAGE_SKILLS:
            skills["languages"].append(token)
        elif lowered in _FRAMEWORK_SKILLS:
            skills["frameworks"].append(token)
        elif lowered in _TOOL_SKILLS:
            skills["tools"].append(token)
        elif any(hint in lowered for hint in _SOFT_SKILL_HINTS):
            skills["soft"].append(token)
        elif any(symbol in token for symbol in ("SQL", "Python", "Java", "Go", "C++")):
            skills["languages"].append(token)
        else:
            skills["tools"].append(token)

    deduped = {}
    for group, items in skills.items():
        seen = set()
        deduped[group] = []
        for item in items:
            key = item.lower()
            if key in seen:
                continue
            deduped[group].append(item)
            seen.add(key)
    return deduped


def _split_skill_token(token: str) -> list[str]:
    cleaned = _clean_line(token).replace("FastAPITeam", "FastAPI Team")
    if not cleaned:
        return []

    known_prefixes = sorted(_LANGUAGE_SKILLS | _FRAMEWORK_SKILLS | _TOOL_SKILLS, key=len, reverse=True)
    lowered = cleaned.lower()
    for prefix in known_prefixes:
        if lowered.startswith(prefix + " "):
            first = cleaned[: len(prefix)]
            rest = cleaned[len(prefix) :].strip()
            if rest:
                return [_clean_line(first), _clean_line(rest)]
    return [cleaned]


def _parse_spoken_languages(section_text: str) -> list[str]:
    if not section_text:
        return []
    matches = _SPOKEN_LANGUAGE_PATTERN.findall(section_text.replace("\n", " "))
    if matches:
        return [_clean_line(match) for match in matches if _clean_line(match)]
    tokens = [_clean_line(part) for part in re.split(r"[•·|]", section_text.replace("\n", " ")) if _clean_line(part)]
    return tokens


def _derive_scoring_keywords(summary: str, skills: dict, experiences: list[dict], headline: str) -> list[str]:
    keywords = []
    seen = set()

    def add_keyword(value: str) -> None:
        cleaned = _clean_text(value).lower()
        if not cleaned or cleaned in seen or len(cleaned) < 2:
            return
        keywords.append(cleaned)
        seen.add(cleaned)

    for value in [headline, summary]:
        for piece in re.split(r"[,./()]+", value):
            cleaned = _clean_text(piece)
            if 2 <= len(cleaned.split()) <= 4:
                add_keyword(cleaned)

    for group in ("languages", "frameworks", "tools"):
        for item in skills.get(group, []):
            add_keyword(item)

    for item in experiences:
        for bullet in item.get("bullets", [])[:3]:
            for match in re.findall(r"\b(?:RAG|LLM|LoRA|FastAPI|Airflow|Docker|PostgreSQL|Power BI|Python|SQL|XGBoost|LangChain|OpenAI)\b", bullet, re.IGNORECASE):
                add_keyword(match)

    return keywords[:25]


def parse_resume_text(text: str) -> dict:
    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [_clean_line(line) for line in normalized_text.splitlines() if _clean_line(line)]
    personal_block = _parse_personal(lines[:6], normalized_text)

    summary = _slice_section(normalized_text, _SUMMARY_HEADERS, _EXPERIENCE_HEADERS + _EDUCATION_HEADERS + _SKILLS_HEADERS)
    experience_text = _slice_section(normalized_text, _EXPERIENCE_HEADERS, _EDUCATION_HEADERS + _SKILLS_HEADERS)
    education_text = _slice_section(normalized_text, _EDUCATION_HEADERS, _SKILLS_HEADERS + _LANGUAGE_HEADERS)
    skills_text = _slice_section(normalized_text, _SKILLS_HEADERS, _LANGUAGE_HEADERS)
    languages_text = _slice_section(normalized_text, _LANGUAGE_HEADERS, ())

    experiences = _parse_experiences(experience_text)
    education = _parse_education(education_text)
    skills = _parse_skills(skills_text)
    spoken_languages = _parse_spoken_languages(languages_text)
    scoring_keywords = _derive_scoring_keywords(summary, skills, experiences, personal_block.get("headline", ""))

    return {
        "personal": personal_block["personal"],
        "headline": personal_block.get("headline", ""),
        "summary": _repair_text_spacing(summary),
        "skills": skills,
        "experiences": experiences,
        "education": education,
        "spoken_languages": spoken_languages,
        "scoring_keywords": scoring_keywords,
        "source_resume_text": normalized_text,
    }


def parse_resume_pdf(pdf_path: str) -> dict:
    text = extract_pdf_text(pdf_path)
    parsed = parse_resume_text(text)
    parsed["source_resume_text"] = text
    return parsed


def load_resume_backed_candidate(raw_candidate: dict | None, source_pdf_path: str | None) -> dict:
    yaml_candidate = raw_candidate or {}
    parsed_pdf = {}

    if source_pdf_path:
        pdf_file = Path(source_pdf_path)
        if pdf_file.exists():
            try:
                parsed_pdf = parse_resume_pdf(str(pdf_file))
            except Exception:
                parsed_pdf = {}

    if has_meaningful_candidate_data(yaml_candidate):
        merged = merge_candidate_data(yaml_candidate, parsed_pdf)
        merged["candidate_source"] = "yaml+pdf" if parsed_pdf else "yaml"
        return merged

    if parsed_pdf:
        merged = merge_candidate_data(yaml_candidate, parsed_pdf)
        merged["candidate_source"] = "pdf_fallback"
        return merged

    merged = merge_candidate_data(yaml_candidate, {})
    merged["candidate_source"] = "yaml_placeholder"
    return merged
