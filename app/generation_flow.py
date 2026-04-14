from __future__ import annotations

import logging
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import psycopg2.errors as _pg_errors

from app.analyzer import analyze_jd, build_updated_resume_keywords
from app.db import insert_application, record_api_usage, refresh_daily_stats
from app.db_postgres import (
    application_slug_exists as pg_application_slug_exists,
    insert_application as pg_insert_application,
    link_job_to_application,
    record_api_usage as pg_record_api_usage,
    refresh_daily_stats as pg_refresh_daily_stats,
)
from app.generator import PackGenerationError, generate_pack
from app.latex import compile_pdf, render_tex
from app.resume_fullness_risk import evaluate_resume_fullness_risk
from app.storage import make_slug, write_pack
from app.storage_cloud import upload_pack_files
from app.targeting import candidate_keywords_from_profile

_log = logging.getLogger(__name__)


class ScoreGateBlocked(Exception):
    def __init__(self, score: float, min_score: float, initial_analysis: dict) -> None:
        self.score = score
        self.min_score = min_score
        self.initial_analysis = initial_analysis


@dataclass
class GenerationResult:
    slug: str
    app_id: int
    company: str
    role: str
    initial_analysis: dict
    updated_analysis: dict
    tokens_used: int
    usage_summary: dict
    pack: object
    resume_fullness_risk: dict
    files: dict
    cloud_paths: dict | None


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


def run_generation(
    *,
    jd_text: str,
    application_url: str | None,
    requested_outputs: list[str],
    job_id_for_app: int | None,
    user_id: str | None,
    candidate_context: dict,
    cfg: dict,
    db_path: str,
    applications_dir: Path,
) -> GenerationResult:
    initial_analysis = analyze_jd(
        jd_text,
        _candidate_keywords(candidate_context),
        application_url=application_url,
    )
    min_score_for_pdf = float(cfg.get("generation", {}).get("min_score_for_pdf", 0))
    if min_score_for_pdf > 0 and initial_analysis["score"] < min_score_for_pdf:
        raise ScoreGateBlocked(
            score=initial_analysis["score"],
            min_score=min_score_for_pdf,
            initial_analysis=initial_analysis,
        )

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
    resume_fullness_risk = evaluate_resume_fullness_risk(
        candidate_context,
        pack,
        jd_analysis=initial_analysis,
    )
    tokens_used = int(usage_summary.get("total_tokens") or 0)
    model_used = str(usage_summary.get("model_used") or cfg["llm"]["model"])
    company = _pick_company_name(initial_analysis.get("company"), detected_company) or "Unknown Company"
    role = initial_analysis.get("role") or "Untitled Role"
    tex_string = render_tex(candidate_context, pack, initial_analysis)
    last_slug_error = ""
    cloud_paths: dict | None = None

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
                resume_fullness_risk=resume_fullness_risk,
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
            _log.info("generate: compile_pdf succeeded path=%s", pdf_path)
        else:
            _log.warning(
                "generate: compile_pdf returned None — resume.pdf will not be uploaded "
                "(check compile_pdf ERROR lines above for pdflatex failure details)"
            )

        if cfg["mode"] == "saas":
            try:
                _log.info(
                    "generate: calling upload_pack_files slug=%s output_dir=%s has_pdf=%s",
                    slug,
                    files["output_dir"],
                    "resume_pdf" in files,
                )
                cloud_paths = upload_pack_files(user_id, slug, files["output_dir"])
                _log.info(
                    "generate: upload_pack_files returned keys=%s resume_pdf_url=%r",
                    list(cloud_paths.keys()),
                    cloud_paths.get("resume_pdf_url"),
                )
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

    return GenerationResult(
        slug=slug,
        app_id=app_id,
        company=company,
        role=role,
        initial_analysis=initial_analysis,
        updated_analysis=updated_analysis,
        tokens_used=tokens_used,
        usage_summary=usage_summary,
        pack=pack,
        resume_fullness_risk=resume_fullness_risk,
        files=files,
        cloud_paths=cloud_paths,
    )
