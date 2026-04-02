from __future__ import annotations

import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from app.analyzer import analyze_jd
from app.db import (
    get_application,
    get_daily_stats,
    get_funnel_stats,
    get_quick_stats,
    insert_application,
    list_applications,
    record_api_usage,
    refresh_daily_stats,
    update_status,
)
from app.generator import PackGenerationError, generate_pack
from app.latex import compile_pdf, render_tex
from app.profile import build_candidate_context
from app.storage import COVER_LETTER_FILENAME, make_slug, set_applications_dir, write_pack

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"
STATIC_DIR = PROJECT_ROOT / "app" / "static"
ALLOWED_OUTPUTS = {"resume", "cover_letter", "linkedin_msg", "email_draft"}
RESUME_PDF_FILENAME = "Ayman_Aourik_Resume.pdf"


def _artifact_url(slug: str, filename: str) -> str:
    return f"/artifacts/{slug}/{filename}"


def _serialize_files(slug: str, files: dict) -> dict:
    response = {"output_dir": {"path": files["output_dir"], "url": None}}
    for key, path in files.items():
        if key == "output_dir":
            continue
        response[key] = {"path": path, "url": _artifact_url(slug, Path(path).name)}
    return response


def _serialize_application(row: dict) -> dict:
    slug = row.get("slug", "")
    outputs = {}
    if row.get("resume_pdf_path"):
        outputs["resume_pdf"] = _artifact_url(slug, Path(row["resume_pdf_path"]).name)
    if row.get("resume_tex_path"):
        outputs["resume_tex"] = _artifact_url(slug, Path(row["resume_tex_path"]).name)
    if row.get("cover_letter"):
        outputs["cover_letter"] = _artifact_url(slug, COVER_LETTER_FILENAME)
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
        "score": row.get("score"),
        "status": row.get("status"),
        "slug": slug,
        "model_used": row.get("model_used"),
        "tokens_used": row.get("tokens_used"),
        "prompt_tokens": row.get("prompt_tokens"),
        "cached_prompt_tokens": row.get("cached_prompt_tokens"),
        "completion_tokens": row.get("completion_tokens"),
        "total_cost_usd": row.get("total_cost_usd"),
        "api_attempts": row.get("api_attempts"),
        "outputs": outputs,
        "folder_path": row.get("outputs_path"),
        "folder_url": outputs["generated_json"],
    }


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(content_length).decode("utf-8") if content_length else "{}"
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc


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
    keywords = list(candidate_context.get("scoring_keywords", []))
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
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self._serve_file(TEMPLATES_DIR / "index.html", "text/html; charset=utf-8")
                    return
                if parsed.path == "/dashboard":
                    self._serve_file(TEMPLATES_DIR / "dashboard.html", "text/html; charset=utf-8")
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
            if parsed.path != "/api/generate":
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            try:
                payload = _read_json(self)
                jd_text = str(payload.get("jd", "")).strip()
                if not jd_text:
                    raise ValueError("Field 'jd' is required.")
                requested_outputs = _normalize_outputs(payload.get("outputs"))
                candidate_context = build_candidate_context(candidate_yaml_path)
                jd_analysis = analyze_jd(jd_text, _candidate_keywords(candidate_context))
                try:
                    pack, usage_summary = generate_pack(
                        jd_text=jd_text,
                        jd_analysis=jd_analysis,
                        candidate_context=candidate_context,
                        outputs=requested_outputs,
                        config=cfg,
                    )
                except PackGenerationError as exc:
                    if exc.usage_summary.get("attempts"):
                        record_api_usage(
                            db_path,
                            exc.usage_summary["attempts"],
                            application_id=None,
                            request_status="failed",
                            error_message=str(exc),
                        )
                    raise ValueError(str(exc)) from exc

                tokens_used = int(usage_summary.get("total_tokens") or 0)
                model_used = str(usage_summary.get("model_used") or cfg["llm"]["model"])
                company = jd_analysis.get("company") or "Unknown Company"
                role = jd_analysis.get("role") or "Untitled Role"
                slug = make_slug(company, role)
                tex_string = render_tex(candidate_context, pack, jd_analysis)
                files = write_pack(
                    applications_dir=str(applications_dir),
                    slug=slug,
                    jd_text=jd_text,
                    pack=pack,
                    tex_string=tex_string,
                    requested_outputs=requested_outputs,
                    usage_summary=usage_summary,
                )
                pdf_path = compile_pdf(
                    files["resume_tex"],
                    files["output_dir"],
                    output_filename=RESUME_PDF_FILENAME,
                )
                if pdf_path:
                    files["resume_pdf"] = pdf_path
                app_id = insert_application(
                    db_path=db_path,
                    company=company,
                    role=role,
                    slug=slug,
                    jd_raw=jd_text,
                    jd_language=jd_analysis.get("language"),
                    jd_location=jd_analysis.get("location"),
                    outputs_path=files["output_dir"],
                    resume_tex_path=files["resume_tex"],
                    resume_pdf_path=files.get("resume_pdf"),
                    cover_letter="cover_letter" in requested_outputs,
                    linkedin_msg="linkedin_msg" in requested_outputs,
                    email_draft="email_draft" in requested_outputs,
                    tokens_used=tokens_used,
                    model_used=model_used,
                    score=float(jd_analysis.get("score") or 0.0),
                    usage_summary=usage_summary,
                )
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
                        "score": jd_analysis.get("score"),
                        "tokens_used": tokens_used,
                        "usage": usage_summary,
                        "analysis": jd_analysis,
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
            self._serve_file(path, mime)

        def _serve_file(self, path: Path, content_type: str) -> None:
            content = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
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
