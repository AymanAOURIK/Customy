"""Shared text cleaning and matching utilities."""
from __future__ import annotations

import re


def clean_text(value: object) -> str:
    """Normalize whitespace and coerce to str."""
    return " ".join(str(value or "").strip().split())


def term_matches_text(text: str, term: str) -> bool:
    """Return True if *term* appears as a whole token in *text* (case-insensitive)."""
    cleaned_term = clean_text(term)
    if not cleaned_term:
        return False
    escaped = re.escape(cleaned_term)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ./+_-]*[A-Za-z0-9]", cleaned_term):
        pattern = rf"(?<!\w){escaped}(?!\w)"
    else:
        pattern = escaped
    return re.search(pattern, str(text or ""), flags=re.IGNORECASE) is not None
