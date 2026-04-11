"""Auth route handlers for Customy V3.

Since Supabase Auth handles signup/login on the frontend (via the JS SDK),
the backend only needs to:
  - Verify a token is valid (GET /api/auth/me)
  - Return the current user's identity

These handlers are registered in server.py during the V3 integration pass.
"""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any

from app.auth import AuthError, is_admin, require_auth

_log = logging.getLogger(__name__)


def _json_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def handle_auth_me(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    """GET /api/auth/me — verify JWT and return user identity.

    Response 200:
      { "user_id": "...", "is_admin": false }

    Response 401:
      { "error": "..." }
    """
    try:
        user_id, payload = require_auth(handler)
    except AuthError as exc:
        _json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    _json_response(
        handler,
        HTTPStatus.OK,
        {
            "user_id": user_id,
            "email": payload.get("email"),
            "is_admin": is_admin(user_id),
        },
    )
