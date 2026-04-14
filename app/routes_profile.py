"""Profile CRUD route handlers for Customy V3.

Endpoints:
  GET    /api/profile        — return the current user's profile
  POST   /api/profile        — create a profile (first-time setup)
  PUT    /api/profile        — update the profile (partial or full)

These handlers are registered in server.py during the V3 integration pass.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any

from app.auth import AuthError, require_auth
from app.candidate_context import build_candidate_context_from_profile_data
from app.http_utils import read_json_body, send_json
from app.profile_db import create_profile, get_profile, update_profile, upsert_profile
from app.profile_enrichment import build_profile_enrichment_plan
from app.profile_quality import build_profile_quality_report
from app.text_utils import sanitize_data_strings

_log = logging.getLogger(__name__)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    payload = read_json_body(handler)
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _claim_str(payload: dict[str, Any], *path: str) -> str:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "").strip()


def _profile_quality_report(profile_data: dict[str, Any]) -> dict[str, object]:
    candidate_context = build_candidate_context_from_profile_data(
        profile_data,
        candidate_source="postgres",
    )
    return build_profile_quality_report(candidate_context)


def _profile_enrichment_plan(
    profile_data: dict[str, Any],
    profile_quality_report: dict[str, object] | None = None,
) -> dict[str, object]:
    report = profile_quality_report or _profile_quality_report(profile_data)
    return build_profile_enrichment_plan(
        report,
        profile_data,
        candidate_source="postgres",
    )


def _profile_response(profile: dict[str, Any]) -> dict[str, Any]:
    body = dict(profile or {})
    quality_report = _profile_quality_report(body)
    body["profile_quality_report"] = quality_report
    body["profile_enrichment_plan"] = _profile_enrichment_plan(body, quality_report)
    return body


def _empty_profile_payload(user_id: str, auth_payload: dict[str, Any]) -> dict[str, Any]:
    profile = {
        "user_id": user_id,
        "full_name": (
            _claim_str(auth_payload, "user_metadata", "full_name")
            or _claim_str(auth_payload, "user_metadata", "name")
        ),
        "email": _claim_str(auth_payload, "email"),
        "phone": "",
        "location": "",
        "linkedin": "",
        "github": "",
        "headline": "",
        "summary": "",
        "skills": {},
        "experiences": [],
        "education": [],
        "spoken_languages": [],
        "scoring_keywords": [],
    }
    return {
        "exists": False,
        "profile": profile,
        "profile_quality_report": _profile_quality_report(profile),
        "profile_enrichment_plan": _profile_enrichment_plan(profile),
    }


def _sanitize_profile_payload(data: dict[str, Any]) -> dict[str, Any]:
    return sanitize_data_strings(data, preserve_newlines=True)


def handle_profile_get(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """GET /api/profile"""
    try:
        user_id, auth_payload = require_auth(handler)
    except AuthError as exc:
        send_json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    profile = get_profile(user_id)
    if profile is None:
        _log.info("profile.get empty_state user_id=%s", user_id)
        send_json(handler, HTTPStatus.OK, _empty_profile_payload(user_id, auth_payload))
        return
    _log.info("profile.get found user_id=%s", user_id)
    send_json(
        handler,
        HTTPStatus.OK,
        {
            "exists": True,
            "profile": profile,
            "profile_quality_report": _profile_quality_report(profile),
            "profile_enrichment_plan": _profile_enrichment_plan(profile),
        },
    )


def handle_profile_create(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """POST /api/profile — create a new profile."""
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        send_json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    try:
        data = _sanitize_profile_payload(_read_json(handler))
    except ValueError as exc:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return

    if not str(data.get("full_name") or "").strip():
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "'full_name' is required"})
        return

    existing = get_profile(user_id)
    if existing:
        send_json(handler, HTTPStatus.CONFLICT, {"error": "Profile already exists. Use PUT to update."})
        return

    try:
        profile = create_profile(user_id, data)
    except Exception as exc:
        _log.exception("Failed to create profile for user %s", user_id)
        send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return

    _log.info("profile.create created user_id=%s", user_id)
    send_json(handler, HTTPStatus.CREATED, _profile_response(profile))


def handle_profile_update(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """PUT /api/profile — update an existing profile (partial update supported)."""
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        send_json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    try:
        data = _sanitize_profile_payload(_read_json(handler))
    except ValueError as exc:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return

    existing = get_profile(user_id)
    if not existing and not str(data.get("full_name") or "").strip():
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "'full_name' is required to create a profile"})
        return

    try:
        if existing:
            profile = update_profile(user_id, data)
            status = HTTPStatus.OK
            _log.info("profile.put updated user_id=%s", user_id)
        else:
            profile = upsert_profile(user_id, data)
            status = HTTPStatus.CREATED
            _log.info("profile.put created_missing_profile user_id=%s", user_id)
    except Exception as exc:
        _log.exception("Failed to update profile for user %s", user_id)
        send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return

    send_json(handler, status, _profile_response(profile))
