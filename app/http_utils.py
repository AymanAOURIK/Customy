"""Shared HTTP request/response helpers.

Centralises JSON body parsing and JSON response writing so every route
module imports from one place instead of duplicating the same logic.
"""
from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any


def read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    """Read and parse a JSON request body.

    Returns an empty dict when Content-Length is absent or zero.
    Raises ValueError on invalid JSON.
    """
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(content_length).decode("utf-8") if content_length else "{}"
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc


def send_json(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: Any) -> None:
    """Serialise *payload* to JSON and write it as the HTTP response."""
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
