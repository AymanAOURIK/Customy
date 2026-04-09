from __future__ import annotations

import re
from urllib.parse import urlparse

from app.targeting import KEYWORD_SIGNAL_CATALOG, normalize_role_title


ROLE_PATTERN = re.compile(
    r"([A-Z][A-Za-z0-9/&,+()' \-]{1,100}(Engineer|Manager|Analyst|Developer|Lead|Scientist|Architect|Consultant|Specialist)(?:\s+(?:Data|AI|IA|ML|Platform|Cloud|Research|Applied|Big|Streaming|Tech|Gen|Architecture|Analytics|Engineering|[A-Z][A-Za-z0-9/&,+()' -]+)){0,8})\b"
)
ROLE_SLASH_AI_PATTERN = re.compile(
    r"([A-Z][A-Za-z0-9/&,+()' \-]{1,100}(?:Lead|Engineer|Manager|Analyst|Developer|Scientist|Architect|Consultant|Specialist)(?:\s+[A-Za-z0-9/&,+()' -]+){0,8}\s*/\s*(?:AI|IA))\b",
    re.IGNORECASE,
)
ROLE_KEYWORD_PATTERN = re.compile(r"\b(Engineer|Manager|Analyst|Developer|Lead|Scientist|Architect|Consultant|Specialist)\b", re.IGNORECASE)
ROLE_LEADIN_PATTERN = re.compile(
    r"\b(?:en tant que|poste de|rôle de|role of|nous recherchons|we are seeking|we are looking for|seeking|looking for)\s+(?:an?\s+|une?\s+|des\s+|de nouveaux talents\s+)?(?P<role>[^,:;\n]+?(?:Lead|Engineer|Manager|Analyst|Developer|Scientist|Architect|Consultant|Specialist)(?:\s+[^,:;\n]+){0,8})",
    re.IGNORECASE,
)
COMPANY_PATTERNS = [
    re.compile(r"^about\s+([A-Za-z][A-Za-z0-9&.' \-]{1,80})$", re.IGNORECASE),
    re.compile(r"^about\s+the\s+company\s*[:\-]?\s*([A-Za-z][A-Za-z0-9&.' \-]{1,80})$", re.IGNORECASE),
    re.compile(r"^why work at\s+([A-Z][A-Za-z0-9&.' \-]{1,80})$", re.IGNORECASE),
    re.compile(r"^([A-Z][A-Za-z0-9&.' \-]{1,80})\s+is\b"),
    re.compile(r"\bat\s+([A-Z][A-Za-z0-9&.' \-]{1,80})"),
    re.compile(r"@\s*([A-Z][A-Za-z0-9&.' \-]{1,80})"),
    re.compile(r"\bjoin\s+([A-Z][A-Za-z0-9&.' \-]{1,80})", re.IGNORECASE),
    re.compile(r"\bcompany\s*[:\-]\s*([A-Za-z][A-Za-z0-9&.' \-]{1,80})", re.IGNORECASE),
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
    r"^(about the job|why work at .+|why join us|where we work|the role|your responsibilities|responsibilities|must-haves|requirements|nice-to-haves|preferred|what we offer|pourquoi nous rejoindre|profil recherché|si vous|cadrage ?& ?conception|développement ?& ?industrialisation|leadership technique|contribution business|l'aventure .+|qualifications|key qualifications|required qualifications|key requirements|about you|your background|your role|the position|what you.ll do|what you will do|what you.d do|key responsibilities|main responsibilities|core responsibilities|vos missions|missions|vos principales missions|profil|le profil|profil id[eé]al|profil appréci[eé]|nous recherchons|ce que nous recherchons|comp[eé]tences requises|comp[eé]tences cl[eé]s|comp[eé]tences cl[eé]s recherch[eé]es|experience required|required experience)$",
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
    "qualifications",
    "key qualifications",
    "required qualifications",
    "key requirements",
    "about you",
    "your background",
    "your role",
    "the position",
    "what you'll do",
    "what you will do",
    "what you'd do",
    "key responsibilities",
    "main responsibilities",
    "core responsibilities",
    "vos missions",
    "missions",
    "vos principales missions",
    "profil",
    "le profil",
    "profil idéal",
    "profil apprécié",
    "nous recherchons",
    "ce que nous recherchons",
    "compétences requises",
    "compétences clés",
    "compétences clés recherchées",
    "experience required",
    "required experience",
}
GENERIC_COMPANY_WORDS = {
    "apply",
    "about the job",
    "board",
    "boards",
    "career",
    "careers",
    "company",
    "greenhouse",
    "jobs",
    "job",
    "join",
    "lever",
    "opening",
    "opportunity",
    "our company",
    "our team",
    "position",
    "role",
    "share",
    "show more options",
    "smartrecruiters",
    "team",
    "the",
    "the job",
    "unknown",
    "unknown company",
    "workable",
}
GENERIC_URL_PARTS = {
    "app",
    "apply",
    "board",
    "boards",
    "career",
    "careers",
    "eu",
    "global",
    "greenhouse",
    "jobs",
    "job",
    "job-boards",
    "myworkdayjobs",
    "openings",
    "positions",
    "recruiting",
    "talent",
    "team",
    "uk",
    "us",
    "wd1",
    "wd3",
    "wd5",
    "wd103",
    "www",
}
_RELATED_SIGNAL_RULES = {
    "langgraph": {"any": (("agent orchestration",),), "all": (("langchain", "ai agents"),)},
}
_ROLE_TOKEN_EQUIVALENTS = {
    "ai": "ai",
    "ia": "ai",
    "engineer": "engineer",
    "ingénieur": "engineer",
    "lead": "lead",
    "scientist": "scientist",
    "science": "scientist",
    "manager": "manager",
    "architect": "architect",
    "developer": "developer",
    "développeur": "developer",
    "analyst": "analyst",
    "analyste": "analyst",
    "data": "data",
}
_ROLE_FAMILY_TOKENS = {"engineer", "lead", "scientist", "manager", "architect", "developer", "analyst"}
_ROLE_DOMAIN_TOKENS = {"ai", "data"}


def _lines(text: str) -> list[str]:
    cleaned = []
    for raw in text.splitlines():
        line = raw.strip().strip("-*•")
        if line:
            cleaned.append(" ".join(line.split()))
    return cleaned


def _clean_company_candidate(value: str) -> str:
    cleaned = " ".join(str(value or "").strip().split()).strip(" .,:;|-")
    cleaned = re.sub(r"\s*\((?:official|officiel)\)\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:careers?|jobs?|job board|team|hiring)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" .,:;|-")


def _looks_like_company_name(value: str) -> bool:
    cleaned = _clean_company_candidate(value)
    if len(cleaned) < 2:
        return False
    lowered = cleaned.lower()
    if lowered in GENERIC_COMPANY_WORDS:
        return False
    if ROLE_KEYWORD_PATTERN.search(cleaned) and len(cleaned.split()) <= 4:
        return False
    return True


def _normalize_heading(value: str) -> str:
    cleaned = re.sub(r"^[^A-Za-zÀ-ÿ0-9]+", "", str(value or "").strip())
    return " ".join(cleaned.split()).strip(" .,:;|-?")


def _humanize_company_slug(value: str) -> str:
    parts = [
        part
        for part in re.split(r"[-_.]+", str(value or "").strip())
        if part and part.lower() not in GENERIC_URL_PARTS
    ]
    if not parts:
        return ""
    normalized = []
    for part in parts:
        if part.isupper():
            normalized.append(part)
        elif part.isalpha() and len(part) <= 3:
            normalized.append(part.upper())
        else:
            normalized.append(part[:1].upper() + part[1:])
    return " ".join(normalized)


def _company_from_url(application_url: str | None) -> str | None:
    cleaned_url = str(application_url or "").strip()
    if not cleaned_url:
        return None
    try:
        parsed = urlparse(cleaned_url)
    except Exception:
        return None
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    subdomains = hostname.split(".")

    candidates = []
    if "greenhouse" in hostname or "lever.co" in hostname or "workable.com" in hostname:
        if path_parts:
            candidates.append(path_parts[0])
    if "ashbyhq.com" in hostname and len(subdomains) > 2:
        candidates.append(subdomains[0])
    if "smartrecruiters.com" in hostname and path_parts:
        candidates.append(path_parts[0])
    if ("myworkdayjobs.com" in hostname or "workdayjobs.com" in hostname) and subdomains:
        candidates.append(subdomains[0])

    for part in subdomains[:-2]:
        if part.lower() not in GENERIC_URL_PARTS:
            candidates.append(part)
            break

    for candidate in candidates:
        humanized = _clean_company_candidate(_humanize_company_slug(candidate))
        if _looks_like_company_name(humanized):
            return humanized
    return None


def _extract_company(lines: list[str], application_url: str | None = None) -> str | None:
    sample = lines[:20]
    for line in sample[:4]:
        cleaned = _clean_company_candidate(_normalize_heading(line))
        if not cleaned:
            continue
        if cleaned.lower() in REQUIREMENT_SECTION_HEADINGS:
            continue
        if ROLE_KEYWORD_PATTERN.search(cleaned):
            continue
        if _looks_like_company_name(cleaned):
            return cleaned
    for line in sample:
        if "|" in line:
            left = line.split("|", 1)[0].strip(" .,:;|-")
            right = line.split("|", 1)[1].strip(" .,:;|-")
            if _looks_like_company_name(left):
                return _clean_company_candidate(left)
            if ROLE_KEYWORD_PATTERN.search(left) and _looks_like_company_name(right):
                return _clean_company_candidate(right)
        if " - " in line:
            left = line.split(" - ", 1)[0].strip(" .,:;|-")
            if _looks_like_company_name(left):
                return _clean_company_candidate(left)
        for pattern in COMPANY_PATTERNS:
            match = pattern.search(line)
            if match:
                company = _clean_company_candidate(match.group(1))
                if _looks_like_company_name(company):
                    return company
    return _company_from_url(application_url)


def _normalize_role(role: str, language: str) -> str:
    cleaned = role.strip(" .,:;|-")
    cleaned = re.sub(
        r"^(?:en tant que|poste de|rôle de|as a|for the role of|we are hiring|we are looking for|we are seeking|looking for|seeking)\s+(?:an?\s+|the\s+|une?\s+)?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*(?:,|:)\s*(?:vos.*|your.*)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:avec|with|using)\b.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return normalize_role_title(cleaned.strip(" .,:;|-"), language)


def _extract_role(lines: list[str], language: str) -> str | None:
    sample = lines[:40]
    for index, line in enumerate(sample):
        slash_ai_match = ROLE_SLASH_AI_PATTERN.search(line)
        if slash_ai_match:
            return _normalize_role(slash_ai_match.group(1), language)

        leadin_match = ROLE_LEADIN_PATTERN.search(line)
        if leadin_match:
            role = _normalize_role(leadin_match.group("role"), language)
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
                return _normalize_role(role, language)

        match = ROLE_PATTERN.search(line)
        if match:
            role = match.group(1)
            role = re.split(r"\bat\b|@", role, maxsplit=1, flags=re.IGNORECASE)[0]
            role = re.sub(r"\s+to join.*$", "", role, flags=re.IGNORECASE)
            return _normalize_role(role, language)

        inline_match = re.search(
            r"\b(?:with|for|as)\s+(?:an?\s+)?([A-Z][A-Za-z0-9/&,+()' \-]{2,80}(?:Lead|Engineer|Manager|Analyst|Developer|Scientist|Architect|Consultant|Specialist)(?:\s+(?:Data|AI|IA|ML|Platform|Cloud|Research|Applied|Big|Streaming|Tech|/|&|-|[A-Z][A-Za-z0-9/&,+()' -]+)){0,8})",
            line,
            re.IGNORECASE,
        )
        if inline_match:
            role = inline_match.group(1).strip(" .,:;|-")
            role = re.split(r"\s+[–-]\s+", role, maxsplit=1)[0].strip()
            return _normalize_role(role, language)
    return None


def _extract_location(text: str, lines: list[str]) -> str | None:
    for line in lines[:10]:
        if "📍" not in line and "|" not in line:
            continue
        left = line.split("|", 1)[0].replace("📍", "").strip(" .,:;|-")
        if not left:
            continue
        if ROLE_KEYWORD_PATTERN.search(left):
            continue
        if len(left.split()) > 4:
            continue
        return left

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

        normalized = _normalize_heading(line.strip("-*• ").strip())
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


def _clean_keyword(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _unique_keywords(items: list[object]) -> list[str]:
    unique = []
    seen = set()
    for item in items:
        cleaned = _clean_keyword(item)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        unique.append(cleaned)
        seen.add(lowered)
    return unique


def _supports_related_signal(signal: str, candidate_keyword_set: set[str]) -> bool:
    rule = _RELATED_SIGNAL_RULES.get(str(signal or "").lower())
    if not rule:
        return False
    if any(all(term in candidate_keyword_set for term in group) for group in rule.get("all", ())):
        return True
    return any(any(term in candidate_keyword_set for term in group) for group in rule.get("any", ()))


def _role_token_set(value: object) -> set[str]:
    normalized = normalize_role_title(value, "en")
    tokens = set()
    for token in re.findall(r"[A-Za-zÀ-ÿ]+", normalized.lower()):
        canonical = _ROLE_TOKEN_EQUIVALENTS.get(token)
        if canonical:
            tokens.add(canonical)
    return tokens


def _has_role_alignment(role: object, candidate_keywords: list[str]) -> bool:
    target_tokens = _role_token_set(role)
    if not target_tokens:
        return False
    target_domains = target_tokens & _ROLE_DOMAIN_TOKENS
    target_family = target_tokens & _ROLE_FAMILY_TOKENS
    for keyword in candidate_keywords:
        keyword_tokens = _role_token_set(keyword)
        if not keyword_tokens:
            continue
        if target_tokens <= keyword_tokens:
            return True
        keyword_domains = keyword_tokens & _ROLE_DOMAIN_TOKENS
        keyword_family = keyword_tokens & _ROLE_FAMILY_TOKENS
        if target_domains and keyword_domains and target_family and keyword_family and (target_domains & keyword_domains):
            return True
    return False


def _requirement_is_covered(requirement: str, candidate_keywords: list[str], candidate_keyword_set: set[str]) -> bool:
    signals = _extract_keyword_signals(requirement)
    if signals:
        for signal in signals:
            lowered = signal.lower()
            if lowered in candidate_keyword_set or _supports_related_signal(lowered, candidate_keyword_set):
                return True
    requirement_lower = requirement.lower()
    for keyword in candidate_keywords:
        lowered = keyword.lower()
        if len(lowered) < 3:
            continue
        if lowered in requirement_lower:
            return True
    return False


def build_updated_resume_keywords(pack: object, jd_analysis: dict | None = None) -> list[str]:
    tailored_skills = getattr(pack, "tailored_skills", {}) or {}
    focus_areas = list(getattr(pack, "focus_areas", []) or [])
    title = _clean_keyword(getattr(pack, "tailored_title", ""))
    summary = _clean_keyword(getattr(pack, "tailored_summary", ""))
    experiences = list(getattr(pack, "tailored_experiences", []) or [])

    resume_lines = [title, summary]
    keyword_candidates: list[object] = []

    if isinstance(tailored_skills, dict):
        for values in tailored_skills.values():
            if isinstance(values, list):
                keyword_candidates.extend(values)
    keyword_candidates.extend(focus_areas)
    if title:
        keyword_candidates.append(title)

    for item in experiences:
        role = _clean_keyword(getattr(item, "role", ""))
        if role:
            keyword_candidates.append(role)
            resume_lines.append(role)
        for bullet in list(getattr(item, "bullets", []) or []):
            cleaned_bullet = _clean_keyword(bullet)
            if cleaned_bullet:
                resume_lines.append(cleaned_bullet)

    combined_resume_text = "\n".join(line for line in resume_lines if line)
    keyword_candidates.extend(_extract_keyword_signals(combined_resume_text))

    if jd_analysis:
        combined_resume_lower = combined_resume_text.lower()
        for keyword in list(jd_analysis.get("matched_keywords", [])) + list(jd_analysis.get("keyword_signals", [])):
            cleaned = _clean_keyword(keyword)
            if cleaned and cleaned.lower() in combined_resume_lower:
                keyword_candidates.append(cleaned)

    return _unique_keywords(keyword_candidates)


def analyze_jd(jd_text: str, candidate_keywords: list[str], application_url: str | None = None) -> dict:
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
    company = _extract_company(first_lines, application_url=application_url)
    role = _extract_role(first_lines, language)
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
    related_keyword_matches = []
    for keyword in keyword_signals:
        lowered = keyword.lower()
        if lowered in candidate_keyword_set:
            continue
        if _supports_related_signal(lowered, candidate_keyword_set):
            related_keyword_matches.append(keyword)

    missing_candidate_keywords = []
    for keyword in keyword_signals:
        lowered = keyword.lower()
        if lowered in candidate_keyword_set or keyword in related_keyword_matches:
            continue
        if keyword not in missing_candidate_keywords:
            missing_candidate_keywords.append(keyword)

    direct_signal_matches = [keyword for keyword in keyword_signals if keyword.lower() in candidate_keyword_set]
    weighted_signal_hits = len(direct_signal_matches) + (0.6 * len(related_keyword_matches))
    signal_ratio = weighted_signal_hits / max(len(keyword_signals), 1)
    covered_requirements = [
        requirement for requirement in top_requirements if _requirement_is_covered(requirement, actual_keywords, candidate_keyword_set)
    ]
    requirement_ratio = len(covered_requirements) / max(len(top_requirements), 1) if top_requirements else 0.0
    role_aligned = _has_role_alignment(role, actual_keywords)

    score = (signal_ratio * 55.0) + (requirement_ratio * 25.0)
    if role_aligned:
        score += 10.0
    if candidate_location and candidate_location in text_lower:
        score += 5.0
    if remote:
        score += 5.0

    return {
        "company": company,
        "role": role,
        "location": location,
        "language": language,
        "seniority": seniority if seniority else "unknown",
        "matched_keywords": matched_keywords,
        "related_keyword_matches": related_keyword_matches,
        "covered_keyword_signals": direct_signal_matches,
        "covered_requirements": covered_requirements,
        "role_aligned": role_aligned,
        "top_requirements": top_requirements,
        "keyword_signals": keyword_signals,
        "missing_candidate_keywords": missing_candidate_keywords,
        "remote": remote,
        "score": round(min(score, 100.0), 1),
    }
