"""Admin query functions for Customy V3.

Uses the Postgres service role connection (bypasses RLS) for admin-only aggregations.
Regular user data is never exposed through these functions without admin authorization.
"""

from __future__ import annotations

import json
from typing import Any

from app.db_postgres import _connect, _row, _rows


def list_users(limit: int = 100) -> list[dict[str, Any]]:
    """Return all users with their activity summary.

    Joins auth.users with profiles and aggregated application stats.
    Requires service role connection to read auth.users.
    """
    with _connect(service_role=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    u.id AS user_id,
                    u.email,
                    u.created_at AS registered_at,
                    u.last_sign_in_at,
                    p.full_name,
                    COUNT(a.id) AS total_applications,
                    MAX(a.created_at) AS last_generated_at,
                    SUM(a.total_cost_usd) AS total_cost_usd
                FROM auth.users u
                LEFT JOIN profiles p ON p.user_id = u.id
                LEFT JOIN applications a ON a.user_id = u.id
                GROUP BY u.id, u.email, u.created_at, u.last_sign_in_at, p.full_name
                ORDER BY u.created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return _rows(cur)


def get_user_detail(user_id: str) -> dict[str, Any]:
    """Return one user's full summary including recent applications."""
    with _connect(service_role=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    u.id AS user_id, u.email, u.created_at AS registered_at,
                    u.last_sign_in_at, p.full_name
                FROM auth.users u
                LEFT JOIN profiles p ON p.user_id = u.id
                WHERE u.id = %s
                """,
                (user_id,),
            )
            user = _row(cur) or {}

            cur.execute(
                """
                SELECT * FROM applications WHERE user_id = %s
                ORDER BY created_at DESC LIMIT 50
                """,
                (user_id,),
            )
            applications = _rows(cur)

            cur.execute(
                """
                SELECT
                    COUNT(*) AS request_count,
                    SUM(total_cost_usd) AS total_cost_usd,
                    SUM(prompt_tokens) AS prompt_tokens,
                    SUM(completion_tokens) AS completion_tokens
                FROM api_usage WHERE user_id = %s
                """,
                (user_id,),
            )
            usage = _row(cur) or {}

    return {**user, "applications": applications, "api_usage": usage}


def get_platform_stats() -> dict[str, Any]:
    """Aggregate stats across all users for the admin dashboard."""
    with _connect(service_role=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM auth.users")
            total_users = (_row(cur) or {}).get("total", 0)

            cur.execute(
                """
                SELECT COUNT(DISTINCT user_id) AS active
                FROM applications
                WHERE created_at >= NOW() - INTERVAL '7 days'
                """
            )
            active_7d = (_row(cur) or {}).get("active", 0)

            cur.execute(
                """
                SELECT COUNT(DISTINCT user_id) AS active
                FROM applications
                WHERE created_at >= NOW() - INTERVAL '30 days'
                """
            )
            active_30d = (_row(cur) or {}).get("active", 0)

            cur.execute("SELECT COUNT(*) AS total FROM applications")
            total_apps = (_row(cur) or {}).get("total", 0)

            cur.execute(
                """
                SELECT
                    SUM(total_cost_usd) AS total_cost_usd,
                    COUNT(*) AS total_requests
                FROM api_usage
                """
            )
            cost_row = _row(cur) or {}

    return {
        "total_users": int(total_users or 0),
        "active_users_7d": int(active_7d or 0),
        "active_users_30d": int(active_30d or 0),
        "total_applications": int(total_apps or 0),
        "total_cost_usd": round(float(cost_row.get("total_cost_usd") or 0.0), 4),
        "total_api_requests": int(cost_row.get("total_requests") or 0),
    }


# ---------------------------------------------------------------------------
# Ideas board
# ---------------------------------------------------------------------------

def list_ideas(status: str | None = None) -> list[dict[str, Any]]:
    with _connect(service_role=True) as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    "SELECT * FROM admin_ideas WHERE status = %s ORDER BY created_at DESC",
                    (status,),
                )
            else:
                cur.execute("SELECT * FROM admin_ideas ORDER BY created_at DESC")
            return _rows(cur)


def create_idea(data: dict[str, Any]) -> dict[str, Any]:
    with _connect(service_role=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO admin_ideas (title, description, category, priority, status, target_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    data.get("title", ""),
                    data.get("description"),
                    data.get("category"),
                    data.get("priority"),
                    data.get("status", "idea"),
                    data.get("target_version"),
                ),
            )
            return _row(cur) or {}


def update_idea(idea_id: int, data: dict[str, Any]) -> dict[str, Any]:
    allowed = {"title", "description", "category", "priority", "status", "target_version"}
    set_clauses = []
    values = []
    for field in allowed:
        if field in data:
            set_clauses.append(f"{field} = %s")
            values.append(data[field])
    if not set_clauses:
        return get_idea(idea_id) or {}
    values.append(idea_id)
    with _connect(service_role=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE admin_ideas SET {', '.join(set_clauses)} WHERE id = %s RETURNING *",
                values,
            )
            return _row(cur) or {}


def get_idea(idea_id: int) -> dict[str, Any] | None:
    with _connect(service_role=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM admin_ideas WHERE id = %s", (idea_id,))
            return _row(cur)


def delete_idea(idea_id: int) -> None:
    with _connect(service_role=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM admin_ideas WHERE id = %s", (idea_id,))
