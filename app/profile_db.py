"""Profile CRUD for Customy V3 (SaaS mode).

Loads and saves the candidate profile from the Postgres `profiles` table.
The returned dict has the same shape as build_candidate_context() in profile.py
so the rest of the pipeline (generator, latex, targeting) works unchanged.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg2.extras

from app.db_postgres import _connect, _row


def get_profile(user_id: str) -> dict[str, Any] | None:
    """Return the profile row for this user, or None if not found."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM profiles WHERE user_id = %s",
                (user_id,),
            )
            row = _row(cur)
    return row


def create_profile(user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new profile row. Returns the created row."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO profiles (
                    user_id, full_name, email, phone, location,
                    linkedin, github, headline, summary,
                    skills, experiences, education,
                    spoken_languages, scoring_keywords
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    user_id,
                    data.get("full_name", ""),
                    data.get("email"),
                    data.get("phone"),
                    data.get("location"),
                    data.get("linkedin"),
                    data.get("github"),
                    data.get("headline"),
                    data.get("summary"),
                    json.dumps(data.get("skills", {})),
                    json.dumps(data.get("experiences", [])),
                    json.dumps(data.get("education", [])),
                    json.dumps(data.get("spoken_languages", [])),
                    json.dumps(data.get("scoring_keywords", [])),
                ),
            )
            row = _row(cur)
    return row or {}


def update_profile(user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Update an existing profile. Returns the updated row."""
    # Build update fields dynamically to allow partial updates
    allowed = {
        "full_name", "email", "phone", "location",
        "linkedin", "github", "headline", "summary",
        "skills", "experiences", "education",
        "spoken_languages", "scoring_keywords",
    }
    json_fields = {"skills", "experiences", "education", "spoken_languages", "scoring_keywords"}

    set_clauses = []
    values = []
    for field in allowed:
        if field in data:
            set_clauses.append(f"{field} = %s")
            value = data[field]
            if field in json_fields and not isinstance(value, str):
                value = json.dumps(value)
            values.append(value)

    if not set_clauses:
        return get_profile(user_id) or {}

    set_clauses.append("updated_at = NOW()")
    values.extend([user_id])

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE profiles SET {', '.join(set_clauses)} WHERE user_id = %s RETURNING *",
                values,
            )
            row = _row(cur)
    return row or {}


def upsert_profile(user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create or update the profile for this user."""
    existing = get_profile(user_id)
    if existing:
        return update_profile(user_id, data)
    return create_profile(user_id, data)


def profile_to_candidate_context(profile: dict[str, Any]) -> dict[str, Any]:
    """Convert a Postgres profiles row into the candidate_context dict shape
    expected by the generation pipeline (generator.py, latex.py, targeting.py).

    This mirrors what build_candidate_context() produces from candidate.yaml.
    """

    def _json(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value if value is not None else {}

    skills = _json(profile.get("skills")) or {}
    experiences = _json(profile.get("experiences")) or []
    education = _json(profile.get("education")) or []
    spoken_languages = _json(profile.get("spoken_languages")) or []
    scoring_keywords = _json(profile.get("scoring_keywords")) or []

    return {
        "candidate_source": "postgres",
        "personal": {
            "name": profile.get("full_name", ""),
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "location": profile.get("location", ""),
            "linkedin": profile.get("linkedin", ""),
            "github": profile.get("github", ""),
            "headline": profile.get("headline", ""),
        },
        "summary": profile.get("summary", ""),
        "skills": skills,
        "experiences": experiences,
        "education": education,
        "spoken_languages": spoken_languages,
        "scoring_keywords": scoring_keywords,
    }
