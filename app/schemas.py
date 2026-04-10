"""LLM response schemas, pattern constants, key alias tuples, and generic dict utilities."""
from __future__ import annotations

import re

from app.text_utils import clean_text as _clean_text

# ---------------------------------------------------------------------------
# OpenAI structured-output schemas
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
FRENCH_MARKER_PATTERN = re.compile(
    r"\b(le|la|les|des|dans|avec|pour|vous|nous|poste|expérience|capacité|gestion|équipe|données)\b",
    re.IGNORECASE,
)
ENGLISH_MARKER_PATTERN = re.compile(
    r"\b(the|and|with|for|from|built|led|replaced|deployed|developed|saving|saved|processing|calls?|week|team|pipeline|handling|accuracy|avoided|costs?|boosted|cut|forecasted|reporting|time|throughput|delivery|months?|year|present)\b",
    re.IGNORECASE,
)
NUMERIC_FACT_PATTERN = re.compile(r"(?<!\w)(?:~?\$?\d[\d,]*(?:\.\d+)?(?:[KMBkmb])?\+?(?:%|x)?)(?!\w)")
TECH_TERM_PATTERN = re.compile(
    r"\b(?:LLM|RAG|LoRA|ChromaDB|OpenAI|LangChain|XGBoost|Power BI|FastAPI|Airflow|Docker|PostgreSQL|CI/CD|MLOps|DataOps|OCR|AWS|GCP|Azure|Kubernetes|Spark|Hadoop|NLP|TensorFlow|Scikit-learn)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Phrase / term ban lists
# ---------------------------------------------------------------------------

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
    "into",
    "your",
    "vous",
    "nous",
    "their",
    "they",
    "them",
    "have",
    "has",
    "with",
    "what",
    "when",
    "where",
    "were",
    "will",
}

# ---------------------------------------------------------------------------
# Payload key alias tuples (for resilient dict lookups)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Generic dict / list utilities used across all sub-modules
# ---------------------------------------------------------------------------


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


def _normalize_match_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean_text(value).lower()).strip()
