"""Auth route handlers for Customy V3.

Since Supabase Auth handles signup/login on the frontend (via the JS SDK),
the backend only needs to:
  - Verify a token is valid (GET /api/auth/me)
  - Return the current user's identity

These handlers are registered in server.py during the V3 integration pass.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler

from app.auth import AuthError, is_admin, is_allowed_user, require_auth
from app.http_utils import send_json

_log = logging.getLogger(__name__)


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
        send_json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return

    email = payload.get("email")
    if not is_allowed_user(user_id, email):
        _log.warning("Access denied for user %s (%s) — not on allowlist", user_id, email)
        send_json(
            handler,
            HTTPStatus.FORBIDDEN,
            {
                "error": "Access not granted. Contact administrator.",
                "access_denied": True,
            },
        )
        return

    send_json(
        handler,
        HTTPStatus.OK,
        {
            "user_id": user_id,
            "email": email,
            "is_admin": is_admin(user_id),
        },
    )
