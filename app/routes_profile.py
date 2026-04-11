"""Profile CRUD route handlers for Customy V3.

Endpoints:
  GET    /api/profile        — return the current user's profile
  POST   /api/profile        — create a profile (first-time setup)
  PUT    /api/profile        — update the profile (partial or full)

These handlers are registered in server.py during the V3 integration pass.
"""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any

from app.auth import AuthError, require_auth
from app.profile_db import create_profile, get_profile, update_profile

_log = logging.getLogger(__name__)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length).decode("utf-8") if length else "{}"
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc


def _json_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def handle_profile_get(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """GET /api/profile"""
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        _json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    profile = get_profile(user_id)
    if profile is None:
        _json_response(handler, HTTPStatus.NOT_FOUND, {"error": "Profile not found"})
        return
    _json_response(handler, HTTPStatus.OK, profile)


def handle_profile_create(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """POST /api/profile — create a new profile."""
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        _json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    try:
        data = _read_json(handler)
    except ValueError as exc:
        _json_response(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return

    if not data.get("full_name", "").strip():
        _json_response(handler, HTTPStatus.BAD_REQUEST, {"error": "'full_name' is required"})
        return

    existing = get_profile(user_id)
    if existing:
        _json_response(handler, HTTPStatus.CONFLICT, {"error": "Profile already exists. Use PUT to update."})
        return

    try:
        profile = create_profile(user_id, data)
    except Exception as exc:
        _log.exception("Failed to create profile for user %s", user_id)
        _json_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return

    _json_response(handler, HTTPStatus.CREATED, profile)


def handle_profile_update(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """PUT /api/profile — update an existing profile (partial update supported)."""
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        _json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    try:
        data = _read_json(handler)
    except ValueError as exc:
        _json_response(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return

    existing = get_profile(user_id)
    if not existing:
        _json_response(handler, HTTPStatus.NOT_FOUND, {"error": "Profile not found. Use POST to create."})
        return

    try:
        profile = update_profile(user_id, data)
    except Exception as exc:
        _log.exception("Failed to update profile for user %s", user_id)
        _json_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return

    _json_response(handler, HTTPStatus.OK, profile)
