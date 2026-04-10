from __future__ import annotations

import re

from app.text_utils import clean_text as _clean_text, term_matches_text as _term_matches_text

REALISTIC_ROLE_TARGETS = [
    "AI Lead",
    "Head of AI",
    "Head of Data and AI",
    "AI Engineering Manager",
    "Applied AI Lead",
    "LLM Engineer Lead",
    "AI & Data Science Lead",
    "AI Automation Lead",
    "Conversational AI Lead",
    "MLOps Lead",
    "AI Product Lead",
    "Lead AI Engineer",
    "Senior AI Engineer",
    "AI Solutions Lead",
    "AI Operations Lead",
    "Generative AI Lead",
    "NLP Engineering Lead",
    "AI Infrastructure Lead",
]

STRETCH_ROLE_TARGETS = [
    "Senior Manager Machine Learning",
    "Director of AI Engineering",
    "Director of Machine Learning",
    "Director of Data Science",
    "Head of Machine Learning",
    "VP of AI",
    "Principal AI Engineer",
    "Staff Machine Learning Engineer",
    "Machine Learning Architect",
]

SKIP_ROLE_TARGETS = [
    "Data Scientist",
    "Machine Learning Engineer",
    "AI Engineer",
    "Data Analyst",
]

LINKEDIN_SEARCH_KEYWORDS = [
    "LLM production",
    "RAG",
    "LLM-as-Judge",
    "AI agents",
    "agentic AI",
    "LangChain",
    "AI automation",
    "generative AI lead",
    "applied AI",
    "remote AI lead",
]

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
    "AI agents",
    "LangGraph",
    "Gen AI",
    "OCR",
    "FastAPI",
    "Airflow",
    "PostgreSQL",
    "TensorFlow",
    "Scikit-learn",
    "LangChain",
    "LangSmith",
    "Langfuse",
    "OpenAI",
    "Power BI",
    "XGBoost",
    "RAG",
    "NLP",
    "React",
    "TypeScript",
    "vector databases",
    "structured outputs",
    "streaming",
    "human-in-the-loop",
    "CI/CD",
    "data architecture",
    "data engineering",
    "data analytics",
    "data mesh",
    "data governance",
    "technical leadership",
    "client proposals",
]

TITLE_BANNED_PREFIXES = (
    "en tant que",
    "as a",
    "for the role of",
    "role of",
    "poste de",
    "rôle de",
)

_UPPERCASE_TOKENS = {
    "AI",
    "IA",
    "ML",
    "LLM",
    "MLOPS",
    "DATAOPS",
    "NLP",
    "OCR",
    "SQL",
    "AWS",
    "GCP",
    "API",
    "RAG",
    "CI/CD",
}
_LOWERCASE_CONNECTORS = {"and", "de", "du", "et", "for", "of", "the", "to"}
_LANGUAGE_SKILL_HINTS = {
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
_FRAMEWORK_SKILL_HINTS = {
    "fastapi",
    "react",
    "dbt",
    "langchain",
    "langgraph",
    "chromadb",
    "xgboost",
    "airflow",
    "tensorflow",
    "scikit-learn",
}
_NON_SKILL_TERMS = {
    "ai delivery",
    "client proposals",
    "cost optimization",
    "data architecture",
    "data analytics",
    "data engineering",
    "data science",
    "document intelligence",
    "machine learning",
    "stakeholder communication",
    "team leadership",
    "technical leadership",
    "automation",
}
_SKILL_CATEGORY_LIMITS = {
    "languages": 4,
    "frameworks": 6,
    "tools": 8,
}
_DERIVED_SKILL_RULES = (
    {
        "name": "AI agents",
        "category": "frameworks",
        "jd_terms": ("AI agents", "agentic AI", "agents IA"),
        "evidence_any": ("AI PM coordination agent", "agent IA", "AI agent", "coordination agent"),
        "evidence_all": (),
    },
    {
        "name": "agent orchestration",
        "category": "frameworks",
        "jd_terms": ("LangGraph", "agent orchestration", "orchestrer", "orchestration"),
        "evidence_any": ("AI PM coordination agent", "agent IA de coordination"),
        "evidence_all": (("LangChain", "agent"),),
    },
    {
        "name": "vector databases",
        "category": "tools",
        "jd_terms": ("vector databases", "vector database", "bases vectorielles"),
        "evidence_any": ("ChromaDB", "Pinecone", "Qdrant", "Weaviate", "FAISS", "Milvus"),
        "evidence_all": (),
    },
    {
        "name": "structured outputs",
        "category": "tools",
        "jd_terms": ("structured outputs", "sorties structurées"),
        "evidence_any": ("structured document information",),
        "evidence_all": (("Pydantic", "document"), ("Pydantic", "structured")),
    },
    {
        "name": "AI API orchestration",
        "category": "tools",
        "jd_terms": ("LLM APIs", "multi-provider", "multi-fournisseurs", "API orchestration"),
        "evidence_any": ("integrated with Freshdesk", "intégré à Freshdesk", "integrating Jira", "intégrant Jira"),
        "evidence_all": (("OpenAI", "Deepgram"), ("OpenAI", "FastAPI")),
    },
)
_LOCALIZED_SKILL_TERMS = {
    "ai agents": {"fr": "agents IA", "en": "AI agents"},
    "agent orchestration": {"fr": "orchestration d'agents", "en": "agent orchestration"},
    "vector databases": {"fr": "bases vectorielles", "en": "vector databases"},
    "structured outputs": {"fr": "sorties structurées", "en": "structured outputs"},
    "ai api orchestration": {"fr": "orchestration d'API IA", "en": "AI API orchestration"},
}


def _normalize_skill_key(value: object) -> str:
    return _clean_text(value).lower()


_DERIVED_RULES_BY_KEY = {_normalize_skill_key(item["name"]): item for item in _DERIVED_SKILL_RULES}


def _iter_profile_strings(value: object) -> list[str]:
    if isinstance(value, dict):
        items = []
        for item in value.values():
            items.extend(_iter_profile_strings(item))
        return items
    if isinstance(value, list):
        items = []
        for item in value:
            items.extend(_iter_profile_strings(item))
        return items
    cleaned = _clean_text(value)
    return [cleaned] if cleaned else []


def _infer_skill_category(key: str, explicit_categories: dict[str, str]) -> str | None:
    if key in explicit_categories:
        return explicit_categories[key]
    if key in _DERIVED_RULES_BY_KEY:
        return str(_DERIVED_RULES_BY_KEY[key]["category"])
    if key in _NON_SKILL_TERMS:
        return None
    if key in _LANGUAGE_SKILL_HINTS:
        return "languages"
    if key in _FRAMEWORK_SKILL_HINTS:
        return "frameworks"
    return "tools"


def _candidate_skill_pool(candidate_context: dict) -> tuple[dict[str, list[str]], dict[str, str]]:
    skills = candidate_context.get("skills", {}) if isinstance(candidate_context.get("skills"), dict) else {}
    explicit_categories: dict[str, str] = {}
    ordered_catalog: list[str] = []
    seen = set()

    categorized_explicit = {"languages": [], "frameworks": [], "tools": []}
    for category in ("languages", "frameworks", "tools"):
        for item in skills.get(category, []) or []:
            cleaned = _clean_text(item)
            key = _normalize_skill_key(cleaned)
            if not cleaned or key in seen:
                continue
            explicit_categories[key] = category
            categorized_explicit[category].append(cleaned)
            ordered_catalog.append(cleaned)
            seen.add(key)

    for item in KEYWORD_SIGNAL_CATALOG + list(candidate_context.get("scoring_keywords", []) or []):
        cleaned = _clean_text(item)
        key = _normalize_skill_key(cleaned)
        if not cleaned or key in seen:
            continue
        ordered_catalog.append(cleaned)
        seen.add(key)

    return {"catalog": ordered_catalog, **categorized_explicit}, explicit_categories


def _profile_text(candidate_context: dict) -> str:
    return "\n".join(_iter_profile_strings(candidate_context))


def _rule_supported(profile_text: str, rule: dict) -> bool:
    if _term_matches_text(profile_text, rule.get("name", "")):
        return True
    if any(_term_matches_text(profile_text, term) for term in rule.get("evidence_any", ())):
        return True
    for group in rule.get("evidence_all", ()):
        if all(_term_matches_text(profile_text, term) for term in group):
            return True
    return False


def _derived_skill_inventory(candidate_context: dict) -> list[tuple[str, str]]:
    profile_text = _profile_text(candidate_context)
    derived = []
    for rule in _DERIVED_SKILL_RULES:
        if _rule_supported(profile_text, rule):
            derived.append((str(rule["category"]), str(rule["name"])))
    return derived


def _jd_strings(jd_analysis: dict) -> list[str]:
    ordered = []
    seen = set()
    for item in (
        list(jd_analysis.get("keyword_signals", []) or [])
        + list(jd_analysis.get("top_requirements", []) or [])
        + [_clean_text(jd_analysis.get("role"))]
        + list(jd_analysis.get("matched_keywords", []) or [])
    ):
        cleaned = _clean_text(item)
        key = _normalize_skill_key(cleaned)
        if not cleaned or key in seen:
            continue
        ordered.append(cleaned)
        seen.add(key)
    return ordered


def _skill_matches_jd(term: str, jd_text: str) -> bool:
    if _term_matches_text(jd_text, term):
        return True
    rule = _DERIVED_RULES_BY_KEY.get(_normalize_skill_key(term))
    if not rule:
        return False
    return any(_term_matches_text(jd_text, alias) for alias in rule.get("jd_terms", ()))


def localize_skill_term(term: str, resume_language: str) -> str:
    localized = _LOCALIZED_SKILL_TERMS.get(_normalize_skill_key(term), {})
    return str(localized.get(resume_language) or term)


def target_resume_concepts(candidate_context: dict, jd_analysis: dict, resume_language: str = "en", limit: int = 4) -> list[str]:
    inventory = derive_candidate_skill_inventory(candidate_context)
    ordered_terms = []
    seen = set()

    def include_term(category: str, term: str, phase: int) -> bool:
        key = _normalize_skill_key(term)
        if phase == 0:
            return category != "languages" and key in _DERIVED_RULES_BY_KEY
        if phase == 1:
            return category != "languages"
        return True

    for phase in range(3):
        for jd_item in _jd_strings(jd_analysis):
            for category in ("frameworks", "tools", "languages"):
                for term in inventory.get(category, []):
                    key = _normalize_skill_key(term)
                    if key in seen or not include_term(category, term, phase) or not _skill_matches_jd(term, jd_item):
                        continue
                    ordered_terms.append(localize_skill_term(term, resume_language))
                    seen.add(key)
                    if len(ordered_terms) >= limit:
                        return ordered_terms
    return ordered_terms


def derive_candidate_skill_inventory(candidate_context: dict) -> dict[str, list[str]]:
    pool, explicit_categories = _candidate_skill_pool(candidate_context)
    profile_text = _profile_text(candidate_context)
    inventory = {"languages": [], "frameworks": [], "tools": []}
    seen_by_category = {category: set() for category in inventory}

    for term in pool["catalog"]:
        key = _normalize_skill_key(term)
        if key in _NON_SKILL_TERMS or not _term_matches_text(profile_text, term):
            continue
        category = _infer_skill_category(key, explicit_categories)
        if not category or key in seen_by_category[category]:
            continue
        inventory[category].append(term)
        seen_by_category[category].add(key)

    for category, term in _derived_skill_inventory(candidate_context):
        key = _normalize_skill_key(term)
        if key in seen_by_category[category]:
            continue
        inventory[category].append(term)
        seen_by_category[category].add(key)

    for category in ("languages", "frameworks", "tools"):
        for item in pool[category]:
            key = _normalize_skill_key(item)
            if key in seen_by_category[category]:
                continue
            inventory[category].append(item)
            seen_by_category[category].add(key)

    return inventory


def candidate_keywords_from_profile(candidate_context: dict) -> list[str]:
    keywords: list[str] = []
    seen = set()

    for item in [candidate_context.get("headline")] + [
        _clean_text((experience or {}).get("role"))
        for experience in list(candidate_context.get("experiences", []) or [])
    ]:
        cleaned = _clean_text(item)
        key = _normalize_skill_key(cleaned)
        if not cleaned or key in seen:
            continue
        keywords.append(cleaned)
        seen.add(key)

    for item in list(candidate_context.get("scoring_keywords", []) or []):
        cleaned = _clean_text(item)
        key = _normalize_skill_key(cleaned)
        if not cleaned or key in seen:
            continue
        keywords.append(cleaned)
        seen.add(key)

    inventory = derive_candidate_skill_inventory(candidate_context)
    for values in inventory.values():
        for item in values:
            cleaned = _clean_text(item)
            key = _normalize_skill_key(cleaned)
            if not cleaned or key in seen:
                continue
            keywords.append(cleaned)
            seen.add(key)

    return keywords


def prioritize_candidate_skills(candidate_context: dict, jd_analysis: dict) -> dict[str, list[str]]:
    inventory = derive_candidate_skill_inventory(candidate_context)
    jd_items = _jd_strings(jd_analysis)
    jd_text = " ".join(jd_items)

    prioritized = {}
    for category in ("languages", "frameworks", "tools"):
        ranked = list(inventory.get(category, []))
        limit = _SKILL_CATEGORY_LIMITS[category]
        matched = []
        seen = set()
        for jd_item in jd_items:
            for item in ranked:
                key = _normalize_skill_key(item)
                if key in seen or not _skill_matches_jd(item, jd_item):
                    continue
                matched.append(item)
                seen.add(key)
        remaining = [item for item in ranked if _normalize_skill_key(item) not in seen and not _term_matches_text(jd_text, item)]
        fuzzy_remaining = [item for item in ranked if _normalize_skill_key(item) not in seen and _term_matches_text(jd_text, item)]
        selected = (matched + fuzzy_remaining + remaining)[:limit]
        prioritized[category] = selected

    return prioritized


def _smart_title_case(text: str) -> str:
    def format_word(word: str) -> str:
        if "/" in word:
            return "/".join(format_word(part) for part in word.split("/") if part)
        upper = word.upper()
        lower = word.lower()
        if upper in _UPPERCASE_TOKENS:
            return upper
        if lower in _LOWERCASE_CONNECTORS:
            return lower
        return word[:1].upper() + word[1:].lower()

    def replace_word(match: re.Match[str]) -> str:
        return format_word(match.group(0))

    return re.sub(r"[A-Za-zÀ-ÿ0-9+-]+(?:/[A-Za-zÀ-ÿ0-9+-]+)?", replace_word, text)


def normalize_role_title(value: object, resume_language: str = "en") -> str:
    title = _clean_text(value)
    if not title:
        return ""

    title = re.sub(
        r"^(?:en tant que|as a|for the role of|role of|poste de|rôle de)\s+",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(
        r"\s*(?:,|:|-)\s*(?:vos principales missions.*|your main responsibilities.*)$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"\btechlead\b", "Tech Lead", title, flags=re.IGNORECASE)
    title = re.sub(r"\bproductmanager\b", "Product Manager", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+to support.*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+with a lead.*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+to join.*$", "", title, flags=re.IGNORECASE)
    # Strip technology platform suffixes appended after an en-dash or em-dash
    title = re.sub(
        r"\s*[\u2013\u2014]\s*(?:MS?\s+Fabric|Microsoft Fabric|Azure\b|AWS\b|GCP\b|"
        r"Databricks|Snowflake|dbt\b|Power\s+BI|Tableau|Salesforce|BigQuery|Redshift|"
        r"Kubernetes|Terraform|Vertex\s+AI|SageMaker|Bedrock|Hadoop|Kafka|Looker)\b.*$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip(" .,:;|-")
    title = re.sub(r"\s*/\s*", " / ", title)
    title = re.sub(r"\s*&\s*", " & ", title)
    title = re.sub(r"\s+", " ", title).strip(" .,:;|-")

    if resume_language == "fr":
        title = re.sub(r"\bData\s*/\s*IA\b", "Data & IA", title, flags=re.IGNORECASE)
        title = re.sub(r"\bData\s+IA\b", "Data & IA", title, flags=re.IGNORECASE)
        title = re.sub(r"\bIA\s+Data\b", "IA & Data", title, flags=re.IGNORECASE)
    else:
        title = re.sub(r"\bData\s*/\s*IA\b", "Data / AI", title, flags=re.IGNORECASE)
        title = re.sub(r"\bData\s+IA\b", "Data / AI", title, flags=re.IGNORECASE)
        title = re.sub(r"\bIA\s+Data\b", "AI / Data", title, flags=re.IGNORECASE)

    title = _smart_title_case(title)
    return re.sub(r"\s+", " ", title).strip(" .,:;|-")


def is_credible_role_title(title: str) -> bool:
    cleaned = _clean_text(title)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if any(lowered.startswith(prefix) for prefix in TITLE_BANNED_PREFIXES):
        return False
    if len(cleaned.split()) < 2:
        return False
    return True
