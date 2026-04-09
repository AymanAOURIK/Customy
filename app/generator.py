from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

from app.models import ApplicationPack
from app.openai_usage import OpenAIUsageRecord, summarize_usage, usage_from_response
from app.targeting import is_credible_role_title, normalize_role_title, prioritize_candidate_skills, target_resume_concepts


PACK_RESPONSE_SCHEMA = {
    "name": "application_pack",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "resume_language",
            "detected_company",
            "tailored_title",
            "tailored_summary",
            "experience_orders",
            "tailored_skills",
            "cover_letter",
            "linkedin_message",
            "email_draft",
            "focus_areas",
            "detected_emails",
            "profile_update_hints",
        ],
        "properties": {
            "resume_language": {"type": "string"},
            "detected_company": {"type": "string"},
            "tailored_title": {"type": "string"},
            "tailored_summary": {"type": "string"},
            "experience_orders": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["company", "role", "bullet_indices", "tailored_bullets"],
                    "properties": {
                        "company": {"type": "string"},
                        "role": {"type": "string"},
                        "bullet_indices": {"type": "array", "items": {"type": "integer"}},
                        "tailored_bullets": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "tailored_skills": {
                "type": "object",
                "additionalProperties": False,
                "required": ["languages", "frameworks", "tools"],
                "properties": {
                    "languages": {"type": "array", "items": {"type": "string"}},
                    "frameworks": {"type": "array", "items": {"type": "string"}},
                    "tools": {"type": "array", "items": {"type": "string"}},
                },
            },
            "cover_letter": {"type": "string"},
            "linkedin_message": {"type": "string"},
            "email_draft": {"type": "string"},
            "focus_areas": {"type": "array", "items": {"type": "string"}},
            "detected_emails": {"type": "array", "items": {"type": "string"}},
            "profile_update_hints": {"type": "array", "items": {"type": "string"}},
        },
    },
}

MAPPING_SCHEMA = {
    "name": "requirement_mapping",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["mappings", "summary_anchor"],
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["requirement", "company", "bullet_index"],
                    "properties": {
                        "requirement": {"type": "string"},
                        "company": {"type": "string"},
                        "bullet_index": {"type": "integer"},
                    },
                },
            },
            "summary_anchor": {"type": "string"},
        },
    },
}

MAPPING_SYSTEM_PROMPT = (
    "You are a resume strategist. Map each key JD requirement to the single best-fit candidate bullet.\n\n"
    "Return JSON only:\n"
    '{"mappings":[{"requirement":"...","company":"...","bullet_index":1}],"summary_anchor":"..."}\n\n'
    "Rules:\n"
    "- bullet_index is 1-based (1 = first bullet of that company block)\n"
    "- Only include mappings where the candidate has real, traceable evidence\n"
    "- Cover at most the top 4 JD requirements\n"
    "- summary_anchor: one sentence describing the candidate's strongest overall capability relevant to this JD, "
    "then their single best proof metric. Prefer evidence from the most recent role unless an older role has "
    "significantly stronger proof. Never write as if the candidate works only at one company — the anchor must "
    "reflect the full career. Must be in the target resume language (fr or en).\n"
    "- Never invent tools, metrics, or outcomes not present in the candidate bullets"
)

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
FRENCH_MARKER_PATTERN = re.compile(r"\b(le|la|les|des|dans|avec|pour|vous|nous|poste|expérience|capacité|gestion|équipe|données)\b", re.IGNORECASE)
ENGLISH_MARKER_PATTERN = re.compile(
    r"\b(the|and|with|for|from|built|led|replaced|deployed|developed|saving|saved|processing|calls?|week|team|pipeline|handling|accuracy|avoided|costs?|boosted|cut|forecasted|reporting|time|throughput|delivery|months?|year|present)\b",
    re.IGNORECASE,
)
NUMERIC_FACT_PATTERN = re.compile(r"(?<!\w)(?:~?\$?\d[\d,]*(?:\.\d+)?(?:[KMBkmb])?\+?(?:%|x)?)(?!\w)")
TECH_TERM_PATTERN = re.compile(
    r"\b(?:LLM|RAG|LoRA|ChromaDB|OpenAI|LangChain|XGBoost|Power BI|FastAPI|Airflow|Docker|PostgreSQL|CI/CD|MLOps|DataOps|OCR|AWS|GCP|Azure|Kubernetes|Spark|Hadoop|NLP|TensorFlow|Scikit-learn)\b",
    re.IGNORECASE,
)
SUMMARY_BANNED_PHRASES = (
    "strong fit",
    "making me a strong fit",
    "en tant que",
    "applying for",
    "excited to apply",
    "i am excited",
    "ideal candidate",
    "perfect fit",
)
GENERIC_EMAIL_PHRASES = (
    "je vous écris pour exprimer mon intérêt",
    "je suis convaincu de pouvoir apporter une valeur ajoutée",
    "merci pour votre considération",
    "i am writing to express my interest",
    "i am confident i can bring value",
    "thank you for your consideration",
)
GENERIC_LINKEDIN_PHRASES = (
    "je suis ayman",
    "expérience significative",
    "je suis très intéressé",
    "je pense pouvoir apporter de la valeur",
    "opportunités chez",
    "i am excited about",
    "i am eager to contribute",
    "add value to your team",
    "let's connect to discuss how i can add value",
)
COVER_LETTER_BANNED_PHRASES = (
    "i am excited to apply",
    "excited to apply",
    "i believe i would be a great fit",
    "great fit",
    "perfect fit",
    "strong fit",
    "je suis enthousiaste a l'idee de postuler",
    "je suis enthousiaste à l'idée de postuler",
    "je serais un excellent choix",
    "excellent choix",
)
COVER_LETTER_CULTURE_TERMS = (
    "doer",
    "mentor",
    "pragmatist",
    "pragmatic",
    "builder",
    "hands-on",
    "ownership",
    "owner",
    "autonomy",
    "autonomous",
    "rigor",
    "rigorous",
    "collaboration",
    "collaborative",
    "curiosity",
    "humble",
    "humility",
    "stakeholder communication",
    "cross-functional",
    "pragmatique",
    "autonomie",
    "autonome",
    "rigueur",
    "execution",
    "delivery-focused",
)
CONTENT_TOKEN_STOPWORDS = {
    "avec",
    "dans",
    "from",
    "pour",
    "that",
    "this",
    "using",
    "used",
    "build",
    "built",
    "lead",
    "led",
    "role",
    "team",
    "data",
    "jobs",
    "plus",
    "pour",
    "avec",
    "from",
    "into",
    "your",
    "vous",
    "nous",
    "their",
    "they",
    "them",
    "have",
    "has",
    "dans",
    "from",
    "with",
    "what",
    "when",
    "where",
    "were",
    "will",
}
ROOT_PAYLOAD_KEYS = ("pack", "application_pack", "result", "data")
RESUME_LANGUAGE_KEYS = ("resume_language", "language", "output_language")
TAILORED_TITLE_KEYS = ("tailored_title", "target_title", "resume_title", "header_title")
TAILORED_SUMMARY_KEYS = ("tailored_summary", "summary", "professional_summary", "profile_summary")
EXPERIENCE_ORDER_KEYS = ("experience_orders", "bullet_orders", "experience_priority")
TAILORED_EXPERIENCE_KEYS = (
    "tailored_experiences",
    "experiences",
    "experience",
    "relevant_experiences",
    "resume_experiences",
)
TAILORED_SKILLS_KEYS = ("tailored_skills", "skills", "prioritized_skills", "skill_priorities")
FOCUS_AREA_KEYS = ("focus_areas", "highlights", "matching_points")
EMAIL_KEYS = ("detected_emails", "emails", "extracted_emails")
PROFILE_UPDATE_HINT_KEYS = ("profile_update_hints", "candidate_update_hints", "profile_notes", "profile_review")
DETECTED_COMPANY_KEYS = ("detected_company",)
SUMMARY_SENTENCE_MIN = 2
SUMMARY_SENTENCE_MAX = 3
TEXT_FIELD_ALIASES = {
    "cover_letter": ("cover_letter", "coverLetter"),
    "linkedin_message": ("linkedin_message", "linkedin_msg", "linkedinMessage"),
    "email_draft": ("email_draft", "emailDraft", "outreach_email"),
}
EXPERIENCE_FIELD_ALIASES = {
    "company": ("company", "employer", "organization"),
    "role": ("role", "title", "position"),
    "start": ("start", "start_date", "from"),
    "end": ("end", "end_date", "to"),
    "bullets": ("bullets", "highlights", "achievements"),
    "bullet_indices": ("bullet_indices", "bulletIndexes", "indices", "order"),
    "tailored_bullets": ("tailored_bullets", "rewritten_bullets", "localized_bullets", "bullets_rewritten"),
}


class PackGenerationError(ValueError):
    def __init__(self, message: str, usage_summary: dict | None = None) -> None:
        super().__init__(message)
        self.usage_summary = usage_summary or summarize_usage([])


def _get_generation_model(config: dict) -> str:
    return config["llm"].get("generation_model", config["llm"].get("model", "gpt-4.1"))


def _get_analysis_model(config: dict) -> str:
    return config["llm"].get("analysis_model", config["llm"].get("model", "gpt-4o-mini"))


def _load_prompt(config: dict) -> str:
    prompt_path = Path(config["paths"]["prompts_dir"]) / "system.md"
    return prompt_path.read_text(encoding="utf-8")


def _candidate_payload(candidate_context: dict) -> dict:
    return {
        "name": candidate_context.get("personal", {}).get("name", ""),
        "headline": candidate_context.get("headline", ""),
        "summary": candidate_context.get("summary", ""),
        "skills": {
            "languages": list(candidate_context.get("skills", {}).get("languages", [])),
            "frameworks": list(candidate_context.get("skills", {}).get("frameworks", [])),
            "tools": list(candidate_context.get("skills", {}).get("tools", [])),
            "soft": list(candidate_context.get("skills", {}).get("soft", [])),
        },
        "experiences": list(candidate_context.get("experiences", [])),
        "education": list(candidate_context.get("education", [])),
        "spoken_languages": list(candidate_context.get("spoken_languages", [])),
    }


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _first_present(data: dict, keys: tuple[str, ...]) -> object:
    for key in keys:
        value = data.get(key)
        if _has_value(value):
            return value
    return None


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _term_matches_text(text: str, term: str) -> bool:
    cleaned_term = _clean_text(term)
    if not cleaned_term:
        return False
    escaped = re.escape(cleaned_term)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ./+_-]*[A-Za-z0-9]", cleaned_term):
        pattern = rf"(?<!\w){escaped}(?!\w)"
    else:
        pattern = escaped
    return re.search(pattern, str(text or ""), flags=re.IGNORECASE) is not None


def _normalize_detected_company(payload: dict) -> str | None:
    company = _clean_text(_first_present(payload, DETECTED_COMPANY_KEYS))
    if not company:
        return None
    lowered = company.lower().strip(" .,:;|-")
    if lowered in {"unknown", "unknown company", "company", "n/a", "none", "not provided"}:
        return None
    return company.strip(" .,:;|-")


def _sentence_chunks(text: object) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [part.strip() for part in parts if part.strip()]


def _paragraph_chunks(text: object) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    return [_clean_text(part) for part in re.split(r"\n\s*\n", raw) if _clean_text(part)]


def _word_count(text: object) -> int:
    cleaned = _clean_text(text)
    if not cleaned:
        return 0
    return len(re.findall(r"\S+", cleaned))


def _content_tokens(text: object) -> set[str]:
    tokens = set()
    for token in re.findall(r"[A-Za-zÀ-ÿ]{4,}", _clean_text(text).lower()):
        if token in CONTENT_TOKEN_STOPWORDS:
            continue
        tokens.add(token)
    return tokens


def _join_phrases(phrases: list[str], resume_language: str) -> str:
    cleaned = [_clean_text(item).strip(" .,:;") for item in phrases if _clean_text(item)]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} {'et' if resume_language == 'fr' else 'and'} {cleaned[1]}"
    if resume_language == "fr":
        return ", ".join(cleaned[:-1]) + f" et {cleaned[-1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"


def _natural_culture_phrase(term: str, resume_language: str) -> str:
    cleaned = _clean_text(term).strip(" .,:;").lower()
    if not cleaned:
        return ""
    if resume_language == "fr":
        mapping = {
            "mentor": "le mentorat",
            "pragmatique": "le pragmatisme",
            "autonomie": "l'autonomie",
            "autonome": "l'autonomie",
            "rigueur": "la rigueur",
            "execution": "l'exécution",
            "delivery-focused": "une exécution orientée résultat",
            "cross-functional": "la collaboration cross-fonctionnelle",
            "stakeholder communication": "la communication avec les parties prenantes",
        }
        return mapping.get(cleaned, cleaned)
    mapping = {
        "doer": "a doer mindset",
        "mentor": "mentoring",
        "pragmatic": "pragmatism",
        "pragmatist": "pragmatism",
        "builder": "building from scratch",
        "hands-on": "a hands-on style",
        "ownership": "ownership",
        "owner": "ownership",
        "autonomy": "autonomy",
        "autonomous": "autonomy",
        "rigor": "rigor",
        "rigorous": "rigor",
        "cross-functional": "cross-functional collaboration",
        "stakeholder communication": "stakeholder communication",
        "delivery-focused": "delivery-focused execution",
    }
    return mapping.get(cleaned, cleaned)


def _ensure_sentence(text: object) -> str:
    cleaned = _clean_text(text)
    if cleaned and cleaned[-1] not in ".!?":
        return cleaned + "."
    return cleaned


def _summary_has_target_length(text: object) -> bool:
    count = len(_sentence_chunks(text))
    return SUMMARY_SENTENCE_MIN <= count <= SUMMARY_SENTENCE_MAX


def _clean_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        text = _clean_text(item)
        if text:
            cleaned.append(text)
    return cleaned


def _unique_text_list(items: list[str]) -> list[str]:
    ordered = []
    seen = set()
    for item in items:
        key = item.lower()
        if not item or key in seen:
            continue
        ordered.append(item)
        seen.add(key)
    return ordered


def _unwrap_payload(payload: object) -> dict:
    current = payload if isinstance(payload, dict) else {}
    while True:
        nested = None
        for key in ROOT_PAYLOAD_KEYS:
            candidate = current.get(key)
            if isinstance(candidate, dict):
                nested = candidate
                break
        if nested is None:
            return current
        current = nested


def _normalize_match_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean_text(value).lower()).strip()


def _normalized_fact_token(value: str) -> str:
    return re.sub(r"[^a-z0-9%+/$]+", "", value.lower())


def _extract_fact_tokens(text: str) -> tuple[set[str], set[str]]:
    metrics = {_normalized_fact_token(match.group(0)) for match in NUMERIC_FACT_PATTERN.finditer(text or "")}
    terms = {_normalize_match_key(match.group(0)) for match in TECH_TERM_PATTERN.finditer(text or "")}
    return metrics, terms


def _bullet_rewrite_is_safe(source_bullet: str, rewritten_bullet: str) -> bool:
    source_metrics, source_terms = _extract_fact_tokens(source_bullet)
    rewritten_metrics, rewritten_terms = _extract_fact_tokens(rewritten_bullet)
    if source_metrics and not source_metrics.issubset(rewritten_metrics):
        return False
    if rewritten_metrics and not rewritten_metrics.issubset(source_metrics):
        return False
    if source_terms and not source_terms.issubset(rewritten_terms):
        return False
    return True


def _resume_language(jd_analysis: dict) -> str:
    return "fr" if _clean_text(jd_analysis.get("language")).lower() == "fr" else "en"


def _contains_banned_phrase(text: str) -> bool:
    lowered = _clean_text(text).lower()
    return any(phrase in lowered for phrase in SUMMARY_BANNED_PHRASES)


def _looks_like_french(text: str) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return False
    if any(char in cleaned for char in "àâçéèêëîïôùûüÿœ"):
        return True
    return len(FRENCH_MARKER_PATTERN.findall(cleaned)) >= 3


def _looks_like_english(text: str) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return False
    return len(ENGLISH_MARKER_PATTERN.findall(cleaned)) >= 3


def _text_conflicts_with_language(text: str, resume_language: str) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return False
    looks_french = _looks_like_french(cleaned)
    looks_english = _looks_like_english(cleaned)
    if resume_language == "fr":
        return looks_english and not looks_french
    return looks_french and not looks_english


def _text_matches_language(text: str, resume_language: str) -> bool:
    if not _clean_text(text):
        return False
    if _text_conflicts_with_language(text, resume_language):
        return False
    if resume_language == "fr":
        return _looks_like_french(text) or not _looks_like_english(text)
    return not _looks_like_french(text)


def _candidate_years_experience(candidate_context: dict) -> int:
    starts = []
    for item in candidate_context.get("experiences", []):
        match = re.fullmatch(r"(\d{4})-(\d{2})", _clean_text((item or {}).get("start")))
        if match:
            starts.append((int(match.group(1)), int(match.group(2))))
    if not starts:
        return 0
    year, month = min(starts)
    months = max((date.today().year - year) * 12 + (date.today().month - month), 0)
    return max(months // 12, 0)


def _experience_year_label(candidate_context: dict, resume_language: str) -> str:
    years = _candidate_years_experience(candidate_context)
    years = max(years, 1)
    if resume_language == "fr":
        return f"{years}+ ans"
    return f"{years}+ years"


def _find_fallback_experience(raw_item: object, fallback_items: list[dict], index: int) -> dict | None:
    source = raw_item if isinstance(raw_item, dict) else {}
    source_company = _normalize_match_key(_first_present(source, EXPERIENCE_FIELD_ALIASES["company"]))
    source_role = _normalize_match_key(_first_present(source, EXPERIENCE_FIELD_ALIASES["role"]))

    for candidate in fallback_items:
        if source_company and source_company != _normalize_match_key(candidate.get("company")):
            continue
        if source_role and source_role != _normalize_match_key(candidate.get("role")):
            continue
        return candidate

    if 0 <= index < len(fallback_items):
        return fallback_items[index]
    return None


def _resolve_bullet_indices(raw_indices: object, bullet_count: int) -> list[int]:
    if not isinstance(raw_indices, list):
        return []

    cleaned_indices = []
    for item in raw_indices:
        try:
            cleaned_indices.append(int(item))
        except (TypeError, ValueError):
            continue

    if not cleaned_indices:
        return []

    zero_based = any(index == 0 for index in cleaned_indices)
    resolved = []
    seen = set()
    for index in cleaned_indices:
        normalized = index if zero_based else index - 1
        if normalized < 0 or normalized >= bullet_count or normalized in seen:
            continue
        resolved.append(normalized)
        seen.add(normalized)
    return resolved


def _match_bullet_order_from_texts(raw_bullets: object, fallback_bullets: list[str]) -> list[int]:
    if not isinstance(raw_bullets, list):
        return []

    normalized_fallback = [_normalize_match_key(item) for item in fallback_bullets]
    order = []
    seen = set()
    for bullet in raw_bullets:
        target = _normalize_match_key(bullet)
        if not target:
            continue
        for index, fallback_value in enumerate(normalized_fallback):
            if index in seen:
                continue
            if target == fallback_value:
                order.append(index)
                seen.add(index)
                break
    return order


def _reorder_bullets(fallback_bullets: list[str], preferred_order: list[int]) -> list[str]:
    if not fallback_bullets:
        return []

    ordered = []
    seen = set()
    for index in preferred_order:
        if index in seen or index < 0 or index >= len(fallback_bullets):
            continue
        ordered.append(_clean_text(fallback_bullets[index]))
        seen.add(index)

    for index, bullet in enumerate(fallback_bullets):
        if index in seen:
            continue
        ordered.append(_clean_text(bullet))
    return [bullet for bullet in ordered if bullet]


def _experience_bullets_for_language(item: dict, resume_language: str) -> list[str]:
    base_bullets = _clean_text_list((item or {}).get("bullets"))
    if resume_language != "fr":
        return base_bullets
    localized_bullets = _clean_text_list((item or {}).get("bullets_fr"))
    if len(localized_bullets) == len(base_bullets):
        return localized_bullets
    return base_bullets


def _cover_letter_focus_phrases(jd_analysis: dict) -> list[str]:
    phrases = []
    seen = set()
    for item in (
        list(jd_analysis.get("top_requirements", []))
        + list(jd_analysis.get("keyword_signals", []))
        + list(jd_analysis.get("matched_keywords", []))
    ):
        cleaned = _clean_text(item).strip(" .,:;")
        if not cleaned or len(cleaned.split()) > 8:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        phrases.append(cleaned)
        seen.add(key)
        if len(phrases) >= 5:
            break
    role = _clean_text(jd_analysis.get("role"))
    if role and not phrases:
        phrases.append(role)
    return phrases


def _cover_letter_culture_phrases(jd_analysis: dict, jd_text: str) -> list[str]:
    lowered_jd = _clean_text(jd_text).lower()
    phrases = []
    seen = set()
    for term in COVER_LETTER_CULTURE_TERMS:
        if term in lowered_jd and term not in seen:
            phrases.append(term)
            seen.add(term)
        if len(phrases) >= 3:
            return phrases
    for phrase in _cover_letter_focus_phrases(jd_analysis):
        lowered_phrase = phrase.lower()
        if not any(term in lowered_phrase for term in COVER_LETTER_CULTURE_TERMS):
            continue
        if lowered_phrase in seen:
            continue
        phrases.append(phrase)
        seen.add(lowered_phrase)
        if len(phrases) >= 3:
            break
    return phrases


def _select_cover_letter_proof_bullets(candidate_context: dict, jd_analysis: dict, resume_language: str) -> list[str]:
    signal_phrases = [
        _clean_text(item).lower()
        for item in (
            list(jd_analysis.get("top_requirements", []))
            + list(jd_analysis.get("keyword_signals", []))
            + list(jd_analysis.get("matched_keywords", []))
            + [_clean_text(jd_analysis.get("role"))]
        )
        if _clean_text(item)
    ]
    signal_tokens = set()
    for phrase in signal_phrases:
        signal_tokens.update(_content_tokens(phrase))

    ranked = []
    for experience_index, item in enumerate(candidate_context.get("experiences", []) or []):
        for bullet in _experience_bullets_for_language(item, resume_language):
            cleaned = _clean_text(bullet)
            if not cleaned:
                continue
            lowered = cleaned.lower()
            metric_count = len(NUMERIC_FACT_PATTERN.findall(cleaned))
            phrase_hits = sum(1 for phrase in signal_phrases if phrase and phrase in lowered)
            token_hits = len(signal_tokens & _content_tokens(cleaned))
            score = (metric_count * 6) + (phrase_hits * 4) + token_hits
            if experience_index == 0:
                score += 1
            ranked.append((score, metric_count, len(cleaned), _ensure_sentence(cleaned)))

    ordered = []
    seen = set()
    for _, _, _, bullet in sorted(ranked, key=lambda item: (-item[0], -item[1], item[2])):
        key = bullet.lower()
        if key in seen:
            continue
        ordered.append(bullet)
        seen.add(key)

    metric_bullets = [bullet for bullet in ordered if NUMERIC_FACT_PATTERN.search(bullet)]
    selected = metric_bullets[:3] if len(metric_bullets) >= 2 else ordered[:3]
    if len(selected) > 2 and sum(_word_count(item) for item in selected) > 55:
        selected = selected[:2]
    for candidate in ordered:
        if len(selected) >= 2:
            break
        if candidate not in selected:
            selected.append(candidate)
    return selected[:3]


def _cover_letter_has_expected_structure(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if re.search(r"(?m)^\s*(?:[-*•#]|\d+\.)\s+", raw):
        return False
    paragraphs = _paragraph_chunks(raw)
    if len(paragraphs) != 4:
        return False
    if len(_sentence_chunks(paragraphs[-1])) != 1:
        return False
    if _word_count(raw) > 200:
        return False
    return len(NUMERIC_FACT_PATTERN.findall(raw)) >= 2


def _cover_letter_is_generic(text: str) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return True
    lowered = cleaned.lower()
    return any(phrase in lowered for phrase in COVER_LETTER_BANNED_PHRASES)


def _build_fallback_cover_letter(
    candidate_context: dict,
    jd_analysis: dict,
    jd_text: str,
    resume_language: str,
) -> str:
    company = _clean_text(jd_analysis.get("company"))
    role = _preferred_email_role(jd_analysis, resume_language)
    focus_phrases = _cover_letter_focus_phrases(jd_analysis)[:3]
    if not focus_phrases and role:
        focus_phrases = [role]
    culture_phrases = _cover_letter_culture_phrases(jd_analysis, jd_text)[:3]
    proofs = _select_cover_letter_proof_bullets(candidate_context, jd_analysis, resume_language)[:2]
    focus_text = _join_phrases(focus_phrases, resume_language)
    culture_text = _join_phrases(
        [_natural_culture_phrase(item, resume_language) for item in culture_phrases if _natural_culture_phrase(item, resume_language)],
        resume_language,
    )
    closing_focus = focus_phrases[0] if focus_phrases else (role or ("ce périmètre" if resume_language == "fr" else "this scope"))
    proof_paragraph = " ".join(proofs).strip()

    if resume_language == "fr":
        focus_target = focus_text or "la livraison de systèmes utiles en production"
        culture_text = culture_text or "ownership, pragmatisme et exécution"
        first = (
            f"Je construis des systèmes data et IA de production qui remplacent une charge manuelle réelle, et l'accent mis par {company} sur {focus_target} correspond exactement au type de problème que j'aime prendre en main."
            if company
            else f"Je construis des systèmes data et IA de production qui remplacent une charge manuelle réelle, et votre focus sur {focus_target} correspond exactement au type de problème que j'aime prendre en main."
        )
        second = proof_paragraph or (
            "J'ai livré des systèmes de production qui automatisent des workflows critiques, réduisent les coûts et améliorent la qualité opérationnelle."
        )
        third = (
            f"L'accent mis sur {culture_text} correspond à ma façon de travailler : exécution directe, arbitrages pragmatiques et collaboration fluide avec les équipes métier et techniques."
        )
        fourth = (
            f"J'apprécie particulièrement la manière dont {company} cadre {closing_focus} comme un vrai sujet opérationnel."
            if company
            else f"J'apprécie particulièrement la manière dont le poste cadre {closing_focus} comme un vrai sujet opérationnel."
        )
    else:
        focus_target = focus_text or "shipping useful production systems"
        culture_text = culture_text or "ownership, pragmatism, and execution"
        first = (
            f"I build production AI and data systems that remove real manual workload, and {company}'s focus on {focus_target} is exactly the kind of operating problem I like to own."
            if company
            else f"I build production AI and data systems that remove real manual workload, and your focus on {focus_target} is exactly the kind of operating problem I like to own."
        )
        second = proof_paragraph or (
            "I have shipped production systems that automate critical workflows, reduce costs, and improve operational quality."
        )
        third = (
            f"The emphasis on {culture_text} matches how I work: direct execution, clear tradeoffs, and steady collaboration with engineers and stakeholders."
        )
        fourth = (
            f"What stands out about {company} is the way you frame {closing_focus} as a real operating problem."
            if company
            else f"What stands out about the role is the way it frames {closing_focus} as a real operating problem."
        )

    paragraphs = [first, second, third, fourth]
    return "\n\n".join(_clean_text(paragraph) for paragraph in paragraphs if _clean_text(paragraph))


def _normalize_tailored_bullets(
    source_bullets: list[str],
    preferred_order: list[int],
    raw_tailored_bullets: object,
    resume_language: str,
) -> list[str]:
    ordered_source = _reorder_bullets(source_bullets, preferred_order)
    rewritten = _clean_text_list(raw_tailored_bullets)
    if len(rewritten) != len(ordered_source):
        return ordered_source

    normalized = []
    for source_bullet, rewritten_bullet in zip(ordered_source, rewritten):
        if (
            not rewritten_bullet
            or not _bullet_rewrite_is_safe(source_bullet, rewritten_bullet)
            or _text_conflicts_with_language(rewritten_bullet, resume_language)
        ):
            normalized.append(source_bullet)
            continue
        normalized.append(rewritten_bullet)
    return normalized


def _experience_start_sort_key(item: dict) -> tuple[int, int]:
    start = _clean_text((item or {}).get("start", ""))
    match = re.fullmatch(r"(\d{4})-(\d{2})", start)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (0, 0)


def _experience_identity(item: dict) -> tuple[str, str, str, str]:
    return (
        _normalize_match_key((item or {}).get("company")),
        _normalize_match_key((item or {}).get("role")),
        _clean_text((item or {}).get("start")),
        _clean_text((item or {}).get("end")),
    )


def _normalize_experiences(payload: dict, candidate_context: dict, resume_language: str) -> list[dict]:
    fallback_items = list(candidate_context.get("experiences", []))
    raw_orders = _first_present(payload, EXPERIENCE_ORDER_KEYS)
    raw_items = raw_orders if isinstance(raw_orders, list) and raw_orders else _first_present(payload, TAILORED_EXPERIENCE_KEYS)
    raw_items = raw_items if isinstance(raw_items, list) and raw_items else fallback_items

    normalized = []
    for index, item in enumerate(raw_items):
        fallback_item = _find_fallback_experience(item, fallback_items, index)
        if not fallback_item:
            continue
        source = item if isinstance(item, dict) else {}
        original_bullets = _clean_text_list(fallback_item.get("bullets"))
        localized_bullets = _experience_bullets_for_language(fallback_item, resume_language)
        preferred_order = _resolve_bullet_indices(_first_present(source, EXPERIENCE_FIELD_ALIASES["bullet_indices"]), len(original_bullets))
        if not preferred_order:
            preferred_order = _match_bullet_order_from_texts(_first_present(source, EXPERIENCE_FIELD_ALIASES["bullets"]), original_bullets)
        if not preferred_order and localized_bullets != original_bullets:
            preferred_order = _match_bullet_order_from_texts(_first_present(source, EXPERIENCE_FIELD_ALIASES["bullets"]), localized_bullets)
        raw_tailored_bullets = _first_present(source, EXPERIENCE_FIELD_ALIASES["tailored_bullets"])
        normalized_item = {
            "company": _clean_text(fallback_item.get("company")),
            "role": _clean_text(fallback_item.get("role")),
            "start": _clean_text(fallback_item.get("start")),
            "end": _clean_text(fallback_item.get("end")),
            "bullets": _normalize_tailored_bullets(localized_bullets, preferred_order, raw_tailored_bullets, resume_language)
            if isinstance(raw_tailored_bullets, list)
            else _reorder_bullets(localized_bullets, preferred_order),
        }
        if normalized_item["company"] and normalized_item["role"] and normalized_item["bullets"]:
            normalized.append(normalized_item)

    if normalized:
        seen_experiences = {_experience_identity(item) for item in normalized}
        for fallback_item in fallback_items:
            identity = _experience_identity(fallback_item)
            if identity in seen_experiences:
                continue
            bullets = _experience_bullets_for_language(fallback_item, resume_language)
            if not bullets:
                continue
            normalized.append(
                {
                    "company": _clean_text(fallback_item.get("company")),
                    "role": _clean_text(fallback_item.get("role")),
                    "start": _clean_text(fallback_item.get("start")),
                    "end": _clean_text(fallback_item.get("end")),
                    "bullets": bullets,
                }
            )
            seen_experiences.add(identity)
        normalized.sort(key=_experience_start_sort_key, reverse=True)
        return normalized

    fallback_normalized = []
    for item in fallback_items:
        bullets = _experience_bullets_for_language(item, resume_language)
        if not bullets:
            continue
        fallback_normalized.append(
            {
                "company": _clean_text(item.get("company")),
                "role": _clean_text(item.get("role")),
                "start": _clean_text(item.get("start")),
                "end": _clean_text(item.get("end")),
                "bullets": bullets,
            }
        )
    return fallback_normalized


def _normalize_skills(payload: dict, candidate_context: dict, jd_analysis: dict) -> dict:
    del payload
    return prioritize_candidate_skills(candidate_context, jd_analysis)


def _collect_detected_emails(jd_text: str, payload: dict) -> list[str]:
    detected = _clean_text_list(_first_present(payload, EMAIL_KEYS))
    seen = {item.lower() for item in detected}
    for match in EMAIL_PATTERN.findall(jd_text or ""):
        cleaned = match.strip()
        if cleaned.lower() not in seen:
            detected.append(cleaned)
            seen.add(cleaned.lower())
    return detected


def _build_fallback_title(candidate_context: dict, jd_analysis: dict, resume_language: str) -> str:
    preferred = normalize_role_title(jd_analysis.get("role"), resume_language)
    if is_credible_role_title(preferred):
        return preferred
    headline = normalize_role_title(candidate_context.get("headline"), resume_language)
    if is_credible_role_title(headline):
        return headline
    experiences = candidate_context.get("experiences") or []
    if experiences:
        fallback_role = normalize_role_title((experiences[0] or {}).get("role"), resume_language)
        if is_credible_role_title(fallback_role):
            return fallback_role
    return "Lead Tech Data & IA" if resume_language == "fr" else "AI & Data Lead"


def _build_fallback_summary(candidate_context: dict, jd_analysis: dict, resume_language: str, title: str) -> str:
    years_label = _experience_year_label(candidate_context, resume_language)
    seniority = _clean_text(jd_analysis.get("seniority")).lower()
    leadership = seniority == "lead" or "lead" in title.lower()
    if resume_language == "fr":
        if leadership:
            return (
                f"{title} avec {years_label} d'expérience dans la mise en production de systèmes data et IA à impact opérationnel mesurable. "
                "Je pilote la livraison du cadrage à la production, j'encadre des équipes techniques et je privilégie des systèmes fiables qui remplacent une charge manuelle réelle avec des arbitrages solides entre impact, coût et maintenabilité."
            )
        return (
            f"Professionnel Data & IA avec {years_label} d'expérience dans la conception et le déploiement de systèmes de production liés à des résultats métier mesurables. "
            "Je transforme les besoins métier en modèles, pipelines et automatisations exploitables en production, avec un focus sur l'exécution concrète, la qualité opérationnelle et la réduction durable de la charge manuelle."
        )
    if leadership:
        return (
            f"{title} with {years_label} of experience shipping production data and AI systems tied to measurable operational impact. "
            "I lead engineers, drive delivery from scoping through production, and focus on reliable systems that replace real manual workload with clear tradeoffs across impact, cost, and maintainability."
        )
    return (
        f"Data and AI professional with {years_label} of experience designing and deploying production systems tied to measurable business outcomes. "
        "I turn business needs into reliable models, pipelines, and automation that teams can operate in production, with a focus on practical delivery, operational quality, and reducing manual workload."
    )


def _summary_bridge_sentence(concepts: list[str], resume_language: str) -> str:
    cleaned = [_clean_text(item).strip(" .,:;") for item in concepts if _clean_text(item)]
    if not cleaned:
        return ""

    lowered = {item.lower() for item in cleaned}
    agent_pair = {"agents ia", "orchestration d'agents"} if resume_language == "fr" else {"ai agents", "agent orchestration"}
    remaining = [item for item in cleaned if item.lower() not in agent_pair]

    if agent_pair.issubset(lowered):
        lead = "les agents IA et leur orchestration" if resume_language == "fr" else "AI agents and their orchestration"
        tail = _join_phrases(remaining, resume_language)
        if resume_language == "fr":
            if tail:
                return f"Mon expérience couvre {lead}, {tail}, ainsi que des intégrations d'API IA livrées en production."
            return f"Mon expérience couvre {lead}, ainsi que des intégrations d'API IA livrées en production."
        if tail:
            return f"My experience covers {lead}, {tail}, along with production AI API integrations."
        return f"My experience covers {lead}, along with production AI API integrations."

    joined = _join_phrases(cleaned, resume_language)
    if resume_language == "fr":
        return f"Mon expérience couvre {joined} et leur mise en production sur des workflows métier réels."
    return f"My experience covers {joined} in production across real business workflows."


def _align_summary_to_jd(summary: str, candidate_context: dict, jd_analysis: dict, resume_language: str) -> str:
    cleaned_summary = _clean_text(summary)
    concepts = target_resume_concepts(candidate_context, jd_analysis, resume_language=resume_language, limit=3)
    if not cleaned_summary or not concepts:
        return cleaned_summary

    missing = [item for item in concepts if not _term_matches_text(cleaned_summary, item)]
    if not missing:
        return cleaned_summary

    bridge_sentence = _summary_bridge_sentence(missing[:3], resume_language)
    if not bridge_sentence:
        return cleaned_summary

    sentences = _sentence_chunks(cleaned_summary)
    if len(sentences) >= SUMMARY_SENTENCE_MAX:
        sentences[-1] = bridge_sentence
    else:
        sentences.append(bridge_sentence)
    candidate = " ".join(sentences[:SUMMARY_SENTENCE_MAX])
    return candidate if _summary_has_target_length(candidate) else cleaned_summary


def _normalize_summary(model_summary: object, candidate_context: dict, jd_analysis: dict, resume_language: str, title: str) -> str:
    summary = _clean_text(model_summary)
    if (
        summary
        and not _contains_banned_phrase(summary)
        and _text_matches_language(summary, resume_language)
        and _summary_has_target_length(summary)
    ):
        return _align_summary_to_jd(summary, candidate_context, jd_analysis, resume_language)
    return _align_summary_to_jd(_build_fallback_summary(candidate_context, jd_analysis, resume_language, title), candidate_context, jd_analysis, resume_language)


def _email_is_generic(text: str) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return True
    lowered = cleaned.lower()
    if any(phrase in lowered for phrase in GENERIC_EMAIL_PHRASES):
        return True
    return len(NUMERIC_FACT_PATTERN.findall(cleaned)) < 2


def _linkedin_is_generic(text: str, resume_language: str) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return True
    lowered = cleaned.lower()
    if any(phrase in lowered for phrase in GENERIC_LINKEDIN_PHRASES):
        return True
    if len(cleaned) > 420:
        return True
    if len(cleaned.split()) < 12:
        return True
    metric_count = len(NUMERIC_FACT_PATTERN.findall(cleaned))
    if resume_language == "fr":
        if "bonjour" not in lowered:
            return True
        return metric_count < 1
    return metric_count < 1


def _email_has_expected_structure(text: str, resume_language: str) -> bool:
    raw = str(text or "")
    lowered = raw.lower()
    if resume_language == "fr":
        stack_hits = sum(1 for token in ("python", "fastapi", "docker", "airflow", "postgresql") if token in lowered)
        return (
            ("objet :" in lowered or "subject:" in lowered)
            and "bonjour" in lowered
            and "quelques exemples concrets" in lowered
            and raw.count("•") >= 3
            and stack_hits >= 3
            and "cordialement" in lowered
        )
    stack_hits = sum(1 for token in ("python", "fastapi", "docker", "airflow", "postgresql") if token in lowered)
    return (
        "hello" in lowered
        and raw.count("•") >= 3
        and stack_hits >= 3
        and ("best regards" in lowered or "regards" in lowered)
    )


def _find_experience(candidate_context: dict, company: str, role: str) -> dict | None:
    company_key = _normalize_match_key(company)
    role_key = _normalize_match_key(role)
    for item in candidate_context.get("experiences", []):
        if company_key != _normalize_match_key((item or {}).get("company")):
            continue
        if role_key != _normalize_match_key((item or {}).get("role")):
            continue
        return item
    return None


def _select_email_proof_bullets(candidate_context: dict, resume_language: str) -> list[str]:
    experiences = candidate_context.get("experiences", []) or []
    candidates = []
    for item in experiences:
        localized = _experience_bullets_for_language(item, resume_language)
        for bullet in localized:
            lowered = bullet.lower()
            score = 0
            if "lead" in lowered or "dirig" in lowered or "équipe" in lowered or "engineers" in lowered or "ingénieurs" in lowered:
                score += 4
            if "$" in bullet or "gpu" in lowered or "cost" in lowered or "coût" in lowered:
                score += 4
            if "llm" in lowered or "ai" in lowered or "ia" in lowered:
                score += 3
            if "%" in bullet or "~" in bullet or "2m+" in lowered or "20k" in lowered or "80k" in lowered or "2,400" in bullet:
                score += 2
            candidates.append((score, bullet))

    ordered = []
    seen = set()
    for _, bullet in sorted(candidates, key=lambda item: item[0], reverse=True):
        key = bullet.lower()
        if key in seen:
            continue
        ordered.append(bullet)
        seen.add(key)
        if len(ordered) >= 3:
            break
    return ordered


def _find_localized_bullet(
    candidate_context: dict,
    resume_language: str,
    company: str,
    role: str,
    *patterns: str,
) -> str:
    experience = _find_experience(candidate_context, company, role)
    if not experience:
        return ""
    bullets = _experience_bullets_for_language(experience, resume_language)
    normalized_patterns = [pattern.lower() for pattern in patterns if pattern]
    for bullet in bullets:
        lowered = bullet.lower()
        if all(pattern in lowered for pattern in normalized_patterns):
            return bullet
    return ""


def _email_years_label(candidate_context: dict, resume_language: str) -> str:
    years = max(_candidate_years_experience(candidate_context), 1)
    if resume_language == "fr":
        return "1 an" if years == 1 else f"{years} ans"
    return "1 year" if years == 1 else f"{years} years"


def _format_contact_phone(phone: str) -> str:
    cleaned = _clean_text(phone)
    digits = re.sub(r"\D+", "", cleaned)
    if cleaned.startswith("+") and digits.startswith("212") and len(digits) == 12:
        return f"+212 {digits[3:6]} {digits[6:9]} {digits[9:12]}"
    return cleaned


def _first_person_fr(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered.startswith(("j'ai ", "je ")):
        return cleaned
    return "J'ai " + cleaned[0].lower() + cleaned[1:]


def _preferred_email_role(jd_analysis: dict, resume_language: str) -> str:
    role = normalize_role_title(jd_analysis.get("role"), resume_language)
    combined = " ".join(
        _clean_text(item)
        for item in (
            [role]
            + list(jd_analysis.get("matched_keywords", []))
            + list(jd_analysis.get("keyword_signals", []))
            + list(jd_analysis.get("top_requirements", []))
            + list(jd_analysis.get("missing_candidate_keywords", []))
        )
    ).lower()
    if role and "data" in role.lower() and "ai" not in role.lower() and "ia" not in role.lower() and (" ai" in combined or "/ ai" in combined or "ia" in combined):
        return f"{role} / AI"
    return role or ("Tech Lead Data / AI" if resume_language == "fr" else "Data / AI Tech Lead")


def _leadership_email_bullet(candidate_context: dict, resume_language: str) -> str:
    if resume_language != "fr":
        return ""
    sizes = []
    for item in candidate_context.get("experiences", []):
        for bullet in _experience_bullets_for_language(item, resume_language):
            lowered = bullet.lower()
            if "équipe" not in lowered and "ingénieur" not in lowered:
                continue
            for match in re.findall(r"\b\d+\b", bullet):
                try:
                    value = int(match)
                except ValueError:
                    continue
                if 2 <= value <= 20:
                    sizes.append(value)
    if sizes:
        low = min(sizes)
        high = max(sizes)
        range_label = f"{low} à {high} ingénieurs" if low != high else f"{low} ingénieurs"
        return (
            f"J'ai encadré des équipes cross-fonctionnelles ({range_label}), "
            "piloté la roadmap AI et géré les arbitrages coût/performance."
        )
    return "J'ai encadré des équipes techniques, piloté la roadmap AI et géré les arbitrages coût/performance."


def _linkedin_interest_topic(jd_analysis: dict, resume_language: str) -> str:
    role = _clean_text(jd_analysis.get("role")).lower()
    combined = " ".join(
        _clean_text(item).lower()
        for item in (
            [role]
            + list(jd_analysis.get("top_requirements", []))
            + list(jd_analysis.get("keyword_signals", []))
            + list(jd_analysis.get("matched_keywords", []))
        )
    )
    if resume_language == "fr":
        if "lead" in role and ("data" in role or "ai" in role):
            return "La partie leadership technique / architecture m'a particulièrement parlé"
        if "architecture" in combined and ("performance" in combined or "releases" in combined):
            return "La partie architecture / performance m'a particulièrement parlé"
        if "architecture" in combined:
            return "La partie architecture m'a particulièrement parlé"
        if "spark" in combined or "scala" in combined or "kafka" in combined:
            return "La partie systèmes distribués / performance m'a particulièrement parlé"
        if "performance" in combined:
            return "La partie performance m'a particulièrement parlé"
        if "leadership" in combined or "encadrer" in combined:
            return "La partie leadership technique m'a particulièrement parlé"
        return "Le scope du poste m'a particulièrement parlé"
    if "lead" in role and ("data" in role or "ai" in role):
        return "The technical leadership / architecture side is especially relevant to me"
    if "architecture" in combined and "performance" in combined:
        return "The architecture / performance angle is especially relevant to me"
    if "architecture" in combined:
        return "The architecture side is especially relevant to me"
    if "performance" in combined:
        return "The performance side is especially relevant to me"
    if "leadership" in combined:
        return "The technical leadership side is especially relevant to me"
    return "The scope of the role is especially relevant to me"


def _distributed_gap_line(jd_analysis: dict, resume_language: str) -> str:
    hints = {_clean_text(item).lower() for item in jd_analysis.get("missing_candidate_keywords", [])}
    distributed = {"spark", "kafka", "scala", "hdfs", "hive", "elasticsearch", "java"}
    if not (hints & distributed):
        if resume_language == "fr":
            return "Sur la stack, je travaille principalement en Python / FastAPI / Docker / Airflow / PostgreSQL."
        return "My main stack is Python / FastAPI / Docker / Airflow / PostgreSQL."
    if resume_language == "fr":
        return (
            "Sur la stack, je travaille principalement en Python / FastAPI / Docker / Airflow / PostgreSQL. "
            "Je monte rapidement sur Spark, Kafka et Scala — des environnements distribués, "
            "j'en gère la logique au quotidien."
        )
    return (
        "My main stack is Python / FastAPI / Docker / Airflow / PostgreSQL. "
        "I ramp quickly on Spark, Kafka, and Scala, and I already operate daily in distributed environments."
    )


def _build_fallback_email(candidate_context: dict, jd_analysis: dict, resume_language: str) -> str:
    name = _clean_text(candidate_context.get("personal", {}).get("name"))
    role = _preferred_email_role(jd_analysis, resume_language)
    location = _clean_text(jd_analysis.get("location"))
    gap_line = _distributed_gap_line(jd_analysis, resume_language)
    if resume_language == "fr":
        years_label = _email_years_label(candidate_context, resume_language)
        intro = f"Je me permets de vous contacter suite à votre offre pour le poste de {role}" + (f" à {location}" if location else "") + "."
        auto_responder = "J'ai déployé un auto-répondeur LLM traitant ~20 000 leads/mois à 96% de précision, en production."
        cv_cost = "J'ai remplacé un pipeline Computer Vision par une approche LLM sur 2M+ véhicules, évitant 20 000$+ en coûts GPU."
        leadership = _leadership_email_bullet(candidate_context, resume_language)
        proof_lines = "\n".join(
            [
                f"• {auto_responder}",
                f"• {cv_cost}",
                f"• {leadership}",
            ]
        )
        body = [
            f"Objet : Candidature – {role} | {name}",
            "",
            "Bonjour,",
            "",
            intro,
            "",
            f"Avec {years_label} d'expérience à construire et livrer des systèmes AI en production — pas des prototypes — je pense correspondre à ce que vous cherchez. Quelques exemples concrets :",
            "",
            proof_lines,
            "",
            gap_line,
        ]
        body.extend(
            [
                "",
                "Je serais ravi d'échanger sur la façon dont je peux contribuer à vos projets data et AI.",
                "",
                "Cordialement,",
                name,
                f"{_clean_text(candidate_context.get('personal', {}).get('email'))} | {_format_contact_phone(_clean_text(candidate_context.get('personal', {}).get('phone')))}",
                "linkedin.com/in/aourik-ayman",
            ]
        )
        return "\n".join(line for line in body if line is not None).strip()

    years_label = _email_years_label(candidate_context, resume_language)
    intro = f"I'm reaching out regarding your {role} opening" + (f" in {location}" if location else "") + "."
    proofs = _select_email_proof_bullets(candidate_context, resume_language)
    proof_lines = "\n".join(f"• {bullet}" for bullet in proofs[:3])
    body = [
        f"Subject: Application – {role} | {name}",
        "",
        "Hello,",
        "",
        intro,
        "",
        f"With {years_label} of experience building and shipping production AI systems, not prototypes, I believe I can contribute quickly. A few concrete examples:",
        "",
        proof_lines,
        "",
        gap_line,
    ]
    body.extend(
        [
            "",
            "I'd be glad to discuss how I can contribute to your data and AI projects.",
            "",
            "Best regards,",
            name,
            f"{_clean_text(candidate_context.get('personal', {}).get('email'))} | {_format_contact_phone(_clean_text(candidate_context.get('personal', {}).get('phone')))}",
        ]
    )
    return "\n".join(line for line in body if line is not None).strip()


def _build_fallback_linkedin_message(candidate_context: dict, jd_analysis: dict, resume_language: str) -> str:
    role = _preferred_email_role(jd_analysis, resume_language)
    location = _clean_text(jd_analysis.get("location"))
    interest = _linkedin_interest_topic(jd_analysis, resume_language)
    if resume_language == "fr":
        location_suffix = f" à {location}" if location else ""
        return (
            f"Bonjour, j'ai vu votre offre de {role}{location_suffix}. "
            f"{interest} : j'ai déjà déployé un auto-répondeur LLM à ~20 000 leads/mois à 96% de précision et remplacé un pipeline Computer Vision sur 2M+ véhicules. "
            "Ravi d'échanger si le sujet est toujours d'actualité."
        )
    location_suffix = f" in {location}" if location else ""
    return (
        f"Hello, I saw your {role} opening{location_suffix}. "
        f"{interest}: I have already deployed an LLM auto-responder at ~20,000 leads/month with 96% accuracy and replaced a computer vision pipeline across 2M+ vehicles. "
        "I'd be glad to connect if the role is still open."
    )


def _repair_pack_content(
    pack: ApplicationPack,
    candidate_context: dict,
    jd_analysis: dict,
    jd_text: str,
    outputs: list[str],
) -> None:
    if "cover_letter" in outputs:
        cover_letter = pack.cover_letter or ""
        if (
            not cover_letter
            or _text_conflicts_with_language(cover_letter, pack.resume_language)
            or _cover_letter_is_generic(cover_letter)
            or not _cover_letter_has_expected_structure(cover_letter)
        ):
            pack.cover_letter = _build_fallback_cover_letter(candidate_context, jd_analysis, jd_text, pack.resume_language)

    if "email_draft" in outputs:
        email = pack.email_draft or ""
        if (
            _text_conflicts_with_language(email, pack.resume_language)
            or _email_is_generic(email)
            or not _email_has_expected_structure(email, pack.resume_language)
        ):
            pack.email_draft = _build_fallback_email(candidate_context, jd_analysis, pack.resume_language)

    if "linkedin_msg" in outputs:
        linkedin = pack.linkedin_message or ""
        if (
            not linkedin
            or _text_conflicts_with_language(linkedin, pack.resume_language)
            or _linkedin_is_generic(linkedin, pack.resume_language)
            or (pack.resume_language == "fr" and not _looks_like_french(linkedin))
            or (pack.resume_language == "en" and _looks_like_french(linkedin))
        ):
            pack.linkedin_message = _build_fallback_linkedin_message(candidate_context, jd_analysis, pack.resume_language)


def _validate_pack_content(pack: ApplicationPack, outputs: list[str]) -> None:
    language_name = "French" if pack.resume_language == "fr" else "English"

    if not _summary_has_target_length(pack.tailored_summary):
        raise ValueError("tailored_summary must contain 2 to 3 sentences.")

    for item in pack.tailored_experiences:
        for bullet in item.bullets:
            if _text_conflicts_with_language(bullet, pack.resume_language):
                raise ValueError(
                    f"Tailored experience bullets must all be in {language_name}. "
                    f"Mixed-language bullet detected for {item.company}: {bullet}"
                )

    if "linkedin_msg" in outputs and pack.linkedin_message and _text_conflicts_with_language(pack.linkedin_message, pack.resume_language):
        raise ValueError(f"linkedin_message must be fully written in {language_name}.")

    if "cover_letter" in outputs:
        cover_letter = pack.cover_letter or ""
        if _text_conflicts_with_language(cover_letter, pack.resume_language):
            raise ValueError(f"cover_letter must be fully written in {language_name}.")
        if _cover_letter_is_generic(cover_letter):
            raise ValueError(
                "cover_letter uses generic application language. Lead with a sharp company-specific hook, "
                "2-3 quantified wins, JD language on working style, and a specific one-sentence close."
            )
        if not _cover_letter_has_expected_structure(cover_letter):
            raise ValueError(
                "cover_letter must be exactly 4 short paragraphs, plain text only, under 200 words total, "
                "with 2-3 quantified wins and a one-sentence closing compliment."
            )

    if "email_draft" in outputs:
        email = pack.email_draft or ""
        if _text_conflicts_with_language(email, pack.resume_language):
            raise ValueError(f"email_draft must be fully written in {language_name}.")
        if _email_is_generic(email):
            raise ValueError(
                "email_draft is too generic. Lead with 2-3 quantified proof points tied to the job, "
                "then close with a low-friction ask."
            )


def _normalize_profile_update_hints(payload: dict, jd_analysis: dict) -> list[str]:
    model_hints = _clean_text_list(_first_present(payload, PROFILE_UPDATE_HINT_KEYS))
    inferred_hints = _clean_text_list(jd_analysis.get("missing_candidate_keywords"))
    return _unique_text_list(model_hints + inferred_hints)


def _normalize_payload(payload: dict, candidate_context: dict, jd_analysis: dict, jd_text: str) -> dict:
    unwrapped = _unwrap_payload(payload)
    resume_language = _resume_language(jd_analysis)
    model_title = normalize_role_title(_first_present(unwrapped, TAILORED_TITLE_KEYS), resume_language)
    preferred_title = normalize_role_title(jd_analysis.get("role"), resume_language)
    if is_credible_role_title(preferred_title):
        title = preferred_title
    elif is_credible_role_title(model_title):
        title = model_title
    else:
        title = _build_fallback_title(candidate_context, jd_analysis, resume_language)
    summary = _normalize_summary(_first_present(unwrapped, TAILORED_SUMMARY_KEYS), candidate_context, jd_analysis, resume_language, title)
    normalized = {
        "resume_language": resume_language,
        "tailored_title": title,
        "tailored_summary": summary,
        "tailored_experiences": _normalize_experiences(unwrapped, candidate_context, resume_language),
        "tailored_skills": _normalize_skills(unwrapped, candidate_context, jd_analysis),
        "focus_areas": _clean_text_list(
            _first_present(unwrapped, FOCUS_AREA_KEYS)
            or jd_analysis.get("top_requirements")
            or jd_analysis.get("keyword_signals")
            or jd_analysis.get("matched_keywords")
        ),
        "detected_emails": _collect_detected_emails(jd_text, unwrapped),
        "profile_update_hints": _normalize_profile_update_hints(unwrapped, jd_analysis),
    }
    for field, aliases in TEXT_FIELD_ALIASES.items():
        value = _first_present(unwrapped, aliases)
        normalized[field] = _clean_text(value) if _has_value(value) else None
    return normalized


def _build_messages(
    prompt: str,
    compact_message: dict,
    *,
    validation_error: str | None = None,
    previous_payload: dict | None = None,
) -> list[dict]:
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(compact_message, ensure_ascii=False, separators=(",", ":"))},
    ]
    if validation_error and previous_payload is not None:
        messages.extend(
            [
                {"role": "assistant", "content": json.dumps(previous_payload, ensure_ascii=False)},
                {
                    "role": "user",
                    "content": (
                        "Repair the previous JSON so it satisfies the required schema. "
                        f"Validation error: {validation_error}. "
                        "Keep all facts grounded in the candidate profile and job description."
                    ),
                },
            ]
        )
    return messages


def _message_content_as_text(message: object) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if item.get("type") == "text" and isinstance(text_value, str):
                    parts.append(text_value)
                elif isinstance(text_value, dict):
                    value = text_value.get("value")
                    if isinstance(value, str):
                        parts.append(value)
            else:
                text_value = getattr(item, "text", None)
                if isinstance(text_value, str):
                    parts.append(text_value)
                else:
                    value = getattr(text_value, "value", None)
                    if isinstance(value, str):
                        parts.append(value)
        return "".join(parts).strip()
    return _clean_text(content)


def _parse_response_payload(response: object) -> dict:
    choices = getattr(response, "choices", [])
    if not choices:
        raise ValueError("Model returned no choices.")
    message = getattr(choices[0], "message", None)
    refusal = getattr(message, "refusal", None) if message is not None else None
    if refusal:
        raise ValueError(f"Model refused the request: {refusal}")
    content = _message_content_as_text(message)
    if not content:
        raise ValueError("Model returned an empty response.")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned invalid JSON: {exc}") from exc


def _create_completion(
    client: object,
    *,
    config: dict,
    messages: list[dict],
    response_format: dict,
) -> object:
    return client.chat.completions.create(
        model=_get_generation_model(config),
        temperature=config["llm"]["temperature"],
        max_tokens=config["llm"]["max_tokens"],
        response_format=response_format,
        messages=messages,
    )


def _should_fallback_to_json_object(error: Exception) -> bool:
    message = str(error).lower()
    return "json_schema" in message or "response_format" in message or "structured" in message


def _request_model_response(client: object, *, config: dict, messages: list[dict]) -> object:
    try:
        return _create_completion(
            client,
            config=config,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": PACK_RESPONSE_SCHEMA},
        )
    except Exception as exc:
        if not _should_fallback_to_json_object(exc):
            raise
    return _create_completion(
        client,
        config=config,
        messages=messages,
        response_format={"type": "json_object"},
    )


def _ensure_requested_outputs(pack: ApplicationPack, outputs: list[str]) -> None:
    if "cover_letter" in outputs and not pack.cover_letter:
        raise ValueError("Model response is missing cover_letter.")
    if "linkedin_msg" in outputs and not pack.linkedin_message:
        raise ValueError("Model response is missing linkedin_message.")
    if "email_draft" in outputs and not pack.email_draft:
        raise ValueError("Model response is missing email_draft.")


def _get_requirement_mapping(
    client: object,
    *,
    config: dict,
    jd_analysis: dict,
    candidate_context: dict,
    resume_language: str,
) -> dict:
    requirements = list(jd_analysis.get("top_requirements") or jd_analysis.get("keyword_signals", [])[:5])
    if not requirements:
        return {"mappings": [], "summary_anchor": ""}

    bullet_blocks = []
    for item in candidate_context.get("experiences", []):
        company = _clean_text((item or {}).get("company", ""))
        bullets = _experience_bullets_for_language(item, resume_language)
        if company and bullets:
            bullet_blocks.append({"company": company, "bullets": bullets})

    if not bullet_blocks:
        return {"mappings": [], "summary_anchor": ""}

    user_message = json.dumps(
        {
            "target_language": resume_language,
            "jd_requirements": requirements[:6],
            "candidate_bullets": bullet_blocks,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    messages = [
        {"role": "system", "content": MAPPING_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    analysis_model = _get_analysis_model(config)
    try:
        response = client.chat.completions.create(
            model=analysis_model,
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_schema", "json_schema": MAPPING_SCHEMA},
            messages=messages,
        )
        content = _message_content_as_text(response.choices[0].message)
        mapping = json.loads(content)
        if not isinstance(mapping, dict):
            return {"mappings": [], "summary_anchor": ""}
        return mapping
    except Exception:
        return {"mappings": [], "summary_anchor": ""}


def generate_pack(
    jd_text: str,
    jd_analysis: dict,
    candidate_context: dict,
    outputs: list[str],
    application_url: str | None,
    config: dict,
) -> tuple[ApplicationPack, dict, str | None]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing. Add it to .env before generating.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("The openai package is not installed. Run pip install -r requirements.txt.") from exc

    prompt = _load_prompt(config)
    resume_language = _resume_language(jd_analysis)

    client = OpenAI(api_key=api_key)
    requirement_mapping = _get_requirement_mapping(
        client,
        config=config,
        jd_analysis=jd_analysis,
        candidate_context=candidate_context,
        resume_language=resume_language,
    )
    compact_message = {
        "requested_outputs": outputs,
        "application_url": application_url or "",
        "resume_language": resume_language,
        "input_language": jd_analysis.get("language", "en"),
        "jd_analysis": {
            "company": jd_analysis.get("company"),
            "role": jd_analysis.get("role"),
            "seniority": jd_analysis.get("seniority"),
            "matched_keywords": jd_analysis.get("matched_keywords", []),
            "top_requirements": jd_analysis.get("top_requirements", []),
            "keyword_signals": jd_analysis.get("keyword_signals", []),
            "missing_candidate_keywords": jd_analysis.get("missing_candidate_keywords", []),
        },
        "requirement_mapping": requirement_mapping,
        "jd_full": jd_text,
        "candidate": _candidate_payload(candidate_context),
    }
    usage_records: list[OpenAIUsageRecord] = []
    previous_payload = None
    last_error = ""

    for attempt_number in range(1, 3):
        messages = _build_messages(
            prompt,
            compact_message,
            validation_error=last_error or None,
            previous_payload=previous_payload,
        )
        try:
            response = _request_model_response(client, config=config, messages=messages)
        except Exception as exc:
            usage_summary = summarize_usage(usage_records)
            raise PackGenerationError(str(exc), usage_summary=usage_summary) from exc

        usage_records.append(
            usage_from_response(
                response,
                request_kind="generate_pack",
                attempt_number=attempt_number,
                fallback_model=_get_generation_model(config),
                config=config,
            )
        )

        try:
            payload = _parse_response_payload(response)
            previous_payload = payload
            unwrapped_payload = _unwrap_payload(payload)
            detected_company = _normalize_detected_company(unwrapped_payload)
            normalized_payload = _normalize_payload(payload, candidate_context, jd_analysis, jd_text)
            pack = ApplicationPack.model_validate(normalized_payload)
            _repair_pack_content(pack, candidate_context, jd_analysis, jd_text, outputs)
            _ensure_requested_outputs(pack, outputs)
            _validate_pack_content(pack, outputs)
        except ValueError as exc:
            last_error = str(exc)
            if "Missing tailored_experiences" in last_error:
                last_error = (
                    f"{last_error}. "
                    f"Candidate experiences loaded: {len(candidate_context.get('experiences', []))}. "
                    f"Candidate source: {candidate_context.get('candidate_source') or 'unknown'}."
                )
            if attempt_number >= 2:
                raise PackGenerationError(last_error, usage_summary=summarize_usage(usage_records)) from exc
            continue

        if "cover_letter" not in outputs:
            pack.cover_letter = None
        if "linkedin_msg" not in outputs:
            pack.linkedin_message = None
        if "email_draft" not in outputs:
            pack.email_draft = None

        return pack, summarize_usage(usage_records), detected_company

    raise PackGenerationError(last_error or "Model response validation failed.", usage_summary=summarize_usage(usage_records))
