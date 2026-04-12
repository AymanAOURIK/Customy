from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import sqlite3
import subprocess
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
from app.targeting import candidate_keywords_from_profile
import psycopg2.errors as _pg_errors
from app.auth import AuthError, require_auth
from app.profile_db import get_profile, profile_to_candidate_context
from app.db_postgres import (
    application_slug_exists as pg_application_slug_exists,
    insert_application as pg_insert_application,
    link_job_to_application,
    record_api_usage as pg_record_api_usage,
    refresh_daily_stats as pg_refresh_daily_stats,
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


def _serialize_files(slug: str, files: dict) -> dict:
    response = {"output_dir": {"path": files["output_dir"], "url": None}}
    for key, path in files.items():
        if key == "output_dir":
            continue
        response[key] = {"path": path, "url": _artifact_url(slug, Path(path).name)}
    return response


def _serialize_application(row: dict) -> dict:
    slug = row.get("slug", "")
    initial_score = row.get("initial_score")
    if initial_score is None:
        initial_score = row.get("score")
    updated_score = row.get("updated_score")
    current_score = updated_score if updated_score is not None else initial_score
    outputs = {}
    if row.get("resume_pdf_path"):
        outputs["resume_pdf"] = _artifact_url(slug, Path(row["resume_pdf_path"]).name)
    if row.get("resume_tex_path"):
        outputs["resume_tex"] = _artifact_url(slug, Path(row["resume_tex_path"]).name)
    if row.get("cover_letter") and row.get("outputs_path"):
        _cl_matches = sorted(Path(row["outputs_path"]).glob("*Cover_letter.txt"))
        if _cl_matches:
            outputs["cover_letter"] = _artifact_url(slug, _cl_matches[0].name)
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
        "folder_path": row.get("outputs_path"),
        "folder_url": f"/api/applications/{row.get('id')}/open-folder" if row.get("id") and row.get("outputs_path") else None,
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


def run_server(host: str, port: int, cfg: dict) -> None:
    set_applications_dir(cfg["paths"]["applications_dir"])
    applications_dir = Path(cfg["paths"]["applications_dir"]).resolve()
    db_path = cfg["paths"]["db_path"]
    candidate_yaml_path = str(PROJECT_ROOT / "candidate.yaml")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            _log.info("%s %s", self.command if hasattr(self, "command") else "-", format % args)

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
                _ev_match = re.fullmatch(r"/api/applications/(\d+)/events", parsed.path)
                if _ev_match:
                    self._handle_application_events(int(_ev_match.group(1)))
                    return
                if parsed.path == "/api/answer-bank":
                    self._json(HTTPStatus.OK, {"answers": get_answer_bank(db_path)})
                    return
                if parsed.path == "/api/interview-prep":
                    sessions = list_prep_sessions(db_path)
                    self._json(HTTPStatus.OK, {"sessions": sessions})
                    return
                _prep_get_match = re.fullmatch(r"/api/interview-prep/(\d+)", parsed.path)
                if _prep_get_match:
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
                try:
                    key = unquote(parsed.path.removeprefix("/api/answer-bank/").removesuffix("/delete"))
                    delete_answer(db_path, key)
                    self._json(HTTPStatus.OK, {"answers": get_answer_bank(db_path)})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

            if parsed.path == "/api/apply-assist":
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
                try:
                    delete_prep_session(db_path, int(_prep_delete_match.group(1)))
                    self._json(HTTPStatus.OK, {"ok": True})
                except Exception as exc:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

            if cfg["mode"] == "saas":
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
                        self._json(
                            HTTPStatus.UNPROCESSABLE_ENTITY,
                            {"error": "Profile not found. Create one via POST /api/profile first."},
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
                            app_id = pg_insert_application(
                                user_id=user_id,
                                company=company,
                                role=role,
                                slug=slug,
                                jd_raw=jd_text,
                                jd_language=initial_analysis.get("language"),
                                jd_location=initial_analysis.get("location"),
                                job_application_url=application_url,
                                resume_tex_url=_artifact_url(slug, "resume.tex"),
                                resume_pdf_url=_artifact_url(slug, _pdf_filename) if pdf_path else None,
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
                        "files": _serialize_files(slug, files),
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
            rows = get_apply_queue(db_path, min_score=min_score)
            apps = []
            for row in rows:
                serialized = _serialize_application(row)
                serialized["archetype"] = row.get("role_archetype") or "general"
                apps.append(serialized)
            self._json(HTTPStatus.OK, {"applications": apps, "count": len(apps)})

        def _handle_analytics(self) -> None:
            self._json(HTTPStatus.OK, get_analytics(db_path))

        def _handle_tracker(self) -> None:
            rows = get_tracker_applications(db_path)
            self._json(
                HTTPStatus.OK,
                {
                    "items": [
                        {**_serialize_application(row), "last_status_at": row.get("last_status_at")}
                        for row in rows
                    ],
                },
            )

        def _handle_application_events(self, app_id: int) -> None:
            row = get_application(db_path, app_id)
            if not row:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Application not found."})
                return
            events = get_application_events(db_path, app_id)
            self._json(HTTPStatus.OK, {"application_id": app_id, "events": events})

        def _handle_stats(self) -> None:
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
            items = list_applications(db_path, status_filter=status, limit=limit, offset=offset)
            self._json(
                HTTPStatus.OK,
                {
                    "items": [_serialize_application(item) for item in items],
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
                    "};</script>"
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
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
