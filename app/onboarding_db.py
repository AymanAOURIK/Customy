"""DB layer for resume_uploads and onboarding_drafts (Customy V3 onboarding).

Mirrors the style and conventions of app/profile_db.py.
All connections use app/db_postgres._connect() with psycopg2 RealDictCursor.
"""
from __future__ import annotations

import json
from typing import Any

from app.db_postgres import _connect, _row


# ---------------------------------------------------------------------------
# resume_uploads
# ---------------------------------------------------------------------------

def insert_resume_upload(
    user_id: str,
    storage_path: str,
    original_filename: str,
    file_size_bytes: int | None,
) -> dict[str, Any]:
    """Insert a new resume_uploads row. Returns the created row."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO resume_uploads
                    (user_id, storage_path, original_filename, file_size_bytes)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (user_id, storage_path, original_filename, file_size_bytes),
            )
            return _row(cur) or {}


def update_resume_upload_parsed(
    upload_id: str,
    parsed_text: str | None,
    parse_error: str | None = None,
) -> None:
    """Set parse_status to 'done' or 'failed' and store the result."""
    status = "done" if parsed_text is not None else "failed"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE resume_uploads
                SET parse_status = %s,
                    parsed_text  = %s,
                    parse_error  = %s
                WHERE id = %s
                """,
                (status, parsed_text, parse_error, upload_id),
            )


def get_latest_resume_upload(user_id: str) -> dict[str, Any] | None:
    """Return the most recently created resume upload for this user, or None."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM resume_uploads
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            )
            return _row(cur)


# ---------------------------------------------------------------------------
# onboarding_drafts
# ---------------------------------------------------------------------------

def upsert_onboarding_draft(
    user_id: str,
    source_resume_upload_id: str,
    draft_data: dict[str, Any],
    gap_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Create or replace the onboarding draft for this user.

    Uses INSERT ... ON CONFLICT (user_id) DO UPDATE so that re-uploading
    a resume resets the draft cleanly.
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO onboarding_drafts
                    (user_id, source_resume_upload_id, draft_data, gap_analysis, status)
                VALUES (%s, %s, %s, %s, 'draft')
                ON CONFLICT (user_id) DO UPDATE SET
                    source_resume_upload_id = EXCLUDED.source_resume_upload_id,
                    draft_data              = EXCLUDED.draft_data,
                    gap_analysis            = EXCLUDED.gap_analysis,
                    status                  = 'draft',
                    updated_at              = NOW()
                RETURNING *
                """,
                (
                    user_id,
                    source_resume_upload_id,
                    json.dumps(draft_data),
                    json.dumps(gap_analysis),
                ),
            )
            return _row(cur) or {}


def get_onboarding_draft(user_id: str) -> dict[str, Any] | None:
    """Return the onboarding draft for this user, or None if not found."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM onboarding_drafts WHERE user_id = %s",
                (user_id,),
            )
            return _row(cur)
