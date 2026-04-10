from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

VALID_STATUSES = {"generated", "applied", "interviewing", "offer", "rejected", "ghosted"}
APPLICATION_EXTRA_COLUMNS = {
    "job_application_url": "TEXT",
    "initial_score": "REAL",
    "updated_score": "REAL",
    "is_duplicate": "INTEGER NOT NULL DEFAULT 0",
    "prompt_tokens": "INTEGER",
    "cached_prompt_tokens": "INTEGER",
    "completion_tokens": "INTEGER",
    "input_cost_usd": "REAL",
    "cached_input_cost_usd": "REAL",
    "output_cost_usd": "REAL",
    "total_cost_usd": "REAL",
    "api_attempts": "INTEGER",
    "pricing_basis": "TEXT",
    "role_archetype": "TEXT",
}


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict:
    return dict(row) if row is not None else {}


def _ensure_columns(conn: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    existing_columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}
    for column_name, column_type in columns.items():
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def init_db(db_path: str) -> None:
    """Creates tables if not exist. Called at startup. Creates data/ dir if missing."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(str(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
                company               TEXT    NOT NULL,
                role                  TEXT    NOT NULL,
                slug                  TEXT    NOT NULL UNIQUE,
                status                TEXT    NOT NULL DEFAULT 'generated',
                is_duplicate          INTEGER NOT NULL DEFAULT 0,
                jd_raw                TEXT    NOT NULL,
                jd_language           TEXT,
                jd_location           TEXT,
                job_application_url   TEXT,
                outputs_path          TEXT,
                resume_tex_path       TEXT,
                resume_pdf_path       TEXT,
                cover_letter          INTEGER NOT NULL DEFAULT 0,
                linkedin_msg          INTEGER NOT NULL DEFAULT 0,
                email_draft           INTEGER NOT NULL DEFAULT 0,
                tokens_used           INTEGER,
                model_used            TEXT,
                score                 REAL,
                initial_score         REAL,
                updated_score         REAL,
                notes                 TEXT,
                prompt_tokens         INTEGER,
                cached_prompt_tokens  INTEGER,
                completion_tokens     INTEGER,
                input_cost_usd        REAL,
                cached_input_cost_usd REAL,
                output_cost_usd       REAL,
                total_cost_usd        REAL,
                api_attempts          INTEGER,
                pricing_basis         TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id   INTEGER NOT NULL REFERENCES applications(id),
                created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
                event_type       TEXT    NOT NULL,
                old_status       TEXT,
                new_status       TEXT,
                detail           TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_stats (
                date             TEXT PRIMARY KEY,
                generated        INTEGER NOT NULL DEFAULT 0,
                applied          INTEGER NOT NULL DEFAULT 0,
                interviews       INTEGER NOT NULL DEFAULT 0,
                offers           INTEGER NOT NULL DEFAULT 0,
                rejections       INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS answer_bank (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                question_key    TEXT    NOT NULL UNIQUE,
                question_text   TEXT    NOT NULL,
                answer_text     TEXT    NOT NULL,
                answer_source   TEXT    NOT NULL DEFAULT 'manual',
                language        TEXT    NOT NULL DEFAULT 'en',
                category        TEXT
            );

            CREATE TABLE IF NOT EXISTS api_usage (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
                application_id        INTEGER REFERENCES applications(id) ON DELETE SET NULL,
                request_kind          TEXT    NOT NULL,
                request_status        TEXT    NOT NULL DEFAULT 'succeeded',
                error_message         TEXT,
                attempt_number        INTEGER NOT NULL DEFAULT 1,
                model_used            TEXT,
                prompt_tokens         INTEGER NOT NULL DEFAULT 0,
                cached_prompt_tokens  INTEGER NOT NULL DEFAULT 0,
                completion_tokens     INTEGER NOT NULL DEFAULT 0,
                total_tokens          INTEGER NOT NULL DEFAULT 0,
                input_cost_usd        REAL,
                cached_input_cost_usd REAL,
                output_cost_usd       REAL,
                total_cost_usd        REAL,
                pricing_basis         TEXT
            );
            """
        )
        _ensure_columns(conn, "applications", APPLICATION_EXTRA_COLUMNS)


def insert_application(
    db_path,
    company,
    role,
    slug,
    jd_raw,
    jd_language,
    jd_location,
    job_application_url,
    outputs_path,
    resume_tex_path,
    resume_pdf_path,
    cover_letter: bool,
    linkedin_msg: bool,
    email_draft: bool,
    tokens_used: int,
    model_used: str,
    initial_score: float | None,
    updated_score: float | None,
    usage_summary: dict | None = None,
    archetype: str | None = None,
) -> int:
    """Returns new application id."""

    usage = usage_summary or {}
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO applications (
                company, role, slug, jd_raw, jd_language, jd_location, job_application_url,
                outputs_path, resume_tex_path, resume_pdf_path,
                cover_letter, linkedin_msg, email_draft,
                tokens_used, model_used, score, initial_score, updated_score,
                prompt_tokens, cached_prompt_tokens, completion_tokens,
                input_cost_usd, cached_input_cost_usd, output_cost_usd, total_cost_usd,
                api_attempts, pricing_basis, role_archetype
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company,
                role,
                slug,
                jd_raw,
                jd_language,
                jd_location,
                job_application_url,
                outputs_path,
                resume_tex_path,
                resume_pdf_path,
                int(cover_letter),
                int(linkedin_msg),
                int(email_draft),
                tokens_used,
                model_used,
                initial_score,
                initial_score,
                updated_score,
                usage.get("prompt_tokens"),
                usage.get("cached_prompt_tokens"),
                usage.get("completion_tokens"),
                usage.get("input_cost_usd"),
                usage.get("cached_input_cost_usd"),
                usage.get("output_cost_usd"),
                usage.get("total_cost_usd"),
                usage.get("attempt_count"),
                usage.get("pricing_basis"),
                archetype,
            ),
        )
        return int(cursor.lastrowid)


def record_api_usage(
    db_path: str,
    attempts: list[dict],
    *,
    application_id: int | None,
    request_status: str,
    error_message: str = "",
) -> None:
    if not attempts:
        return
    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO api_usage (
                application_id, request_kind, request_status, error_message,
                attempt_number, model_used,
                prompt_tokens, cached_prompt_tokens, completion_tokens, total_tokens,
                input_cost_usd, cached_input_cost_usd, output_cost_usd, total_cost_usd,
                pricing_basis
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    application_id,
                    str(attempt.get("request_kind") or "generate_pack"),
                    request_status,
                    error_message or None,
                    int(attempt.get("attempt_number") or 0),
                    str(attempt.get("model_used") or ""),
                    int(attempt.get("prompt_tokens") or 0),
                    int(attempt.get("cached_prompt_tokens") or 0),
                    int(attempt.get("completion_tokens") or 0),
                    int(attempt.get("total_tokens") or 0),
                    attempt.get("input_cost_usd"),
                    attempt.get("cached_input_cost_usd"),
                    attempt.get("output_cost_usd"),
                    attempt.get("total_cost_usd"),
                    str(attempt.get("pricing_basis") or ""),
                )
                for attempt in attempts
            ],
        )


def get_application(db_path, app_id: int) -> dict:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    return _row_to_dict(row)


def application_slug_exists(db_path: str, slug: str) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM applications WHERE slug = ? LIMIT 1", (slug,)).fetchone()
    return row is not None


def list_applications(db_path, status_filter=None, limit=50, offset=0) -> list[dict]:
    with _connect(db_path) as conn:
        if status_filter:
            rows = conn.execute(
                """
                SELECT * FROM applications
                WHERE status = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (status_filter, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM applications
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
    return [dict(row) for row in rows]


def update_status(db_path, app_id: int, new_status: str, detail: str = "") -> None:
    """Also inserts an event row with event_type='status_change'."""

    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")

    with _connect(db_path) as conn:
        row = conn.execute("SELECT status FROM applications WHERE id = ?", (app_id,)).fetchone()
        if row is None:
            raise ValueError(f"Application {app_id} does not exist.")
        old_status = row["status"]
        conn.execute("UPDATE applications SET status = ? WHERE id = ?", (new_status, app_id))
        conn.execute(
            """
            INSERT INTO events (application_id, event_type, old_status, new_status, detail)
            VALUES (?, 'status_change', ?, ?, ?)
            """,
            (app_id, old_status, new_status, detail),
        )


def set_duplicate_flag(db_path: str, app_id: int, is_duplicate: bool, detail: str = "") -> None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT is_duplicate FROM applications WHERE id = ?", (app_id,)).fetchone()
        if row is None:
            raise ValueError(f"Application {app_id} does not exist.")
        old_value = int(row["is_duplicate"] or 0)
        new_value = int(bool(is_duplicate))
        if old_value == new_value:
            return
        conn.execute("UPDATE applications SET is_duplicate = ? WHERE id = ?", (new_value, app_id))
        conn.execute(
            """
            INSERT INTO events (application_id, event_type, detail)
            VALUES (?, 'duplicate_flag_change', ?)
            """,
            (
                app_id,
                detail or f"is_duplicate:{old_value}->{new_value}",
            ),
        )


def get_funnel_stats(db_path) -> dict:
    """Returns {generated: N, applied: N, interviewing: N, offer: N, rejected: N, ghosted: N}."""

    stats = {status: 0 for status in VALID_STATUSES}
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM applications
            WHERE COALESCE(is_duplicate, 0) = 0
            GROUP BY status
            """
        ).fetchall()
    for row in rows:
        stats[row["status"]] = int(row["count"])
    return stats


def refresh_daily_stats(db_path) -> None:
    """Recomputes daily_stats from applications table. Called after every insert."""

    with _connect(db_path) as conn:
        conn.execute("DELETE FROM daily_stats")
        rows = conn.execute(
            """
            SELECT
                substr(created_at, 1, 10) AS date,
                COUNT(*) AS generated,
                SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) AS applied,
                SUM(CASE WHEN status = 'interviewing' THEN 1 ELSE 0 END) AS interviews,
                SUM(CASE WHEN status = 'offer' THEN 1 ELSE 0 END) AS offers,
                SUM(CASE WHEN status IN ('rejected', 'ghosted') THEN 1 ELSE 0 END) AS rejections
            FROM applications
            WHERE COALESCE(is_duplicate, 0) = 0
            GROUP BY substr(created_at, 1, 10)
            ORDER BY date
            """
        ).fetchall()
        conn.executemany(
            """
            INSERT INTO daily_stats (date, generated, applied, interviews, offers, rejections)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["date"],
                    int(row["generated"] or 0),
                    int(row["applied"] or 0),
                    int(row["interviews"] or 0),
                    int(row["offers"] or 0),
                    int(row["rejections"] or 0),
                )
                for row in rows
            ],
        )


def get_daily_stats(db_path, days: int = 30) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM daily_stats WHERE date >= date('now', ?) ORDER BY date ASC",
            (f"-{int(days) - 1} days",),
        ).fetchall()
    existing = {row["date"]: dict(row) for row in rows}
    result = []
    start = date.today() - timedelta(days=days - 1)
    for index in range(days):
        current = start + timedelta(days=index)
        key = current.isoformat()
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


def get_quick_stats(db_path) -> dict:
    with _connect(db_path) as conn:
        week_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM applications
            WHERE date(created_at) >= date('now', '-6 days')
              AND COALESCE(is_duplicate, 0) = 0
            """
        ).fetchone()["count"]
        month_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM applications
            WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
              AND COALESCE(is_duplicate, 0) = 0
            """
        ).fetchone()["count"]
        score_row = conn.execute(
            """
            SELECT
                AVG(COALESCE(initial_score, score)) AS avg_initial_score,
                AVG(updated_score) AS avg_updated_score,
                AVG(COALESCE(updated_score, initial_score, score)) AS avg_score
            FROM applications
            WHERE COALESCE(is_duplicate, 0) = 0
            """
        ).fetchone()
        role_row = conn.execute(
            """
            SELECT role, COUNT(*) AS count FROM applications
            WHERE role != ''
              AND COALESCE(is_duplicate, 0) = 0
            GROUP BY role
            ORDER BY count DESC, role ASC
            LIMIT 1
            """
        ).fetchone()
        usage_row = conn.execute(
            """
            SELECT
                COUNT(*) AS request_count,
                SUM(CASE WHEN request_status = 'failed' THEN 1 ELSE 0 END) AS failed_request_count,
                SUM(prompt_tokens) AS prompt_tokens,
                SUM(cached_prompt_tokens) AS cached_prompt_tokens,
                SUM(completion_tokens) AS completion_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(total_cost_usd) AS total_cost_usd,
                AVG(total_cost_usd) AS average_cost_usd
            FROM api_usage
            """
        ).fetchone()
    return {
        "applications_this_week": int(week_count or 0),
        "applications_this_month": int(month_count or 0),
        "average_initial_score": round(float(score_row["avg_initial_score"]), 1) if score_row["avg_initial_score"] is not None else None,
        "average_updated_score": round(float(score_row["avg_updated_score"]), 1) if score_row["avg_updated_score"] is not None else None,
        "average_score": round(float(score_row["avg_score"]), 1) if score_row["avg_score"] is not None else None,
        "most_targeted_role": role_row["role"] if role_row else "",
        "openai_request_count": int(usage_row["request_count"] or 0),
        "openai_failed_request_count": int(usage_row["failed_request_count"] or 0),
        "openai_prompt_tokens": int(usage_row["prompt_tokens"] or 0),
        "openai_cached_prompt_tokens": int(usage_row["cached_prompt_tokens"] or 0),
        "openai_completion_tokens": int(usage_row["completion_tokens"] or 0),
        "openai_total_tokens": int(usage_row["total_tokens"] or 0),
        "openai_total_cost_usd": round(float(usage_row["total_cost_usd"] or 0.0), 7),
        "openai_average_cost_usd": round(float(usage_row["average_cost_usd"] or 0.0), 7),
    }


def get_apply_queue(db_path: str, min_score: float = 0.0, limit: int = 200) -> list[dict]:
    """Returns generated-but-not-applied applications sorted by score descending."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM applications
            WHERE status = 'generated'
              AND COALESCE(is_duplicate, 0) = 0
              AND COALESCE(updated_score, initial_score, score, 0) >= ?
            ORDER BY COALESCE(updated_score, initial_score, score, 0) DESC,
                     datetime(created_at) DESC
            LIMIT ?
            """,
            (min_score, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_analytics(db_path: str) -> dict:
    """Funnel conversion rates, archetype breakdown, score distribution, score by outcome."""
    with _connect(db_path) as conn:
        funnel_rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM applications
            WHERE COALESCE(is_duplicate, 0) = 0
            GROUP BY status
            """
        ).fetchall()
        archetype_rows = conn.execute(
            """
            SELECT COALESCE(role_archetype, 'general') AS archetype,
                   COUNT(*) AS count,
                   ROUND(AVG(COALESCE(updated_score, initial_score, score)), 1) AS avg_score,
                   SUM(CASE WHEN status IN ('interviewing', 'offer') THEN 1 ELSE 0 END) AS positive_outcomes,
                   SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) AS applied_count
            FROM applications
            WHERE COALESCE(is_duplicate, 0) = 0
            GROUP BY role_archetype
            ORDER BY count DESC
            """
        ).fetchall()
        score_dist_rows = conn.execute(
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
            WHERE COALESCE(is_duplicate, 0) = 0
            GROUP BY bucket
            ORDER BY bucket DESC
            """
        ).fetchall()
        outcome_rows = conn.execute(
            """
            SELECT status,
                   ROUND(AVG(COALESCE(updated_score, initial_score, score)), 1) AS avg_score,
                   COUNT(*) AS count
            FROM applications
            WHERE COALESCE(is_duplicate, 0) = 0
            GROUP BY status
            ORDER BY count DESC
            """
        ).fetchall()

    funnel = {row["status"]: int(row["count"]) for row in funnel_rows}
    total = sum(funnel.values()) or 1
    post_generated = sum(
        funnel.get(s, 0) for s in ("applied", "interviewing", "offer", "rejected", "ghosted")
    )
    applied_plus = sum(funnel.get(s, 0) for s in ("interviewing", "offer"))

    return {
        "funnel": funnel,
        "conversion_rates": {
            "generated_to_applied": round(post_generated / total * 100, 1),
            "applied_to_interview": round(
                funnel.get("interviewing", 0) / max(post_generated, 1) * 100, 1
            ),
            "interview_to_offer": round(
                funnel.get("offer", 0) / max(funnel.get("interviewing", 1), 1) * 100, 1
            ),
        },
        "archetypes": [dict(r) for r in archetype_rows],
        "score_distribution": [dict(r) for r in score_dist_rows],
        "score_by_outcome": [dict(r) for r in outcome_rows],
    }


def get_answer_bank(db_path: str) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM answer_bank ORDER BY category, question_key"
        ).fetchall()
    return [dict(row) for row in rows]


def upsert_answer(
    db_path: str,
    question_key: str,
    question_text: str,
    answer_text: str,
    *,
    category: str = "",
    language: str = "en",
    source: str = "manual",
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO answer_bank
                (question_key, question_text, answer_text, answer_source, language, category, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(question_key) DO UPDATE SET
                question_text  = excluded.question_text,
                answer_text    = excluded.answer_text,
                answer_source  = excluded.answer_source,
                language       = excluded.language,
                category       = excluded.category,
                updated_at     = datetime('now')
            """,
            (question_key, question_text, answer_text, source, language, category or None),
        )


def delete_answer(db_path: str, question_key: str) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM answer_bank WHERE question_key = ?", (question_key,))
