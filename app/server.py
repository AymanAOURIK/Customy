from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from app.db import (
    get_analytics,
    get_application,
    get_application_events,
    get_apply_queue,
    get_daily_stats,
    get_funnel_stats,
    get_quick_stats,
    get_tracker_applications,
    list_applications,
    refresh_daily_stats,
    set_duplicate_flag,
    update_application_notes,
    update_status,
)
from app.generation_flow import GenerationResult, ScoreGateBlocked, run_generation
from app.http_utils import read_json_body
from app.profile import build_candidate_context
from app.storage import set_applications_dir
from app.storage_cloud import get_signed_url_for_path
from app.onboarding_db import get_onboarding_draft as get_onboarding_draft_db
from app.auth import AuthError, is_admin, require_auth
from app.profile_db import get_profile, profile_to_candidate_context
from app.profile_readiness import evaluate_saved_profile_readiness
from app.db_postgres import (
    get_analytics as pg_get_analytics,
    get_application as pg_get_application,
    get_application_events as pg_get_application_events,
    get_apply_queue as pg_get_apply_queue,
    get_daily_stats as pg_get_daily_stats,
    get_funnel_stats as pg_get_funnel_stats,
    get_quick_stats as pg_get_quick_stats,
    get_tracker_applications as pg_get_tracker_applications,
    list_applications as pg_list_applications,
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
from app.routes_onboarding import dispatch_onboarding_get, dispatch_onboarding_post
from app.routes_profile import handle_profile_create, handle_profile_get, handle_profile_update
from app.routes_local import dispatch_local_get, dispatch_local_patch, dispatch_local_post
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

_log = logging.getLogger(__name__)

_ADMIN_ONLY_APPLICATION_FIELDS = (
    "model_used",
    "tokens_used",
    "prompt_tokens",
    "cached_prompt_tokens",
    "completion_tokens",
    "total_cost_usd",
    "api_attempts",
)

_ADMIN_ONLY_QUICK_STATS_FIELDS = (
    "openai_request_count",
    "openai_failed_request_count",
    "openai_prompt_tokens",
    "openai_cached_prompt_tokens",
    "openai_completion_tokens",
    "openai_total_tokens",
    "openai_total_cost_usd",
    "openai_average_cost_usd",
)


def _artifact_url(slug: str, filename: str) -> str:
    return f"/artifacts/{slug}/{filename}"


def _viewer_can_see_admin_fields(cfg: dict, user_id: str | None = None) -> bool:
    if cfg.get("mode") != "saas":
        return True
    return bool(user_id) and is_admin(user_id)


def _sanitize_quick_stats(
    quick_stats: dict | None,
    *,
    include_admin_fields: bool,
) -> dict:
    payload = dict(quick_stats or {})
    if include_admin_fields:
        return payload
    for key in _ADMIN_ONLY_QUICK_STATS_FIELDS:
        payload.pop(key, None)
    return payload


def _artifact_ref(path: object, url: object, *, include_internal_fields: bool) -> dict:
    path_str = str(path or "").strip()
    payload = {
        "url": url,
        "filename": Path(path_str).name if path_str else "",
    }
    if include_internal_fields:
        payload["path"] = path_str
    return payload


def _sanitize_resume_fullness_risk(
    risk: dict | None,
    *,
    include_internal_fields: bool,
) -> dict | None:
    if not isinstance(risk, dict):
        return risk
    payload = dict(risk)
    if include_internal_fields:
        return payload
    payload.pop("report_version", None)
    payload.pop("counters", None)
    for key in ("blockers", "warnings"):
        issues = payload.get(key)
        if not isinstance(issues, list):
            continue
        sanitized: list[dict] = []
        for issue in issues:
            if not isinstance(issue, dict):
                sanitized.append(issue)
                continue
            issue_payload = dict(issue)
            issue_payload.pop("code", None)
            issue_payload.pop("details", None)
            sanitized.append(issue_payload)
        payload[key] = sanitized
    return payload


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


def _serialize_files(
    slug: str,
    files: dict,
    cloud_paths: dict | None = None,
    *,
    include_internal_fields: bool = True,
) -> dict:
    if cloud_paths:
        cloud_key_map = {
            "resume_tex": "resume_tex_url",
            "resume_pdf": "resume_pdf_url",
            "cover_letter": "cover_letter_url",
            "linkedin_message": "linkedin_msg_url",
            "email_draft": "email_draft_url",
            "generated_json": "generated_json_url",
        }
        response = {"output_dir": _artifact_ref(None, None, include_internal_fields=include_internal_fields)}
        for key, path in files.items():
            if key in {"output_dir", "cover_letter_filename"}:
                continue
            stored_path = cloud_paths.get(cloud_key_map.get(key, ""))
            response[key] = _artifact_ref(
                stored_path,
                get_signed_url_for_path(stored_path) if stored_path else None,
                include_internal_fields=include_internal_fields,
            )
        return response

    response = {
        "output_dir": _artifact_ref(
            files["output_dir"],
            None,
            include_internal_fields=include_internal_fields,
        )
    }
    for key, path in files.items():
        if key in {"output_dir", "cover_letter_filename"}:
            continue
        response[key] = _artifact_ref(
            path,
            _artifact_url(slug, Path(path).name),
            include_internal_fields=include_internal_fields,
        )
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


def _serialize_application_files(
    row: dict,
    *,
    cloud_mode: bool = False,
    include_internal_fields: bool = True,
) -> dict:
    files: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []

    def add_file(key: str, label: str, path: object, url: str) -> None:
        path_str = str(path or "").strip()
        payload = {
            "key": key,
            "label": label,
            "filename": Path(path_str).name if path_str else "",
            "url": url,
        }
        if include_internal_fields:
            payload["path"] = path_str
        files.append(payload)

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


def _serialize_application(
    row: dict,
    *,
    cloud_mode: bool = False,
    include_admin_fields: bool = True,
    include_internal_fields: bool = True,
) -> dict:
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

    payload = {
        "id": row.get("id"),
        "created_at": row.get("created_at"),
        "company": row.get("company"),
        "role": row.get("role"),
        "score": current_score,
        "initial_score": initial_score,
        "updated_score": updated_score,
        "status": row.get("status"),
        "is_duplicate": bool(row.get("is_duplicate")),
        "outputs": outputs,
        "job_application_url": row.get("job_application_url"),
        "notes": row.get("notes") or "",
    }
    if include_internal_fields:
        payload["slug"] = slug
        payload["folder_path"] = None if cloud_mode else row.get("outputs_path")
        payload["folder_url"] = None if cloud_mode else (
            f"/api/applications/{row.get('id')}/open-folder" if row.get("id") and row.get("outputs_path") else None
        )
    if include_admin_fields:
        for key in _ADMIN_ONLY_APPLICATION_FIELDS:
            payload[key] = row.get(key)
    return payload


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
                if dispatch_local_get(self, parsed.path, cfg):
                    return
                if cfg["mode"] == "saas":
                    if parsed.path == "/api/auth/me":
                        handle_auth_me(self, cfg)
                        return
                    if parsed.path == "/api/profile":
                        handle_profile_get(self, cfg)
                        return
                    if dispatch_onboarding_get(self, parsed.path, cfg):
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
            if dispatch_local_post(self, parsed.path, cfg):
                return
            if cfg["mode"] == "saas":
                if dispatch_onboarding_post(self, parsed.path, cfg):
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
                payload = read_json_body(self)
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
                    readiness = evaluate_saved_profile_readiness(profile)
                    readiness_gate = readiness["profile_readiness_gate"]
                    if readiness_gate.get("decision") == "blocked":
                        quality_report = readiness["profile_quality_report"]
                        _log.warning(
                            "generate.blocked_profile_readiness user_id=%s status=%s blockers=%s warnings=%s",
                            user_id,
                            readiness_gate.get("status"),
                            len(quality_report.get("blockers") or []),
                            len(quality_report.get("warnings") or []),
                        )
                        self._json(HTTPStatus.UNPROCESSABLE_ENTITY, readiness)
                        return
                    candidate_context = profile_to_candidate_context(profile)
                else:
                    candidate_context = build_candidate_context(candidate_yaml_path)
                # ─────────────────────────────────────────────────────────────────────

                try:
                    result = run_generation(
                        jd_text=jd_text,
                        application_url=application_url,
                        requested_outputs=requested_outputs,
                        job_id_for_app=job_id_for_app,
                        user_id=user_id,
                        candidate_context=candidate_context,
                        cfg=cfg,
                        db_path=db_path,
                        applications_dir=applications_dir,
                    )
                    admin_view = _viewer_can_see_admin_fields(cfg, user_id)
                except ScoreGateBlocked as exc:
                    self._json(
                        HTTPStatus.OK,
                        {
                            "score_gate": True,
                            "score": exc.score,
                            "min_score": exc.min_score,
                            "archetype": exc.initial_analysis.get("archetype"),
                            "ats_vendor": exc.initial_analysis.get("ats_vendor"),
                            "message": (
                                f"Score {exc.score} is below the configured minimum "
                                f"of {exc.min_score}. Generation skipped."
                            ),
                            "analysis": exc.initial_analysis,
                        },
                    )
                    return

                response = {
                    "company": result.company,
                    "role": result.role,
                    "application_url": application_url,
                    "score": result.updated_analysis.get("score"),
                    "initial_score": result.initial_analysis.get("score"),
                    "updated_score": result.updated_analysis.get("score"),
                    "archetype": result.initial_analysis.get("archetype"),
                    "ats_vendor": result.initial_analysis.get("ats_vendor"),
                    "exact_phrases": result.initial_analysis.get("exact_phrases", []),
                    "analysis": result.initial_analysis,
                    "initial_analysis": result.initial_analysis,
                    "updated_analysis": result.updated_analysis,
                    "resume_fullness_risk": _sanitize_resume_fullness_risk(
                        result.resume_fullness_risk,
                        include_internal_fields=admin_view,
                    ),
                    "pack": result.pack.model_dump(),
                    "files": _serialize_files(
                        result.slug,
                        result.files,
                        cloud_paths=result.cloud_paths if cfg["mode"] == "saas" else None,
                        include_internal_fields=admin_view,
                    ),
                }
                if admin_view:
                    response.update(
                        {
                            "slug": result.slug,
                            "app_id": result.app_id,
                            "tokens_used": result.tokens_used,
                            "usage": result.usage_summary,
                        }
                    )
                self._json(HTTPStatus.OK, response)
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_PATCH(self) -> None:
            parsed = urlparse(self.path)
            if dispatch_local_patch(self, parsed.path, cfg):
                return
            duplicate_match = re.fullmatch(r"/api/applications/(\d+)/duplicate", parsed.path)
            if duplicate_match:
                try:
                    payload = read_json_body(self)
                    app_id = int(duplicate_match.group(1))
                    is_duplicate = _normalize_bool(payload.get("is_duplicate"), "is_duplicate")
                    detail = str(payload.get("detail", "")).strip()
                    if cfg["mode"] == "saas":
                        user_id = self._require_saas_user_id()
                        if user_id is None:
                            return
                        admin_view = _viewer_can_see_admin_fields(cfg, user_id)
                        pg_set_duplicate_flag(user_id, app_id, is_duplicate, detail)
                        pg_refresh_daily_stats(user_id)
                        row = pg_get_application(user_id, app_id)
                        self._json(
                            HTTPStatus.OK,
                            {
                                "application": _serialize_application(
                                    row,
                                    cloud_mode=True,
                                    include_admin_fields=admin_view,
                                    include_internal_fields=admin_view,
                                )
                            },
                        )
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
                    payload = read_json_body(self)
                    app_id = int(_notes_match.group(1))
                    notes = str(payload.get("notes", "")).strip()
                    if cfg["mode"] == "saas":
                        user_id = self._require_saas_user_id()
                        if user_id is None:
                            return
                        admin_view = _viewer_can_see_admin_fields(cfg, user_id)
                        pg_update_application_notes(user_id, app_id, notes)
                        row = pg_get_application(user_id, app_id)
                        self._json(
                            HTTPStatus.OK,
                            {
                                "application": _serialize_application(
                                    row,
                                    cloud_mode=True,
                                    include_admin_fields=admin_view,
                                    include_internal_fields=admin_view,
                                )
                            },
                        )
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
                payload = read_json_body(self)
                app_id = int(match.group(1))
                new_status = str(payload.get("new_status", "")).strip()
                detail = str(payload.get("detail", "")).strip()
                if not new_status:
                    raise ValueError("Field 'new_status' is required.")
                if cfg["mode"] == "saas":
                    user_id = self._require_saas_user_id()
                    if user_id is None:
                        return
                    admin_view = _viewer_can_see_admin_fields(cfg, user_id)
                    pg_update_status(user_id, app_id, new_status, detail)
                    pg_refresh_daily_stats(user_id)
                    row = pg_get_application(user_id, app_id)
                    self._json(
                        HTTPStatus.OK,
                        {
                            "application": _serialize_application(
                                row,
                                cloud_mode=True,
                                include_admin_fields=admin_view,
                                include_internal_fields=admin_view,
                            )
                        },
                    )
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
            admin_view = True
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                admin_view = _viewer_can_see_admin_fields(cfg, user_id)
                rows = pg_get_apply_queue(user_id, min_score=min_score)
            else:
                rows = get_apply_queue(db_path, min_score=min_score)
            apps = []
            for row in rows:
                serialized = _serialize_application(
                    row,
                    cloud_mode=cfg["mode"] == "saas",
                    include_admin_fields=admin_view,
                    include_internal_fields=admin_view,
                )
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
            admin_view = True
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                admin_view = _viewer_can_see_admin_fields(cfg, user_id)
                rows = pg_get_tracker_applications(user_id)
            else:
                rows = get_tracker_applications(db_path)
            self._json(
                HTTPStatus.OK,
                {
                    "items": [
                        {
                            **_serialize_application(
                                row,
                                cloud_mode=cfg["mode"] == "saas",
                                include_admin_fields=admin_view,
                                include_internal_fields=admin_view,
                            ),
                            "last_status_at": row.get("last_status_at"),
                        }
                        for row in rows
                    ],
                },
            )

        def _handle_application_files(self, app_id: int) -> None:
            admin_view = True
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                admin_view = _viewer_can_see_admin_fields(cfg, user_id)
                row = pg_get_application(user_id, app_id)
            else:
                row = get_application(db_path, app_id)
            if not row:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Application not found."})
                return
            payload = {
                "application": {
                    "company": row.get("company"),
                    "role": row.get("role"),
                },
                **_serialize_application_files(
                    row,
                    cloud_mode=cfg["mode"] == "saas",
                    include_internal_fields=admin_view,
                ),
            }
            if admin_view:
                payload["application_id"] = app_id
                payload["application"]["id"] = row.get("id")
                payload["application"]["slug"] = row.get("slug")
            self._json(HTTPStatus.OK, payload)

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
            admin_view = True
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                admin_view = _viewer_can_see_admin_fields(cfg, user_id)
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
                    "quick_stats": _sanitize_quick_stats(
                        quick_stats,
                        include_admin_fields=admin_view,
                    ),
                },
            )

        def _handle_applications(self, query_string: str) -> None:
            params = parse_qs(query_string)
            limit = int(params.get("limit", ["50"])[0])
            offset = int(params.get("offset", ["0"])[0])
            status = params.get("status", [""])[0] or None
            admin_view = True
            if cfg["mode"] == "saas":
                user_id = self._require_saas_user_id()
                if user_id is None:
                    return
                admin_view = _viewer_can_see_admin_fields(cfg, user_id)
                items = pg_list_applications(user_id, status_filter=status, limit=limit, offset=offset)
            else:
                items = list_applications(db_path, status_filter=status, limit=limit, offset=offset)
            self._json(
                HTTPStatus.OK,
                {
                    "items": [
                        _serialize_application(
                            item,
                            cloud_mode=cfg["mode"] == "saas",
                            include_admin_fields=admin_view,
                            include_internal_fields=admin_view,
                        )
                        for item in items
                    ],
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
