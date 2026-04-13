from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import sqlite3
import subprocess
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from app.analyzer import analyze_jd, build_updated_resume_keywords
from app.db import (
    create_prep_session,
    delete_answer,
    delete_prep_session,
    get_analytics,
    get_answer_bank,
    get_answer_by_key,
    get_application,
    get_application_events,
    get_apply_queue,
    get_daily_stats,
    get_funnel_stats,
    get_prep_session,
    get_quick_stats,
    get_tracker_applications,
    insert_application,
    list_applications,
    list_prep_sessions,
    record_api_usage,
    refresh_daily_stats,
    set_duplicate_flag,
    update_application_notes,
    update_prep_session,
    update_status,
    upsert_answer,
)
from app.generator import PackGenerationError, generate_pack
from app.latex import compile_pdf, render_tex
from app.playfill import build_fill_plan, run_playwright_fill
from app.profile import build_candidate_context
from app.storage import make_slug, set_applications_dir, write_pack
from app.storage_cloud import get_signed_url_for_path, upload_bytes_at_path, upload_pack_files
from app.resume_parser import extract_text as extract_resume_text
from app.onboarding import extract_draft as onboarding_extract_draft
from app.onboarding_db import (
    get_onboarding_draft as get_onboarding_draft_db,
    insert_resume_upload,
    update_resume_upload_parsed,
    upsert_onboarding_draft,
)
from app.targeting import candidate_keywords_from_profile
import psycopg2.errors as _pg_errors
from app.auth import AuthError, require_auth
from app.profile_db import get_profile, profile_to_candidate_context
from app.db_postgres import (
    application_slug_exists as pg_application_slug_exists,
    get_analytics as pg_get_analytics,
    get_application as pg_get_application,
    get_application_events as pg_get_application_events,
    get_apply_queue as pg_get_apply_queue,
    get_daily_stats as pg_get_daily_stats,
    get_funnel_stats as pg_get_funnel_stats,
    get_quick_stats as pg_get_quick_stats,
    get_tracker_applications as pg_get_tracker_applications,
    insert_application as pg_insert_application,
    link_job_to_application,
    list_applications as pg_list_applications,
    record_api_usage as pg_record_api_usage,
    refresh_daily_stats as pg_refresh_daily_stats,
    set_duplicate_flag as pg_set_duplicate_flag,
    update_application_notes as pg_update_application_notes,
    update_status as pg_update_status,
)
from app.routes_auth import handle_auth_me
from app.routes_jobs import (
    dispatch_jobs_delete,
    dispatch_jobs_get,
    dispatch_jobs_patch,
    dispatch_jobs_post,
)
from app.routes_profile import handle_profile_create, handle_profile_get, handle_profile_update
from app.routes_admin import (
    dispatch_admin_delete,
    dispatch_admin_get,
    dispatch_admin_post,
    dispatch_admin_put,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"
STATIC_DIR = PROJECT_ROOT / "app" / "static"
ALLOWED_OUTPUTS = {"resume", "cover_letter", "linkedin_msg", "email_draft"}

# ── Interview prep question templates ─────────────────────────────────────

_PREP_BEHAVIORAL: list[tuple[str, str]] = [
    ("Tell me about a time you led a technical project end-to-end.", "behavioral"),
    ("Describe a situation where you had to make a decision with incomplete information.", "behavioral"),
    ("Give an example of a time you persuaded stakeholders of a technical direction.", "behavioral"),
    ("Tell me about a time you failed and what you learned from it.", "behavioral"),
    ("Describe a time you worked under tight deadlines. How did you manage priorities?", "behavioral"),
    ("Tell me about a time you mentored or helped a colleague grow professionally.", "behavioral"),
]

_PREP_TECHNICAL: dict[str, list[str]] = {
    "ai_platform": [
        "How do you design an ML pipeline for production reliability?",
        "What is your approach to model monitoring and drift detection?",
        "Walk me through how you would set up an MLOps stack from scratch.",
        "How do you handle data quality issues in a production ML pipeline?",
    ],
    "agentic": [
        "Explain how you would design an agentic system with tool use and memory.",
        "What are the key failure modes of LLM-based autonomous agents?",
        "How do you evaluate a RAG pipeline's accuracy and reliability in production?",
        "How would you approach prompt engineering for a complex multi-step agent?",
    ],
    "ai_pm": [
        "How do you define success metrics for an AI-powered product feature?",
        "Describe how you would prioritize ML model improvements against other features.",
        "How do you communicate technical AI limitations to non-technical stakeholders?",
        "Walk me through your process for gathering requirements for an AI feature.",
    ],
    "ai_architect": [
        "How do you evaluate different vector database solutions for a RAG system?",
        "What are your considerations when designing a multi-model AI architecture?",
        "How do you approach scalability in a real-time ML inference system?",
        "Describe your approach to AI system observability and debugging.",
    ],
    "ai_forward_deployed": [
        "How do you approach understanding a new client's technical environment?",
        "Describe how you would demo an AI product to a skeptical technical audience.",
        "How do you handle customer escalations about AI output quality?",
        "How do you translate customer feedback into actionable product requirements?",
    ],
    "ai_transformation": [
        "How have you driven AI adoption across teams that were initially resistant?",
        "Describe your approach to building an internal AI capability roadmap.",
        "How do you measure the ROI of an AI transformation initiative?",
        "What change management techniques do you apply when rolling out AI tools?",
    ],
    "general": [
        "Walk me through your experience with data pipelines and ETL processes.",
        "How do you approach system design for a data-intensive application?",
        "Describe your debugging process when a production system is slow or failing.",
        "How do you stay current with rapidly evolving technologies in your field?",
    ],
}

_PREP_SITUATIONAL: list[str] = [
    "If you joined this team tomorrow, what would your first 30 days look like?",
    "How would you handle a situation where a key model in production starts underperforming?",
    "Imagine you have been given a poorly documented legacy codebase. How do you approach it?",
]


def _generate_prep_questions(archetype: str | None) -> list[dict]:
    """Returns a starter question set based on role archetype. No LLM required."""
    import uuid
    arch = str(archetype or "general").lower()
    tech = _PREP_TECHNICAL.get(arch, _PREP_TECHNICAL["general"])
    questions: list[dict] = []
    for text, cat in _PREP_BEHAVIORAL[:4]:
        questions.append({"id": uuid.uuid4().hex[:8], "text": text, "category": cat, "answer": "", "confidence": ""})
    for text in tech[:4]:
        questions.append({"id": uuid.uuid4().hex[:8], "text": text, "category": "technical", "answer": "", "confidence": ""})
    for text in _PREP_SITUATIONAL[:2]:
        questions.append({"id": uuid.uuid4().hex[:8], "text": text, "category": "situational", "answer": "", "confidence": ""})
    return questions

_log = logging.getLogger(__name__)


def _artifact_url(slug: str, filename: str) -> str:
    return f"/artifacts/{slug}/{filename}"


def _normalize_application_url(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "://" not in raw and re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/.*)?", raw):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Field 'application_url' must be a valid http/https URL.")
    return parsed.geturl()


def _clean_company_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).strip(" .,:;|-")


def _company_quality(value: object) -> int:
    company = _clean_company_name(value)
    if not company:
        return 0
    lowered = company.lower()
    if lowered in {"unknown", "unknown company", "company", "our company", "our team", "team"}:
        return 0
    score = 1
    if " " in company or "&" in company or "." in company:
        score += 1
    if any(char.isupper() for char in company[1:]):
        score += 1
    if len(company) >= 5:
        score += 1
    return score


def _pick_company_name(*candidates: object) -> str | None:
    best = ""
    best_score = 0
    for candidate in candidates:
        cleaned = _clean_company_name(candidate)
        score = _company_quality(cleaned)
        if score > best_score:
            best = cleaned
            best_score = score
    return best or None


def _open_folder_in_file_manager(path: str, applications_dir: Path) -> None:
    target = Path(path).resolve()
    if applications_dir != target and applications_dir not in target.parents:
        raise ValueError("Application folder path is outside the configured applications directory.")
    if not target.exists() or not target.is_dir():
        raise ValueError("Application folder not found.")

    command: list[str] | None = None
    if os.name == "nt":
        command = ["explorer.exe", str(target)]
    elif shutil.which("explorer.exe"):
        explorer_target = str(target)
        if shutil.which("wslpath"):
            try:
                explorer_target = subprocess.check_output(
                    ["wslpath", "-w", str(target)],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip() or explorer_target
            except Exception:
                explorer_target = str(target)
        command = ["explorer.exe", explorer_target]
    elif shutil.which("xdg-open"):
        command = ["xdg-open", str(target)]
    elif shutil.which("open"):
        command = ["open", str(target)]

    if not command:
        raise ValueError("No supported file manager opener is available on this system.")

    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        raise ValueError(f"Could not open the application folder: {exc}") from exc


def _serialize_files(slug: str, files: dict, cloud_paths: dict | None = None) -> dict:
    if cloud_paths:
        cloud_key_map = {
            "resume_tex": "resume_tex_url",
            "resume_pdf": "resume_pdf_url",
            "cover_letter": "cover_letter_url",
            "linkedin_message": "linkedin_msg_url",
            "email_draft": "email_draft_url",
            "generated_json": "generated_json_url",
        }
        response = {"output_dir": {"path": None, "url": None}}
        for key, path in files.items():
            if key in {"output_dir", "cover_letter_filename"}:
                continue
            stored_path = cloud_paths.get(cloud_key_map.get(key, ""))
            response[key] = {
                "path": stored_path,
                "url": get_signed_url_for_path(stored_path) if stored_path else None,
            }
        return response

    response = {"output_dir": {"path": files["output_dir"], "url": None}}
    for key, path in files.items():
        if key in {"output_dir", "cover_letter_filename"}:
            continue
        response[key] = {"path": path, "url": _artifact_url(slug, Path(path).name)}
    return response


def _local_cover_letter_path(outputs_path: object) -> Path | None:
    raw_path = str(outputs_path or "").strip()
    if not raw_path:
        return None
    matches = sorted(Path(raw_path).glob("*Cover_letter.txt"))
    return matches[0] if matches else None


def _derived_generated_json_storage_path(row: dict) -> str | None:
    user_id = str(row.get("user_id") or "").strip()
    slug = str(row.get("slug") or "").strip()
    if not user_id or not slug:
        return None
    return f"{user_id}/{slug}/generated.json"


def _serialize_application_files(row: dict, *, cloud_mode: bool = False) -> dict:
    files: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []

    def add_file(key: str, label: str, path: object, url: str) -> None:
        path_str = str(path or "").strip()
        files.append(
            {
                "key": key,
                "label": label,
                "path": path_str,
                "filename": Path(path_str).name if path_str else "",
                "url": url,
            }
        )

    def add_missing(key: str, label: str, reason: str) -> None:
        missing.append({"key": key, "label": label, "reason": reason})

    if cloud_mode:
        for key, label, stored_path, expected in (
            ("resume_pdf", "Resume PDF", row.get("resume_pdf_url"), True),
            ("resume_tex", "Resume TEX", row.get("resume_tex_url"), True),
            ("cover_letter", "Cover Letter", row.get("cover_letter_url"), bool(row.get("cover_letter"))),
            ("linkedin_message", "LinkedIn Message", row.get("linkedin_msg_url"), bool(row.get("linkedin_msg"))),
            ("email_draft", "Email Draft", row.get("email_draft_url"), bool(row.get("email_draft"))),
            (
                "generated_json",
                "Generated JSON",
                row.get("generated_json_url") or _derived_generated_json_storage_path(row),
                True,
            ),
        ):
            if stored_path:
                try:
                    add_file(key, label, stored_path, get_signed_url_for_path(str(stored_path)))
                except Exception as exc:
                    _log.warning(
                        "artifact.sign_failed app_id=%s key=%s path=%s error=%s",
                        row.get("id"),
                        key,
                        stored_path,
                        exc,
                    )
                    add_missing(key, label, "File is not available right now.")
                continue
            if expected:
                add_missing(key, label, "File was not generated for this application.")
        return {"files": files, "missing": missing}

    outputs_path = str(row.get("outputs_path") or "").strip()
    if row.get("resume_pdf_path"):
        add_file(
            "resume_pdf",
            "Resume PDF",
            row["resume_pdf_path"],
            _artifact_url(str(row.get("slug") or ""), Path(str(row["resume_pdf_path"])).name),
        )
    else:
        add_missing("resume_pdf", "Resume PDF", "PDF was not generated for this application.")

    if row.get("resume_tex_path"):
        add_file(
            "resume_tex",
            "Resume TEX",
            row["resume_tex_path"],
            _artifact_url(str(row.get("slug") or ""), Path(str(row["resume_tex_path"])).name),
        )
    else:
        add_missing("resume_tex", "Resume TEX", "File was not generated for this application.")

    cover_letter_path = _local_cover_letter_path(outputs_path)
    if cover_letter_path is not None:
        add_file(
            "cover_letter",
            "Cover Letter",
            str(cover_letter_path),
            _artifact_url(str(row.get("slug") or ""), cover_letter_path.name),
        )
    elif row.get("cover_letter"):
        add_missing("cover_letter", "Cover Letter", "File was not generated for this application.")

    for key, label, filename, enabled in (
        ("linkedin_message", "LinkedIn Message", "linkedin_message.md", bool(row.get("linkedin_msg"))),
        ("email_draft", "Email Draft", "email_draft.md", bool(row.get("email_draft"))),
    ):
        local_path = Path(outputs_path) / filename if outputs_path else None
        if local_path and local_path.is_file():
            add_file(
                key,
                label,
                str(local_path),
                _artifact_url(str(row.get("slug") or ""), filename),
            )
        elif enabled:
            add_missing(key, label, "File was not generated for this application.")

    generated_json_path = Path(outputs_path) / "generated.json" if outputs_path else None
    if generated_json_path and generated_json_path.is_file():
        add_file(
            "generated_json",
            "Generated JSON",
            str(generated_json_path),
            _artifact_url(str(row.get("slug") or ""), "generated.json"),
        )
    else:
        add_missing("generated_json", "Generated JSON", "File was not generated for this application.")

    return {"files": files, "missing": missing}


def _serialize_application(row: dict, *, cloud_mode: bool = False) -> dict:
    slug = row.get("slug", "")
    initial_score = row.get("initial_score")
    if initial_score is None:
        initial_score = row.get("score")
    updated_score = row.get("updated_score")
    current_score = updated_score if updated_score is not None else initial_score
    outputs = {}
    if cloud_mode:
        if row.get("resume_pdf_url"):
            outputs["resume_pdf"] = get_signed_url_for_path(str(row["resume_pdf_url"]))
        if row.get("resume_tex_url"):
            outputs["resume_tex"] = get_signed_url_for_path(str(row["resume_tex_url"]))
        if row.get("cover_letter_url"):
            outputs["cover_letter"] = get_signed_url_for_path(str(row["cover_letter_url"]))
        if row.get("linkedin_msg_url"):
            outputs["linkedin_message"] = get_signed_url_for_path(str(row["linkedin_msg_url"]))
        if row.get("email_draft_url"):
            outputs["email_draft"] = get_signed_url_for_path(str(row["email_draft_url"]))
    else:
        if row.get("resume_pdf_path"):
            outputs["resume_pdf"] = _artifact_url(slug, Path(row["resume_pdf_path"]).name)
        if row.get("resume_tex_path"):
            outputs["resume_tex"] = _artifact_url(slug, Path(row["resume_tex_path"]).name)
        if row.get("cover_letter") and row.get("outputs_path"):
            _cl_path = _local_cover_letter_path(row["outputs_path"])
            if _cl_path is not None:
                outputs["cover_letter"] = _artifact_url(slug, _cl_path.name)
        if row.get("linkedin_msg"):
            outputs["linkedin_message"] = _artifact_url(slug, "linkedin_message.md")
        if row.get("email_draft"):
            outputs["email_draft"] = _artifact_url(slug, "email_draft.md")
        outputs["generated_json"] = _artifact_url(slug, "generated.json")

    return {
        "id": row.get("id"),
        "created_at": row.get("created_at"),
        "company": row.get("company"),
        "role": row.get("role"),
        "score": current_score,
        "initial_score": initial_score,
        "updated_score": updated_score,
        "status": row.get("status"),
        "is_duplicate": bool(row.get("is_duplicate")),
        "slug": slug,
        "model_used": row.get("model_used"),
        "tokens_used": row.get("tokens_used"),
        "prompt_tokens": row.get("prompt_tokens"),
        "cached_prompt_tokens": row.get("cached_prompt_tokens"),
        "completion_tokens": row.get("completion_tokens"),
        "total_cost_usd": row.get("total_cost_usd"),
        "api_attempts": row.get("api_attempts"),
        "outputs": outputs,
        "job_application_url": row.get("job_application_url"),
        "notes": row.get("notes") or "",
        "folder_path": None if cloud_mode else row.get("outputs_path"),
        "folder_url": None if cloud_mode else (
            f"/api/applications/{row.get('id')}/open-folder" if row.get("id") and row.get("outputs_path") else None
        ),
    }


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(content_length).decode("utf-8") if content_length else "{}"
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc


def _normalize_bool(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"Field '{field_name}' must be a boolean.")


def _normalize_outputs(raw_outputs: object) -> list[str]:
    outputs = ["resume"]
    if not isinstance(raw_outputs, list):
        return outputs
    for item in raw_outputs:
        value = str(item).strip()
        if value in ALLOWED_OUTPUTS and value not in outputs:
            outputs.append(value)
    return outputs


def _candidate_keywords(candidate_context: dict) -> list[str]:
    keywords = candidate_keywords_from_profile(candidate_context)
    location = candidate_context.get("personal", {}).get("location", "").strip()
    if location:
        keywords.append(f"location:{location}")
    return keywords


def _updated_resume_keywords(pack: object, jd_analysis: dict, candidate_context: dict) -> list[str]:
    keywords = build_updated_resume_keywords(pack, jd_analysis)
    location = candidate_context.get("personal", {}).get("location", "").strip()
    if location:
        keywords.append(f"location:{location}")
    return keywords


_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


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


def _parse_upload_file(handler: BaseHTTPRequestHandler) -> tuple[str, bytes, str | None]:
    """Parse a multipart/form-data upload request.

    Extracts the field named 'file' and returns (filename, file_bytes, content_type).
    Raises ValueError on any validation failure so the caller can return 400.
    """
    content_type = handler.headers.get("Content-Type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise ValueError("Expected multipart/form-data content type")

    # Extract the boundary token
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
        handler.rfile.read(content_length)  # drain to keep connection healthy
        raise ValueError("File too large. Maximum allowed size is 5 MB.")

    body = handler.rfile.read(content_length)
    sep = b"--" + boundary

    for raw_part in body.split(sep):
        # Skip preamble, epilogue, and the closing "--" marker
        if raw_part in (b"", b"--\r\n", b"--", b"\r\n"):
            continue
        header_end = raw_part.find(b"\r\n\r\n")
        if header_end == -1:
            continue

        headers_block = raw_part[:header_end].lstrip(b"\r\n")
        part_body = raw_part[header_end + 4:]
        # Strip the trailing \r\n that precedes the next boundary delimiter
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


def run_server(host: str, port: int, cfg: dict) -> None:
    set_applications_dir(cfg["paths"]["applications_dir"])
    applications_dir = Path(cfg["paths"]["applications_dir"]).resolve()
    db_path = cfg["paths"]["db_path"]
    candidate_yaml_path = str(PROJECT_ROOT / "candidate.yaml")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            _log.info("%s %s", self.command if hasattr(self, "command") else "-", format % args)

        def _require_saas_user_id(self) -> str | None:
            if cfg["mode"] != "saas":
                return None
            try:
                user_id, _ = require_auth(self)
            except AuthError as exc:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
                return None
            return user_id

        def _saas_local_only(self, feature_name: str) -> None:
            self._json(
                HTTPStatus.NOT_IMPLEMENTED,
                {"error": f"{feature_name} is not enabled in public SaaS mode yet."},
            )

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self._serve_dashboard()
                    return
                if parsed.path == "/dashboard":
                    self._serve_dashboard()
                    return
                if parsed.path.startswith("/static/"):
                    filename = parsed.path.removeprefix("/static/")
                    self._serve_static(filename)
                    return
                if parsed.path.startswith("/artifacts/"):
                    if cfg["mode"] == "saas":
                        self._json(HTTPStatus.FORBIDDEN, {"error": "Artifact access is not available in SaaS mode."})
                        return
                    self._serve_artifact(parsed.path)
                    return
                if parsed.path == "/api/health":
                    self._json(HTTPStatus.OK, {"status": "ok"})
                    return
                if parsed.path == "/api/stats":
                    self._handle_stats()
                    return
                if parsed.path == "/api/applications":
                    self._handle_applications(parsed.query)
                    return
                if parsed.path == "/api/apply-queue":
                    self._handle_apply_queue(parsed.query)
                    return
                if parsed.path == "/api/analytics":
                    self._handle_analytics()
                    return
                if parsed.path == "/api/tracker":
                    self._handle_tracker()
                    return
                _files_match = re.fullmatch(r"/api/applications/(\d+)/files", parsed.path)
                if _files_match:
                    self._handle_application_files(int(_files_match.group(1)))
                    return
                _ev_match = re.fullmatch(r"/api/applications/(\d+)/events", parsed.path)
                if _ev_match:
                    self._handle_application_events(int(_ev_match.group(1)))
                    return
                if parsed.path == "/api/answer-bank":
                    if cfg["mode"] == "saas":
                        self._saas_local_only("Answer Bank")
                        return
                    self._json(HTTPStatus.OK, {"answers": get_answer_bank(db_path)})
                    return
                if parsed.path == "/api/interview-prep":
                    if cfg["mode"] == "saas":
                        self._saas_local_only("Interview Prep")
                        return
                    sessions = list_prep_sessions(db_path)
                    self._json(HTTPStatus.OK, {"sessions": sessions})
                    return
                _prep_get_match = re.fullmatch(r"/api/interview-prep/(\d+)", parsed.path)
                if _prep_get_match:
                    if cfg["mode"] == "saas":
                        self._saas_local_only("Interview Prep")
                        return
                    session = get_prep_session(db_path, int(_prep_get_match.group(1)))
                    if not session:
                        self._json(HTTPStatus.NOT_FOUND, {"error": "Prep session not found."})
                        return
                    self._json(HTTPStatus.OK, {"session": session})
                    return
                if cfg["mode"] == "saas":
                    if parsed.path == "/api/auth/me":
                        handle_auth_me(self, cfg)
                        return
                    if parsed.path == "/api/profile":
                        handle_profile_get(self, cfg)
                        return
                    if parsed.path == "/api/onboarding/draft":
                        try:
                            user_id, _ = require_auth(self)
                        except AuthError as exc:
                            self._json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
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
                        self._json(HTTPStatus.OK, _onboarding_draft_payload(draft))
                        return
                    if dispatch_jobs_get(self, parsed.path, cfg):
                        return
                    if parsed.path.startswith("/api/admin/"):
                        if dispatch_admin_get(self, parsed.path, cfg):
                            return
                        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                        return
                self.send_error(HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                if parsed.path.startswith("/api/"):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                else:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:
                if parsed.path.startswith("/api/"):
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                else:
                    self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            open_folder_match = re.fullmatch(r"/api/applications/(\d+)/open-folder", parsed.path)
            if open_folder_match:
                if cfg["mode"] == "saas":
                    self._saas_local_only("Open folder")
                    return
                try:
                    app_id = int(open_folder_match.group(1))
                    row = get_application(db_path, app_id)
                    if not row:
                        raise ValueError(f"Application {app_id} does not exist.")
                    _open_folder_in_file_manager(str(row.get("outputs_path") or ""), applications_dir)
                    self._json(HTTPStatus.OK, {"status": "ok"})
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            if parsed.path == "/api/answer-bank":
                if cfg["mode"] == "saas":
                    self._saas_local_only("Answer Bank")
                    return
                try:
                    payload = _read_json(self)
                    question_key = str(payload.get("question_key") or "").strip()
                    answer_text = str(payload.get("answer_text") or "").strip()
                    if not question_key or not answer_text:
                        raise ValueError("Fields 'question_key' and 'answer_text' are required.")
                    upsert_answer(
                        db_path,
                        question_key=question_key,
                        question_text=str(payload.get("question_text") or question_key).strip(),
                        answer_text=answer_text,
                        category=str(payload.get("category") or "").strip(),
                        language=str(payload.get("language") or "en").strip(),
                        source="manual",
                    )
                    self._json(HTTPStatus.OK, {"answers": get_answer_bank(db_path)})
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

            if parsed.path == "/api/answer-question":
                if cfg["mode"] == "saas":
                    self._saas_local_only("Answer Bank")
                    return
                try:
                    payload = _read_json(self)
                    question = str(payload.get("question") or "").strip().lower()
                    if not question:
                        raise ValueError("Field 'question' is required.")
                    answers = get_answer_bank(db_path)
                    _CATEGORY_KEYWORDS: dict[str, list[str]] = {
                        "work_authorization": ["authorized", "work authorization", "visa", "sponsorship", "eligible to work", "right to work", "work permit"],
                        "salary": ["salary", "compensation", "pay", "rate", "expectations", "package", "remuneration"],
                        "availability": ["start date", "available", "notice period", "when can you start", "earliest start"],
                        "relocation": ["relocate", "relocation", "move to", "willing to move"],
                        "linkedin": ["linkedin", "linkedin url", "professional profile"],
                        "github": ["github", "portfolio", "code samples", "github url"],
                    }
                    matched_category = next(
                        (cat for cat, keywords in _CATEGORY_KEYWORDS.items() if any(kw in question for kw in keywords)),
                        None,
                    )
                    matched_answer = next(
                        (a for a in answers if a.get("category") == matched_category),
                        None,
                    ) if matched_category else None
                    self._json(HTTPStatus.OK, {
                        "matched": matched_answer is not None,
                        "category": matched_category,
                        "answer": matched_answer,
                        "hint": None if matched_answer else (
                            f"No answer saved for category '{matched_category}'. Add it in the Answer Bank."
                            if matched_category else "Question did not match any known category."
                        ),
                    })
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

            if parsed.path.startswith("/api/answer-bank/") and parsed.path.endswith("/delete"):
                if cfg["mode"] == "saas":
                    self._saas_local_only("Answer Bank")
                    return
                try:
                    key = unquote(parsed.path.removeprefix("/api/answer-bank/").removesuffix("/delete"))
                    delete_answer(db_path, key)
                    self._json(HTTPStatus.OK, {"answers": get_answer_bank(db_path)})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

            if parsed.path == "/api/apply-assist":
                if cfg["mode"] == "saas":
                    self._saas_local_only("Apply Assist")
                    return
                try:
                    payload = _read_json(self)
                    app_id = payload.get("app_id")
                    market = str(payload.get("market") or "").strip().lower() or None
                    use_playwright = bool(payload.get("use_playwright", False))

                    # Resolve ATS vendor and cover letter from the stored application
                    ats_vendor: str | None = None
                    cover_letter_text: str | None = None
                    application_url_for_pw: str | None = None
                    if app_id is not None:
                        row = get_application(db_path, int(app_id))
                        if not row:
                            raise ValueError(f"Application {app_id} not found.")
                        ats_vendor = row.get("role_archetype")  # archetype stored, vendor comes from analysis
                        # Try to read cover letter text from disk
                        outputs_path = row.get("outputs_path") or ""
                        if outputs_path:
                            cl_matches = sorted(Path(outputs_path).glob("*Cover_letter.txt"))
                            if cl_matches:
                                try:
                                    cover_letter_text = cl_matches[0].read_text(encoding="utf-8")
                                except Exception:
                                    pass
                        application_url_for_pw = row.get("job_application_url")
                        # Re-derive ats_vendor from application URL if stored
                        if application_url_for_pw:
                            from app.analyzer import _detect_ats_vendor  # type: ignore[attr-defined]
                            ats_vendor = _detect_ats_vendor(application_url_for_pw)

                    fill_plan = build_fill_plan(
                        db_path=db_path,
                        ats_vendor=ats_vendor,
                        market=market,
                        cover_letter_text=cover_letter_text,
                    )

                    playwright_result: dict | None = None
                    if use_playwright and application_url_for_pw:
                        playwright_result = run_playwright_fill(application_url_for_pw, fill_plan)

                    self._json(HTTPStatus.OK, {
                        "fill_plan": fill_plan,
                        "playwright": playwright_result,
                    })
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

            if parsed.path == "/api/interview-prep":
                if cfg["mode"] == "saas":
                    self._saas_local_only("Interview Prep")
                    return
                try:
                    payload = _read_json(self)
                    company = str(payload.get("company") or "").strip()
                    role = str(payload.get("role") or "").strip()
                    raw_app_id = payload.get("application_id")
                    application_id: int | None = int(raw_app_id) if raw_app_id is not None else None
                    archetype: str | None = None
                    if application_id is not None:
                        app_row = get_application(db_path, application_id)
                        if not app_row:
                            raise ValueError(f"Application {application_id} not found.")
                        if not company:
                            company = str(app_row.get("company") or "")
                        if not role:
                            role = str(app_row.get("role") or "")
                        archetype = app_row.get("role_archetype")
                    if not role:
                        raise ValueError("Field 'role' is required.")
                    questions = _generate_prep_questions(archetype)
                    session_id = create_prep_session(
                        db_path,
                        application_id=application_id,
                        company=company,
                        role=role,
                        questions=questions,
                    )
                    session = get_prep_session(db_path, session_id)
                    self._json(HTTPStatus.CREATED, {"session": session})
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

            _prep_delete_match = re.fullmatch(r"/api/interview-prep/(\d+)/delete", parsed.path)
            if _prep_delete_match:
                if cfg["mode"] == "saas":
                    self._saas_local_only("Interview Prep")
                    return
                try:
                    delete_prep_session(db_path, int(_prep_delete_match.group(1)))
                    self._json(HTTPStatus.OK, {"ok": True})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

            if cfg["mode"] == "saas":
                if parsed.path == "/api/resume/upload":
                    try:
                        user_id, _ = require_auth(self)
                    except AuthError as exc:
                        self._json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
                        return
                    request_content_type = self.headers.get("Content-Type", "").strip()
                    try:
                        filename, file_bytes, uploaded_content_type = _parse_upload_file(self)
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
                        self._json(status, payload)
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
                        self._json(status, payload)
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
                    except Exception as exc:
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
                        self._json(status, payload)
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
                        self._json(status, payload)
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
                        self._json(status, payload)
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
                        self._json(status, payload)
                        return
                    try:
                        draft_data, gap_analysis = onboarding_extract_draft(parsed_text, cfg)
                        _log.info(
                            "resume_upload.draft_extracted user_id=%s upload_id=%s experiences=%d skill_count=%s",
                            user_id,
                            upload_id,
                            len(draft_data.get("experiences") or []),
                            gap_analysis.get("skill_count"),
                        )
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
                        self._json(status, payload)
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
                        self._json(status, payload)
                        return
                    draft_payload = _onboarding_draft_payload(draft_row)
                    self._json(
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
                    return
                if parsed.path == "/api/profile":
                    handle_profile_create(self, cfg)
                    return
                if dispatch_jobs_post(self, parsed.path, cfg):
                    return
                if parsed.path.startswith("/api/admin/"):
                    if dispatch_admin_post(self, parsed.path, cfg):
                        return
                    self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                    return
            if parsed.path != "/api/generate":
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            try:
                payload = _read_json(self)
                jd_text = str(payload.get("jd", "")).strip()
                if not jd_text:
                    raise ValueError("Field 'jd' is required.")
                application_url = _normalize_application_url(payload.get("application_url"))
                requested_outputs = _normalize_outputs(payload.get("outputs"))
                _raw_job_id = payload.get("job_id")
                job_id_for_app: int | None = int(_raw_job_id) if _raw_job_id is not None else None

                # ── Candidate context: DB profile (saas) or candidate.yaml (local) ──
                user_id: str | None = None
                if cfg["mode"] == "saas":
                    try:
                        user_id, _ = require_auth(self)
                    except AuthError as exc:
                        self._json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
                        return
                    profile = get_profile(user_id)
                    if not profile:
                        has_onboarding_draft = get_onboarding_draft_db(user_id) is not None
                        _log.warning(
                            "generate.blocked_missing_profile user_id=%s has_onboarding_draft=%s",
                            user_id,
                            has_onboarding_draft,
                        )
                        self._json(
                            HTTPStatus.UNPROCESSABLE_ENTITY,
                            {
                                "error": "profile_incomplete",
                                "detail": "Finish onboarding and save your profile before generating documents.",
                                "has_onboarding_draft": has_onboarding_draft,
                            },
                        )
                        return
                    candidate_context = profile_to_candidate_context(profile)
                else:
                    candidate_context = build_candidate_context(candidate_yaml_path)
                # ─────────────────────────────────────────────────────────────────────

                initial_analysis = analyze_jd(
                    jd_text,
                    _candidate_keywords(candidate_context),
                    application_url=application_url,
                )
                min_score_for_pdf = float(cfg.get("generation", {}).get("min_score_for_pdf", 0))
                if min_score_for_pdf > 0 and initial_analysis["score"] < min_score_for_pdf:
                    self._json(
                        HTTPStatus.OK,
                        {
                            "score_gate": True,
                            "score": initial_analysis["score"],
                            "min_score": min_score_for_pdf,
                            "archetype": initial_analysis.get("archetype"),
                            "ats_vendor": initial_analysis.get("ats_vendor"),
                            "message": (
                                f"Score {initial_analysis['score']} is below the configured minimum "
                                f"of {min_score_for_pdf}. Generation skipped."
                            ),
                            "analysis": initial_analysis,
                        },
                    )
                    return
                try:
                    pack, usage_summary, detected_company = generate_pack(
                        jd_text=jd_text,
                        jd_analysis=initial_analysis,
                        candidate_context=candidate_context,
                        outputs=requested_outputs,
                        application_url=application_url,
                        config=cfg,
                    )
                except PackGenerationError as exc:
                    if exc.usage_summary.get("attempts"):
                        if cfg["mode"] == "saas":
                            pg_record_api_usage(
                                user_id,
                                exc.usage_summary["attempts"],
                                application_id=None,
                                request_status="failed",
                                error_message=str(exc),
                            )
                        else:
                            record_api_usage(
                                db_path,
                                exc.usage_summary["attempts"],
                                application_id=None,
                                request_status="failed",
                                error_message=str(exc),
                            )
                    raise ValueError(str(exc)) from exc

                updated_analysis = analyze_jd(
                    jd_text,
                    _updated_resume_keywords(pack, initial_analysis, candidate_context),
                    application_url=application_url,
                )
                tokens_used = int(usage_summary.get("total_tokens") or 0)
                model_used = str(usage_summary.get("model_used") or cfg["llm"]["model"])
                company = _pick_company_name(initial_analysis.get("company"), detected_company) or "Unknown Company"
                role = initial_analysis.get("role") or "Untitled Role"
                tex_string = render_tex(candidate_context, pack, initial_analysis)
                last_slug_error = ""
                for _ in range(8):
                    if cfg["mode"] == "saas":
                        _uid = user_id
                        slug = make_slug(
                            company, role,
                            slug_exists_fn=lambda s: pg_application_slug_exists(_uid, s),
                        )
                    else:
                        slug = make_slug(company, role, db_path=db_path)
                    _cand_name = candidate_context.get("personal", {}).get("name") or "Candidate"
                    _pdf_filename = re.sub(r"\s+", "_", _cand_name.strip()) + "_Resume.pdf"
                    try:
                        files = write_pack(
                            applications_dir=str(applications_dir),
                            slug=slug,
                            jd_text=jd_text,
                            application_url=application_url,
                            pack=pack,
                            tex_string=tex_string,
                            requested_outputs=requested_outputs,
                            candidate_name=_cand_name,
                            usage_summary=usage_summary,
                            initial_analysis=initial_analysis,
                            updated_analysis=updated_analysis,
                        )
                    except FileExistsError:
                        last_slug_error = f"Output folder already exists for slug {slug}."
                        continue

                    pdf_path = compile_pdf(
                        files["resume_tex"],
                        files["output_dir"],
                        output_filename=_pdf_filename,
                    )
                    if pdf_path:
                        files["resume_pdf"] = pdf_path

                    if cfg["mode"] == "saas":
                        try:
                            cloud_paths = upload_pack_files(user_id, slug, files["output_dir"])
                            app_id = pg_insert_application(
                                user_id=user_id,
                                company=company,
                                role=role,
                                slug=slug,
                                jd_raw=jd_text,
                                jd_language=initial_analysis.get("language"),
                                jd_location=initial_analysis.get("location"),
                                job_application_url=application_url,
                                resume_tex_url=cloud_paths.get("resume_tex_url"),
                                resume_pdf_url=cloud_paths.get("resume_pdf_url"),
                                cover_letter_url=cloud_paths.get("cover_letter_url"),
                                linkedin_msg_url=cloud_paths.get("linkedin_msg_url"),
                                email_draft_url=cloud_paths.get("email_draft_url"),
                                cover_letter="cover_letter" in requested_outputs,
                                linkedin_msg="linkedin_msg" in requested_outputs,
                                email_draft="email_draft" in requested_outputs,
                                tokens_used=tokens_used,
                                model_used=model_used,
                                initial_score=float(initial_analysis.get("score") or 0.0),
                                updated_score=float(updated_analysis.get("score") or 0.0),
                                usage_summary=usage_summary,
                                archetype=initial_analysis.get("archetype"),
                                job_id=job_id_for_app,
                            )
                            break
                        except Exception as exc:
                            if isinstance(exc, _pg_errors.UniqueViolation):
                                last_slug_error = str(exc)
                                continue
                            raise
                    else:
                        try:
                            app_id = insert_application(
                                db_path=db_path,
                                company=company,
                                role=role,
                                slug=slug,
                                jd_raw=jd_text,
                                jd_language=initial_analysis.get("language"),
                                jd_location=initial_analysis.get("location"),
                                job_application_url=application_url,
                                outputs_path=files["output_dir"],
                                resume_tex_path=files["resume_tex"],
                                resume_pdf_path=files.get("resume_pdf"),
                                cover_letter="cover_letter" in requested_outputs,
                                linkedin_msg="linkedin_msg" in requested_outputs,
                                email_draft="email_draft" in requested_outputs,
                                tokens_used=tokens_used,
                                model_used=model_used,
                                initial_score=float(initial_analysis.get("score") or 0.0),
                                updated_score=float(updated_analysis.get("score") or 0.0),
                                usage_summary=usage_summary,
                                archetype=initial_analysis.get("archetype"),
                            )
                            break
                        except sqlite3.IntegrityError as exc:
                            if "applications.slug" not in str(exc).lower() and "applications.slug" not in repr(exc).lower():
                                raise
                            last_slug_error = str(exc)
                            continue
                else:
                    raise ValueError(
                        last_slug_error or "Could not allocate a unique application slug after multiple attempts."
                    )

                if cfg["mode"] == "saas":
                    if job_id_for_app:
                        try:
                            link_job_to_application(user_id, job_id_for_app, app_id)
                        except Exception:
                            _log.warning(
                                "Failed to link job %s to application %s",
                                job_id_for_app, app_id,
                            )
                    pg_record_api_usage(
                        user_id,
                        usage_summary.get("attempts", []),
                        application_id=app_id,
                        request_status="succeeded",
                    )
                    pg_refresh_daily_stats(user_id)
                    shutil.rmtree(files["output_dir"], ignore_errors=True)
                else:
                    record_api_usage(
                        db_path,
                        usage_summary.get("attempts", []),
                        application_id=app_id,
                        request_status="succeeded",
                    )
                    refresh_daily_stats(db_path)

                self._json(
                    HTTPStatus.OK,
                    {
                        "slug": slug,
                        "app_id": app_id,
                        "company": company,
                        "role": role,
                        "application_url": application_url,
                        "score": updated_analysis.get("score"),
                        "initial_score": initial_analysis.get("score"),
                        "updated_score": updated_analysis.get("score"),
                        "archetype": initial_analysis.get("archetype"),
                        "ats_vendor": initial_analysis.get("ats_vendor"),
                        "exact_phrases": initial_analysis.get("exact_phrases", []),
                        "tokens_used": tokens_used,
                        "usage": usage_summary,
                        "analysis": initial_analysis,
                        "initial_analysis": initial_analysis,
                        "updated_analysis": updated_analysis,
                        "pack": pack.model_dump(),
                        "files": _serialize_files(
                            slug,
                            files,
                            cloud_paths=cloud_paths if cfg["mode"] == "saas" else None,
                        ),
                    },
                )
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_PATCH(self) -> None:
            parsed = urlparse(self.path)
            _prep_patch_match = re.fullmatch(r"/api/interview-prep/(\d+)", parsed.path)
            if _prep_patch_match:
                if cfg["mode"] == "saas":
                    self._saas_local_only("Interview Prep")
                    return
                try:
                    session_id = int(_prep_patch_match.group(1))
                    payload = _read_json(self)
                    questions = payload.get("questions")
                    notes = payload.get("notes")
                    update_prep_session(
                        db_path,
                        session_id,
                        questions=questions if isinstance(questions, list) else None,
                        notes=str(notes) if notes is not None else None,
                    )
                    session = get_prep_session(db_path, session_id)
                    self._json(HTTPStatus.OK, {"session": session})
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            duplicate_match = re.fullmatch(r"/api/applications/(\d+)/duplicate", parsed.path)
            if duplicate_match:
                try:
                    payload = _read_json(self)
                    app_id = int(duplicate_match.group(1))
                    is_duplicate = _normalize_bool(payload.get("is_duplicate"), "is_duplicate")
                    detail = str(payload.get("detail", "")).strip()
                    if cfg["mode"] == "saas":
                        user_id = self._require_saas_user_id()
                        if user_id is None:
                            return
                        pg_set_duplicate_flag(user_id, app_id, is_duplicate, detail)
                        pg_refresh_daily_stats(user_id)
                        row = pg_get_application(user_id, app_id)
                        self._json(HTTPStatus.OK, {"application": _serialize_application(row, cloud_mode=True)})
                    else:
                        set_duplicate_flag(db_path, app_id, is_duplicate, detail)
                        refresh_daily_stats(db_path)
                        row = get_application(db_path, app_id)
                        self._json(HTTPStatus.OK, {"application": _serialize_application(row)})
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            if cfg["mode"] == "saas" and dispatch_jobs_patch(self, parsed.path, cfg):
                return
            _notes_match = re.fullmatch(r"/api/applications/(\d+)/notes", parsed.path)
            if _notes_match:
                try:
                    payload = _read_json(self)
                    app_id = int(_notes_match.group(1))
                    notes = str(payload.get("notes", "")).strip()
                    if cfg["mode"] == "saas":
                        user_id = self._require_saas_user_id()
                        if user_id is None:
                            return
                        pg_update_application_notes(user_id, app_id, notes)
                        row = pg_get_application(user_id, app_id)
                        self._json(HTTPStatus.OK, {"application": _serialize_application(row, cloud_mode=True)})
                    else:
                        update_application_notes(db_path, app_id, notes)
                        row = get_application(db_path, app_id)
                        self._json(HTTPStatus.OK, {"application": _serialize_application(row)})
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            match = re.fullmatch(r"/api/applications/(\d+)/status", parsed.path)
            if not match:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            try:
                payload = _read_json(self)
                app_id = int(match.group(1))
                new_status = str(payload.get("new_status", "")).strip()
                detail = str(payload.get("detail", "")).strip()
                if not new_status:
                    raise ValueError("Field 'new_status' is required.")
                if cfg["mode"] == "saas":
                    user_id = self._require_saas_user_id()
                    if user_id is None:
                        return
                    pg_update_status(user_id, app_id, new_status, detail)
                    pg_refresh_daily_stats(user_id)
                    row = pg_get_application(user_id, app_id)
                    self._json(HTTPStatus.OK, {"application": _serialize_application(row, cloud_mode=True)})
                else:
                    update_status(db_path, app_id, new_status, detail)
                    refresh_daily_stats(db_path)
                    row = get_application(db_path, app_id)
                    self._json(HTTPStatus.OK, {"application": _serialize_application(row)})
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_PUT(self) -> None:
            if cfg["mode"] != "saas":
                self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Method not allowed"})
                return
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/profile":
                    handle_profile_update(self, cfg)
                    return
                if parsed.path.startswith("/api/admin/"):
                    if dispatch_admin_put(self, parsed.path, cfg):
                        return
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_DELETE(self) -> None:
            if cfg["mode"] != "saas":
                self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Method not allowed"})
                return
            parsed = urlparse(self.path)
            try:
                if dispatch_jobs_delete(self, parsed.path, cfg):
                    return
                if parsed.path.startswith("/api/admin/"):
                    if dispatch_admin_delete(self, parsed.path, cfg):
                        return
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_OPTIONS(self) -> None:
            if cfg["mode"] != "saas":
                self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
                return
            origin = cfg.get("cors_origin", "*")
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Max-Age", "86400")
            self.end_headers()

        def _handle_apply_queue(self, query_string: str) -> None:
            from urllib.parse import parse_qs
            params = parse_qs(query_string or "")
            min_score = float((params.get("min_score") or ["0"])[0])
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                rows = pg_get_apply_queue(user_id, min_score=min_score)
            else:
                rows = get_apply_queue(db_path, min_score=min_score)
            apps = []
            for row in rows:
                serialized = _serialize_application(row, cloud_mode=cfg["mode"] == "saas")
                serialized["archetype"] = row.get("role_archetype") or "general"
                apps.append(serialized)
            self._json(HTTPStatus.OK, {"applications": apps, "count": len(apps)})

        def _handle_analytics(self) -> None:
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                self._json(HTTPStatus.OK, pg_get_analytics(user_id))
                return
            self._json(HTTPStatus.OK, get_analytics(db_path))

        def _handle_tracker(self) -> None:
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                rows = pg_get_tracker_applications(user_id)
            else:
                rows = get_tracker_applications(db_path)
            self._json(
                HTTPStatus.OK,
                {
                    "items": [
                        {
                            **_serialize_application(row, cloud_mode=cfg["mode"] == "saas"),
                            "last_status_at": row.get("last_status_at"),
                        }
                        for row in rows
                    ],
                },
            )

        def _handle_application_files(self, app_id: int) -> None:
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                row = pg_get_application(user_id, app_id)
            else:
                row = get_application(db_path, app_id)
            if not row:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Application not found."})
                return
            self._json(
                HTTPStatus.OK,
                {
                    "application_id": app_id,
                    "application": {
                        "id": row.get("id"),
                        "company": row.get("company"),
                        "role": row.get("role"),
                        "slug": row.get("slug"),
                    },
                    **_serialize_application_files(row, cloud_mode=cfg["mode"] == "saas"),
                },
            )

        def _handle_application_events(self, app_id: int) -> None:
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                row = pg_get_application(user_id, app_id)
                events = pg_get_application_events(user_id, app_id)
            else:
                row = get_application(db_path, app_id)
                events = get_application_events(db_path, app_id)
            if not row:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Application not found."})
                return
            self._json(HTTPStatus.OK, {"application_id": app_id, "events": events})

        def _handle_stats(self) -> None:
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                pg_refresh_daily_stats(user_id)
                funnel = pg_get_funnel_stats(user_id)
                daily_stats = pg_get_daily_stats(user_id, days=30)
                quick_stats = pg_get_quick_stats(user_id)
            else:
                refresh_daily_stats(db_path)
                funnel = get_funnel_stats(db_path)
                daily_stats = get_daily_stats(db_path, days=30)
                quick_stats = get_quick_stats(db_path)
            self._json(
                HTTPStatus.OK,
                {
                    "funnel": funnel,
                    "daily_stats": daily_stats,
                    "quick_stats": quick_stats,
                },
            )

        def _handle_applications(self, query_string: str) -> None:
            params = parse_qs(query_string)
            limit = int(params.get("limit", ["50"])[0])
            offset = int(params.get("offset", ["0"])[0])
            status = params.get("status", [""])[0] or None
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                items = pg_list_applications(user_id, status_filter=status, limit=limit, offset=offset)
            else:
                items = list_applications(db_path, status_filter=status, limit=limit, offset=offset)
            self._json(
                HTTPStatus.OK,
                {
                    "items": [_serialize_application(item, cloud_mode=cfg["mode"] == "saas") for item in items],
                    "limit": limit,
                    "offset": offset,
                    "status": status,
                },
            )

        def _serve_dashboard(self) -> None:
            """Serve dashboard.html with an injected CUSTOMY_CONFIG script block."""
            path = TEMPLATES_DIR / "dashboard.html"
            html = path.read_bytes().decode("utf-8")
            if cfg["mode"] == "saas":
                supabase_url = cfg.get("supabase", {}).get("url", "")
                anon_key = cfg.get("supabase", {}).get("anon_key", "")
                config_script = (
                    "<script>window.CUSTOMY_CONFIG = {"
                    'mode: "saas", '
                    "supabaseUrl: " + json.dumps(supabase_url) + ", "
                    "supabaseAnonKey: " + json.dumps(anon_key) +
                    "};"
                    "document.documentElement.setAttribute('data-saas-loading','');"
                    "</script>"
                )
            else:
                config_script = '<script>window.CUSTOMY_CONFIG = {mode: "local"};</script>'
            html = html.replace("<!-- __CUSTOMY_CONFIG__ -->", config_script, 1)
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self, filename: str) -> None:
            path = (STATIC_DIR / filename).resolve()
            if STATIC_DIR.resolve() not in path.parents or not path.is_file():
                raise ValueError("Static asset not found.")
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self._serve_file(path, mime)

        def _serve_artifact(self, request_path: str) -> None:
            relative = unquote(request_path.removeprefix("/artifacts/")).strip("/")
            path = (applications_dir / relative).resolve()
            if applications_dir not in path.parents or not path.is_file():
                raise ValueError("Artifact not found.")
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            attachment_filename = path.name if path.name.endswith("_Cover_letter.txt") else None
            self._serve_file(path, mime, attachment_filename=attachment_filename)

        def _serve_file(self, path: Path, content_type: str, attachment_filename: str | None = None) -> None:
            content = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            if attachment_filename:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment_filename}"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _json(self, status: HTTPStatus, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
