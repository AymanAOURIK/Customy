"""Onboarding Phase 1 route handlers."""

from __future__ import annotations

import logging
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from app.auth import AuthError, require_auth
from app.db_postgres import record_api_usage as pg_record_api_usage
from app.http_utils import send_json
from app.onboarding import (
    OnboardingExtractionError,
    extract_draft as onboarding_extract_draft,
)
from app.onboarding_db import (
    get_onboarding_draft as get_onboarding_draft_db,
    insert_resume_upload,
    update_resume_upload_parsed,
    upsert_onboarding_draft,
)
from app.resume_parser import extract_text as extract_resume_text
from app.storage_cloud import upload_bytes_at_path

_log = logging.getLogger("app.server")

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


def dispatch_onboarding_get(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    if path == "/api/onboarding/draft":
        handle_onboarding_draft_get(handler, cfg)
        return True
    return False


def dispatch_onboarding_post(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    if path == "/api/resume/upload":
        handle_resume_upload(handler, cfg)
        return True
    return False


def _resume_file_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _resume_storage_content_type(filename: str, uploaded_content_type: str | None) -> str:
    extension = _resume_file_extension(filename)
    if extension == ".pdf":
        return "application/pdf"
    if extension == ".md":
        return "text/markdown"
    if extension == ".txt":
        return "text/plain"
    return (uploaded_content_type or "application/octet-stream").strip() or "application/octet-stream"


def _resume_upload_error_payload(
    code: str,
    message: str,
    *,
    status: int,
    details: dict[str, object] | None = None,
) -> tuple[HTTPStatus, dict[str, object]]:
    payload: dict[str, object] = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "status": status,
        },
    }
    if details:
        payload["error"]["details"] = details
    return HTTPStatus(status), payload


def _onboarding_draft_payload(draft: dict | None) -> dict[str, object]:
    if draft is None:
        return {
            "exists": False,
            "status": "empty",
            "draft_data": {},
            "gap_analysis": {},
        }
    return {
        "exists": True,
        "id": str(draft.get("id") or ""),
        "status": str(draft.get("status") or "draft"),
        "source_resume_upload_id": (
            str(draft.get("source_resume_upload_id"))
            if draft.get("source_resume_upload_id") is not None
            else None
        ),
        "updated_at": str(draft.get("updated_at") or ""),
        "draft_data": draft.get("draft_data") or {},
        "gap_analysis": draft.get("gap_analysis") or {},
    }


def _record_onboarding_usage(
    user_id: str,
    usage_summary: dict[str, object] | None,
    *,
    request_status: str,
    error_message: str = "",
) -> None:
    attempts = list((usage_summary or {}).get("attempts") or [])
    if not attempts:
        return
    try:
        pg_record_api_usage(
            user_id,
            attempts,
            application_id=None,
            request_status=request_status,
            error_message=error_message,
        )
    except Exception:
        _log.exception(
            "resume_upload.usage_persist_failed user_id=%s request_status=%s",
            user_id,
            request_status,
        )


def _parse_upload_file(handler: BaseHTTPRequestHandler) -> tuple[str, bytes, str | None]:
    """Parse a multipart/form-data upload request.

    Extracts the field named 'file' and returns (filename, file_bytes, content_type).
    Raises ValueError on any validation failure so the caller can return 400.
    """
    content_type = handler.headers.get("Content-Type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise ValueError("Expected multipart/form-data content type")

    boundary: bytes | None = None
    for segment in content_type.split(";"):
        segment = segment.strip()
        if segment.lower().startswith("boundary="):
            boundary = segment[len("boundary="):].strip().strip('"').encode("ascii")
            break
    if not boundary:
        raise ValueError("Malformed Content-Type: missing boundary")

    content_length = int(handler.headers.get("Content-Length", 0) or 0)
    if content_length <= 0:
        raise ValueError("Empty request body")
    if content_length > _MAX_UPLOAD_BYTES:
        handler.rfile.read(content_length)
        raise ValueError("File too large. Maximum allowed size is 5 MB.")

    body = handler.rfile.read(content_length)
    sep = b"--" + boundary

    for raw_part in body.split(sep):
        if raw_part in (b"", b"--\r\n", b"--", b"\r\n"):
            continue
        header_end = raw_part.find(b"\r\n\r\n")
        if header_end == -1:
            continue

        headers_block = raw_part[:header_end].lstrip(b"\r\n")
        part_body = raw_part[header_end + 4:]
        if part_body.endswith(b"\r\n"):
            part_body = part_body[:-2]

        field_name: str | None = None
        filename: str | None = None
        part_content_type: str | None = None
        for raw_header in headers_block.split(b"\r\n"):
            header_str = raw_header.decode("utf-8", errors="replace")
            header_lower = header_str.lower()
            if header_lower.startswith("content-type:"):
                part_content_type = header_str.split(":", 1)[1].strip()
                continue
            if not header_lower.startswith("content-disposition:"):
                continue
            for token in header_str.split(";"):
                token = token.strip()
                if token.lower().startswith("name="):
                    field_name = token[5:].strip().strip('"')
                elif token.lower().startswith("filename="):
                    filename = token[9:].strip().strip('"')

        if field_name == "file" and filename:
            safe_name = Path(filename).name.strip()
            if not safe_name:
                raise ValueError("Uploaded file is missing a valid filename")
            if not part_body:
                raise ValueError("Uploaded file is empty")
            return safe_name, part_body, part_content_type

    raise ValueError("No 'file' field found in the upload")


def handle_onboarding_draft_get(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        send_json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return
    draft = get_onboarding_draft_db(user_id)
    if draft is None:
        _log.info("onboarding_draft.get empty_state user_id=%s", user_id)
    else:
        _log.info(
            "onboarding_draft.get found user_id=%s status=%s",
            user_id,
            draft.get("status"),
        )
    send_json(handler, HTTPStatus.OK, _onboarding_draft_payload(draft))


def handle_resume_upload(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    try:
        user_id, _ = require_auth(handler)
    except AuthError as exc:
        send_json(handler, HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        return
    request_content_type = handler.headers.get("Content-Type", "").strip()
    try:
        filename, file_bytes, uploaded_content_type = _parse_upload_file(handler)
    except ValueError as exc:
        _log.warning(
            "resume_upload.invalid_request user_id=%s request_content_type=%s error=%s",
            user_id,
            request_content_type,
            exc,
        )
        status, payload = _resume_upload_error_payload(
            "invalid_upload_request",
            str(exc),
            status=HTTPStatus.BAD_REQUEST,
            details={"request_content_type": request_content_type},
        )
        send_json(handler, status, payload)
        return
    extension = _resume_file_extension(filename)
    storage_content_type = _resume_storage_content_type(filename, uploaded_content_type)
    parse_path = "pdf" if extension == ".pdf" else "plain_text"
    _log.info(
        "resume_upload.start user_id=%s filename=%s extension=%s request_content_type=%s file_content_type=%s size_bytes=%d",
        user_id,
        filename,
        extension,
        request_content_type,
        uploaded_content_type or "",
        len(file_bytes),
    )
    if extension not in {".pdf", ".txt", ".md"}:
        _log.warning(
            "resume_upload.unsupported_type user_id=%s filename=%s extension=%s",
            user_id,
            filename,
            extension,
        )
        status, payload = _resume_upload_error_payload(
            "unsupported_file_type",
            "Only .pdf, .txt, and .md files are accepted.",
            status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            details={
                "filename": filename,
                "extension": extension,
                "file_content_type": uploaded_content_type or "",
            },
        )
        send_json(handler, status, payload)
        return
    upload_uuid = str(uuid.uuid4())
    storage_path = f"{user_id}/resumes/{upload_uuid}/{filename}"
    try:
        upload_bytes_at_path(storage_path, file_bytes, storage_content_type)
        _log.info(
            "resume_upload.storage_saved user_id=%s filename=%s storage_path=%s",
            user_id,
            filename,
            storage_path,
        )
    except Exception:
        _log.exception(
            "resume_upload.storage_failed user_id=%s filename=%s storage_path=%s",
            user_id,
            filename,
            storage_path,
        )
        status, payload = _resume_upload_error_payload(
            "resume_storage_failed",
            "Resume file upload to storage failed.",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            details={"filename": filename, "storage_path": storage_path},
        )
        send_json(handler, status, payload)
        return
    try:
        upload_row = insert_resume_upload(user_id, storage_path, filename, len(file_bytes))
        upload_id = str(upload_row["id"])
        _log.info(
            "resume_upload.db_inserted user_id=%s upload_id=%s filename=%s",
            user_id,
            upload_id,
            filename,
        )
    except Exception:
        _log.exception(
            "resume_upload.db_insert_failed user_id=%s filename=%s storage_path=%s",
            user_id,
            filename,
            storage_path,
        )
        status, payload = _resume_upload_error_payload(
            "resume_upload_db_insert_failed",
            "Resume upload metadata could not be saved.",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            details={"filename": filename, "storage_path": storage_path},
        )
        send_json(handler, status, payload)
        return
    _log.info(
        "resume_upload.parse_selected user_id=%s upload_id=%s parse_path=%s",
        user_id,
        upload_id,
        parse_path,
    )
    try:
        parsed_text = extract_resume_text(file_bytes, filename)
        _log.info(
            "resume_upload.parsed user_id=%s upload_id=%s text_length=%d",
            user_id,
            upload_id,
            len(parsed_text),
        )
    except ValueError as exc:
        try:
            update_resume_upload_parsed(upload_id, None, parse_error=str(exc))
        except Exception:
            _log.exception(
                "resume_upload.parse_failure_mark_failed user_id=%s upload_id=%s",
                user_id,
                upload_id,
            )
        _log.warning(
            "resume_upload.parse_failed user_id=%s upload_id=%s filename=%s error=%s",
            user_id,
            upload_id,
            filename,
            exc,
        )
        status, payload = _resume_upload_error_payload(
            "resume_parse_failed",
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            details={
                "filename": filename,
                "extension": extension,
                "parse_path": parse_path,
            },
        )
        send_json(handler, status, payload)
        return
    try:
        update_resume_upload_parsed(upload_id, parsed_text)
        _log.info(
            "resume_upload.db_parse_saved user_id=%s upload_id=%s text_length=%d",
            user_id,
            upload_id,
            len(parsed_text),
        )
    except Exception:
        _log.exception(
            "resume_upload.db_parse_save_failed user_id=%s upload_id=%s",
            user_id,
            upload_id,
        )
        status, payload = _resume_upload_error_payload(
            "resume_parse_store_failed",
            "Resume text was extracted but could not be stored.",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            details={"upload_id": upload_id, "filename": filename},
        )
        send_json(handler, status, payload)
        return
    try:
        draft_data, gap_analysis, usage_summary = onboarding_extract_draft(parsed_text, cfg)
        _log.info(
            "resume_upload.draft_extracted user_id=%s upload_id=%s experiences=%d skill_count=%s",
            user_id,
            upload_id,
            len(draft_data.get("experiences") or []),
            gap_analysis.get("skill_count"),
        )
        _record_onboarding_usage(
            user_id,
            usage_summary,
            request_status="succeeded",
        )
    except OnboardingExtractionError as exc:
        _record_onboarding_usage(
            user_id,
            exc.usage_summary,
            request_status="failed",
            error_message=str(exc),
        )
        _log.exception(
            "resume_upload.draft_extract_failed user_id=%s upload_id=%s",
            user_id,
            upload_id,
        )
        status, payload = _resume_upload_error_payload(
            "extract_failed",
            str(exc),
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            details={"upload_id": upload_id},
        )
        send_json(handler, status, payload)
        return
    except ValueError as exc:
        _log.exception(
            "resume_upload.draft_extract_failed user_id=%s upload_id=%s",
            user_id,
            upload_id,
        )
        status, payload = _resume_upload_error_payload(
            "extract_failed",
            str(exc),
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            details={"upload_id": upload_id},
        )
        send_json(handler, status, payload)
        return
    try:
        draft_row = upsert_onboarding_draft(user_id, upload_id, draft_data, gap_analysis)
        _log.info(
            "resume_upload.draft_saved user_id=%s upload_id=%s draft_status=%s",
            user_id,
            upload_id,
            draft_row.get("status", "draft"),
        )
    except Exception:
        _log.exception(
            "resume_upload.draft_save_failed user_id=%s upload_id=%s",
            user_id,
            upload_id,
        )
        status, payload = _resume_upload_error_payload(
            "onboarding_draft_store_failed",
            "Resume was parsed but the onboarding draft could not be saved.",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            details={"upload_id": upload_id},
        )
        send_json(handler, status, payload)
        return
    draft_payload = _onboarding_draft_payload(draft_row)
    send_json(
        handler,
        HTTPStatus.OK,
        {
            "ok": True,
            "upload": {
                "id": upload_id,
                "filename": filename,
                "extension": extension,
                "content_type": storage_content_type,
                "storage_path": storage_path,
                "file_size_bytes": len(file_bytes),
                "parse_path": parse_path,
                "text_length": len(parsed_text),
                "parse_status": "done",
            },
            "draft": draft_payload,
            "draft_data": draft_payload.get("draft_data", {}),
            "gap_analysis": draft_payload.get("gap_analysis", {}),
        },
    )
