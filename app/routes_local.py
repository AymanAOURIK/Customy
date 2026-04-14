"""Local-only route handlers.

All endpoints in this module are unavailable in SaaS mode and return 501
when called from a SaaS deployment.  They are dispatched from server.py
via the dispatch_local_* functions, following the same pattern used by
routes_jobs.py and routes_admin.py.
"""
from __future__ import annotations

import logging
import re
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

from app.db import (
    create_prep_session,
    delete_answer,
    delete_prep_session,
    get_answer_bank,
    get_application,
    get_prep_session,
    list_prep_sessions,
    update_prep_session,
    upsert_answer,
)
from app.http_utils import read_json_body, send_json
from app.playfill import build_fill_plan, run_playwright_fill

_log = logging.getLogger(__name__)


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

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "work_authorization": ["authorized", "work authorization", "visa", "sponsorship", "eligible to work", "right to work", "work permit"],
    "salary": ["salary", "compensation", "pay", "rate", "expectations", "package", "remuneration"],
    "availability": ["start date", "available", "notice period", "when can you start", "earliest start"],
    "relocation": ["relocate", "relocation", "move to", "willing to move"],
    "linkedin": ["linkedin", "linkedin url", "professional profile"],
    "github": ["github", "portfolio", "code samples", "github url"],
}


def _generate_prep_questions(archetype: str | None) -> list[dict]:
    """Returns a starter question set based on role archetype. No LLM required."""
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


def _saas_local_only(handler: BaseHTTPRequestHandler, feature_name: str) -> None:
    send_json(
        handler,
        HTTPStatus.NOT_IMPLEMENTED,
        {"error": f"{feature_name} is not enabled in public SaaS mode yet."},
    )


# ── URL patterns ───────────────────────────────────────────────────────────

_PREP_SESSION_RE = re.compile(r"^/api/interview-prep/(\d+)$")
_PREP_DELETE_RE = re.compile(r"^/api/interview-prep/(\d+)/delete$")


# ── GET handlers ───────────────────────────────────────────────────────────

def _handle_answer_bank_get(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    db_path = cfg["paths"]["db_path"]
    send_json(handler, HTTPStatus.OK, {"answers": get_answer_bank(db_path)})


def _handle_interview_prep_list(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    db_path = cfg["paths"]["db_path"]
    sessions = list_prep_sessions(db_path)
    send_json(handler, HTTPStatus.OK, {"sessions": sessions})


def _handle_interview_prep_get(handler: BaseHTTPRequestHandler, session_id: int, cfg: dict) -> None:
    db_path = cfg["paths"]["db_path"]
    session = get_prep_session(db_path, session_id)
    if not session:
        send_json(handler, HTTPStatus.NOT_FOUND, {"error": "Prep session not found."})
        return
    send_json(handler, HTTPStatus.OK, {"session": session})


# ── POST handlers ──────────────────────────────────────────────────────────

def _handle_answer_bank_upsert(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    db_path = cfg["paths"]["db_path"]
    try:
        payload = read_json_body(handler)
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
        send_json(handler, HTTPStatus.OK, {"answers": get_answer_bank(db_path)})
    except ValueError as exc:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
    except Exception as exc:
        send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def _handle_answer_question(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    db_path = cfg["paths"]["db_path"]
    try:
        payload = read_json_body(handler)
        question = str(payload.get("question") or "").strip().lower()
        if not question:
            raise ValueError("Field 'question' is required.")
        answers = get_answer_bank(db_path)
        matched_category = next(
            (cat for cat, keywords in _CATEGORY_KEYWORDS.items() if any(kw in question for kw in keywords)),
            None,
        )
        matched_answer = (
            next((a for a in answers if a.get("category") == matched_category), None)
            if matched_category
            else None
        )
        send_json(handler, HTTPStatus.OK, {
            "matched": matched_answer is not None,
            "category": matched_category,
            "answer": matched_answer,
            "hint": None if matched_answer else (
                f"No answer saved for category '{matched_category}'. Add it in the Answer Bank."
                if matched_category else "Question did not match any known category."
            ),
        })
    except ValueError as exc:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
    except Exception as exc:
        send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def _handle_answer_bank_delete(handler: BaseHTTPRequestHandler, raw_path: str, cfg: dict) -> None:
    db_path = cfg["paths"]["db_path"]
    try:
        key = unquote(raw_path.removeprefix("/api/answer-bank/").removesuffix("/delete"))
        delete_answer(db_path, key)
        send_json(handler, HTTPStatus.OK, {"answers": get_answer_bank(db_path)})
    except Exception as exc:
        send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def _handle_apply_assist(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    db_path = cfg["paths"]["db_path"]
    try:
        payload = read_json_body(handler)
        app_id = payload.get("app_id")
        market = str(payload.get("market") or "").strip().lower() or None
        use_playwright = bool(payload.get("use_playwright", False))

        ats_vendor: str | None = None
        cover_letter_text: str | None = None
        application_url_for_pw: str | None = None
        if app_id is not None:
            row = get_application(db_path, int(app_id))
            if not row:
                raise ValueError(f"Application {app_id} not found.")
            ats_vendor = row.get("role_archetype")
            outputs_path = row.get("outputs_path") or ""
            if outputs_path:
                cl_matches = sorted(Path(outputs_path).glob("*Cover_letter.txt"))
                if cl_matches:
                    try:
                        cover_letter_text = cl_matches[0].read_text(encoding="utf-8")
                    except Exception:
                        pass
            application_url_for_pw = row.get("job_application_url")
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

        send_json(handler, HTTPStatus.OK, {
            "fill_plan": fill_plan,
            "playwright": playwright_result,
        })
    except ValueError as exc:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
    except Exception as exc:
        send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def _handle_interview_prep_create(handler: BaseHTTPRequestHandler, cfg: dict) -> None:
    db_path = cfg["paths"]["db_path"]
    try:
        payload = read_json_body(handler)
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
        send_json(handler, HTTPStatus.CREATED, {"session": session})
    except ValueError as exc:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
    except Exception as exc:
        send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def _handle_interview_prep_delete(handler: BaseHTTPRequestHandler, session_id: int, cfg: dict) -> None:
    db_path = cfg["paths"]["db_path"]
    try:
        delete_prep_session(db_path, session_id)
        send_json(handler, HTTPStatus.OK, {"ok": True})
    except Exception as exc:
        send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


# ── PATCH handlers ─────────────────────────────────────────────────────────

def _handle_interview_prep_patch(handler: BaseHTTPRequestHandler, session_id: int, cfg: dict) -> None:
    db_path = cfg["paths"]["db_path"]
    try:
        payload = read_json_body(handler)
        questions = payload.get("questions")
        notes = payload.get("notes")
        update_prep_session(
            db_path,
            session_id,
            questions=questions if isinstance(questions, list) else None,
            notes=str(notes) if notes is not None else None,
        )
        session = get_prep_session(db_path, session_id)
        send_json(handler, HTTPStatus.OK, {"session": session})
    except ValueError as exc:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
    except Exception as exc:
        send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


# ── Dispatch entry points (called from server.py) ──────────────────────────

def dispatch_local_get(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    """Return True if the path matched a local-only GET route (handled or 501'd)."""
    if path == "/api/answer-bank":
        if cfg["mode"] == "saas":
            _saas_local_only(handler, "Answer Bank")
        else:
            _handle_answer_bank_get(handler, cfg)
        return True
    if path == "/api/interview-prep":
        if cfg["mode"] == "saas":
            _saas_local_only(handler, "Interview Prep")
        else:
            _handle_interview_prep_list(handler, cfg)
        return True
    m = _PREP_SESSION_RE.fullmatch(path)
    if m:
        if cfg["mode"] == "saas":
            _saas_local_only(handler, "Interview Prep")
        else:
            _handle_interview_prep_get(handler, int(m.group(1)), cfg)
        return True
    return False


def dispatch_local_post(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    """Return True if the path matched a local-only POST route (handled or 501'd)."""
    if path == "/api/answer-bank":
        if cfg["mode"] == "saas":
            _saas_local_only(handler, "Answer Bank")
        else:
            _handle_answer_bank_upsert(handler, cfg)
        return True
    if path == "/api/answer-question":
        if cfg["mode"] == "saas":
            _saas_local_only(handler, "Answer Bank")
        else:
            _handle_answer_question(handler, cfg)
        return True
    if path.startswith("/api/answer-bank/") and path.endswith("/delete"):
        if cfg["mode"] == "saas":
            _saas_local_only(handler, "Answer Bank")
        else:
            _handle_answer_bank_delete(handler, path, cfg)
        return True
    if path == "/api/apply-assist":
        if cfg["mode"] == "saas":
            _saas_local_only(handler, "Apply Assist")
        else:
            _handle_apply_assist(handler, cfg)
        return True
    if path == "/api/interview-prep":
        if cfg["mode"] == "saas":
            _saas_local_only(handler, "Interview Prep")
        else:
            _handle_interview_prep_create(handler, cfg)
        return True
    m = _PREP_DELETE_RE.fullmatch(path)
    if m:
        if cfg["mode"] == "saas":
            _saas_local_only(handler, "Interview Prep")
        else:
            _handle_interview_prep_delete(handler, int(m.group(1)), cfg)
        return True
    return False


def dispatch_local_patch(handler: BaseHTTPRequestHandler, path: str, cfg: dict) -> bool:
    """Return True if the path matched a local-only PATCH route (handled or 501'd)."""
    m = _PREP_SESSION_RE.fullmatch(path)
    if m:
        if cfg["mode"] == "saas":
            _saas_local_only(handler, "Interview Prep")
        else:
            _handle_interview_prep_patch(handler, int(m.group(1)), cfg)
        return True
    return False
