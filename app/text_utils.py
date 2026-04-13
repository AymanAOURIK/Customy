"""Shared text cleaning and matching utilities."""
from __future__ import annotations

import re
from typing import Any


def clean_text(value: object) -> str:
    """Normalize whitespace and coerce to str."""
    return " ".join(str(value or "").strip().split())


def sanitize_text(value: object, *, preserve_newlines: bool = True) -> str:
    """Strip NUL/control characters while preserving readable text structure."""
    text = str(value or "")
    if not text:
        return ""

    text = text.replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    cleaned_chars: list[str] = []
    for char in text:
        codepoint = ord(char)
        if char == "\x00":
            continue
        if char == "\n" and preserve_newlines:
            cleaned_chars.append(char)
            continue
        if char == "\t":
            cleaned_chars.append(char)
            continue
        if codepoint < 32 or codepoint == 127:
            cleaned_chars.append(" ")
            continue
        cleaned_chars.append(char)

    cleaned = "".join(cleaned_chars)
    if preserve_newlines:
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()
    return " ".join(cleaned.split())


def sanitize_data_strings(value: Any, *, preserve_newlines: bool = True) -> Any:
    """Recursively sanitize string values inside dict/list payloads."""
    if isinstance(value, str):
        return sanitize_text(value, preserve_newlines=preserve_newlines)
    if isinstance(value, list):
        return [sanitize_data_strings(item, preserve_newlines=preserve_newlines) for item in value]
    if isinstance(value, dict):
        return {
            key: sanitize_data_strings(item, preserve_newlines=preserve_newlines)
            for key, item in value.items()
        }
    return value


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
