"""Language detection, language matching, and bullet localisation helpers."""
from __future__ import annotations

from app.schemas import ENGLISH_MARKER_PATTERN, FRENCH_MARKER_PATTERN, _clean_text_list
from app.text_utils import clean_text as _clean_text


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


def _resume_language(jd_analysis: dict) -> str:
    return "fr" if _clean_text(jd_analysis.get("language")).lower() == "fr" else "en"


def _experience_bullets_for_language(item: dict, resume_language: str) -> list[str]:
    base_bullets = _clean_text_list((item or {}).get("bullets"))
    if resume_language != "fr":
        return base_bullets
    localized_bullets = _clean_text_list((item or {}).get("bullets_fr"))
    if len(localized_bullets) == len(base_bullets):
        return localized_bullets
    return base_bullets
