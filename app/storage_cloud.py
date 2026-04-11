"""Supabase Storage adapter for Customy V3 (SaaS mode).

Artifacts are stored under: artifacts/<user_id>/<slug>/<filename>
Access is via signed URLs valid for 1 hour.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_supabase_client: Any = None


def _get_client() -> Any:
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client

        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        _supabase_client = create_client(url, key)
    return _supabase_client


BUCKET = "artifacts"
SIGNED_URL_TTL = 3600  # seconds


def _storage_path(user_id: str, slug: str, filename: str) -> str:
    return f"{user_id}/{slug}/{filename}"


def upload_bytes(user_id: str, slug: str, filename: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload raw bytes to Supabase Storage. Returns the storage path."""
    client = _get_client()
    path = _storage_path(user_id, slug, filename)
    client.storage.from_(BUCKET).upload(
        path,
        data,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return path


def upload_file(user_id: str, slug: str, filename: str, local_path: str) -> str:
    """Upload a local file to Supabase Storage. Returns the storage path."""
    path_obj = Path(local_path)
    data = path_obj.read_bytes()
    content_type = _guess_content_type(path_obj.suffix)
    return upload_bytes(user_id, slug, filename, data, content_type)


def get_signed_url(user_id: str, slug: str, filename: str) -> str:
    """Return a short-lived signed URL for a stored artifact."""
    client = _get_client()
    path = _storage_path(user_id, slug, filename)
    response = client.storage.from_(BUCKET).create_signed_url(path, SIGNED_URL_TTL)
    return response["signedURL"]


def upload_pack_files(user_id: str, slug: str, local_dir: str) -> dict[str, str]:
    """Upload all artifact files from a local pack directory.

    Returns a dict mapping artifact key to signed URL:
      {
        "resume_tex_url": "...",
        "resume_pdf_url": "...",   # only if PDF exists
        "cover_letter_url": "...", # only if present
        "linkedin_msg_url": "...", # only if present
        "email_draft_url": "...",  # only if present
        "generated_json_url": "...",
      }
    """
    base = Path(local_dir)
    urls: dict[str, str] = {}

    _upload_if_exists(user_id, slug, base, "resume.tex", "resume_tex_url", urls)
    _upload_if_exists(user_id, slug, base, "resume.pdf", "resume_pdf_url", urls)
    _upload_if_exists(user_id, slug, base, "generated.json", "generated_json_url", urls)
    _upload_if_exists(user_id, slug, base, "linkedin_message.md", "linkedin_msg_url", urls)
    _upload_if_exists(user_id, slug, base, "email_draft.md", "email_draft_url", urls)

    # cover letter filename varies: <Name>_Cover_letter.txt
    for path in base.glob("*_Cover_letter.txt"):
        storage_path = upload_file(user_id, slug, path.name, str(path))
        urls["cover_letter_url"] = get_signed_url(user_id, slug, path.name)
        break

    return urls


def _upload_if_exists(
    user_id: str,
    slug: str,
    base: Path,
    filename: str,
    key: str,
    urls: dict[str, str],
) -> None:
    local = base / filename
    if local.exists():
        upload_file(user_id, slug, filename, str(local))
        urls[key] = get_signed_url(user_id, slug, filename)


def _guess_content_type(suffix: str) -> str:
    mapping = {
        ".tex": "text/plain",
        ".pdf": "application/pdf",
        ".json": "application/json",
        ".md": "text/markdown",
        ".txt": "text/plain",
    }
    return mapping.get(suffix.lower(), "application/octet-stream")
