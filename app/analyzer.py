from __future__ import annotations

import re


ROLE_PATTERN = re.compile(
    r"([A-Z][A-Za-z0-9/&,+()' \-]{1,100}(Engineer|Manager|Analyst|Developer|Lead|Scientist|Architect|Consultant|Specialist)(?:\s+(?:Data|AI|IA|ML|Platform|Cloud|Research|Applied|Big|Streaming|Tech|Gen|Architecture|Analytics|Engineering|[A-Z][A-Za-z0-9/&,+()' -]+)){0,8})\b"
)
ROLE_KEYWORD_PATTERN = re.compile(r"\b(Engineer|Manager|Analyst|Developer|Lead|Scientist|Architect|Consultant|Specialist)\b", re.IGNORECASE)
ROLE_LEADIN_PATTERN = re.compile(
    r"\b(?:en tant que|poste de|rôle de|role of|nous recherchons|we are seeking|we are looking for|seeking|looking for)\s+(?:an?\s+|une?\s+|des\s+|de nouveaux talents\s+)?(?P<role>[^,:;\n]+?(?:Lead|Engineer|Manager|Analyst|Developer|Scientist|Architect|Consultant|Specialist)(?:\s+[^,:;\n]+){0,8})",
    re.IGNORECASE,
)
COMPANY_PATTERNS = [
    re.compile(r"^why work at\s+([A-Z][A-Za-z0-9&.' \-]{1,80})$", re.IGNORECASE),
    re.compile(r"^([A-Z][A-Za-z0-9&.' \-]{1,80})\s+is\b"),
    re.compile(r"\bat\s+([A-Z][A-Za-z0-9&.' \-]{1,80})"),
    re.compile(r"@\s*([A-Z][A-Za-z0-9&.' \-]{1,80})"),
    re.compile(r"\bjoin\s+([A-Z][A-Za-z0-9&.' \-]{1,80})", re.IGNORECASE),
    re.compile(r"\bcompany\s*[:\-]\s*([A-Z][A-Za-z0-9&.' \-]{1,80})", re.IGNORECASE),
    re.compile(r"\bteam\s+([A-Z][A-Za-z0-9&.' \-]{1,80})", re.IGNORECASE),
    re.compile(r"\bchez\s+([A-Z][A-Za-z0-9&.' \-]{1,80})", re.IGNORECASE),
]
LOCATION_PATTERNS = [
    re.compile(r"\b(location|based in|lieu|localisation)\s*[:\-]\s*([A-Za-z0-9,()/ \-]{2,80})", re.IGNORECASE),
    re.compile(r"\b(remote|hybrid|on[- ]?site)\b\s*[|/,-]?\s*([A-Za-z0-9,()/ \-]{2,80})", re.IGNORECASE),
]
REMOTE_PATTERN = re.compile(r"\b(remote|fully remote|work from home|wfh|distributed)\b", re.IGNORECASE)
LEAD_PATTERN = re.compile(r"\b(lead|head of)\b", re.IGNORECASE)
SENIOR_PATTERN = re.compile(r"\b(senior|principal|staff)\b", re.IGNORECASE)
JUNIOR_PATTERN = re.compile(r"\b(junior|entry[ .-]?level|graduate|intern)\b", re.IGNORECASE)
FRENCH_WORDS = re.compile(r"\b(le|la|les|de|du|des|en|et|pour|avec|vous|nous)\b", re.IGNORECASE)
SECTION_HEADING_PATTERN = re.compile(
    r"^(about the job|why work at .+|where we work|the role|your responsibilities|responsibilities|must-haves|requirements|nice-to-haves|preferred|what we offer|profil recherché|si vous|cadrage ?& ?conception|développement ?& ?industrialisation|leadership technique|contribution business|l'aventure .+)$",
    re.IGNORECASE,
)
REQUIREMENT_SECTION_HEADINGS = {
    "your responsibilities",
    "responsibilities",
    "must-haves",
    "requirements",
    "nice-to-haves",
    "preferred",
    "profil recherché",
    "si vous",
    "cadrage & conception",
    "développement & industrialisation",
    "leadership technique",
    "contribution business",
}
KEYWORD_SIGNAL_CATALOG = [
    "Python",
    "SQL",
    "Docker",
    "Kubernetes",
    "Spark",
    "Hadoop",
    "AWS",
    "GCP",
    "Azure",
    "MLOps",
    "DataOps",
    "LLM",
    "Gen AI",
    "OCR",
    "FastAPI",
    "Airflow",
    "PostgreSQL",
    "TensorFlow",
    "Scikit-learn",
    "LangChain",
    "OpenAI",
    "Power BI",
    "XGBoost",
    "RAG",
    "NLP",
    "CI/CD",
    "data architecture",
    "data engineering",
    "data analytics",
    "data mesh",
    "data governance",
    "technical leadership",
    "client proposals",
]


def _lines(text: str) -> list[str]:
    cleaned = []
    for raw in text.splitlines():
        line = raw.strip().strip("-*•")
        if line:
            cleaned.append(" ".join(line.split()))
    return cleaned


def _extract_company(lines: list[str]) -> str | None:
    sample = lines[:20]
    for line in sample:
        for pattern in COMPANY_PATTERNS:
            match = pattern.search(line)
            if match:
                company = match.group(1).strip(" .,:;|-")
                if len(company) > 1:
                    return company
    return None


def _normalize_role(role: str) -> str:
    cleaned = role.strip(" .,:;|-")
    cleaned = re.sub(r"^(?:en tant que|poste de|rôle de|as a|for the role of)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*(?:,|:)\s*(?:vos.*|your.*)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bData\s+IA\b", "Data & IA", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bData\s*/\s*IA\b", "Data & IA", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bIA\s+Data\b", "IA & Data", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" .,:;|-")


def _extract_role(lines: list[str]) -> str | None:
    sample = lines[:40]
    for index, line in enumerate(sample):
        leadin_match = ROLE_LEADIN_PATTERN.search(line)
        if leadin_match:
            role = _normalize_role(leadin_match.group("role"))
            if role:
                return role

        if "|" in line:
            right = line.split("|", 1)[1].strip()
            right = re.split(r"\s+[–-]\s+", right, maxsplit=1)[0].strip()
            right = re.sub(r"\([^)]*\)$", "", right).strip()
            if ROLE_KEYWORD_PATTERN.search(right):
                return _normalize_role(right)

        if line.lower() in {"the role", "role", "position", "poste", "intitulé"} and index + 1 < len(sample):
            match = ROLE_PATTERN.search(sample[index + 1])
            if match:
                role = match.group(1).strip(" .,:;|-")
                role = re.sub(r"\s+to join.*$", "", role, flags=re.IGNORECASE)
                return _normalize_role(role)

        match = ROLE_PATTERN.search(line)
        if match:
            role = match.group(1)
            role = re.split(r"\bat\b|@", role, maxsplit=1, flags=re.IGNORECASE)[0]
            role = re.sub(r"\s+to join.*$", "", role, flags=re.IGNORECASE)
            return _normalize_role(role)

        inline_match = re.search(
            r"\b(?:with|for|as)\s+(?:an?\s+)?([A-Z][A-Za-z0-9/&,+()' \-]{2,80}(?:Lead|Engineer|Manager|Analyst|Developer|Scientist|Architect|Consultant|Specialist)(?:\s+(?:Data|AI|IA|ML|Platform|Cloud|Research|Applied|Big|Streaming|Tech|/|&|-|[A-Z][A-Za-z0-9/&,+()' -]+)){0,8})",
            line,
            re.IGNORECASE,
        )
        if inline_match:
            role = inline_match.group(1).strip(" .,:;|-")
            role = re.split(r"\s+[–-]\s+", role, maxsplit=1)[0].strip()
            return _normalize_role(role)
    return None


def _extract_location(text: str, lines: list[str]) -> str | None:
    sample_text = "\n".join(lines[:8]) + "\n" + text[:600]
    for pattern in LOCATION_PATTERNS:
        match = pattern.search(sample_text)
        if match:
            location = match.group(match.lastindex or 1).strip(" .,:;|-")
            if location:
                return location
    return "Remote" if REMOTE_PATTERN.search(text) else None


def _detect_language(text: str) -> str:
    non_space_chars = [char for char in text if not char.isspace()]
    arabic_chars = [char for char in non_space_chars if 0x0600 <= ord(char) <= 0x06FF]
    if non_space_chars and (len(arabic_chars) / len(non_space_chars)) > 0.15:
        return "ar"
    if len(FRENCH_WORDS.findall(text)) >= 5:
        return "fr"
    return "en"


def _detect_seniority(text: str) -> str:
    if LEAD_PATTERN.search(text):
        return "lead"
    if SENIOR_PATTERN.search(text):
        return "senior"
    if JUNIOR_PATTERN.search(text):
        return "junior"
    return "mid"


def _extract_top_requirements(text: str) -> list[str]:
    raw_lines = [raw.strip() for raw in (text or "").splitlines()]
    section = ""
    requirements = []
    seen = set()

    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            continue

        normalized = line.strip("-*• ").strip()
        lowered = normalized.lower()

        if SECTION_HEADING_PATTERN.match(normalized):
            section = lowered
            continue

        if section not in REQUIREMENT_SECTION_HEADINGS:
            continue

        if len(normalized) < 12:
            continue

        if normalized.endswith(":"):
            continue

        if normalized.lower().startswith(("we conduct", "what we offer", "about the job", "alors", "l'aventure")):
            continue

        key = normalized.lower()
        if key in seen:
            continue

        requirements.append(normalized)
        seen.add(key)

        if len(requirements) >= 6:
            break

    return requirements


def _extract_keyword_signals(text: str) -> list[str]:
    text_lower = (text or "").lower()
    found = []
    for keyword in KEYWORD_SIGNAL_CATALOG:
        if keyword.lower() in text_lower and keyword not in found:
            found.append(keyword)
    return found


def analyze_jd(jd_text: str, candidate_keywords: list[str]) -> dict:
    """
    Returns:
    {
        "company":                    str | None,
        "role":                       str | None,
        "location":                   str | None,
        "language":                   "en" | "fr" | "ar",
        "seniority":                  "junior" | "mid" | "senior" | "lead" | "unknown",
        "matched_keywords":           list[str],
        "top_requirements":           list[str],
        "keyword_signals":            list[str],
        "missing_candidate_keywords": list[str],
        "remote":                     bool,
        "score":                      float
    }
    """

    text = jd_text or ""
    text_lower = text.lower()
    first_lines = _lines(text)
    remote = bool(REMOTE_PATTERN.search(text))
    seniority = _detect_seniority(text)
    language = _detect_language(text)
    company = _extract_company(first_lines)
    role = _extract_role(first_lines)
    location = _extract_location(text, first_lines)
    top_requirements = _extract_top_requirements(text)
    keyword_signals = _extract_keyword_signals(text)

    actual_keywords: list[str] = []
    candidate_location = ""
    for item in candidate_keywords:
        keyword = str(item).strip()
        if not keyword:
            continue
        if keyword.lower().startswith("location:"):
            candidate_location = keyword.split(":", 1)[1].strip().lower()
            continue
        actual_keywords.append(keyword)

    matched_keywords = []
    for keyword in actual_keywords:
        if keyword.lower() in text_lower and keyword not in matched_keywords:
            matched_keywords.append(keyword)

    candidate_keyword_set = {keyword.lower() for keyword in actual_keywords}
    missing_candidate_keywords = []
    for keyword in keyword_signals:
        lowered = keyword.lower()
        if lowered in candidate_keyword_set:
            continue
        if keyword not in missing_candidate_keywords:
            missing_candidate_keywords.append(keyword)

    keyword_ratio = len(matched_keywords) / max(len(actual_keywords), 1)
    score = keyword_ratio * 60.0
    if seniority in {"mid", "senior", "lead"}:
        score += 20.0
    if remote:
        score += 10.0
    if candidate_location and candidate_location in text_lower:
        score += 10.0

    return {
        "company": company,
        "role": role,
        "location": location,
        "language": language,
        "seniority": seniority if seniority else "unknown",
        "matched_keywords": matched_keywords,
        "top_requirements": top_requirements,
        "keyword_signals": keyword_signals,
        "missing_candidate_keywords": missing_candidate_keywords,
        "remote": remote,
        "score": round(min(score, 100.0), 1),
    }
