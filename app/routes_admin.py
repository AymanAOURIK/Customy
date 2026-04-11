"""Admin route handlers for Customy V3.

All endpoints require admin JWT. Regular users get 403.

Endpoints:
  GET  /api/admin/users              — list all users with activity summary
  GET  /api/admin/users/<id>         — single user detail
  GET  /api/admin/stats              — platform-wide aggregates
  GET  /api/admin/ideas              — ideas board list
  POST /api/admin/ideas              — create an idea
  PUT  /api/admin/ideas/<id>         — update an idea
  DELETE /api/admin/ideas/<id>       — delete an idea

These handlers are registered in server.py during the V3 integration pass.
"""

from __future__ import annotations

import json
import logging
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.admin import (
    create_idea,
    delete_idea,
    get_platform_stats,
    get_user_detail,
    list_ideas,
    list_users,
    update_idea,
)
from app.auth import AuthError, require_admin

_log = logging.getLogger(__name__)

_IDEA_PATH_RE = re.compile(r"^/api/admin/ideas/(\d+)$")
_USER_PATH_RE = re.compile(r"^/api/admin/users/([0-9a-f-]+)$")


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


def _require_admin(handler: BaseHTTPRequestHandler) -> str | None:
    """Return user_id if admin, or write 401/403 and return None."""
    try:
        user_id, _ = require_admin(handler)
        return user_id
    except AuthError as exc:
        msg = str(exc)
        status = HTTPStatus.FORBIDDEN if "Admin access" in msg else HTTPStatus.UNAUTHORIZED
        _json_response(handler, status, {"error": msg})
        return None


# ---------------------------------------------------------------------------
# GET handlers
# ---------------------------------------------------------------------------

def handle_admin_users(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """GET /api/admin/users"""
    if _require_admin(handler) is None:
        return
    try:
        users = list_users()
    except Exception as exc:
        _log.exception("admin users query failed")
        _json_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return
    _json_response(handler, HTTPStatus.OK, {"users": users})


def handle_admin_user_detail(handler: BaseHTTPRequestHandler, target_user_id: str, cfg: dict) -> None:
    """GET /api/admin/users/<id>"""
    if _require_admin(handler) is None:
        return
    try:
        detail = get_user_detail(target_user_id)
    except Exception as exc:
        _log.exception("admin user detail failed for %s", target_user_id)
        _json_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return
    _json_response(handler, HTTPStatus.OK, detail)


def handle_admin_stats(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """GET /api/admin/stats"""
    if _require_admin(handler) is None:
        return
    try:
        stats = get_platform_stats()
    except Exception as exc:
        _log.exception("admin stats query failed")
        _json_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return
    _json_response(handler, HTTPStatus.OK, stats)


def handle_admin_ideas_list(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """GET /api/admin/ideas"""
    if _require_admin(handler) is None:
        return
    parsed = urlparse(handler.path)
    qs = parse_qs(parsed.query)
    status = qs.get("status", [None])[0]
    try:
        ideas = list_ideas(status=status)
    except Exception as exc:
        _log.exception("admin ideas list failed")
        _json_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return
    _json_response(handler, HTTPStatus.OK, {"ideas": ideas})


# ---------------------------------------------------------------------------
# POST / PUT / DELETE handlers
# ---------------------------------------------------------------------------

def handle_admin_idea_create(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """POST /api/admin/ideas"""
    if _require_admin(handler) is None:
        return
    try:
        data = _read_json(handler)
    except ValueError as exc:
        _json_response(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return
    if not data.get("title", "").strip():
        _json_response(handler, HTTPStatus.BAD_REQUEST, {"error": "'title' is required"})
        return
    try:
        idea = create_idea(data)
    except Exception as exc:
        _log.exception("admin idea create failed")
        _json_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return
    _json_response(handler, HTTPStatus.CREATED, idea)


def handle_admin_idea_update(handler: BaseHTTPRequestHandler, idea_id: int, cfg: dict) -> None:
    """PUT /api/admin/ideas/<id>"""
    if _require_admin(handler) is None:
        return
    try:
        data = _read_json(handler)
    except ValueError as exc:
        _json_response(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return
    try:
        idea = update_idea(idea_id, data)
    except Exception as exc:
        _log.exception("admin idea update failed for id=%s", idea_id)
        _json_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return
    _json_response(handler, HTTPStatus.OK, idea)


def handle_admin_idea_delete(handler: BaseHTTPRequestHandler, idea_id: int, cfg: dict) -> None:
    """DELETE /api/admin/ideas/<id>"""
    if _require_admin(handler) is None:
        return
    try:
        delete_idea(idea_id)
    except Exception as exc:
        _log.exception("admin idea delete failed for id=%s", idea_id)
        _json_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        return
    _json_response(handler, HTTPStatus.OK, {"deleted": idea_id})


# ---------------------------------------------------------------------------
# Dispatcher helpers (called from server.py)
# ---------------------------------------------------------------------------

def dispatch_admin_get(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    """Try to match and handle a GET /api/admin/* request.

    Returns True if handled, False if not matched (caller should 404).
    """
    if path == "/api/admin/users":
        handle_admin_users(handler, cfg)
        return True
    m = _USER_PATH_RE.match(path)
    if m:
        handle_admin_user_detail(handler, m.group(1), cfg)
        return True
    if path == "/api/admin/stats":
        handle_admin_stats(handler, cfg)
        return True
    if path == "/api/admin/ideas":
        handle_admin_ideas_list(handler, cfg)
        return True
    return False


def dispatch_admin_post(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    if path == "/api/admin/ideas":
        handle_admin_idea_create(handler, cfg)
        return True
    return False


def dispatch_admin_put(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    m = _IDEA_PATH_RE.match(path)
    if m:
        handle_admin_idea_update(handler, int(m.group(1)), cfg)
        return True
    return False


def dispatch_admin_delete(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    m = _IDEA_PATH_RE.match(path)
    if m:
        handle_admin_idea_delete(handler, int(m.group(1)), cfg)
        return True
    return False
