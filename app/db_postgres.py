"""Postgres DB layer for Customy V3 (SaaS mode).

All functions mirror app/db.py but operate on Postgres with user_id isolation.
Uses a simple connection-per-call approach (psycopg2 with autocommit=False).
RLS enforces row isolation at the DB level; user_id params add defence-in-depth.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any, Generator

import psycopg2
import psycopg2.extras

VALID_STATUSES = {"generated", "applied", "interviewing", "offer", "rejected", "ghosted"}


def _get_dsn(service_role: bool = False) -> str:
    """Return the Postgres DSN. service_role=True uses the direct service-key URL."""
    if service_role:
        dsn = os.environ.get("DATABASE_URL_SERVICE", os.environ.get("DATABASE_URL", ""))
    else:
        dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")
    return dsn


@contextmanager
def _connect(service_role: bool = False) -> Generator[psycopg2.extensions.connection, None, None]:
    """Context manager that yields a psycopg2 connection and commits/rolls back."""
    conn = psycopg2.connect(_get_dsn(service_role), cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row(cursor: psycopg2.extensions.cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    return dict(row) if row else None


def _rows(cursor: psycopg2.extensions.cursor) -> list[dict[str, Any]]:
    return [dict(r) for r in cursor.fetchall()]


def _coerce_bool(value: Any) -> bool:
    """Normalize insert/update flags to real Python booleans for Postgres."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off", ""}:
            return False
    return bool(value)


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

def insert_application(
    user_id: str,
    company: str,
    role: str,
    slug: str,
    jd_raw: str,
    jd_language: str | None,
    jd_location: str | None,
    job_application_url: str | None,
    resume_tex_url: str | None,
    resume_pdf_url: str | None,
    cover_letter_url: str | None,
    linkedin_msg_url: str | None,
    email_draft_url: str | None,
    cover_letter: bool,
    linkedin_msg: bool,
    email_draft: bool,
    tokens_used: int | None,
    model_used: str | None,
    initial_score: float | None,
    updated_score: float | None,
    usage_summary: dict | None = None,
    archetype: str | None = None,
    job_id: int | None = None,
) -> int:
    """Insert a new application row. Returns the new application id."""
    usage = usage_summary or {}
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO applications (
                    user_id, company, role, slug, jd_raw, jd_language, jd_location,
                    job_application_url, job_id,
                    resume_tex_url, resume_pdf_url, cover_letter_url, linkedin_msg_url, email_draft_url,
                    cover_letter, linkedin_msg, email_draft,
                    tokens_used, model_used, score, initial_score, updated_score,
                    prompt_tokens, cached_prompt_tokens, completion_tokens,
                    input_cost_usd, cached_input_cost_usd, output_cost_usd, total_cost_usd,
                    api_attempts, pricing_basis, role_archetype
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING id
                """,
                (
                    user_id, company, role, slug, jd_raw, jd_language, jd_location,
                    job_application_url, job_id,
                    resume_tex_url, resume_pdf_url, cover_letter_url, linkedin_msg_url, email_draft_url,
                    _coerce_bool(cover_letter), _coerce_bool(linkedin_msg), _coerce_bool(email_draft),
                    tokens_used, model_used, initial_score, initial_score, updated_score,
                    usage.get("prompt_tokens"), usage.get("cached_prompt_tokens"),
                    usage.get("completion_tokens"),
                    usage.get("input_cost_usd"), usage.get("cached_input_cost_usd"),
                    usage.get("output_cost_usd"), usage.get("total_cost_usd"),
                    usage.get("attempt_count"), usage.get("pricing_basis"), archetype,
                ),
            )
            row = _row(cur)
            return int(row["id"])


def get_application(user_id: str, app_id: int) -> dict[str, Any]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM applications WHERE id = %s AND user_id = %s",
                (app_id, user_id),
            )
            return _row(cur) or {}


def application_slug_exists(user_id: str, slug: str) -> bool:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM applications WHERE slug = %s AND user_id = %s LIMIT 1",
                (slug, user_id),
            )
            return cur.fetchone() is not None


def list_applications(
    user_id: str,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cur:
            if status_filter:
                cur.execute(
                    """
                    SELECT * FROM applications
                    WHERE user_id = %s AND status = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, status_filter, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM applications
                    WHERE user_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, limit, offset),
                )
            return _rows(cur)


def update_status(user_id: str, app_id: int, new_status: str, detail: str = "") -> None:
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM applications WHERE id = %s AND user_id = %s",
                (app_id, user_id),
            )
            row = _row(cur)
            if row is None:
                raise ValueError(f"Application {app_id} not found")
            old_status = row["status"]
            cur.execute(
                "UPDATE applications SET status = %s WHERE id = %s AND user_id = %s",
                (new_status, app_id, user_id),
            )
            cur.execute(
                """
                INSERT INTO events (application_id, event_type, old_status, new_status, detail)
                VALUES (%s, 'status_change', %s, %s, %s)
                """,
                (app_id, old_status, new_status, detail),
            )


def set_duplicate_flag(user_id: str, app_id: int, is_duplicate: bool, detail: str = "") -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_duplicate FROM applications WHERE id = %s AND user_id = %s",
                (app_id, user_id),
            )
            row = _row(cur)
            if row is None:
                raise ValueError(f"Application {app_id} not found")
            old_value = int(row["is_duplicate"] or 0)
            new_value = int(bool(is_duplicate))
            if old_value == new_value:
                return
            cur.execute(
                "UPDATE applications SET is_duplicate = %s WHERE id = %s AND user_id = %s",
                (new_value, app_id, user_id),
            )
            cur.execute(
                """
                INSERT INTO events (application_id, event_type, detail)
                VALUES (%s, 'duplicate_flag_change', %s)
                """,
                (app_id, detail or f"is_duplicate:{old_value}->{new_value}"),
            )


def get_application_events(user_id: str, app_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.*
                FROM events e
                JOIN applications a ON a.id = e.application_id
                WHERE e.application_id = %s AND a.user_id = %s
                ORDER BY e.created_at ASC, e.id ASC
                """,
                (app_id, user_id),
            )
            return _rows(cur)


def update_application_notes(user_id: str, app_id: int, notes: str) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE applications
                SET notes = %s
                WHERE id = %s AND user_id = %s
                """,
                (notes.strip() or None, app_id, user_id),
            )
            if cur.rowcount == 0:
                raise ValueError(f"Application {app_id} not found")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_funnel_stats(user_id: str) -> dict[str, int]:
    stats: dict[str, int] = {s: 0 for s in VALID_STATUSES}
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM jobs
                WHERE user_id = %s
                GROUP BY status
                """,
                (user_id,),
            )
            for row in _rows(cur):
                if row["status"] in stats:
                    stats[row["status"]] = int(row["count"])
    return stats


def get_daily_stats(user_id: str, days: int = 30) -> list[dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
            cur.execute(
                """
                SELECT
                    date::text AS date,
                    generated, applied, interviews, offers, rejections
                FROM daily_stats
                WHERE user_id = %s AND date >= %s
                ORDER BY date ASC
                """,
                (user_id, cutoff),
            )
            existing = {r["date"]: r for r in _rows(cur)}
    result = []
    start = date.today() - timedelta(days=days - 1)
    for i in range(days):
        key = (start + timedelta(days=i)).isoformat()
        result.append(
            existing.get(
                key,
                {
                    "date": key,
                    "generated": 0,
                    "applied": 0,
                    "interviews": 0,
                    "offers": 0,
                    "rejections": 0,
                },
            )
        )
    return result


def refresh_daily_stats(user_id: str) -> None:
    """Recompute daily_stats for this user from the jobs table."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM daily_stats WHERE user_id = %s", (user_id,))
            cur.execute(
                """
                INSERT INTO daily_stats (user_id, date, generated, applied, interviews, offers, rejections)
                SELECT
                    user_id,
                    created_at::date AS date,
                    COUNT(*) FILTER (WHERE status NOT IN ('saved', 'archived')) AS generated,
                    COUNT(*) FILTER (WHERE status = 'applied') AS applied,
                    COUNT(*) FILTER (WHERE status = 'interviewing') AS interviews,
                    COUNT(*) FILTER (WHERE status = 'offer') AS offers,
                    COUNT(*) FILTER (WHERE status IN ('rejected', 'ghosted')) AS rejections
                FROM jobs
                WHERE user_id = %s
                GROUP BY user_id, created_at::date
                ON CONFLICT (user_id, date) DO UPDATE SET
                    generated  = EXCLUDED.generated,
                    applied    = EXCLUDED.applied,
                    interviews = EXCLUDED.interviews,
                    offers     = EXCLUDED.offers,
                    rejections = EXCLUDED.rejections
                """,
                (user_id,),
            )


def get_quick_stats(user_id: str) -> dict[str, Any]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '6 days') AS week_count,
                    COUNT(*) FILTER (WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW())) AS month_count,
                    AVG(relevance_score) AS avg_score
                FROM jobs
                WHERE user_id = %s
                """,
                (user_id,),
            )
            stats_row = _row(cur) or {}

            cur.execute(
                """
                SELECT title AS role, COUNT(*) AS count FROM jobs
                WHERE user_id = %s AND title != ''
                GROUP BY title ORDER BY count DESC, title ASC LIMIT 1
                """,
                (user_id,),
            )
            role_row = _row(cur)

            cur.execute(
                """
                SELECT
                    COUNT(*) AS request_count,
                    SUM(CASE WHEN request_status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                    SUM(prompt_tokens) AS prompt_tokens,
                    SUM(cached_prompt_tokens) AS cached_prompt_tokens,
                    SUM(completion_tokens) AS completion_tokens,
                    SUM(total_tokens) AS total_tokens,
                    SUM(total_cost_usd) AS total_cost_usd,
                    AVG(total_cost_usd) AS average_cost_usd
                FROM api_usage
                WHERE user_id = %s
                """,
                (user_id,),
            )
            usage_row = _row(cur) or {}

    def _f(v: Any) -> float | None:
        return round(float(v), 1) if v is not None else None

    return {
        "applications_this_week": int(stats_row.get("week_count") or 0),
        "applications_this_month": int(stats_row.get("month_count") or 0),
        "average_initial_score": _f(stats_row.get("avg_score")),
        "average_updated_score": None,
        "average_score": _f(stats_row.get("avg_score")),
        "most_targeted_role": role_row["role"] if role_row else "",
        "openai_request_count": int(usage_row.get("request_count") or 0),
        "openai_failed_request_count": int(usage_row.get("failed_count") or 0),
        "openai_prompt_tokens": int(usage_row.get("prompt_tokens") or 0),
        "openai_cached_prompt_tokens": int(usage_row.get("cached_prompt_tokens") or 0),
        "openai_completion_tokens": int(usage_row.get("completion_tokens") or 0),
        "openai_total_tokens": int(usage_row.get("total_tokens") or 0),
        "openai_total_cost_usd": round(float(usage_row.get("total_cost_usd") or 0.0), 7),
        "openai_average_cost_usd": round(float(usage_row.get("average_cost_usd") or 0.0), 7),
    }


def get_apply_queue(user_id: str, min_score: float = 0.0, limit: int = 200) -> list[dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM applications
                WHERE user_id = %s
                  AND status = 'generated'
                  AND COALESCE(is_duplicate, 0) = 0
                  AND COALESCE(updated_score, initial_score, score, 0) >= %s
                ORDER BY COALESCE(updated_score, initial_score, score, 0) DESC, created_at DESC
                LIMIT %s
                """,
                (user_id, min_score, limit),
            )
            return _rows(cur)


def get_analytics(user_id: str) -> dict[str, Any]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM applications WHERE user_id = %s AND COALESCE(is_duplicate, 0) = 0
                GROUP BY status
                """,
                (user_id,),
            )
            funnel = {r["status"]: int(r["count"]) for r in _rows(cur)}
            total = sum(funnel.values()) or 1
            post_gen = sum(funnel.get(s, 0) for s in ("applied", "interviewing", "offer", "rejected", "ghosted"))

            cur.execute(
                """
                SELECT COALESCE(role_archetype, 'general') AS archetype,
                       COUNT(*) AS count,
                       ROUND(AVG(COALESCE(updated_score, initial_score, score))::numeric, 1) AS avg_score,
                       SUM(CASE WHEN status IN ('interviewing', 'offer') THEN 1 ELSE 0 END) AS positive_outcomes,
                       SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) AS applied_count
                FROM applications
                WHERE user_id = %s AND COALESCE(is_duplicate, 0) = 0
                GROUP BY role_archetype ORDER BY count DESC
                """,
                (user_id,),
            )
            archetypes = _rows(cur)

            cur.execute(
                """
                SELECT
                  CASE
                    WHEN COALESCE(score, 0) >= 80 THEN '80-100'
                    WHEN COALESCE(score, 0) >= 60 THEN '60-79'
                    WHEN COALESCE(score, 0) >= 40 THEN '40-59'
                    ELSE '0-39'
                  END AS bucket,
                  COUNT(*) AS count
                FROM applications
                WHERE user_id = %s AND COALESCE(is_duplicate, 0) = 0
                GROUP BY bucket ORDER BY bucket DESC
                """,
                (user_id,),
            )
            score_dist = _rows(cur)

            cur.execute(
                """
                SELECT status,
                       ROUND(AVG(COALESCE(updated_score, initial_score, score))::numeric, 1) AS avg_score,
                       COUNT(*) AS count
                FROM applications
                WHERE user_id = %s AND COALESCE(is_duplicate, 0) = 0
                GROUP BY status ORDER BY count DESC
                """,
                (user_id,),
            )
            score_by_outcome = _rows(cur)

    return {
        "funnel": funnel,
        "conversion_rates": {
            "generated_to_applied": round(post_gen / total * 100, 1),
            "applied_to_interview": round(funnel.get("interviewing", 0) / max(post_gen, 1) * 100, 1),
            "interview_to_offer": round(
                funnel.get("offer", 0) / max(funnel.get("interviewing", 1), 1) * 100, 1
            ),
        },
        "archetypes": archetypes,
        "score_distribution": score_dist,
        "score_by_outcome": score_by_outcome,
    }


def get_tracker_applications(user_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.*,
                    COALESCE(last_ev.created_at, a.created_at) AS last_status_at
                FROM applications a
                LEFT JOIN (
                    SELECT application_id, MAX(created_at) AS created_at
                    FROM events
                    WHERE event_type = 'status_change'
                    GROUP BY application_id
                ) last_ev ON last_ev.application_id = a.id
                WHERE a.user_id = %s AND COALESCE(a.is_duplicate, 0) = 0
                ORDER BY
                    CASE a.status
                        WHEN 'offer'        THEN 1
                        WHEN 'interviewing' THEN 2
                        WHEN 'applied'      THEN 3
                        WHEN 'generated'    THEN 4
                        WHEN 'ghosted'      THEN 5
                        WHEN 'rejected'     THEN 6
                        ELSE 7
                    END,
                    COALESCE(last_ev.created_at, a.created_at) DESC,
                    a.id DESC
                """,
                (user_id,),
            )
            return _rows(cur)


# ---------------------------------------------------------------------------
# API usage
# ---------------------------------------------------------------------------

def record_api_usage(
    user_id: str,
    attempts: list[dict[str, Any]],
    *,
    application_id: int | None,
    request_status: str,
    error_message: str = "",
) -> None:
    if not attempts:
        return
    with _connect() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                """
                INSERT INTO api_usage (
                    user_id, application_id, request_kind, request_status, error_message,
                    attempt_number, model_used,
                    prompt_tokens, cached_prompt_tokens, completion_tokens, total_tokens,
                    input_cost_usd, cached_input_cost_usd, output_cost_usd, total_cost_usd,
                    pricing_basis
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        user_id,
                        application_id,
                        str(a.get("request_kind") or "generate_pack"),
                        request_status,
                        error_message or None,
                        int(a.get("attempt_number") or 0),
                        str(a.get("model_used") or ""),
                        int(a.get("prompt_tokens") or 0),
                        int(a.get("cached_prompt_tokens") or 0),
                        int(a.get("completion_tokens") or 0),
                        int(a.get("total_tokens") or 0),
                        a.get("input_cost_usd"),
                        a.get("cached_input_cost_usd"),
                        a.get("output_cost_usd"),
                        a.get("total_cost_usd"),
                        str(a.get("pricing_basis") or ""),
                    )
                    for a in attempts
                ],
            )


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def insert_job(
    user_id: str,
    source: str,
    source_url: str | None,
    fingerprint: str,
    title: str,
    company: str | None,
    location_raw: str | None,
    description_text: str,
    posted_date: str | None = None,
    salary_raw: str | None = None,
    relevance_score: float | None = None,
    jd_analysis_json: str | None = None,
    notes: str | None = None,
) -> int:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jobs (
                    user_id, source, source_url, fingerprint, title, company,
                    location_raw, description_text, posted_date, salary_raw,
                    relevance_score, jd_analysis_json, notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, fingerprint) DO NOTHING
                RETURNING id
                """,
                (
                    user_id, source, source_url, fingerprint, title, company,
                    location_raw, description_text, posted_date, salary_raw,
                    relevance_score, jd_analysis_json, notes,
                ),
            )
            row = _row(cur)
            return int(row["id"]) if row else -1  # -1 = duplicate


def get_job(user_id: str, job_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM jobs WHERE id = %s AND user_id = %s",
                (job_id, user_id),
            )
            return _row(cur)


def list_jobs(
    user_id: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    """
                    SELECT * FROM jobs WHERE user_id = %s AND status = %s
                    ORDER BY created_at DESC LIMIT %s OFFSET %s
                    """,
                    (user_id, status, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM jobs WHERE user_id = %s
                    ORDER BY created_at DESC LIMIT %s OFFSET %s
                    """,
                    (user_id, limit, offset),
                )
            return _rows(cur)


def update_job_status(user_id: str, job_id: int, status: str) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status = %s WHERE id = %s AND user_id = %s",
                (status, job_id, user_id),
            )


def update_job_structured(user_id: str, job_id: int, structured_json: str, score: float | None) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs
                SET structured_job_json = %s, relevance_score = COALESCE(%s, relevance_score)
                WHERE id = %s AND user_id = %s
                """,
                (structured_json, score, job_id, user_id),
            )


def link_job_to_application(user_id: str, job_id: int, application_id: int) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs SET application_id = %s, status = 'generated'
                WHERE id = %s AND user_id = %s
                """,
                (application_id, job_id, user_id),
            )


def update_job_notes(user_id: str, job_id: int, notes: str | None) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET notes = %s WHERE id = %s AND user_id = %s",
                (notes, job_id, user_id),
            )


def delete_job(user_id: str, job_id: int) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM jobs WHERE id = %s AND user_id = %s",
                (job_id, user_id),
            )
