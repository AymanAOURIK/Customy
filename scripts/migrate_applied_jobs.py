from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
from typing import Iterable

import psycopg2
import psycopg2.extras


def _sqlite_rows(sqlite_path: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT
                id,
                created_at,
                company,
                role,
                jd_raw,
                jd_location,
                job_application_url,
                notes
            FROM applications
            WHERE status = 'applied'
            ORDER BY datetime(created_at) ASC, id ASC
            """
        ).fetchall()
    finally:
        conn.close()


def _fingerprint(source_url: str | None, company: str | None, title: str, description_text: str) -> str:
    if source_url:
        raw = source_url.strip().rstrip("/").lower()
    else:
        snippet = description_text.strip()[:300].lower()
        raw = f"{(company or '').strip().lower()}|{title.strip().lower()}|{snippet}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _connect_postgres() -> psycopg2.extensions.connection:
    dsn = os.environ.get("DATABASE_URL_SERVICE", "").strip() or os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("Set DATABASE_URL_SERVICE or DATABASE_URL before running the migration.")
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def _resolve_user_id(conn: psycopg2.extensions.connection, email: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM auth.users WHERE lower(email) = lower(%s) LIMIT 1", (email,))
        row = cur.fetchone()
    if not row:
        raise RuntimeError(f"No Supabase auth user found for email: {email}")
    return str(row["id"])


def _job_rows(source_rows: Iterable[sqlite3.Row], target_user_id: str) -> list[tuple]:
    out: list[tuple] = []
    for row in source_rows:
        title = str(row["role"] or "").strip() or "Untitled Role"
        company = str(row["company"] or "").strip() or None
        description_text = str(row["jd_raw"] or "").strip()
        source_url = str(row["job_application_url"] or "").strip() or None
        notes = str(row["notes"] or "").strip() or None
        migration_note = f"[migrated from local SQLite application #{row['id']}]"
        combined_notes = migration_note if not notes else f"{migration_note}\n{notes}"
        out.append(
            (
                target_user_id,
                str(row["created_at"] or "").strip() or None,
                "local_migration",
                source_url,
                _fingerprint(source_url, company, title, description_text),
                title,
                company,
                str(row["jd_location"] or "").strip() or None,
                description_text,
                "applied",
                combined_notes,
            )
        )
    return out


def migrate(sqlite_path: str, target_user_id: str, dry_run: bool) -> None:
    source_rows = _sqlite_rows(sqlite_path)
    print(f"Found {len(source_rows)} applied rows in {sqlite_path}")
    if not source_rows:
        return

    jobs = _job_rows(source_rows, target_user_id)
    print(f"Prepared {len(jobs)} jobs for user {target_user_id}")
    if dry_run:
        preview = jobs[:3]
        for idx, row in enumerate(preview, start=1):
            print(f"Preview {idx}: created_at={row[1]} company={row[6]} title={row[5]} status={row[9]}")
        return

    with _connect_postgres() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                """
                INSERT INTO jobs (
                    user_id,
                    created_at,
                    source,
                    source_url,
                    fingerprint,
                    title,
                    company,
                    location_raw,
                    description_text,
                    status,
                    notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, fingerprint) DO NOTHING
                """,
                jobs,
                page_size=100,
            )
        conn.commit()
    print("Migration completed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate applied jobs from local SQLite to Postgres jobs table.")
    parser.add_argument("--sqlite-path", default="data/customy.db")
    parser.add_argument("--target-user-id")
    parser.add_argument("--target-email")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.target_user_id and not args.target_email:
        parser.error("Provide --target-user-id or --target-email")

    target_user_id = args.target_user_id
    if not target_user_id:
        with _connect_postgres() as conn:
            target_user_id = _resolve_user_id(conn, str(args.target_email or "").strip())
        print(f"Resolved {args.target_email} -> {target_user_id}")

    migrate(args.sqlite_path, target_user_id, args.dry_run)


if __name__ == "__main__":
    main()
