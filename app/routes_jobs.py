"""Job CRUD route handlers for Customy WT6.

Endpoints (SaaS mode only, JWT-authenticated):
  GET    /api/jobs              — list user's saved jobs
  POST   /api/jobs              — create a job (manual intake)
  GET    /api/jobs/<id>         — get a single job with full description
  PATCH  /api/jobs/<id>/status  — update job status
  PATCH  /api/jobs/<id>/notes   — update job notes
  DELETE /api/jobs/<id>         — delete a job

All handlers are dispatched from server.py via the dispatch_jobs_* helpers.
User isolation is enforced: every DB call passes user_id from the JWT.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.auth import AuthError, require_auth
from app.db_postgres import (
    delete_job,
    get_job,
    insert_job,
    list_jobs,
    update_job_notes,
    update_job_status,
)

_log = logging.getLogger(__name__)

VALID_JOB_STATUSES = frozenset(
    {"saved", "applied", "interviewing", "offer", "rejected", "ghosted", "archived"}
)

_JOB_ID_RE = re.compile(r"^/api/jobs/(\d+)$")
_JOB_STATUS_RE = re.compile(r"^/api/jobs/(\d+)/status$")
_JOB_NOTES_RE = re.compile(r"^/api/jobs/(\d+)/notes$")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length).decode("utf-8") if length else "{}"
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc


def _json(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _fingerprint(source_url: str | None, company: str | None, title: str, description_text: str) -> str:
    """Stable per-user deduplication fingerprint.

    Uses the source URL when available (normalised). Falls back to a hash of
    company + title + first 300 chars of the description so that manually
    entered duplicates are caught as well.
    """
    if source_url:
        raw = source_url.strip().rstrip("/").lower()
    else:
        co = (company or "").strip().lower()
        ti = title.strip().lower()
        snippet = description_text.strip()[:300].lower()
        raw = f"{co}|{ti}|{snippet}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _serialize_job(row: dict, full: bool = False) -> dict:
    """Serialize a DB row to the API response shape.

    full=True adds description_text (omitted in list responses to keep
    payloads small).
    """
    out: dict[str, Any] = {
        "id": row.get("id"),
        "created_at": str(row.get("created_at") or ""),
        "title": row.get("title"),
        "company": row.get("company"),
        "location_raw": row.get("location_raw"),
        "source": row.get("source"),
        "source_url": row.get("source_url"),
        "salary_raw": row.get("salary_raw"),
        "status": row.get("status"),
        "relevance_score": row.get("relevance_score"),
        "notes": row.get("notes"),
        "application_id": row.get("application_id"),
    }
    if full:
        out["description_text"] = row.get("description_text")
    return out


# ---------------------------------------------------------------------------
# Dispatch entry points (called from server.py)
# ---------------------------------------------------------------------------

def dispatch_jobs_get(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    """Return True if the request was handled."""
    if path == "/api/jobs":
        _handle_jobs_list(handler, cfg)
        return True
    m = _JOB_ID_RE.fullmatch(path)
    if m:
        _handle_job_get(handler, int(m.group(1)), cfg)
        return True
    return False


def dispatch_jobs_post(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    if path == "/api/jobs":
        _handle_jobs_create(handler, cfg)
        return True
    return False


def dispatch_jobs_patch(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    m = _JOB_STATUS_RE.fullmatch(path)
    if m:
        _handle_job_status(handler, int(m.group(1)), cfg)
        return True
    m = _JOB_NOTES_RE.fullmatch(path)
    if m:
        _handle_job_notes(handler, int(m.group(1)), cfg)
        return True
    return False


def dispatch_jobs_delete(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    m = _JOB_ID_RE.fullmatch(path)
    if m:
        _handle_job_delete(handler, int(m.group(1)), cfg)
        return True
    return False


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def _handle_jobs_list(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """GET /api/jobs"""
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        _json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    query = urlparse(handler.path).query
    params = parse_qs(query or "")
    status = params.get("status", [""])[0] or None
    limit = min(int((params.get("limit", ["50"])[0]) or 50), 200)
    offset = int((params.get("offset", ["0"])[0]) or 0)

    jobs = list_jobs(user_id, status=status, limit=limit, offset=offset)
    _json(handler, HTTPStatus.OK, {
        "jobs": [_serialize_job(j) for j in jobs],
        "count": len(jobs),
        "limit": limit,
        "offset": offset,
    })


def _handle_job_get(handler: BaseHTTPRequestHandler, job_id: int, cfg: dict) -> None:
    """GET /api/jobs/<id>"""
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        _json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    job = get_job(user_id, job_id)
    if job is None:
        _json(handler, HTTPStatus.NOT_FOUND, {"error": f"Job {job_id} not found"})
        return
    _json(handler, HTTPStatus.OK, _serialize_job(job, full=True))


def _handle_jobs_create(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """POST /api/jobs"""
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        _json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    try:
        payload = _read_json(handler)
    except ValueError as exc:
        _json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return

    title = str(payload.get("title") or "").strip()
    description_text = str(payload.get("description_text") or "").strip()
    if not title:
        _json(handler, HTTPStatus.BAD_REQUEST, {"error": "'title' is required"})
        return
    if not description_text:
        _json(handler, HTTPStatus.BAD_REQUEST, {"error": "'description_text' is required"})
        return

    company = str(payload.get("company") or "").strip() or None
    source_url = str(payload.get("source_url") or "").strip() or None
    location_raw = str(payload.get("location_raw") or "").strip() or None
    salary_raw = str(payload.get("salary_raw") or "").strip() or None
    notes = str(payload.get("notes") or "").strip() or None

    fp = _fingerprint(source_url, company, title, description_text)

    try:
        job_id = insert_job(
            user_id=user_id,
            source="manual",
            source_url=source_url,
            fingerprint=fp,
            title=title,
            company=company,
            location_raw=location_raw,
            description_text=description_text,
            salary_raw=salary_raw,
            notes=notes,
        )
    except Exception:
        _log.exception("Failed to insert job for user %s", user_id)
        _json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Failed to save job"})
        return

    if job_id == -1:
        _json(handler, HTTPStatus.CONFLICT, {"error": "A job with the same fingerprint already exists."})
        return

    job = get_job(user_id, job_id)
    _json(handler, HTTPStatus.CREATED, _serialize_job(job, full=True) if job else {"id": job_id})


def _handle_job_status(handler: BaseHTTPRequestHandler, job_id: int, cfg: dict) -> None:
    """PATCH /api/jobs/<id>/status"""
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        _json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    try:
        payload = _read_json(handler)
    except ValueError as exc:
        _json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return

    new_status = str(payload.get("status") or "").strip()
    if not new_status:
        _json(handler, HTTPStatus.BAD_REQUEST, {"error": "'status' is required"})
        return
    if new_status not in VALID_JOB_STATUSES:
        _json(handler, HTTPStatus.BAD_REQUEST, {
            "error": f"Invalid status '{new_status}'. Must be one of: {', '.join(sorted(VALID_JOB_STATUSES))}"
        })
        return

    job = get_job(user_id, job_id)
    if job is None:
        _json(handler, HTTPStatus.NOT_FOUND, {"error": f"Job {job_id} not found"})
        return

    update_job_status(user_id, job_id, new_status)
    updated = get_job(user_id, job_id)
    _json(handler, HTTPStatus.OK, _serialize_job(updated) if updated else {"id": job_id, "status": new_status})


def _handle_job_notes(handler: BaseHTTPRequestHandler, job_id: int, cfg: dict) -> None:
    """PATCH /api/jobs/<id>/notes"""
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        _json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    try:
        payload = _read_json(handler)
    except ValueError as exc:
        _json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return

    notes = str(payload.get("notes") or "").strip() or None

    job = get_job(user_id, job_id)
    if job is None:
        _json(handler, HTTPStatus.NOT_FOUND, {"error": f"Job {job_id} not found"})
        return

    update_job_notes(user_id, job_id, notes)
    updated = get_job(user_id, job_id)
    _json(handler, HTTPStatus.OK, _serialize_job(updated) if updated else {"id": job_id})


def _handle_job_delete(handler: BaseHTTPRequestHandler, job_id: int, cfg: dict) -> None:
    """DELETE /api/jobs/<id>"""
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        _json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    job = get_job(user_id, job_id)
    if job is None:
        _json(handler, HTTPStatus.NOT_FOUND, {"error": f"Job {job_id} not found"})
        return

    delete_job(user_id, job_id)
    _json(handler, HTTPStatus.OK, {"deleted": True, "id": job_id})
