from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

from app.models import ApplicationPack
from app.openai_usage import OpenAIUsageRecord, summarize_usage, usage_from_response


PACK_RESPONSE_SCHEMA = {
    "name": "application_pack",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "resume_language",
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

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
FRENCH_MARKER_PATTERN = re.compile(r"\b(le|la|les|des|dans|avec|pour|vous|nous|poste|expérience|capacité|gestion|équipe|données)\b", re.IGNORECASE)
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
TITLE_BANNED_PREFIXES = (
    "en tant que",
    "as a",
    "for the role of",
    "role of",
    "poste de",
    "rôle de",
)
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


def _summary_matches_language(text: str, resume_language: str) -> bool:
    if not _clean_text(text):
        return False
    is_french = _looks_like_french(text)
    if resume_language == "fr":
        return is_french
    return not is_french


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


def _normalize_role_title(value: object, resume_language: str) -> str:
    title = _clean_text(value)
    if not title:
        return ""
    title = re.sub(r"^(?:en tant que|as a|for the role of|role of|poste de|rôle de)\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*(?:,|:|-)\s*(?:vos principales missions.*|your main responsibilities.*)$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" .,:;|-")
    if resume_language == "fr":
        title = re.sub(r"\bData\s*/\s*IA\b", "Data & IA", title, flags=re.IGNORECASE)
        title = re.sub(r"\bData\s+IA\b", "Data & IA", title, flags=re.IGNORECASE)
        title = re.sub(r"\bIA\s+Data\b", "IA & Data", title, flags=re.IGNORECASE)
    else:
        title = re.sub(r"\bData\s*/\s*IA\b", "Data / AI", title, flags=re.IGNORECASE)
        title = re.sub(r"\bData\s+IA\b", "Data / AI", title, flags=re.IGNORECASE)
    return title


def _title_is_credible(title: str) -> bool:
    cleaned = _clean_text(title)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if any(lowered.startswith(prefix) for prefix in TITLE_BANNED_PREFIXES):
        return False
    if len(cleaned.split()) < 2:
        return False
    return True


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


def _normalize_tailored_bullets(source_bullets: list[str], preferred_order: list[int], raw_tailored_bullets: object) -> list[str]:
    ordered_source = _reorder_bullets(source_bullets, preferred_order)
    rewritten = _clean_text_list(raw_tailored_bullets)
    if len(rewritten) != len(ordered_source):
        return ordered_source

    normalized = []
    for source_bullet, rewritten_bullet in zip(ordered_source, rewritten):
        if not rewritten_bullet or not _bullet_rewrite_is_safe(source_bullet, rewritten_bullet):
            normalized.append(source_bullet)
            continue
        normalized.append(rewritten_bullet)
    return normalized


def _normalize_experiences(payload: dict, candidate_context: dict) -> list[dict]:
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
        preferred_order = _resolve_bullet_indices(_first_present(source, EXPERIENCE_FIELD_ALIASES["bullet_indices"]), len(fallback_item.get("bullets", [])))
        if not preferred_order:
            preferred_order = _match_bullet_order_from_texts(_first_present(source, EXPERIENCE_FIELD_ALIASES["bullets"]), fallback_item.get("bullets", []))
        raw_tailored_bullets = _first_present(source, EXPERIENCE_FIELD_ALIASES["tailored_bullets"])
        normalized_item = {
            "company": _clean_text(fallback_item.get("company")),
            "role": _clean_text(fallback_item.get("role")),
            "start": _clean_text(fallback_item.get("start")),
            "end": _clean_text(fallback_item.get("end")),
            "bullets": _normalize_tailored_bullets(fallback_item.get("bullets", []), preferred_order, raw_tailored_bullets)
            if isinstance(raw_tailored_bullets, list)
            else _reorder_bullets(fallback_item.get("bullets", []), preferred_order),
        }
        if normalized_item["company"] and normalized_item["role"] and normalized_item["bullets"]:
            normalized.append(normalized_item)

    if normalized:
        return normalized

    fallback_normalized = []
    for item in fallback_items:
        bullets = _clean_text_list(item.get("bullets"))
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


def _normalize_skills(payload: dict, candidate_context: dict) -> dict:
    fallback = candidate_context.get("skills", {}) if isinstance(candidate_context.get("skills"), dict) else {}
    raw = _first_present(payload, TAILORED_SKILLS_KEYS)
    source = raw if isinstance(raw, dict) else {}
    normalized = {}

    for field in ("languages", "frameworks", "tools"):
        fallback_values = _clean_text_list(fallback.get(field))
        requested = _clean_text_list(source.get(field))
        available_map = {_clean_text(item).lower(): item for item in fallback_values}
        ordered = []
        seen = set()

        for item in requested:
            key = item.lower()
            if key not in available_map or key in seen:
                continue
            ordered.append(available_map[key])
            seen.add(key)

        for item in fallback_values:
            key = item.lower()
            if key in seen:
                continue
            ordered.append(item)
            seen.add(key)

        normalized[field] = ordered

    return normalized


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
    preferred = _normalize_role_title(jd_analysis.get("role"), resume_language)
    if _title_is_credible(preferred):
        return preferred
    headline = _normalize_role_title(candidate_context.get("headline"), resume_language)
    if _title_is_credible(headline):
        return headline
    experiences = candidate_context.get("experiences") or []
    if experiences:
        fallback_role = _normalize_role_title((experiences[0] or {}).get("role"), resume_language)
        if _title_is_credible(fallback_role):
            return fallback_role
    return "Lead Tech Data & IA" if resume_language == "fr" else "AI & Data Lead"


def _build_fallback_summary(candidate_context: dict, jd_analysis: dict, resume_language: str, title: str) -> str:
    years_label = _experience_year_label(candidate_context, resume_language)
    seniority = _clean_text(jd_analysis.get("seniority")).lower()
    leadership = seniority == "lead" or "lead" in title.lower()
    if resume_language == "fr":
        if leadership:
            return (
                f"{title} avec {years_label} d'expérience dans la mise en production de systèmes data et IA à fort impact. "
                "J'encadre des équipes techniques et pilote des pipelines, services et applications IA de la conception à la production, "
                "avec un focus sur la scalabilité, la qualité d'exécution et la performance opérationnelle."
            )
        return (
            f"Professionnel Data & IA avec {years_label} d'expérience dans la conception, le déploiement et l'industrialisation de solutions orientées impact métier. "
            "Je transforme les besoins métier en systèmes fiables, mesurables et exploitables en production."
        )
    if leadership:
        return (
            f"{title} with {years_label} of experience shipping production data and AI systems with measurable business impact. "
            "I lead engineers and drive delivery from scoping to production, with a focus on scalable architecture, operational reliability, and cost-aware execution."
        )
    return (
        f"Data and AI professional with {years_label} of experience designing, deploying, and industrializing systems tied to measurable business outcomes. "
        "I turn business needs into reliable production workflows, models, and automation."
    )


def _normalize_summary(model_summary: object, candidate_context: dict, jd_analysis: dict, resume_language: str, title: str) -> str:
    summary = _clean_text(model_summary)
    if summary and not _contains_banned_phrase(summary) and _summary_matches_language(summary, resume_language):
        return summary
    return _build_fallback_summary(candidate_context, jd_analysis, resume_language, title)


def _normalize_profile_update_hints(payload: dict, jd_analysis: dict) -> list[str]:
    model_hints = _clean_text_list(_first_present(payload, PROFILE_UPDATE_HINT_KEYS))
    inferred_hints = _clean_text_list(jd_analysis.get("missing_candidate_keywords"))
    return _unique_text_list(model_hints + inferred_hints)


def _normalize_payload(payload: dict, candidate_context: dict, jd_analysis: dict, jd_text: str) -> dict:
    unwrapped = _unwrap_payload(payload)
    resume_language = _resume_language(jd_analysis)
    model_title = _normalize_role_title(_first_present(unwrapped, TAILORED_TITLE_KEYS), resume_language)
    title = model_title if _title_is_credible(model_title) else _build_fallback_title(candidate_context, jd_analysis, resume_language)
    summary = _normalize_summary(_first_present(unwrapped, TAILORED_SUMMARY_KEYS), candidate_context, jd_analysis, resume_language, title)
    normalized = {
        "resume_language": resume_language,
        "tailored_title": title,
        "tailored_summary": summary,
        "tailored_experiences": _normalize_experiences(unwrapped, candidate_context),
        "tailored_skills": _normalize_skills(unwrapped, candidate_context),
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
        model=config["llm"]["model"],
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


def generate_pack(
    jd_text: str,
    jd_analysis: dict,
    candidate_context: dict,
    outputs: list[str],
    config: dict,
) -> tuple[ApplicationPack, dict]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing. Add it to .env before generating.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("The openai package is not installed. Run pip install -r requirements.txt.") from exc

    prompt = _load_prompt(config)
    resume_language = _resume_language(jd_analysis)
    compact_message = {
        "requested_outputs": outputs,
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
        "jd_full": jd_text,
        "candidate": _candidate_payload(candidate_context),
    }

    client = OpenAI(api_key=api_key)
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
                fallback_model=config["llm"]["model"],
                config=config,
            )
        )

        try:
            payload = _parse_response_payload(response)
            previous_payload = payload
            normalized_payload = _normalize_payload(payload, candidate_context, jd_analysis, jd_text)
            pack = ApplicationPack.model_validate(normalized_payload)
            _ensure_requested_outputs(pack, outputs)
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

        return pack, summarize_usage(usage_records)

    raise PackGenerationError(last_error or "Model response validation failed.", usage_summary=summarize_usage(usage_records))
