"""Deterministic source-resume signal indexing for later onboarding comparisons.

Builds a compact, rule-based summary from parsed resume text without using the
JD analyzer, generator, or any LLM call.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from app.text_utils import sanitize_text

SOURCE_SIGNAL_INDEX_VERSION = "source_signal_index.v1"

_SECTION_ALIASES = {
    "summary": (
        "summary",
        "professional summary",
        "profile",
        "about",
        "about me",
        "profil",
        "resume summary",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "career history",
        "experience professionnelle",
        "expérience professionnelle",
        "parcours professionnel",
    ),
    "education": (
        "education",
        "formation",
        "academic background",
    ),
    "skills": (
        "skills",
        "technical skills",
        "core skills",
        "competencies",
        "competences",
        "competences techniques",
        "competences technique",
        "compétences",
        "compétences techniques",
        "stack technique",
        "stack technologique",
    ),
    "projects": (
        "projects",
        "selected projects",
        "personal projects",
        "key projects",
        "projets",
    ),
    "certifications": (
        "certifications",
        "certification",
        "certificates",
        "certificate",
        "licenses",
        "licences",
        "credentials",
    ),
    "languages": (
        "languages",
        "spoken languages",
        "langues",
    ),
    "awards": (
        "awards",
        "honors",
        "distinctions",
    ),
    "volunteering": (
        "volunteering",
        "volunteer experience",
        "community",
        "bénévolat",
    ),
}

_OPTIONAL_SECTION_KEYS = {"projects", "certifications"}
_EXPERIENCE_SECTION_KEYS = {"experience"}

_BULLET_PREFIX_PATTERN = re.compile(
    r"^(?:[-*•▪◦●○■▸▹►»]|[0-9]+[.)])\s+"
)
_DATE_LINE_PATTERN = re.compile(
    r"(?ix)"
    r"(?:"
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
    r"janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|"
    r"septembre|octobre|novembre|decembre|décembre|present|current|présent)\b"
    r"|"
    r"\b\d{4}\b"
    r")"
    r".{0,40}"
    r"(?:-|–|—|to|a|à|/)"
    r".{0,40}"
    r"(?:"
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
    r"janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|"
    r"septembre|octobre|novembre|decembre|décembre|present|current|présent)\b"
    r"|"
    r"\b\d{4}\b"
    r")"
)
_METRIC_SIGNAL_PATTERN = re.compile(
    r"(?ix)(?<!\w)(?:"
    r"~?\$?\d[\d,]*(?:\.\d+)?(?:[kmb])?\+?(?:%|x)"
    r"|"
    r"~?\$?\d[\d,]*(?:\.\d+)?\s?(?:thousand|million|billion)"
    r")(?!\w)"
)
_METRIC_UNIT_PATTERN = re.compile(
    r"(?ix)(?<!\w)"
    r"\d[\d,]*(?:\.\d+)?(?:[kmb])?\+?"
    r"\s?"
    r"(?:"
    r"hours?|hrs?|days?|weeks?|months?|years?|"
    r"users?|customers?|clients?|requests?|rows?|records?|documents?|tickets?|"
    r"pipelines?|workflows?|jobs?|services?|deployments?|calls?|reports?|dashboards?|"
    r"models?|datasets?|teams?|engineers?|analysts?|countries?|regions?|projects?|"
    r"leads?|agents?|incidents?|alerts?|experiments?|features?|minutes?|seconds?"
    r")"
    r"(?:\s+(?:per|/)\s+(?:day|week|month|year|hour|minute|second))?"
    r"\b"
)

_TOOL_SYSTEM_ALIASES = {
    "Airflow": ("airflow",),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure",),
    "Azure OpenAI": ("azure openai",),
    "BigQuery": ("bigquery", "big query"),
    "CI/CD": ("ci/cd", "ci cd"),
    "ChromaDB": ("chromadb",),
    "Databricks": ("databricks",),
    "dbt": ("dbt",),
    "Deepgram": ("deepgram",),
    "Docker": ("docker",),
    "Django": ("django",),
    "Elasticsearch": ("elasticsearch",),
    "Express": ("express", "express.js"),
    "FAISS": ("faiss",),
    "FastAPI": ("fastapi",),
    "Flask": ("flask",),
    "GCP": ("gcp", "google cloud platform"),
    "Git": ("git",),
    "GitHub Actions": ("github actions",),
    "Grafana": ("grafana",),
    "Hadoop": ("hadoop",),
    "Kafka": ("kafka",),
    "Kubernetes": ("kubernetes", "k8s"),
    "LangChain": ("langchain",),
    "LangGraph": ("langgraph",),
    "Linux": ("linux",),
    "LLM": ("llm", "large language model", "large language models"),
    "LoRA": ("lora",),
    "Looker": ("looker",),
    "MongoDB": ("mongodb",),
    "MySQL": ("mysql",),
    "Next.js": ("next.js",),
    "NLP": ("nlp", "natural language processing"),
    "Node.js": ("node.js", "nodejs"),
    "NumPy": ("numpy",),
    "OCR": ("ocr",),
    "OpenAI": ("openai",),
    "Pandas": ("pandas",),
    "PostgreSQL": ("postgresql", "postgres"),
    "Power BI": ("power bi",),
    "Prometheus": ("prometheus",),
    "PyTorch": ("pytorch",),
    "Python": ("python",),
    "RAG": ("rag", "retrieval augmented generation"),
    "React": ("react",),
    "Redis": ("redis",),
    "Scikit-learn": ("scikit-learn", "sklearn"),
    "Snowflake": ("snowflake",),
    "Spark": ("spark", "apache spark"),
    "SQL": ("sql",),
    "Streamlit": ("streamlit",),
    "Supabase": ("supabase",),
    "Tableau": ("tableau",),
    "TensorFlow": ("tensorflow",),
    "Terraform": ("terraform",),
    "TypeScript": ("typescript",),
    "XGBoost": ("xgboost",),
}

_COMPILED_TOOL_PATTERNS = tuple(
    (
        canonical,
        tuple(
            re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)
            for alias in aliases
        ),
    )
    for canonical, aliases in _TOOL_SYSTEM_ALIASES.items()
)


def build_source_signal_index(parsed_text: str) -> dict[str, object]:
    """Return a deterministic rule-based summary of parsed source-resume text."""
    sanitized = sanitize_text(parsed_text, preserve_newlines=True)
    lines = _build_line_records(sanitized)
    sections = _detect_sections(lines)
    line_to_section = _build_line_to_section_map(sections)
    experience_entries = _detect_experience_entries(lines, sections, line_to_section)
    line_to_experience = _build_line_to_experience_map(experience_entries)
    metric_bearing_lines = _detect_metric_bearing_lines(lines, line_to_section, line_to_experience)
    tool_system_terms = _detect_tool_system_terms(lines, line_to_section, line_to_experience)
    _annotate_experience_entries(experience_entries, metric_bearing_lines, tool_system_terms)
    optional_sections_detected = [
        section["section_key"]
        for section in sections
        if str(section.get("section_key")) in _OPTIONAL_SECTION_KEYS
    ]

    return {
        "index_version": SOURCE_SIGNAL_INDEX_VERSION,
        "source_text_sha256": hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
        "line_count": len(lines),
        "counts": {
            "sections_detected": len(sections),
            "experience_entries": len(experience_entries),
            "tool_system_terms": len(tool_system_terms),
            "metric_bearing_lines": len(metric_bearing_lines),
        },
        "sections_detected": sections,
        "optional_sections_detected": optional_sections_detected,
        "experience_entries": experience_entries,
        "tool_system_terms": tool_system_terms,
        "metric_bearing_lines": metric_bearing_lines,
    }


def _build_line_records(text: str) -> list[dict[str, object]]:
    if not text:
        return []
    return [
        {
            "number": index,
            "text": line.rstrip(),
            "stripped": line.strip(),
        }
        for index, line in enumerate(text.split("\n"), start=1)
    ]


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9+.#/ ]+", " ", normalized)
    return " ".join(normalized.split())


def _match_section_key(line: str) -> str | None:
    candidates = [_normalize_text(line)]
    if ":" in line:
        candidates.append(_normalize_text(line.split(":", 1)[0]))

    for candidate in candidates:
        if not candidate:
            continue
        for section_key, aliases in _SECTION_ALIASES.items():
            if candidate in aliases:
                return section_key
    return None


def _detect_sections(lines: list[dict[str, object]]) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    for record in lines:
        stripped = str(record["stripped"])
        if not stripped:
            continue
        section_key = _match_section_key(stripped)
        if not section_key:
            continue
        sections.append(
            {
                "position": len(sections),
                "section_key": section_key,
                "heading": stripped,
                "line_number": int(record["number"]),
            }
        )

    for index, section in enumerate(sections):
        next_line = (
            int(sections[index + 1]["line_number"]) - 1
            if index + 1 < len(sections)
            else len(lines)
        )
        section["line_start"] = int(section["line_number"])
        section["line_end"] = next_line
    return sections


def _build_line_to_section_map(sections: list[dict[str, object]]) -> dict[int, str]:
    line_to_section: dict[int, str] = {}
    for section in sections:
        start = int(section["line_start"])
        end = int(section["line_end"])
        key = str(section["section_key"])
        for line_number in range(start, end + 1):
            line_to_section[line_number] = key
    return line_to_section


def _detect_experience_entries(
    lines: list[dict[str, object]],
    sections: list[dict[str, object]],
    line_to_section: dict[int, str],
) -> list[dict[str, object]]:
    has_experience_section = any(
        str(section.get("section_key")) in _EXPERIENCE_SECTION_KEYS for section in sections
    )
    experience_heading_lines = {
        int(section["line_number"])
        for section in sections
        if str(section.get("section_key")) in _EXPERIENCE_SECTION_KEYS
    }
    candidate_lines = [
        record
        for record in lines
        if (
            line_to_section.get(int(record["number"])) in _EXPERIENCE_SECTION_KEYS
            and int(record["number"]) not in experience_heading_lines
            if has_experience_section
            else line_to_section.get(int(record["number"])) is None
        )
    ]
    blocks = _extract_experience_blocks(candidate_lines)

    entries: list[dict[str, object]] = []
    for block in blocks:
        entry = _parse_experience_block(block, position=len(entries))
        if entry is None:
            continue
        entries.append(entry)
    return entries


def _extract_experience_blocks(
    lines: list[dict[str, object]],
) -> list[list[dict[str, object]]]:
    blocks: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []

    for record in lines:
        stripped = str(record["stripped"])
        if not stripped:
            if current:
                blocks.append(current)
                current = []
            continue

        if current and _starts_new_experience_block(current, record):
            blocks.append(current)
            current = [record]
            continue

        current.append(record)

    if current:
        blocks.append(current)
    return blocks


def _starts_new_experience_block(
    current: list[dict[str, object]],
    candidate: dict[str, object],
) -> bool:
    previous = current[-1]
    previous_text = str(previous["stripped"])
    candidate_text = str(candidate["stripped"])
    previous_number = int(previous["number"])
    candidate_number = int(candidate["number"])

    if candidate_number > previous_number + 1:
        return True
    if _is_bullet_line(previous_text) and not _is_bullet_line(candidate_text) and _looks_like_header_line(candidate_text):
        return True
    if _looks_like_date_line(candidate_text) and any(
        _looks_like_date_line(str(item["stripped"])) for item in current
    ):
        return True
    return False


def _parse_experience_block(
    block: list[dict[str, object]],
    *,
    position: int,
) -> dict[str, object] | None:
    header_records: list[dict[str, object]] = []
    detail_records: list[dict[str, object]] = []
    details_started = False

    for record in block:
        stripped = str(record["stripped"])
        if not details_started and not _is_bullet_line(stripped):
            header_records.append(record)
            continue
        details_started = True
        detail_records.append(record)

    if not detail_records:
        date_index = _first_date_header_index(header_records)
        if date_index is not None and date_index < len(header_records) - 1:
            detail_records = header_records[date_index + 1 :]
            header_records = header_records[: date_index + 1]

    if not _is_experience_like_block(header_records, detail_records):
        return None

    date_text = _first_date_text(header_records)
    role, organization = _extract_role_and_organization(header_records)

    return {
        "position": position,
        "section_key": "experience",
        "line_start": int(block[0]["number"]),
        "line_end": int(block[-1]["number"]),
        "header_line_numbers": [int(record["number"]) for record in header_records],
        "detail_line_numbers": [int(record["number"]) for record in detail_records],
        "header_lines": [str(record["stripped"]) for record in header_records],
        "role": role,
        "organization": organization,
        "date_text": date_text,
        "detail_line_count": len(detail_records),
        "bullet_count_estimate": _estimate_bullet_count(detail_records),
    }


def _is_experience_like_block(
    header_records: list[dict[str, object]],
    detail_records: list[dict[str, object]],
) -> bool:
    if not header_records:
        return False

    header_lines = [str(record["stripped"]) for record in header_records]
    has_date = any(_looks_like_date_line(line) for line in header_lines)
    has_separator = any(_header_parts(line) for line in header_lines)

    if has_date and (detail_records or has_separator or len(header_records) >= 2):
        return True
    if detail_records and (has_separator or len(header_records) >= 2):
        return True
    return False


def _first_date_header_index(header_records: list[dict[str, object]]) -> int | None:
    for index, record in enumerate(header_records):
        if _looks_like_date_line(str(record["stripped"])):
            return index
    return None


def _first_date_text(header_records: list[dict[str, object]]) -> str | None:
    for record in header_records:
        stripped = str(record["stripped"])
        parts = _header_parts(stripped)
        for part in parts:
            if _looks_like_date_line(part):
                return part
        if _looks_like_date_line(stripped):
            return stripped
    return None


def _extract_role_and_organization(
    header_records: list[dict[str, object]],
) -> tuple[str | None, str | None]:
    combined_parts: list[str] = []
    for record in header_records:
        stripped = str(record["stripped"])
        if not stripped:
            continue
        parts = _header_parts(stripped)
        if parts:
            combined_parts.extend(parts)
            continue
        if not _looks_like_date_line(stripped):
            combined_parts.append(stripped)

    cleaned_parts = [part for part in combined_parts if part and not _looks_like_date_line(part)]
    if len(cleaned_parts) >= 2:
        return cleaned_parts[0], cleaned_parts[1]
    if cleaned_parts:
        return cleaned_parts[0], None

    texts = [str(record["stripped"]) for record in header_records if str(record["stripped"])]
    if len(texts) >= 2:
        return texts[0], texts[1]
    if not texts:
        return None, None
    return texts[0], None


def _header_parts(text: str) -> list[str]:
    split_patterns = (
        r"\s\|\s",
        r"\s@\s",
        r"\sat\s",
        r"\schez\s",
        r"\s[-–—]\s",
    )
    for pattern in split_patterns:
        if not re.search(pattern, text, flags=re.IGNORECASE):
            continue
        parts = [part.strip(" ,|") for part in re.split(pattern, text) if part.strip(" ,|")]
        if len(parts) >= 2:
            return parts
    return []


def _estimate_bullet_count(detail_records: list[dict[str, object]]) -> int:
    if not detail_records:
        return 0
    bullet_lines = sum(1 for record in detail_records if _is_bullet_line(str(record["stripped"])))
    return bullet_lines or len(detail_records)


def _is_bullet_line(text: str) -> bool:
    return _BULLET_PREFIX_PATTERN.match(text or "") is not None


def _looks_like_header_line(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned or _is_bullet_line(cleaned):
        return False
    if len(cleaned) > 140:
        return False
    if cleaned.endswith("."):
        return False
    return True


def _looks_like_date_line(text: str) -> bool:
    return _DATE_LINE_PATTERN.search(text or "") is not None


def _build_line_to_experience_map(experience_entries: list[dict[str, object]]) -> dict[int, int]:
    line_to_experience: dict[int, int] = {}
    for entry in experience_entries:
        position = int(entry["position"])
        start = int(entry["line_start"])
        end = int(entry["line_end"])
        for line_number in range(start, end + 1):
            line_to_experience[line_number] = position
    return line_to_experience


def _detect_metric_bearing_lines(
    lines: list[dict[str, object]],
    line_to_section: dict[int, str],
    line_to_experience: dict[int, int],
) -> list[dict[str, object]]:
    metric_lines: list[dict[str, object]] = []
    for record in lines:
        stripped = str(record["stripped"])
        if not stripped:
            continue
        tokens = _metric_tokens_for_line(stripped)
        if not tokens:
            continue
        line_number = int(record["number"])
        metric_lines.append(
            {
                "line_number": line_number,
                "section_key": line_to_section.get(line_number),
                "experience_position": line_to_experience.get(line_number),
                "text": stripped,
                "matched_tokens": tokens,
            }
        )
    return metric_lines


def _metric_tokens_for_line(text: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    for pattern in (_METRIC_SIGNAL_PATTERN, _METRIC_UNIT_PATTERN):
        for match in pattern.finditer(text or ""):
            token = match.group(0).strip()
            if token:
                matches.append((match.start(), token))
    matches.sort(key=lambda item: item[0])

    tokens: list[str] = []
    seen: set[str] = set()
    for _, token in matches:
        normalized = _normalize_text(token)
        if normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(token)
    return tokens


def _detect_tool_system_terms(
    lines: list[dict[str, object]],
    line_to_section: dict[int, str],
    line_to_experience: dict[int, int],
) -> list[dict[str, object]]:
    term_map: dict[str, dict[str, object]] = {}

    for record in lines:
        stripped = str(record["stripped"])
        if not stripped:
            continue

        line_number = int(record["number"])
        for canonical, patterns in _COMPILED_TOOL_PATTERNS:
            match_positions = [
                match.start()
                for pattern in patterns
                for match in [pattern.search(stripped)]
                if match is not None
            ]
            if not match_positions:
                continue
            first_match_column = min(match_positions)

            entry = term_map.setdefault(
                canonical,
                {
                    "term": canonical,
                    "normalized_term": _normalize_text(canonical),
                    "line_numbers": [],
                    "sections": [],
                    "experience_positions": [],
                    "_first_match": (line_number, first_match_column),
                },
            )
            if line_number not in entry["line_numbers"]:
                entry["line_numbers"].append(line_number)
            section_key = line_to_section.get(line_number)
            if section_key and section_key not in entry["sections"]:
                entry["sections"].append(section_key)
            experience_position = line_to_experience.get(line_number)
            if (
                experience_position is not None
                and experience_position not in entry["experience_positions"]
            ):
                entry["experience_positions"].append(experience_position)

    terms = list(term_map.values())
    for term in terms:
        term["count"] = len(term["line_numbers"])
    terms.sort(key=lambda item: (item["_first_match"][0], item["_first_match"][1], str(item["term"])))
    for term in terms:
        term.pop("_first_match", None)
    return terms


def _annotate_experience_entries(
    experience_entries: list[dict[str, object]],
    metric_bearing_lines: list[dict[str, object]],
    tool_system_terms: list[dict[str, object]],
) -> None:
    metric_by_experience: dict[int, list[int]] = {}
    for item in metric_bearing_lines:
        experience_position = item.get("experience_position")
        if experience_position is None:
            continue
        metric_by_experience.setdefault(int(experience_position), []).append(int(item["line_number"]))

    tools_by_experience: dict[int, list[str]] = {}
    for item in tool_system_terms:
        for experience_position in item.get("experience_positions") or []:
            tools_by_experience.setdefault(int(experience_position), []).append(str(item["term"]))

    for entry in experience_entries:
        position = int(entry["position"])
        metric_line_numbers = metric_by_experience.get(position, [])
        entry["metric_line_count"] = len(metric_line_numbers)
        entry["metric_line_numbers"] = metric_line_numbers
        entry["tool_system_terms"] = _unique_preserve_order(tools_by_experience.get(position, []))


def _unique_preserve_order(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_values.append(value)
    return unique_values
