"""JWT authentication for Customy V3.

Supports both legacy HS256 JWT-secret verification and the newer Supabase
JWKS-based signing keys flow.
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler
from typing import Any

import jwt as pyjwt
from jwt import PyJWKClient

_JWT_SECRET: str | None = None
_JWKS_URL: str | None = None
_JWKS_CLIENT: PyJWKClient | None = None
_ADMIN_USER_IDS: set[str] = set()
_ADMIN_IDS_LOADED = False
_ADMIN_EMAILS: set[str] | None = None


class AuthError(Exception):
    """Raised on authentication or authorization failures."""

    pass


def _get_jwt_secret() -> str:
    global _JWT_SECRET
    if _JWT_SECRET is None:
        secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
        if not secret:
            raise RuntimeError("SUPABASE_JWT_SECRET is not set")
        _JWT_SECRET = secret
    return _JWT_SECRET


def _get_jwks_url() -> str:
    global _JWKS_URL
    if _JWKS_URL is None:
        explicit = os.environ.get("SUPABASE_JWKS_URL", "").strip()
        if explicit:
            _JWKS_URL = explicit
        else:
            base_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
            if not base_url:
                raise RuntimeError("Set SUPABASE_URL or SUPABASE_JWKS_URL for JWT verification")
            _JWKS_URL = f"{base_url}/auth/v1/.well-known/jwks.json"
    return _JWKS_URL


def _get_jwks_client() -> PyJWKClient:
    global _JWKS_CLIENT
    if _JWKS_CLIENT is None:
        _JWKS_CLIENT = PyJWKClient(_get_jwks_url())
    return _JWKS_CLIENT


def _get_admin_ids() -> set[str]:
    global _ADMIN_USER_IDS, _ADMIN_IDS_LOADED
    if not _ADMIN_IDS_LOADED:
        raw = os.environ.get("ADMIN_USER_IDS", "")
        _ADMIN_USER_IDS = {uid.strip() for uid in raw.split(",") if uid.strip()}
        _ADMIN_IDS_LOADED = True
    return _ADMIN_USER_IDS


def _get_admin_emails() -> set[str]:
    global _ADMIN_EMAILS
    if _ADMIN_EMAILS is None:
        raw = os.environ.get("ADMIN_USER_EMAILS", "")
        _ADMIN_EMAILS = {e.strip().lower() for e in raw.split(",") if e.strip()}
    return _ADMIN_EMAILS


_ALLOWED_EMAILS: set[str] | None = None


def _get_allowed_emails() -> set[str]:
    global _ALLOWED_EMAILS
    if _ALLOWED_EMAILS is None:
        raw = os.environ.get("ALLOWED_USER_EMAILS", "")
        _ALLOWED_EMAILS = {e.strip().lower() for e in raw.split(",") if e.strip()}
    return _ALLOWED_EMAILS


def is_allowed_user(user_id: str, email: str | None = None) -> bool:
    """Return True if this user is permitted to access the application.

    Rules (evaluated in order):
    1. Local mode → always True (no restriction in dev).
    2. Admin users (ADMIN_USER_IDS) → always True.
    3. ALLOWED_USER_EMAILS env var not set → True (open access / backward-compat).
    4. Email present in ALLOWED_USER_EMAILS → True.
    5. Otherwise → False (invite-only enforcement).
    """
    if os.environ.get("CUSTOMY_MODE", "local").strip().lower() != "saas":
        return True
    if is_admin(user_id):
        return True
    allowed = _get_allowed_emails()
    if not allowed:
        return True
    return bool(email and email.strip().lower() in allowed)


def verify_jwt(token: str) -> dict[str, Any]:
    """Decode and verify a Supabase JWT. Returns the payload dict on success."""
    try:
        header = pyjwt.get_unverified_header(token)
        algorithm = str(header.get("alg") or "").strip()
        if not algorithm:
            raise AuthError("Token missing signing algorithm")

        if algorithm.startswith("HS"):
            payload: dict[str, Any] = pyjwt.decode(
                token,
                _get_jwt_secret(),
                algorithms=[algorithm],
                audience="authenticated",
                options={"verify_exp": True},
            )
        else:
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
            payload = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience="authenticated",
                options={"verify_exp": True},
            )
    except pyjwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except pyjwt.InvalidAudienceError:
        raise AuthError("Invalid token audience")
    except RuntimeError as exc:
        raise AuthError(str(exc))
    except pyjwt.InvalidTokenError as exc:
        raise AuthError(f"Invalid token: {exc}")
    return payload


def get_user_id(payload: dict[str, Any]) -> str:
    """Extract the user UUID from a verified JWT payload."""
    uid = payload.get("sub")
    if not uid:
        raise AuthError("Token missing 'sub' claim")
    return str(uid)


def is_admin(user_id: str, email: str | None = None) -> bool:
    """Return True if this user is listed in admin ids or admin emails."""
    if user_id in _get_admin_ids():
        return True
    return bool(email and email.strip().lower() in _get_admin_emails())


def extract_bearer_token(auth_header: str | None) -> str:
    """Parse 'Bearer <token>' from an Authorization header value."""
    if not auth_header or not auth_header.startswith("Bearer "):
        raise AuthError("Missing or invalid Authorization header")
    return auth_header[len("Bearer "):]


def require_auth(handler: BaseHTTPRequestHandler) -> tuple[str, dict[str, Any]]:
    """Validate the JWT from the request Authorization header.

    Returns (user_id, payload) on success.
    Raises AuthError on any failure.
    """
    auth_header = handler.headers.get("Authorization")
    token = extract_bearer_token(auth_header)
    payload = verify_jwt(token)
    user_id = get_user_id(payload)
    return user_id, payload


def require_admin(handler: BaseHTTPRequestHandler) -> tuple[str, dict[str, Any]]:
    """Like require_auth but also asserts admin membership.

    Raises AuthError with 403-level message if not admin.
    """
    user_id, payload = require_auth(handler)
    if not is_admin(user_id, payload.get("email")):
        raise AuthError("Admin access required")
    return user_id, payload
