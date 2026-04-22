from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import patch

jwt_stub = types.ModuleType("jwt")
jwt_stub.PyJWKClient = object
jwt_stub.ExpiredSignatureError = type("ExpiredSignatureError", (Exception,), {})
jwt_stub.InvalidAudienceError = type("InvalidAudienceError", (Exception,), {})
jwt_stub.InvalidTokenError = type("InvalidTokenError", (Exception,), {})
jwt_stub.get_unverified_header = lambda token: {"alg": "HS256"}
jwt_stub.decode = lambda *args, **kwargs: {"sub": "user-1", "email": "admin@example.com"}
sys.modules.setdefault("jwt", jwt_stub)

from app.auth import is_admin, require_admin


class DummyHandler:
    headers = {"Authorization": "Bearer token"}


class AdminAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        for key in ("ADMIN_USER_IDS", "ADMIN_USER_EMAILS"):
            os.environ.pop(key, None)

    @patch("app.auth._ADMIN_IDS_LOADED", False)
    @patch("app.auth._ADMIN_USER_IDS", set())
    @patch("app.auth._ADMIN_EMAILS", None)
    def test_is_admin_accepts_configured_email(self) -> None:
        os.environ["ADMIN_USER_EMAILS"] = "admin@example.com"
        self.assertTrue(is_admin("user-1", "admin@example.com"))
        self.assertFalse(is_admin("user-1", "other@example.com"))

    @patch("app.auth.require_auth", return_value=("user-1", {"email": "admin@example.com"}))
    @patch("app.auth._ADMIN_IDS_LOADED", False)
    @patch("app.auth._ADMIN_USER_IDS", set())
    @patch("app.auth._ADMIN_EMAILS", None)
    def test_require_admin_allows_admin_email(self, _mock_require_auth) -> None:
        os.environ["ADMIN_USER_EMAILS"] = "admin@example.com"
        user_id, payload = require_admin(DummyHandler())
        self.assertEqual(user_id, "user-1")
        self.assertEqual(payload["email"], "admin@example.com")


if __name__ == "__main__":
    unittest.main()
